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

    _render_global_kpi(filtered_results)
    st.divider()
    _render_parameter_breakdown(filtered_results)
    st.divider()
    _render_sector_compliance_map(filtered_results)
    st.divider()
    _render_plan_view(filtered_results, config)
    st.divider()
    _render_deviation_histograms(filtered_results, config)


# ---------------------------------------------------------------------------
# Section 1: Global KPI
# ---------------------------------------------------------------------------

def _render_global_kpi(results) -> None:
    """Tarjeta grande con el cumplimiento global y promedio."""
    total_eval = 0
    total_cumple = 0

    for r in results:
        for key in ('height_status', 'angle_status', 'berm_status'):
            s = r.get(key)
            if s and s != "-":
                total_eval += 1
                if s == "CUMPLE":
                    total_cumple += 1

    pct = (total_cumple / total_eval * 100) if total_eval > 0 else 0

    st.subheader("📊 Cumplimiento Global")

    cols = st.columns([1, 1, 1])
    color = "green" if pct >= 70 else "orange" if pct >= 50 else "red"

    with cols[0]:
        st.markdown(
            f"<div style='text-align:center; padding:1.2rem; "
            f"background:rgba({0 if pct < 70 else 0},{153 if pct >= 70 else 140},{0 if pct >= 70 else 60},0.1); "
            f"border-radius:12px; border:2px solid {color};'>"
            f"<div style='font-size:3rem; font-weight:800; color:{color};'>"
            f"{pct:.1f}%</div>"
            f"<div style='font-size:0.9rem; color:#888;'>Cumplimiento</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with cols[1]:
        st.markdown(
            f"<div style='text-align:center; padding:1.2rem; "
            f"background:rgba(0,100,0,0.08); border-radius:12px;'>"
            f"<div style='font-size:2.2rem; font-weight:700; color:green;'>"
            f"{total_cumple}</div>"
            f"<div style='font-size:0.9rem; color:#888;'>Parámetros CUMPLE</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with cols[2]:
        no_cumple = total_eval - total_cumple
        st.markdown(
            f"<div style='text-align:center; padding:1.2rem; "
            f"background:rgba(180,0,0,0.08); border-radius:12px;'>"
            f"<div style='font-size:2.2rem; font-weight:700; color:#B22222;'>"
            f"{no_cumple}</div>"
            f"<div style='font-size:0.9rem; color:#888;'>Parámetros NO CUMPLE</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Section 2: Parameter breakdown (% cumplimiento + promedio real)
# ---------------------------------------------------------------------------

def _render_parameter_breakdown(results) -> None:
    """Tabla clara: por cada parámetro, % cumplimiento y promedio real."""
    st.subheader("📋 Detalle por Parámetro")

    param_specs = [
        ('height_status', 'Altura de Banco', 'height_real', 'm'),
        ('angle_status', 'Ángulo de Cara', 'angle_real', '°'),
        ('berm_status', 'Ancho de Berma', 'berm_real', 'm'),
    ]

    rows = []
    for key, label, real_field, unit in param_specs:
        valid = [r for r in results if r.get(key) and r[key] != "-"]
        total = len(valid)
        cumple = sum(1 for r in valid if r[key] == "CUMPLE")
        pct = (cumple / total * 100) if total > 0 else 0

        real_values = [r[real_field] for r in valid if r.get(real_field) is not None]
        avg_real = (sum(real_values) / len(real_values)) if real_values else 0

        rows.append({
            'Parámetro': label,
            'Total Evaluado': total,
            'Cumple': cumple,
            'No Cumple': total - cumple,
            '% Cumplimiento': f"{pct:.0f}%",
            'Promedio Real': f"{avg_real:.1f} {unit}",
        })

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

def _render_sector_compliance_map(results) -> None:
    """Mapa de calor por sector: dónde se cumple y dónde no."""
    st.subheader("🗺️ Cumplimiento por Sector")

    sector_data = {}
    for r in results:
        sector = r.get('sector', 'Sin Sector') or 'Sin Sector'
        if sector not in sector_data:
            sector_data[sector] = {'cumple': 0, 'no_cumple': 0, 'total': 0}
        for key in ('height_status', 'angle_status', 'berm_status'):
            s = r.get(key)
            if s and s != "-":
                sector_data[sector]['total'] += 1
                if s == "CUMPLE":
                    sector_data[sector]['cumple'] += 1
                else:
                    sector_data[sector]['no_cumple'] += 1

    if not sector_data:
        st.info("No hay datos de sector disponibles.")
        return

    rows = []
    for sector, counts in sorted(sector_data.items()):
        pct = (counts['cumple'] / counts['total'] * 100) if counts['total'] > 0 else 0
        rows.append({
            'Sector': sector,
            'Cumple': counts['cumple'],
            'No Cumple': counts['no_cumple'],
            'Total': counts['total'],
            '% Cumplimiento': round(pct, 1),
        })

    df_sectors = pd.DataFrame(rows)

    # Colorear por compliance
    fig = go.Figure()
    for _, row in df_sectors.iterrows():
        color = '#2E7D32' if row['% Cumplimiento'] >= 70 else '#F9A825' if row['% Cumplimiento'] >= 50 else '#C62828'
        fig.add_trace(go.Bar(
            x=[row['Sector']],
            y=[row['% Cumplimiento']],
            marker_color=color,
            text=f"{row['% Cumplimiento']:.0f}%<br>({row['Cumple']}/{row['Total']})",
            textposition='inside',
            showlegend=False,
            name=row['Sector'],
        ))

    fig.update_layout(
        title="Cumplimiento % por Sector",
        yaxis_title="% Cumplimiento",
        yaxis_range=[0, 100],
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    fig.add_hline(y=70, line_dash="dash", line_color="green",
                  annotation_text="Meta 70%", annotation_position="top left")
    st.plotly_chart(fig, use_container_width=True)

    # Tabla detallada
    st.dataframe(df_sectors, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Section 4: Plan view (perfiles en planta verde/rojo)
# ---------------------------------------------------------------------------

def _render_plan_view(results, config: dict) -> None:
    """Vista en planta con topografía + perfiles coloreados por score.

    Fondo: curvas de nivel de la topografía (espaciado 5m, cota base
           = grid_ref de la barra lateral).
    Líneas: cada perfil como segmento verde (CUMPLE) o rojo (NO CUMPLE).

    Score por banco: berma=60, ángulo=20, altura=20.
    Score por sección = promedio de bench_score.
    Verde si score >= 70, rojo si < 70.
    """
    import numpy as np
    from core.section_cutter import azimuth_to_direction
    from ui.plots import mesh_to_contour_data
    from core.config import VISUALIZATION

    st.subheader("🗺️ Plano de Cumplimiento por Perfil")

    sections = st.session_state.get('sections', [])
    if not sections:
        st.info("No hay secciones disponibles para dibujar el plano.")
        return

    # Calcular score por sección desde los resultados
    section_scores = {}
    section_status = {}
    for r in results:
        sec_name = r.get('section', '')
        if sec_name not in section_scores:
            section_scores[sec_name] = []
        match_type = r.get('type', 'MATCH')
        if match_type == 'MATCH':
            section_scores[sec_name].append(r.get('bench_score', 0))

    for sec_name, scores in section_scores.items():
        avg = sum(scores) / len(scores) if scores else 0
        section_status[sec_name] = {
            'score': round(avg, 1),
            'cumple': avg >= 70,
        }

    fig = go.Figure()

    # ── Fondo: curvas de nivel de la topografía ──
    # Espaciado fijo de 5m, cota base = grid_ref de la barra lateral.
    mesh_topo = st.session_state.get('mesh_topo')
    if mesh_topo is not None:
        xi, yi, _, _, zig = mesh_to_contour_data(mesh_topo, grid_size=300)
        if xi is not None and zig is not None:
            z_min = float(np.nanmin(zig))
            z_max = float(np.nanmax(zig))
            grid_ref = float(config.get('grid_ref', VISUALIZATION.grid_ref))
            contour_interval = 5.0  # metros
            fig.add_trace(go.Contour(
                x=xi, y=yi, z=zig,
                contours=dict(
                    start=grid_ref,
                    end=z_max,
                    size=contour_interval,
                    showlabels=True,
                    labelfont=dict(size=8, color='#5D4037'),
                    coloring='lines',
                ),
                line=dict(color='#8D6E63', width=1.0),
                showscale=False,
                name='Curvas de Nivel',
                hovertemplate='E: %{x:.1f}<br>N: %{y:.1f}<br>Elev: %{z:.1f}m<extra>Topo</extra>',
            ))

    # ── Perfiles: líneas verde/rojo sobre las curvas ──
    for sec in sections:
        name = sec.name
        status = section_status.get(name, {'score': 0, 'cumple': False})
        color = '#2E7D32' if status['cumple'] else '#C62828'
        score = status['score']

        # Calcular endpoints de la sección
        origin = np.asarray(sec.origin)
        direction = azimuth_to_direction(sec.azimuth)
        half_len = sec.length / 2.0
        p1 = origin - direction * half_len
        p2 = origin + direction * half_len

        # Línea del perfil
        fig.add_trace(go.Scatter(
            x=[p1[0], p2[0]],
            y=[p1[1], p2[1]],
            mode='lines+text',
            line=dict(color=color, width=5),
            text=[None, f"{name}<br>{score:.0f}"],
            textposition='top center',
            textfont=dict(size=9, color=color),
            name=f"{name} ({'✅' if status['cumple'] else '❌'} {score:.0f})",
            hovertemplate=(
                f"<b>{name}</b><br>"
                f"Score: {score:.0f}/100<br>"
                f"Estado: {'CUMPLE' if status['cumple'] else 'NO CUMPLE'}<br>"
                f"Azimut: {sec.azimuth:.0f}°<br>"
                f"Sector: {sec.sector or 'N/A'}"
                "<extra></extra>"
            ),
            showlegend=True,
        ))

    # Layout
    fig.update_layout(
        title="Vista en Planta — Topografía + Cumplimiento por Perfil",
        xaxis_title='Este (m)',
        yaxis_title='Norte (m)',
        yaxis=dict(scaleanchor='x', scaleratio=1),
        height=600,
        margin=dict(l=40, r=60, t=50, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5,
            font=dict(size=8),
        ),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Leyenda explicativa
    cols = st.columns(2)
    with cols[0]:
        st.markdown(
            "<div style='background:rgba(46,125,50,0.1); padding:0.8rem; "
            "border-radius:8px; border-left:4px solid #2E7D32;'>"
            "<b>🟢 Verde (≥ 70 pts)</b><br>"
            "<span style='font-size:0.85rem;'>Berma (60) + Ángulo (20) + Altura (20)</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            "<div style='background:rgba(198,40,40,0.1); padding:0.8rem; "
            "border-radius:8px; border-left:4px solid #C62828;'>"
            "<b>🔴 Rojo (&lt; 70 pts)</b><br>"
            "<span style='font-size:0.85rem;'>No cumple con la ponderación mínima</span>"
            "</div>",
            unsafe_allow_html=True,
        )


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
