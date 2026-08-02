"""Blast file upload and processing section."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd
import streamlit as st

from core.calculo_tronadura import procesar_pozos
from core.column_mapping import apply_mapping, validate_mapping
from core.geometry_contract import (
    GEOMETRY_CONFIGURATION_VERSION,
    GeometryConfiguration,
    GeometryConfigurationError,
)
from ui.modulo_tronadura.column_mapper import (
    clear_confirmed_mapping,
    get_confirmed_mapping,
    render_column_mapper,
)
from ui.modulo_tronadura.enrichment import (
    compute_drill_compliance_if_design,
    enrich_processed,
    read_uploaded_bytes,
)
from ui.modulo_tronadura.state import (
    get_blast_cached_name,
    get_blast_df,
    get_blast_processed,
    get_ref_line_traces,
    reset_blast_processed_state,
    set_blast_cached_name,
    set_blast_df,
    set_blast_lines,
    set_blast_processed,
)

logger = logging.getLogger(__name__)


def render_upload_section() -> None:
    """Render file uploaders, preview, process button and drill compliance."""
    ref_traces = get_ref_line_traces()
    if ref_traces:
        st.caption(f"📍 {len(ref_traces)} línea(s) de referencia cargada(s) desde el panel lateral")

    st.markdown("""
    Sube el reporte de pozos (CSV / Excel). Se requieren columnas con coordenadas
    (Latitud_Geo, Longitud_Geo, Nombre_Banco), trayectoria (Inclinacion_real,
    Azimuth_real, longitud_real) y opcionalmente Kilos_Cargados_real para colorear.
    """)

    uploaded = st.file_uploader(
        "Archivo de pozos (CSV o Excel)",
        type=["csv", "xlsx", "xls"],
        key="blast_file",
    )
    design_uploaded = st.file_uploader(
        "Diseño de perforación (CSV, opcional)",
        type=["csv"],
        key="blast_design_file",
    )
    hardness_uploaded = st.file_uploader(
        "Reporte de perforación (rig) — CSV opcional",
        type=["csv"],
        key="blast_drill_hardness_file",
        help="CSV con Pozo, Tiempo Inicial/Final, Profundidad, Equipo y coordenadas. Enriquece cada pozo con dureza, índice de dureza y tasa de penetración.",
    )

    if uploaded is None:
        if not ref_traces:
            st.info("⏳ Esperando archivo de pozos y/o líneas de referencia para procesar.")
        return

    try:
        df = read_uploaded_bytes(uploaded.getvalue(), uploaded.name)
    except Exception:
        logger.exception("Failed to read blast file")
        st.error("No se pudo leer el archivo de pozos. Revisa la consola para detalles.")
        return

    st.subheader("Vista previa del archivo")
    st.dataframe(df.head(20), width="stretch")
    st.caption(f"{len(df)} filas | Columnas: {', '.join(df.columns[:10])}{'...' if len(df.columns) > 10 else ''}")

    cached_name = get_blast_cached_name()
    if cached_name != uploaded.name:
        set_blast_cached_name(uploaded.name)
        reset_blast_processed_state()
        # New file — also reset the column-mapper confirmed mapping so the
        # next render starts from the auto-detected baseline.
        clear_confirmed_mapping("blast")

    # ── Column mapper ──────────────────────────────────────────────────────
    # The mapper is always rendered when a file is uploaded. It returns the
    # mapping dict if the user clicked "Confirmar mapeo", or None if the user
    # is still picking columns. We hold processing until then.
    confirmed_mapping = render_column_mapper(df, key_prefix="blast")

    # Re-fetch from session_state in case a previous rerun had confirmed
    # but this rerun the user just opened the mapper again (e.g. scrolled
    # down) — keep the previously confirmed value.
    if confirmed_mapping is None:
        confirmed_mapping = get_confirmed_mapping("blast")

    if confirmed_mapping is None:
        st.info(
            "✋ Confirma el mapeo de columnas arriba antes de procesar el archivo."
        )
        return

    # The mapper already validated the mapping (the confirm button is
    # disabled while invalid), but we re-check defensively in case the
    # session_state was mutated externally. We do *not* apply the mapping
    # here: we hand the raw df + mapping to ``procesar_pozos``, which
    # takes a dedicated ``column_map`` branch that knows how to apply it
    # against the raw source columns.
    errors = validate_mapping(confirmed_mapping)
    if errors:
        st.error(
            "El mapeo confirmado tiene errores. Ajusta las columnas arriba: "
            + "; ".join(errors)
        )
        return
    # Quick smoke check: at least one row must produce a valid mapped frame,
    # so the user gets immediate feedback instead of waiting for the worker.
    smoke = apply_mapping(df.head(1), confirmed_mapping)
    if smoke.empty and not confirmed_mapping:
        # No mapping at all — should already be filtered above; defensive only.
        st.error("Mapeo vacío. Selecciona al menos las columnas requeridas.")
        return

    # Cierre final §2.2: convención angular EXPLÍCITA y confirmada — la
    # interfaz comienza sin selección implícita y el procesamiento se
    # bloquea hasta que el usuario confirme.
    with st.expander("📐 Convención geométrica del evento", expanded=False):
        incl_label = st.selectbox(
            "Convención de inclinación",
            options=["Seleccione una convención", "Desviación desde la vertical", "Dip desde la horizontal"],
            index=0,
            help=(
                "Debe declarar la convención antes de procesar. Desviación desde "
                "la vertical: 0° = pozo vertical (canónica). Dip desde la "
                "horizontal: 0° = horizontal. -65° se resuelve conservando la "
                "orientación antes de convertir."
            ),
            key="blast_incl_convention_selector",
        )
        if "vertical" in incl_label:
            st.session_state["blast_incl_convention"] = "from_vertical"
        elif "Dip" in incl_label:
            st.session_state["blast_incl_convention"] = "dip_from_horizontal"
        else:
            st.session_state.pop("blast_incl_convention", None)

        sign_label = st.selectbox(
            "Tratamiento del signo (controla la geometría)",
            options=["Usar valor absoluto", "Signo negativo representa dip descendente", "Convención definida por la fuente"],
            index=0,
            help=(
                "Política REAL de normalización: ABSOLUTE_VALUE usa la magnitud; "
                "NEGATIVE_IS_DOWNWARD_DIP (solo con dip) conserva la semántica "
                "descendente; SOURCE_DEFINED exige una regla explícita — sin ella "
                "el procesamiento se bloquea."
            ),
            key="blast_incl_sign_convention",
        )
        if sign_label.startswith("Usar"):
            st.session_state["blast_sign_rule"] = "ABSOLUTE_VALUE"
        elif sign_label.startswith("Signo negativo"):
            st.session_state["blast_sign_rule"] = "NEGATIVE_IS_DOWNWARD_DIP"
        else:
            st.session_state["blast_sign_rule"] = "SOURCE_DEFINED"
            st.selectbox(
                "Regla de la fuente (obligatoria para SOURCE_DEFINED)",
                options=["negative_is_downward_dip", "positive_only", "absolute_value"],
                index=0,
                help="Sin una regla explícita la geometría se bloquea.",
                key="blast_sign_source_rule",
            )
        az_label = st.selectbox(
            "Convención de azimut (controla la geometría)",
            options=["Horario desde el Norte", "Antihorario desde el Norte", "Horario desde el Este", "Antihorario desde el Este"],
            index=0,
            key="blast_az_convention_selector",
        )
        az_map = {
            "Horario desde el Norte": "CLOCKWISE_FROM_NORTH",
            "Antihorario desde el Norte": "COUNTERCLOCKWISE_FROM_NORTH",
            "Horario desde el Este": "CLOCKWISE_FROM_EAST",
            "Antihorario desde el Este": "COUNTERCLOCKWISE_FROM_EAST",
        }
        st.session_state["blast_az_convention"] = az_map[az_label]
        st.selectbox(
            "Unidad angular de INCLINACIÓN",
            options=["Grados", "Radianes"],
            index=0,
            key="blast_incl_unit",
            help="Unidad independiente para la columna de inclinación.",
        )
        st.selectbox(
            "Unidad angular de AZIMUT",
            options=["Grados", "Radianes"],
            index=0,
            key="blast_az_unit",
            help="Unidad independiente para la columna de azimut (puede diferir de incl).",
        )
        st.caption(
            "Azimut: grados en sentido horario desde el Norte (canónico). La "
            "selección se persiste en la configuración reproducible del evento "
            f"(versión {GEOMETRY_CONFIGURATION_VERSION})."
        )
        bench_h_ui = st.number_input(
            "Altura de banco (m) — obligatoria para cota de banco",
            min_value=0.0,
            value=0.0,
            step=0.5,
            help=(
                "Si la columna de elevación es cota de banco, la altura DEBE "
                "declararse; sin ella la cota no se transforma y la geometría "
                "dependiente queda bloqueada (nunca 15 m automáticos)."
            ),
            key="blast_bench_height_input",
        )
        st.session_state["blast_bench_height_m"] = (
            bench_h_ui if bench_h_ui and bench_h_ui > 0 else None
        )
        convention_confirmed = bool(
            st.checkbox(
                "Confirmo la convención geométrica seleccionada",
                value=False,
                help="Confirmación explícita: sin ella el procesamiento se bloquea.",
                key="blast_geometry_confirmed",
            )
        )
        if not convention_confirmed:
            st.warning(
                "⚠️ **Convención geométrica no confirmada.** El procesamiento "
                "quedará bloqueado hasta que seleccione y confirme la convención "
                "de inclinación (y declare la altura de banco si la elevación es "
                "cota de banco)."
            )
        elif st.session_state.get("blast_incl_convention") is None:
            st.error("Seleccione una convención de inclinación para continuar.")

    can_process = bool(st.session_state.get("blast_geometry_confirmed", False)) and \
        st.session_state.get("blast_incl_convention") is not None

    if st.button("🚀 Procesar Pozos", type="primary", key="process_blast", disabled=not can_process):
        progress = st.progress(0.0, text="Encolando trabajo de procesamiento…")
        status = st.empty()
        status.info("⏳ Procesando pozos en segundo plano…")

        # Fase 1.1 cierre §2.3 + integración §3.2/4.2: la configuración
        # geométrica se construye como un contrato versionado y validado
        # que el operador confirma explícitamente. La confirmación visual
        # se transmite como ``geometry_user_confirmed=True`` al backend.
        incl_conv_ui = st.session_state.get("blast_incl_convention", None)
        bench_h_ui = st.session_state.get("blast_bench_height_m", None)
        try:
            bench_h_ui = float(bench_h_ui) if bench_h_ui not in (None, "") else None
        except (TypeError, ValueError):
            bench_h_ui = None

        # Source columns: derived from the CONFIRMED column mapping (the
        # operator selected these names). When the mapper didn't capture
        # Incl/Az we cannot construct a v2 contract — surface the error.
        incl_src_col = (confirmed_mapping or {}).get("Incl") or ""
        az_src_col = (confirmed_mapping or {}).get("Az") or ""

        # Build the v2 contract. ``geometry_user_confirmed`` is True ONLY
        # when the operator ticked the confirmation checkbox in this UI.
        # Integración §3.2 — the value MUST reach ``procesar_pozos``.
        operator_confirmed = bool(
            st.session_state.get("blast_geometry_confirmed", False)
        )
        cfg = GeometryConfiguration(
            geometry_user_confirmed=operator_confirmed,
            inclination_convention=(
                {"from_vertical": "FROM_VERTICAL",
                 "dip_from_horizontal": "DIP_FROM_HORIZONTAL"}.get(incl_conv_ui or "")
                if incl_conv_ui else None
            ),
            inclination_sign_convention=st.session_state.get(
                "blast_sign_rule", "ABSOLUTE_VALUE"
            ),
            inclination_source_rule=st.session_state.get(
                "blast_sign_source_rule", ""
            ),
            inclination_unit=(
                "RADIANS"
                if st.session_state.get("blast_incl_unit", "Grados") == "Radianes"
                else "DEGREES"
            ),
            azimuth_convention=st.session_state.get(
                "blast_az_convention", "CLOCKWISE_FROM_NORTH"
            ),
            azimuth_unit=(
                "RADIANS"
                if st.session_state.get("blast_az_unit", "Grados") == "Radianes"
                else "DEGREES"
            ),
            inclination_source_column=incl_src_col,
            azimuth_source_column=az_src_col,
        )
        try:
            cfg.validate()
        except GeometryConfigurationError as exc:
            st.error(f"Configuración geométrica inválida: {exc}")
            set_blast_processed(False)
            status.empty()
            progress.empty()
            return

        # procesar_pozos has a dedicated ``column_map`` branch that calls
        # apply_mapping once without round-tripping through _resolve_column_aliases.
        # That branch is what we want when the user just confirmed a mapping in
        # the UI. The legacy alias-based auto-detection is still available to
        # other callers (e.g. CLI ingestion) via procesar_pozos(df).
        local_df = df.copy()
        try:
            def _run_with_progress(
                source_df: pd.DataFrame,
                cmap: dict[str, str | None] | None,
                geometry_cfg: GeometryConfiguration,
                bench_height: float | None,
            ) -> tuple[pd.DataFrame, Any, Any, Any]:
                try:
                    progress.progress(0.1, text="Calculando trayectorias (toe)…")
                except Exception:
                    pass
                result = procesar_pozos(
                    source_df,
                    cmap,
                    geometry_configuration=geometry_cfg,
                    bench_height_m=bench_height,
                )
                try:
                    progress.progress(0.9, text="Empacando resultados…")
                except Exception:
                    pass
                return result

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _run_with_progress, local_df, confirmed_mapping, cfg, bench_h_ui
                )
                try:
                    df_clean, x_lines, y_lines, z_lines = future.result()
                except (KeyError, GeometryConfigurationError) as e:
                    st.error(str(e))
                    set_blast_processed(False)
                    status.empty()
                    progress.empty()
                    return

            df_clean = enrich_processed(
                df_clean,
                hardness_bytes=hardness_uploaded.getvalue() if hardness_uploaded is not None else None,
            )
            set_blast_df(df_clean)
            set_blast_lines(x_lines, y_lines, z_lines)
            set_blast_processed(True)
            status.success("✅ Pozos procesados correctamente")
            progress.progress(1.0, text="Listo")
        except Exception:
            logger.exception("Failed to process blast holes")
            st.error("No se pudieron procesar los pozos. Revisa la consola para detalles.")
            set_blast_processed(False)
            status.empty()
            progress.empty()

    if not get_blast_processed():
        return

    df_clean = get_blast_df()
    if df_clean is None:
        return

    if design_uploaded is None:
        st.info("Sin diseño cargado — omitiendo verificación")
    else:
        try:
            design_df = read_uploaded_bytes(design_uploaded.getvalue(), design_uploaded.name)
            compliance = compute_drill_compliance_if_design(design_df, df_clean)
            _render_drill_compliance_block(compliance)
        except Exception:
            logger.exception("Failed to compute drill compliance")
            st.error("No se pudo analizar el cumplimiento del diseño de perforación.")


def _render_drill_compliance_block(result) -> None:
    with st.expander("Cumplimiento del diseño de perforación", expanded=True):
        score = result["compliance_score"]
        st.metric("Cumplimiento", f"{score * 100:.1f}%" if score is not None else "Sin datos")
        if not result["per_hole"].empty:
            st.dataframe(result["per_hole"], width="stretch")
        if result["per_group"] is not None:
            st.subheader("Cumplimiento por malla")
            st.dataframe(result["per_group"], width="stretch")
        unmatched = result["unmatched"]
        if unmatched["design"]:
            st.warning(f"{len(unmatched['design'])} pozos de diseño sin coincidencia")
        if unmatched["actual"]:
            st.warning(f"{len(unmatched['actual'])} pozos perforados sin coincidencia")
        for message in result["warnings"]:
            st.info(message)
