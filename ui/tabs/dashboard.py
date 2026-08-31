"""
Results tab: compliance dashboard — simplified CUMPLE / NO CUMPLE.

Design principles:
- Binary status: CUMPLE or NO CUMPLE (no "FUERA DE TOLERANCIA").
- Clear KPIs: % cumplimiento por parámetro + promedio real.
- Map: dónde se cumple y dónde no (por sector).
"""
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from ui.filter_cache import _ensure_filter_values
from ui.filters import apply_comparison_filters, collect_active_filters_from_session_state
from ui.tabs.blast_correlation.data import resolve_achievement_tolerances
from ui.tabs.blast_correlation.renderers import format_achievement_caption
from ui.tabs.dashboard_achievement import (
    build_achievement_histograms,
    build_achievement_summary,
    build_parameter_breakdown_rows,
    build_sector_rows,
)


def render_tab_dashboard(config: dict) -> None:
    results = st.session_state.comparison_results
    if not results:
        return

    with st.expander("🔎 Filtros", expanded=False):
        cols_filter = st.columns(4)
        fv = _ensure_filter_values()

        cols_filter[0].multiselect(
            "Filtrar por Sector:", fv['sectors'], default=[], key="dash_filter_sector")
        cols_filter[1].multiselect(
            "Filtrar por Nivel (Cota):", fv['levels'], default=[], key="dash_filter_level")
        cols_filter[2].multiselect(
            "Filtrar por Sección:", fv['sections'], default=[], key="dash_filter_section")
        cols_filter[3].multiselect(
            "Filtrar por Banco:", fv['benches'], default=[], key="dash_filter_bench")

    active = collect_active_filters_from_session_state(prefix="dash_filter")
    filtered_results = apply_comparison_filters(list(results), active)

    if not filtered_results:
        st.warning("⚠️ No hay resultados que coincidan con los filtros seleccionados.")
        return

    ct_tol = resolve_achievement_tolerances(
        (config or {}).get('tolerances', {}).get('crest_toe_deviation'))

    _render_global_kpi(filtered_results)
    _render_achievement_kpi(filtered_results, ct_tol)
    st.divider()
    _render_parameter_breakdown(filtered_results, ct_tol)
    st.divider()
    _render_sector_compliance_map(filtered_results, ct_tol)
    st.divider()
    _render_plan_view(filtered_results, config)
    st.divider()
    _render_deviation_histograms(filtered_results, config)


# ---------------------------------------------------------------------------
# Section 1: Global KPI
# ---------------------------------------------------------------------------

