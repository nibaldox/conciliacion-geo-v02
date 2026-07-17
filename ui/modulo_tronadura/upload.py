"""Blast file upload and processing section."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd
import streamlit as st

from core.calculo_tronadura import procesar_pozos
from core.column_mapping import apply_mapping, validate_mapping
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

    if st.button("🚀 Procesar Pozos", type="primary", key="process_blast"):
        progress = st.progress(0.0, text="Encolando trabajo de procesamiento…")
        status = st.empty()
        status.info("⏳ Procesando pozos en segundo plano…")

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
            ) -> tuple[pd.DataFrame, Any, Any, Any]:
                try:
                    progress.progress(0.1, text="Calculando trayectorias (toe)…")
                except Exception:
                    pass
                result = procesar_pozos(source_df, cmap)
                try:
                    progress.progress(0.9, text="Empacando resultados…")
                except Exception:
                    pass
                return result

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_with_progress, local_df, confirmed_mapping)
                try:
                    df_clean, x_lines, y_lines, z_lines = future.result()
                except KeyError as e:
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
