"""Pure Plotly trace builders for the Profiles tab.

No Streamlit calls. Each helper appends traces to a ``go.Figure`` and
returns nothing.
"""
import numpy as np
import plotly.graph_objects as go

from core.geom_utils import calculate_profile_deviation
from core.profile_compliance import compute_sector_deviations


SECTOR_AREA_COLORS = {
    "overbreak": "rgba(220, 50, 50, 0.45)",
    "underbreak": "rgba(255, 200, 50, 0.45)",
    "compliant": "rgba(80, 200, 120, 0.35)",
    "mixed": "rgba(180, 80, 180, 0.45)",
}

_SECTOR_AREA_HOVERTEMPLATE = (
    "<b>Sector %{customdata[0]}</b><br>"
    "Clase: %{customdata[1]}<br>"
    "Rango: [%{customdata[2]:.1f}, %{customdata[3]:.1f}] m<br>"
    "Δh medio: %{customdata[4]:+.2f} m<br>"
    "Δh máx: %{customdata[5]:+.2f} m<br>"
    "Área sobre: %{customdata[6]:.2f} m²<br>"
    "Área deuda: %{customdata[7]:.2f} m²<br>"
    "<extra></extra>"
)


def add_sector_areas_traces(fig, pd_prof, pt_prof, d_i, z_ref_i, z_eval_i, a_over, a_under):
    try:
        design_d = np.asarray(pd_prof.distances, dtype=float)
        design_e = np.asarray(pd_prof.elevations, dtype=float)
        topo_d = np.asarray(pt_prof.distances, dtype=float)
        topo_e = np.asarray(pt_prof.elevations, dtype=float)
        sectors = compute_sector_deviations(design_d, design_e, topo_d, topo_e)
    except Exception:
        sectors = []

    if not sectors:
        add_area_traces(fig, d_i, z_ref_i, z_eval_i, a_over, a_under)
        return

    do = np.argsort(design_d)
    design_d, design_e = design_d[do], design_e[do]
    to = np.argsort(topo_d)
    topo_d, topo_e = topo_d[to], topo_e[to]

    customdata = np.empty((len(sectors), 8), dtype=object)
    for k, s in enumerate(sectors):
        customdata[k] = [
            s.sector_id, s.classification, s.d_start, s.d_end,
            s.mean_delta_h, s.max_delta_h, s.area_above_m2, s.area_below_m2,
        ]

    for k, s in enumerate(sectors):
        mask = (topo_d >= s.d_start) & (topo_d <= s.d_end)
        if not np.any(mask):
            continue
        d_clip = topo_d[mask]
        e_design_clip = np.interp(d_clip, design_d, design_e)
        e_topo_clip = topo_e[mask]
        trace_customdata = np.tile(customdata[k], (2 * len(d_clip), 1))
        fig.add_trace(go.Scatter(
            x=np.concatenate([d_clip, d_clip[::-1]]),
            y=np.concatenate([e_design_clip, e_topo_clip[::-1]]),
            fill="toself",
            fillcolor=SECTOR_AREA_COLORS.get(s.classification, SECTOR_AREA_COLORS["compliant"]),
            line=dict(width=0),
            hoveron="fills",
            hovertemplate=_SECTOR_AREA_HOVERTEMPLATE,
            customdata=trace_customdata,
            name=f"Sector {s.sector_id} ({s.classification})",
            showlegend=False,
        ))


def add_area_traces(fig, d_i, z_ref_i, z_eval_i, a_over, a_under):
    mask_u = z_eval_i >= z_ref_i
    if np.any(mask_u):
        fig.add_trace(go.Scatter(
            x=np.concatenate([d_i[mask_u], d_i[mask_u][::-1]]),
            y=np.concatenate([z_eval_i[mask_u], z_ref_i[mask_u][::-1]]),
            fill='toself', fillcolor='rgba(0,0,255,0.3)',
            line=dict(width=0), name=f'Deuda ({a_under:.1f} m²)', hoverinfo='skip',
            showlegend=False))

    mask_o = z_eval_i < z_ref_i
    if np.any(mask_o):
        fig.add_trace(go.Scatter(
            x=np.concatenate([d_i[mask_o], d_i[mask_o][::-1]]),
            y=np.concatenate([z_eval_i[mask_o], z_ref_i[mask_o][::-1]]),
            fill='toself', fillcolor='rgba(255,0,0,0.3)',
            line=dict(width=0), name=f'Sobre-exc. ({a_over:.1f} m²)', hoverinfo='skip',
            showlegend=False))