def _render_global_kpi(results) -> None:
    """Tarjeta grande con el cumplimiento global.

    El cumplimiento global es el promedio de los scores por perfil
    (section_score), donde cada perfil ya tiene un score ponderado
    (berma=60, ángulo=20, altura=20).
    """
    # Agrupar scores por sección
    section_scores: dict[str, list[float]] = {}
    for r in results:
        sec_name = r.get('section', '')
        if sec_name not in section_scores:
            section_scores[sec_name] = []
        if r.get('type') == 'MATCH':
            section_scores[sec_name].append(r.get('bench_score', 0))

    # Score por sección = promedio de bench_score de sus bancos
    per_section_scores: list[float] = []
    for sec_name, scores in section_scores.items():
        if scores:
            per_section_scores.append(sum(scores) / len(scores))

    # Score global = promedio simple de los scores por sección
    global_score = (sum(per_section_scores) / len(per_section_scores)
                    if per_section_scores else 0)
    pct = global_score  # Ya está en escala 0-100

    # Contadores binarios para las tarjetas (cumple/no cumple por perfil)
    total_cumple = sum(1 for s in per_section_scores if s >= 70)
    no_cumple = len(per_section_scores) - total_cumple

    st.subheader("📊 Cumplimiento Global")
    st.caption(f"Promedio ponderado de {len(per_section_scores)} perfiles "
               f"(berma=60, ángulo=20, altura=20)")

    cols = st.columns([1, 1, 1])
    color = "green" if pct >= 70 else "orange" if pct >= 50 else "red"

    with cols[0]:
        st.markdown(
            f"<div style='text-align:center; padding:1.2rem; "
            f"background:rgba({0 if pct < 70 else 0},{153 if pct >= 70 else 140},{0 if pct >= 70 else 60},0.1); "
            f"border-radius:12px; border:2px solid {color};'>"
            f"<div style='font-size:3rem; font-weight:800; color:{color};'>"
            f"{pct:.1f}</div>"
            f"<div style='font-size:0.9rem; color:#888;'>Score Global / 100</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with cols[1]:
        st.markdown(
            f"<div style='text-align:center; padding:1.2rem; "
            f"background:rgba(0,100,0,0.08); border-radius:12px;'>"
            f"<div style='font-size:2.2rem; font-weight:700; color:green;'>"
            f"{total_cumple}</div>"
            f"<div style='font-size:0.9rem; color:#888;'>Perfiles CUMPLE (≥70)</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with cols[2]:
        st.markdown(
            f"<div style='text-align:center; padding:1.2rem; "
            f"background:rgba(180,0,0,0.08); border-radius:12px;'>"
            f"<div style='font-size:2.2rem; font-weight:700; color:#B22222;'>"
            f"{no_cumple}</div>"
            f"<div style='font-size:0.9rem; color:#888;'>Perfiles NO CUMPLE</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Section 1b: Logro Diseño — Cresta, Pata y Berma (métrica separada)
# ---------------------------------------------------------------------------

def _render_achievement_kpi(results, ct_tol: dict) -> None:
    """KPIs de Logro Diseño: global (parcial) + % estricto por elemento."""
    st.subheader("🎯 Logro Diseño — Cresta, Pata y Berma")
    summary = build_achievement_summary(results, ct_tol)
    if summary is None:
        st.info("Sin datos de logro evaluables (se requieren desviaciones de "
                "cresta/pata o estado de berma).")
        return

    def _card(label, pct, denom, color):
        value = "—" if denom == 0 else f"{pct}%"
        st.markdown(
            f"<div style='text-align:center; padding:1rem; "
            f"background:rgba(0,100,0,0.08); border-radius:12px;'>"
            f"<div style='font-size:2rem; font-weight:700; color:{color};'>"
            f"{value}</div>"
            f"<div style='font-size:0.85rem; color:#888;'>{label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    cols = st.columns(4)
    with cols[0]:
        pct = summary["global"]
        color = "green" if pct >= 70 else "orange" if pct >= 50 else "#B22222"
        _card("Logro Diseño Global (parcial)", pct, 1, color)
    with cols[1]:
        _card("Cresta CUMPLE estricto", summary["crest_pct"], summary["crest_denom"], "green")
    with cols[2]:
        _card("Pata CUMPLE estricto", summary["toe_pct"], summary["toe_denom"], "green")
    with cols[3]:
        _card("Berma CUMPLE estricto", summary["berm_pct"], summary["berm_denom"], "green")

    st.caption(
        format_achievement_caption(summary["ct_tol"])
        + " · El score global da 50% de crédito a FUERA DE TOLERANCIA; "
        "las tarjetas por elemento cuentan sólo CUMPLE estricto."
    )


# ---------------------------------------------------------------------------
# Section 2: Parameter breakdown (% cumplimiento + promedio real)
# ---------------------------------------------------------------------------

def _render_parameter_breakdown(results, ct_tol: dict) -> None:
    """Tabla clara: por cada parámetro, % cumplimiento y promedio real."""
    st.subheader("📋 Detalle por Parámetro")

    rows = build_parameter_breakdown_rows(results, ct_tol)
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            '% Cumplimiento': st.column_config.TextColumn(width='small'),
        },
    )

    # Bar chart: CUMPLE vs NO CUMPLE (sin "FUERA DE TOLERANCIA")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name='CUMPLE', x=[r['Parámetro'] for r in rows],
        y=[r['Cumple'] for r in rows],
        marker_color='#2E7D32', text=[r['% Cumplimiento'] for r in rows],
        textposition='inside',
    ))
    fig.add_trace(go.Bar(
        name='NO CUMPLE', x=[r['Parámetro'] for r in rows],
        y=[r['No Cumple'] for r in rows],
        marker_color='#C62828', text=[str(v) for v in [r['No Cumple'] for r in rows]],
        textposition='inside',
    ))
    fig.update_layout(
        barmode='stack',
        title="Cumplimiento por Parámetro (binario)",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section 3: Sector compliance map (dónde se cumple, dónde no)
# ---------------------------------------------------------------------------

def _render_sector_compliance_map(results, ct_tol: dict) -> None:
    """Mapa por sector: cumplimiento geotécnico y Logro Diseño separados."""
    st.subheader("🗺️ Cumplimiento por Sector")

    sector_rows = build_sector_rows(results, ct_tol)
    if not sector_rows:
        st.info("No hay datos de sector disponibles.")
        return

    df_sectors = pd.DataFrame(sector_rows)
    df_disp = df_sectors.copy()
    df_disp["Logro Diseño (%)"] = df_disp["Logro Diseño (%)"].map(
        lambda v: "Sin datos" if v is None else v)
    st.dataframe(df_disp, use_container_width=True, hide_index=True)

    # Barras agrupadas: dos métricas separadas, nunca promediadas
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name='Cumplimiento Geotécnico (%)',
        x=df_sectors['Sector'], y=df_sectors['% Cumplimiento'],
        marker_color='#2E7D32', textposition='outside',
        text=[f"{v:.0f}%" for v in df_sectors['% Cumplimiento']],
    ))
    logro = df_sectors[df_sectors['Logro Diseño (%)'].notna()]
    fig.add_trace(go.Bar(
        name='Logro Diseño (%)',
        x=logro['Sector'], y=logro['Logro Diseño (%)'],
        marker_color='#1565C0', textposition='outside',
        text=[f"{v:.0f}%" for v in logro['Logro Diseño (%)']],
    ))
    fig.update_layout(
        barmode='group',
        title="Cumplimiento Geotécnico vs Logro Diseño por Sector",
        yaxis_title="%", yaxis_range=[0, 105],
        height=380,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.add_hline(y=70, line_dash="dash", line_color="green",
                  annotation_text="Meta 70%", annotation_position="top left")
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section 4: Plan view (perfiles en planta verde/rojo)
# ---------------------------------------------------------------------------

def _render_plan_view(results, config: dict) -> None:
    """Vista en planta: topografía STL real (Mesh3d gris) + perfiles por score.

    Fondo: malla STL de topografía real en gris neutro, con el máximo
    detalle razonable (full hasta 500k caras; high-detail 250k por encima).
    Líneas: cada perfil como segmento 3D verde (CUMPLE) o rojo (NO CUMPLE).

    Score por sección = media de bench_score (MATCH) o section_score
    canónico; verde si score >= 70, rojo si < 70.
    """
    from contextlib import nullcontext

    from ui.tabs.dashboard_plan_view import (
        build_plan_view_figure,
        build_topo_profile_map,
        compute_section_status,
        ensure_plan_mesh_topo,
        plan_high_detail_needed,
        select_plan_mesh,
    )

    st.subheader("🗺️ Plano de Cumplimiento por Perfil")

    sections = st.session_state.get('sections', [])
    if not sections:
        st.info("No hay secciones disponibles para dibujar el plano.")
        return

    section_status = compute_section_status(results)

    mesh_topo = st.session_state.get('mesh_topo')
    decimated_mesh_topo = st.session_state.get('decimated_mesh_topo')

    spinner = (st.spinner("Preparando superficie de detalle...")
               if plan_high_detail_needed(mesh_topo, st.session_state)
               else nullcontext())
    with spinner:
        plan_mesh_topo = ensure_plan_mesh_topo(mesh_topo, st.session_state)

    mesh = select_plan_mesh(mesh_topo, decimated_mesh_topo, plan_mesh_topo)

    if mesh_topo is None:
        st.warning("⚠️ No hay STL topográfico real cargado; no se dibuja la superficie.")
    elif mesh is None:
        st.warning(
            "⚠️ La topografía no contiene geometría renderizable "
            "o no hay una malla optimizada disponible."
        )

    # Drape the compliance profiles on the real topographic surface using
    # the canonical cuts already computed in step 3 (profiles_topo in
    # parallel with processed_sections). No mesh cut is repeated here; a
    # section without a canonical profile is simply not drawn.
    profiles_topo = st.session_state.get('profiles_topo') or []
    processed_sections = st.session_state.get('processed_sections') or []
    profiles_by_name = build_topo_profile_map(processed_sections, profiles_topo)

    fig = build_plan_view_figure(mesh, sections, section_status,
                                 profiles_by_name=profiles_by_name)
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section 5: Deviation histograms
# ---------------------------------------------------------------------------

def _render_deviation_histograms(results, config: dict) -> None:
    """Histogramas de desviación con líneas de tolerancia."""
    st.subheader("📈 Distribución de Desviaciones")

    tol = config['tolerances']
    col1, col2, col3 = st.columns(3)

    with col1:
        devs_h = [r['height_dev'] for r in results if r['height_dev'] is not None]
        fig_h = go.Figure(go.Histogram(x=devs_h, nbinsx=15, marker_color='royalblue'))
        fig_h.update_layout(title="Desv. Altura (m)", height=300,
                            xaxis_title="Desviación (m)", yaxis_title="Frecuencia",
                            margin=dict(l=20, r=10, t=40, b=20))
        fig_h.add_vrect(
            x0=-tol['bench_height']['neg'], x1=tol['bench_height']['pos'],
            fillcolor="green", opacity=0.1, layer="below",
            annotation_text="CUMPLE", annotation_position="top left",
        )
        st.plotly_chart(fig_h, use_container_width=True)

    with col2:
        devs_a = [r['angle_dev'] for r in results if r['angle_dev'] is not None]
        fig_a = go.Figure(go.Histogram(x=devs_a, nbinsx=15, marker_color='forestgreen'))
        fig_a.update_layout(title="Desv. Ángulo (°)", height=300,
                            xaxis_title="Desviación (°)", yaxis_title="Frecuencia",
                            margin=dict(l=20, r=10, t=40, b=20))
        fig_a.add_vrect(
            x0=-tol['face_angle']['neg'], x1=tol['face_angle']['pos'],
            fillcolor="green", opacity=0.1, layer="below",
            annotation_text="CUMPLE", annotation_position="top left",
        )
        st.plotly_chart(fig_a, use_container_width=True)

    with col3:
        berm_vals = [r['berm_real'] for r in results
                     if r['berm_real'] is not None and r['berm_real'] > 0]
        if berm_vals:
            fig_b = go.Figure(go.Histogram(x=berm_vals, nbinsx=15, marker_color='#FF7F0E'))
            fig_b.update_layout(title="Ancho Berma (m)", height=300,
                                xaxis_title="Ancho (m)", yaxis_title="Frecuencia",
                                margin=dict(l=20, r=10, t=40, b=20))
            fig_b.add_vline(
                x=config['min_berm_width'], line_dash="dash", line_color="red",
                annotation_text="Mínimo", annotation_position="top right",
            )
            st.plotly_chart(fig_b, use_container_width=True)

    # Segunda fila: Δ Cresta y Δ Pata (Logro Diseño, tolerancia firmada)
    ct_tol = resolve_achievement_tolerances(
        (config or {}).get('tolerances', {}).get('crest_toe_deviation'))
    hist_specs = build_achievement_histograms(results, ct_tol)
    cols_delta = st.columns(2)
    for col, spec in zip(cols_delta, hist_specs):
        with col:
            if not spec["values"]:
                st.info(f"Sin datos de {spec['title']}.")
                continue
            fig_d = go.Figure(go.Histogram(
                x=spec["values"], nbinsx=15, marker_color='#1565C0'))
            fig_d.update_layout(title=spec["title"], height=300,
                                xaxis_title="Desviación (m)", yaxis_title="Frecuencia",
                                margin=dict(l=20, r=10, t=40, b=20))
            fig_d.add_vrect(
                x0=spec["x0"], x1=spec["x1"],
                fillcolor="green", opacity=0.1, layer="below",
                annotation_text="CUMPLE", annotation_position="top left",
            )
            st.plotly_chart(fig_d, use_container_width=True)
