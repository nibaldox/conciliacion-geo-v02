"""Geotechnical correlation tab for blast-hole analysis."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import streamlit as st

from core.config import DEFAULTS
from core.geom_utils import find_df_column
from core.stability_analysis import suggest_face_angle_for_fs
from ui.blast_analysis import build_pf_deviation_scatter
from ui.modulo_tronadura.figures import (
    build_pasadura_figure,
    build_sector_deviation_figure,
    build_sector_table_rows,
    compute_pasadura_series,
    get_sector_face_angle_note,
)
from ui.modulo_tronadura.projections import (
    compute_sector_deviation_data,
    get_profile_pair_or_cut,
    project_blast_to_sections,
    compute_signed_correlations,
)
from ui.modulo_tronadura.state import (
    get_blast_df,
    get_comparison_results,
    get_mesh_design,
    get_mesh_topo,
    get_sections,
    get_sector_bench_h,
    get_sector_fs_target,
    get_sector_rmr,
    get_sector_tolerance,
    set_sector_tolerance,
)

logger = logging.getLogger(__name__)


def render_correlation_tab(df_clean: pd.DataFrame) -> None:
    """Render the "🔬 Correlación Geotécnica" tab."""
    df_filtered = df_clean.copy()

    st.subheader("🔬 Análisis de Pasadura (Sub-drilling)")
    st.markdown("""
    La **pasadura** es la profundidad que el pozo se perfora por debajo de la pata teórica del banco diseñado.
    Un rango óptimo típico en minería a cielo abierto es de **0.5 a 1.5 metros** para asegurar que el piso se rompa bien sin dejar lomos.
    """)

    pasadura_series = compute_pasadura_series(df_filtered)
    p_mean = pasadura_series.mean()
    p_min, p_max = DEFAULTS.blast_correlation_pasadura_optimal
    p_optimal = ((pasadura_series >= p_min) & (pasadura_series <= p_max)).sum()
    p_pct = p_optimal / len(df_filtered) * 100 if len(df_filtered) > 0 else 0

    col_p1, col_p2 = st.columns(2)
    col_p1.metric("Pasadura Promedio", f"{p_mean:.2f} m")
    col_p2.metric(f"Pozos en Rango Óptimo ({p_min}m - {p_max}m)", f"{p_pct:.1f}%", f"{p_optimal}/{len(df_filtered)} pozos")

    fig_pas = build_pasadura_figure(pasadura_series, p_min, p_max)
    st.plotly_chart(fig_pas, width="stretch")

    _render_sector_deviations()

    st.markdown("---")
    st.subheader("💥 Correlación Geotécnica: Daño vs Explosivos")
    st.markdown("""
    Analiza si las secciones con mayor sobre-excavación (*overbreak*) coinciden espacialmente con mayor concentración de explosivos en las inmediaciones de esa sección.
    """)

    use_temporal_filter = st.checkbox(
        "Filtrar pozos por fecha de tronadura (recomendado)",
        value=True,
        key="tron_use_temporal_filter",
        help="Excluye pozos tronados después del levantamiento topográfico para evitar correlaciones espurias.",
    )
    fecha_levantamiento = None
    if use_temporal_filter:
        fecha_levantamiento = st.date_input(
            "Fecha de levantamiento topográfico:",
            value=None,
            key="tron_fecha_levantamiento",
            help="Solo se incluyen pozos tronados en o antes de esta fecha.",
        )
        if fecha_levantamiento is None:
            st.warning("⚠️ No se ha indicado fecha de levantamiento: la correlación puede incluir pozos tronados después del levantamiento, generando resultados espurios.")
    else:
        st.info("ℹ️ Filtro temporal desactivado: la correlación puede incluir pozos tronados después del levantamiento.")

    fecha_corte_str = fecha_levantamiento.isoformat() if fecha_levantamiento else None

    comparison = get_comparison_results()
    sections = get_sections()

    if not comparison or not sections:
        st.info("💡 Realiza la Conciliación Geotécnica primero (Paso 3 y Paso 4) para correlacionar el daño de los taludes con los explosivos.")
        return

    kg_col = find_df_column(
        df_filtered, ["Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg"],
        raise_error=False,
    )

    if not kg_col:
        st.warning("⚠️ No se encontró columna de Kg de explosivos (`Kilos_Cargados_real`, etc.) para cruzar la energía.")
        return

    df_comp = pd.DataFrame(comparison)

    if "delta_crest" not in df_comp.columns:
        st.warning("⚠️ No se encontró la columna `delta_crest` (con signo) en la conciliación; no es posible separar sobre-excavación de deuda.")
        return

    df_comp_signed = df_comp.dropna(subset=["delta_crest"])
    df_comp_signed_over = df_comp_signed[df_comp_signed["delta_crest"] > 0]
    df_comp_signed_under = df_comp_signed[df_comp_signed["delta_crest"] < 0]

    sec_over_grouped = df_comp_signed_over.groupby("section")["delta_crest"].mean()
    sec_under_grouped = df_comp_signed_under.groupby("section")["delta_crest"].mean()

    kernel_rows = project_blast_to_sections(
        df_filtered,
        sections,
        kg_col=kg_col,
        tolerance=DEFAULTS.blast_correlation_radius_m,
        fecha_corte=fecha_corte_str,
    )

    corr_data = []
    pf_available = False
    for row in kernel_rows:
        sec_name = row["section_name"]
        avg_over_break = float(sec_over_grouped.get(sec_name, 0.0) or 0.0)
        avg_under_break = float(sec_under_grouped.get(sec_name, 0.0) or 0.0)
        pf_vol = row["pf_vol_avg_kgm3"]
        if pf_vol is not None and not (isinstance(pf_vol, float) and np.isnan(pf_vol)):
            pf_available = True
        corr_data.append({
            "Sección": sec_name,
            "Kg_Explosivo": row["total_kg"],
            "Pozos_Cercanos": row["num_pozos"],
            "PF_Vol_kgm3": pf_vol,
            "Energía_MJ": row["energy_total_mj"],
            "Sobre-excavación_Media_m": avg_over_break,
            "Deuda/Relleno_Media_m": avg_under_break,
        })

    df_corr = pd.DataFrame(corr_data)

    if df_corr.empty or df_corr["Kg_Explosivo"].sum() == 0:
        st.info("💡 No hay suficientes pozos con carga explosiva cercanos a las secciones para realizar la correlación.")
        return

    st.dataframe(df_corr, width="stretch")

    if pf_available:
        x_col = "PF_Vol_kgm3"
        x_label = "Powder Factor Volumétrico (kg/m³)"
        x_caption_metric = "powder factor (kg/m³)"
        x_fallback = False
    else:
        x_col = "Kg_Explosivo"
        x_label = "Carga Explosiva Acumulada (Kg) — fallback sin PF"
        x_caption_metric = "carga explosiva"
        x_fallback = True

    fig_scat = build_pf_deviation_scatter(
        df_corr,
        x_col=x_col,
        x_label=x_label,
        radius_m=DEFAULTS.blast_correlation_radius_m,
        show_ols=True,
    )
    st.plotly_chart(fig_scat, width="stretch")
    if x_fallback:
        st.caption("ℹ️ Scatter con Kg crudo: powder factor no disponible (faltan columnas de burden/espaciamiento).")

    r_over, r_under = compute_signed_correlations(df_corr, x_col)

    if r_over > 0.5:
        st.success(f"📈 **Sobre-excavación — Correlación Fuerte Positiva (r = {r_over:.2f})**: Las secciones con mayor {x_caption_metric} presentan sistemáticamente mayor sobre-quiebre en la cresta. Es consistente con daño por exceso de energía.")
    elif r_over > 0.3:
        st.info(f"📈 **Sobre-excavación — Correlación Moderada Positiva (r = {r_over:.2f})**")
    else:
        st.info(f"⚖️ **Sobre-excavación — Correlación Débil/Nula (r = {r_over:.2f})**: El sobre-quiebre no parece estar fuertemente ligado de forma directa a la {x_caption_metric} de esta vecindad.")

    df_corr_with_under = df_corr[df_corr["Deuda/Relleno_Media_m"] < 0]
    if df_corr_with_under.empty:
        st.caption("Sin datos de deuda (todos delta_crest ≥ 0) para calcular correlación separada.")
    elif r_under < -0.5:
        st.warning(f"📉 **Deuda/Relleno — Correlación Negativa Fuerte (r = {r_under:.2f})**: Donde hay menos {x_caption_metric} se observa mayor deuda; puede indicar déficit de energía o sub-excavación previa al relevamiento topográfico.")
    elif r_under > 0.5:
        st.info(f"📈 **Deuda/Relleno — Correlación Positiva (r = {r_under:.2f})**")
    else:
        st.info(f"⚖️ **Deuda/Relleno — Correlación Débil/Nula (r = {r_under:.2f})**")


def _render_sector_deviations() -> None:
    sections = get_sections()
    mesh_design = get_mesh_design()
    mesh_topo = get_mesh_topo()

    if not sections or mesh_design is None or mesh_topo is None:
        return

    with st.expander(
        "🟥🟨 Sectorización de sobre-excavación / deuda (hover por tramo)",
        expanded=False,
    ):
        st.markdown(
            "Cada tramo entre crestas/patas del diseño se clasifica por la "
            "desviación integrada frente a la topografía real: **rojo = "
            "sobre-excavación**, **amarillo = deuda**, **verde = cumplimiento**, "
            "**morado = mixto**. Pasa el mouse sobre un tramo para ver sus valores."
        )

        sec_names = [s.name for s in sections]
        sel_name = st.selectbox("Sección a sectorizar:", sec_names, key="sector_dev_section")
        sel_sec = next((s for s in sections if s.name == sel_name), None)
        if sel_sec is None:
            return

        tolerance_m = st.slider(
            "Tolerancia vertical para clasificar 'cumplimiento' (m):",
            min_value=0.05, max_value=1.0,
            value=float(get_sector_tolerance()), step=0.05,
            key="sector_dev_tolerance",
        )
        set_sector_tolerance(tolerance_m)

        pd_prof, pt_prof = get_profile_pair_or_cut(sel_name, sections, mesh_design, mesh_topo)
        sectors, design_d, design_e, topo_d, topo_e = compute_sector_deviation_data(
            pd_prof, pt_prof, tolerance_m,
        )

        if sectors is None:
            st.info("No hay perfiles de diseño/topografía disponibles para esta sección.")
            return

        if not sectors:
            st.info("Los perfiles de diseño y topografía no se superponen; no hay tramos que sectorizar.")
            return

        fig_sectors = build_sector_deviation_figure(sectors, design_d, design_e, topo_d, topo_e)
        st.plotly_chart(fig_sectors, width="stretch")

        rows = build_sector_table_rows(sectors)
        st.dataframe(pd.DataFrame(rows), width="stretch")

        _render_face_angle_suggestion()


def _render_face_angle_suggestion() -> None:
    with st.expander("🎯 Sugerencia de ángulo de cara (FS objetivo)", expanded=False):
        st.caption(get_sector_face_angle_note())
        fs_target = st.slider("Factor de seguridad objetivo", 1.0, 2.5, 1.3, 0.05, key="sector_fs_target")
        rmr = st.number_input("RMR del macizo (0-100)", 0, 100, 60, key="sector_rmr")
        h = st.number_input("Altura de banco objetivo (m)", 5, 30, 15, key="sector_bench_h")
        if st.button("Calcular ángulo sugerido", key="sector_calc_angle"):
            try:
                ang = suggest_face_angle_for_fs(
                    fs_target=fs_target, rock_mass_rating=float(rmr), bench_height_m=float(h),
                )
                st.success(f"Ángulo de cara máximo sugerido: {ang:.1f}° (FS ≥ {fs_target})")
            except Exception as exc:
                st.error(f"No se pudo calcular: {exc}")