def add_bench_annotations(fig, sec_comps, d_i, z_ref_i, z_eval_i):
    dx = 0.1
    hover_x, hover_y, hover_text, hover_colors, hover_symbols = [], [], [], [], []

    for comp in sec_comps:
        c_type = comp.get('type', 'MATCH')

        if c_type == 'MISSING':
            bd = comp.get('bench_design')
            if bd:
                hover_x.append(bd.crest_distance)
                hover_y.append(bd.crest_elevation)
                hover_text.append(f"<b>Cota {bd.toe_elevation:.0f}</b><br>❌ NO CONSTRUIDO")
                hover_colors.append("red")
                hover_symbols.append("x")
            continue

        if c_type == 'EXTRA':
            bt = comp.get('bench_real')
            if bt:
                hover_x.append(bt.crest_distance)
                hover_y.append(bt.crest_elevation)
                hover_text.append(f"<b>Cota {bt.toe_elevation:.0f}</b><br>⚠️ BANCO ADICIONAL")
                hover_colors.append("orange")
                hover_symbols.append("triangle-up")
            continue

        bd = comp.get('bench_design')
        if not bd:
            continue

        bt = comp.get('bench_real')

        start_dist = bd.toe_distance
        end_dist = bd.crest_distance + bd.berm_width
        idx_start = np.searchsorted(d_i, start_dist)
        idx_end = np.searchsorted(d_i, end_dist)

        if idx_end > idx_start:
            diff_slice = z_eval_i[idx_start:idx_end] - z_ref_i[idx_start:idx_end]
            a_u_b = np.sum(diff_slice[diff_slice > 0]) * dx
            a_o_b = np.sum(np.abs(diff_slice[diff_slice < 0])) * dx

            statuses = [comp.get('height_status'), comp.get('angle_status'), comp.get('berm_status')]
            if "NO CUMPLE" in statuses or "FALTA RAMPA" in statuses:
                b_status, color_s = "❌", "red"
            elif "FUERA DE TOLERANCIA" in statuses or "RAMPA (Desv. Ancho)" in statuses:
                b_status, color_s = "⚠️", "orange"
            else:
                b_status, color_s = "✅", "green"

            d_crest = comp.get('delta_crest')
            d_toe = comp.get('delta_toe')
            txt_crest = f"{d_crest:+.2f}m" if d_crest is not None else "N/A"
            txt_toe = f"{d_toe:+.2f}m" if d_toe is not None else "N/A"
            c_crest = "red" if d_crest and d_crest < -0.5 else "blue" if d_crest and d_crest > 0.5 else "black"
            c_toe = "red" if d_toe and d_toe < -0.5 else "blue" if d_toe and d_toe > 0.5 else "black"

            h_real = bt.bench_height if bt else None
            h_line = f"H.real: {h_real:.2f}m" if h_real is not None else "H.real: N/A"
            face_angle_real = bt.face_angle if bt else None
            face_line = f"Cara: {face_angle_real:.1f}°" if face_angle_real is not None else "Cara: N/A"

            hover_x.append(bd.crest_distance)
            hover_y.append(bd.crest_elevation)
            hover_text.append(
                f"<b>Cota {bd.toe_elevation:.0f}</b> {b_status}<br>"
                f"ΔCr: <span style='color:{c_crest}'>{txt_crest}</span><br>"
                f"ΔPa: <span style='color:{c_toe}'>{txt_toe}</span><br>"
                f"<b>{face_line}</b><br>"
                f"<b>{h_line}</b>")
            hover_colors.append(color_s)
            hover_symbols.append("circle")

    if hover_x:
        fig.add_trace(go.Scatter(
            x=hover_x, y=hover_y, mode='markers', name='Info Bancos',
            marker=dict(color=hover_colors, symbol=hover_symbols, size=10,
                        line=dict(color='black', width=1)),
            text=hover_text, hoverinfo='text',
            hoverlabel=dict(bgcolor="rgba(20, 20, 20, 0.55)", bordercolor="rgba(255,255,255,0.3)",
                             font=dict(color="white"), font_size=13),
            showlegend=False))


