"""
Módulo de Análisis de Tronadura (Drill & Blast).

Streamlit UI for uploading blast-hole reports, processing them via
core.calculo_tronadura, and rendering 3D visualizations with Plotly.
Also overlays reference lines (mallas) loaded from the sidebar uploader.
"""
import io

import plotly.graph_objects as go
import streamlit as st

from core.calculo_tronadura import procesar_pozos
from ui.ref_lines import add_ref_lines_3d


def render_modulo_tronadura() -> None:
    st.header("💥 Análisis de Tronadura — Pozos de Voladura")

    ref_traces = st.session_state.get('ref_line_traces', {})
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

    if uploaded is None:
        if not ref_traces:
            st.info("⏳ Esperando archivo de pozos y/o líneas de referencia para procesar.")
        return

    try:
        df = _read_uploaded(uploaded)
    except Exception as e:
        st.error(f"Error al leer archivo: {e}")
        return

    st.subheader("Vista previa del archivo")
    st.dataframe(df.head(20), use_container_width=True)
    st.caption(f"{len(df)} filas | Columnas: {', '.join(df.columns[:10])}{'...' if len(df.columns) > 10 else ''}")

    if st.button("🚀 Procesar Pozos", type="primary", key="process_blast"):
        with st.spinner("Calculando coordenadas de fondo (toe)..."):
            try:
                df_clean, x_lines, y_lines, z_lines = procesar_pozos(df)
            except KeyError as e:
                st.error(str(e))
                return

        col1, col2, col3 = st.columns(3)
        col1.metric("Pozos procesados", len(df_clean))
        col2.metric(
            "Elevación collar",
            f"{df_clean['Z_collar'].min():.1f} – {df_clean['Z_collar'].max():.1f} m",
        )
        col3.metric(
            "Profundidad promedio",
            f"{df_clean['Len'].mean():.1f} m",
        )

        st.session_state['blast_df_clean'] = df_clean

        _render_3d(df_clean, x_lines, y_lines, z_lines)

        with st.expander("📋 Datos procesados"):
            st.dataframe(df_clean, use_container_width=True)


def _read_uploaded(uploaded) -> "pd.DataFrame":
    import pandas as pd

    name = uploaded.name.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(uploaded.read()))
    content = uploaded.read().decode("utf-8")
    return pd.read_csv(io.StringIO(content))


def _render_3d(df, x_lines, y_lines, z_lines) -> None:
    fig = go.Figure()

    add_ref_lines_3d(fig, z_value=float(df['Z_collar'].max()) + 5)

    fig.add_trace(go.Scatter3d(
        x=x_lines, y=y_lines, z=z_lines,
        mode='lines',
        line=dict(color='gray', width=2),
        name='Trayectorias',
        hoverinfo='skip',
    ))

    color_col = _find_col(df, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'])
    if color_col:
        marker = dict(
            size=4,
            color=df[color_col].values.astype(float),
            colorscale='Inferno',
            showscale=True,
            colorbar=dict(title="kg"),
        )
    else:
        marker = dict(size=4, color='orange')

    fig.add_trace(go.Scatter3d(
        x=df['X'].values,
        y=df['Y'].values,
        z=df['Z_collar'].values,
        mode='markers',
        marker=marker,
        name='Collars',
        hovertemplate='X: %{x:.1f}<br>Y: %{y:.1f}<br>Z: %{z:.1f}<extra>Collar</extra>',
    ))

    fig.update_layout(
        scene=dict(
            aspectmode='data',
            xaxis_title='Este (m)',
            yaxis_title='Norte (m)',
            zaxis_title='Elevación (m)',
        ),
        height=700,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )

    st.plotly_chart(fig, use_container_width=True)


def _find_col(df, candidates: list[str]):
    for c in candidates:
        if c in df.columns:
            return c
    lower_map = {col.lower(): col for col in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None
