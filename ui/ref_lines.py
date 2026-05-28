"""
Shared reference lines uploader.

Loads multiple CSV files representing blast mesh boundaries (mallas),
crests, toes, etc. Stores traces in st.session_state.ref_line_traces
so any module can access them.
"""
import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_PALETTE = [
    'crimson', 'dodgerblue', 'forestgreen', 'darkorange', 'purple',
    'teal', 'gold', 'deeppink', 'cyan', 'lime',
    'tomato', 'steelblue', 'olive', 'coral', 'orchid',
]


def render_ref_lines_uploader() -> None:
    """Render the multi-file CSV uploader in the sidebar."""
    st.subheader("📐 Líneas de Referencia (Mallas)")

    ref_files = st.file_uploader(
        "Cargar líneas (CSV: X, Y)",
        type=["csv", "txt"],
        accept_multiple_files=True,
        key="ref_lines_multi",
        help="Sube uno o más CSV con columnas X,Y. Cada archivo se grafica "
             "como una línea independiente con color y leyenda propios.",
    )

    if not ref_files:
        st.caption("Sin archivos cargados")
        return

    current_names = {f.name for f in ref_files}
    prev_names = st.session_state.get('_ref_file_names', set())

    if current_names != prev_names:
        st.session_state['_ref_file_names'] = current_names
        _parse_files(ref_files)

    traces = st.session_state.get('ref_line_traces', {})
    if traces:
        st.caption(f"{len(traces)} línea(s) cargada(s)")
        for label, t in traces.items():
            st.caption(f"• {label} — {t['n_points']} pts")


def _parse_files(ref_files) -> None:
    st.session_state.ref_line_traces = {}

    for idx, f in enumerate(ref_files):
        try:
            content = f.read().decode('utf-8')
            f.seek(0)
            df = pd.read_csv(io.StringIO(content), header=None, nrows=50000)
        except Exception as e:
            st.warning(f"Error leyendo {f.name}: {e}")
            continue

        if df.shape[1] < 2:
            st.warning(f"{f.name}: requiere al menos 2 columnas (X, Y)")
            continue

        coords = df.iloc[:, :2].apply(pd.to_numeric, errors='coerce').dropna()
        if coords.empty:
            st.warning(f"{f.name}: sin coordenadas válidas")
            continue

        label = f.name.rsplit('.', 1)[0]
        color = _PALETTE[idx % len(_PALETTE)]

        st.session_state.ref_line_traces[label] = {
            'x': coords.iloc[:, 0].values,
            'y': coords.iloc[:, 1].values,
            'color': color,
            'n_points': len(coords),
        }


def add_ref_lines_2d(fig: go.Figure) -> None:
    """Add 2D reference line traces to an existing Plotly figure."""
    traces = st.session_state.get('ref_line_traces', {})
    for label, t in traces.items():
        fig.add_trace(go.Scatter(
            x=t['x'], y=t['y'],
            mode='lines+markers',
            line=dict(color=t['color'], width=2),
            marker=dict(size=3, color=t['color']),
            name=label,
            hovertemplate=f'{label}<br>E: %{{x:.1f}}<br>N: %{{y:.1f}}<extra></extra>',
        ))


def add_ref_lines_3d(fig: go.Figure, z_value: float = None) -> None:
    """Add 3D reference line traces to an existing Plotly figure.

    If z_value is None, uses the mean Z of each line's bounding box
    estimated from session state or 0.
    """
    traces = st.session_state.get('ref_line_traces', {})
    for label, t in traces.items():
        z = z_value if z_value is not None else 0.0
        n = len(t['x'])
        fig.add_trace(go.Scatter3d(
            x=t['x'], y=t['y'], z=[z] * n,
            mode='lines+markers',
            line=dict(color=t['color'], width=3),
            marker=dict(size=3, color=t['color']),
            name=label,
            hovertemplate=f'{label}<br>E: %{{x:.1f}}<br>N: %{{y:.1f}}<extra></extra>',
        ))