def add_semaphore_traces(fig, pd_prof, pt_prof, config):
    devs = calculate_profile_deviation(pd_prof, pt_prof)
    T = config['tolerances']['bench_height']['pos']

    mask_ok = devs <= T
    mask_warn = (devs > T) & (devs <= 1.5 * T)
    mask_nok = devs > 1.5 * T

    fig.add_trace(go.Scatter(
        x=pt_prof.distances, y=pt_prof.elevations,
        mode='lines', name='Topo (Traza)',
        line=dict(color='gray', width=0.5), showlegend=False))

    if np.any(mask_ok):
        fig.add_trace(go.Scatter(
            x=pt_prof.distances[mask_ok], y=pt_prof.elevations[mask_ok],
            mode='markers', name=f'Cumple (<{T}m)',
            marker=dict(color='#006100', size=3),
            showlegend=False))
    if np.any(mask_warn):
        fig.add_trace(go.Scatter(
            x=pt_prof.distances[mask_warn], y=pt_prof.elevations[mask_warn],
            mode='markers', name='Alerta',
            marker=dict(color='#FFD700', size=4),
            showlegend=False))
    if np.any(mask_nok):
        fig.add_trace(go.Scatter(
            x=pt_prof.distances[mask_nok], y=pt_prof.elevations[mask_nok],
            mode='markers', name='No Cumple',
            marker=dict(color='#FF0000', size=4),
            showlegend=False))


def add_reconciled_trace(fig, rd, re, color, label, dash, width=1.5, show_berm_width=False,
                         comparison_results=None, topo_benches=None, showlegend=True):
    if len(rd) > 0:
        fig.add_trace(go.Scatter(
            x=rd, y=re, mode='lines+markers', name=label,
            line=dict(color=color, width=width, dash=dash),
            marker=dict(size=5 if width == 1.5 else 6, symbol='diamond', color=color),
            showlegend=showlegend))
        if show_berm_width and comparison_results is not None and topo_benches is not None:
            add_berm_width_indicators(fig, topo_benches, comparison_results)


def add_berm_width_indicators(fig, benches, comparison_results):
    bt_to_design = {}
    for comp in comparison_results:
        if comp.get('type') == 'MATCH':
            bt = comp.get('bench_real')
            bd = comp.get('bench_design')
            if bt is not None and bd is not None:
                bt_to_design[id(bt)] = bd.bench_number

    for j, bench in enumerate(benches):
        bench_id = id(bench)
        if bench_id not in bt_to_design:
            continue
        design_num = bt_to_design[bench_id]

        berm = bench.berm_width
        if berm <= 0:
            continue

        if j == 0:
            x1 = min(bench.toe_distance, bench.crest_distance)
            if bench.toe_distance > bench.crest_distance:
                berm_e = bench.crest_elevation
                x0 = x1 - berm
            else:
                berm_e = bench.toe_elevation
                x0 = x1 - berm
        else:
            b_prev = benches[j - 1]
            # Usar el toe extendido del banco anterior cuando existe piso
            # local, para que el indicador coincida con la extensión angular
            # que dibuja el perfil conciliado.
            from core.bench_classify import _extended_toe_distance
            prev_toe_ext = _extended_toe_distance(b_prev)
            x0 = max(prev_toe_ext, b_prev.crest_distance)
            x1 = min(bench.toe_distance, bench.crest_distance)

            if b_prev.toe_distance > b_prev.crest_distance:
                berm_e = b_prev.toe_elevation
            else:
                berm_e = b_prev.crest_elevation

        mid_x = (x0 + x1) / 2

        fig.add_annotation(
            x=mid_x, y=berm_e,
            text=f"B{design_num}={berm:.1f}m",
            showarrow=False,
            font=dict(size=12, color="darkorange"),
            xanchor='center', yanchor='bottom',
            align='center',
        )
        fig.add_shape(
            type="line",
            x0=x0, y0=berm_e, x1=x1, y1=berm_e,
            line=dict(color="darkorange", width=1.5, dash="dash"),
        )
