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
from core.geom_utils import find_df_column
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

    # Clear processed state if file changes
    if 'blast_cached_name' not in st.session_state or st.session_state['blast_cached_name'] != uploaded.name:
        st.session_state['blast_cached_name'] = uploaded.name
        st.session_state['blast_df_clean'] = None
        st.session_state['blast_x_lines'] = None
        st.session_state['blast_y_lines'] = None
        st.session_state['blast_z_lines'] = None
        st.session_state['blast_processed'] = False

    if st.button("🚀 Procesar Pozos", type="primary", key="process_blast"):
        with st.spinner("Calculando coordenadas de fondo (toe)..."):
            try:
                df_clean, x_lines, y_lines, z_lines = procesar_pozos(df)
                st.session_state['blast_df_clean'] = df_clean
                st.session_state['blast_x_lines'] = x_lines
                st.session_state['blast_y_lines'] = y_lines
                st.session_state['blast_z_lines'] = z_lines
                st.session_state['blast_processed'] = True
            except KeyError as e:
                st.error(str(e))
                st.session_state['blast_processed'] = False

    if st.session_state.get('blast_processed', False):
        df_clean = st.session_state['blast_df_clean']

        tab_3d, tab_corr = st.tabs(["📊 Visualización 3D y Filtros", "🔬 Correlación Geotécnica"])

        with tab_3d:
            # --- Filtering Panel ---
            with st.expander("🔎 Filtros de Tronadura", expanded=False):
                f_cols = st.columns(4)

                malla_col = find_df_column(df_clean, ['holes_polygon', 'Nombre_Malla_Original'], raise_error=False)
                if malla_col:
                    all_mallas = sorted(df_clean[malla_col].dropna().unique().tolist())
                    sel_mallas = f_cols[0].multiselect("Filtrar por Malla:", all_mallas, default=[])
                else:
                    sel_mallas = []

                banco_col = find_df_column(df_clean, ['Nombre_Banco', 'Banco'], raise_error=False)
                if banco_col:
                    all_bancos = sorted(df_clean[banco_col].dropna().unique().tolist())
                    sel_bancos = f_cols[1].multiselect("Filtrar por Banco:", all_bancos, default=[])
                else:
                    sel_bancos = []

                min_len = float(df_clean['Len'].min())
                max_len = float(df_clean['Len'].max())
                if min_len < max_len:
                    sel_len = f_cols[2].slider("Profundidad (m):", min_len, max_len, (min_len, max_len))
                else:
                    sel_len = (min_len, max_len)

                kg_col = find_df_column(df_clean, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'], raise_error=False)
                if kg_col:
                    min_kg = float(df_clean[kg_col].fillna(0).min())
                    max_kg = float(df_clean[kg_col].fillna(0).max())
                    if min_kg < max_kg:
                        sel_kg = f_cols[3].slider("Explosivo (Kg):", min_kg, max_kg, (min_kg, max_kg))
                    else:
                        sel_kg = (min_kg, max_kg)
                else:
                    sel_kg = None

            # Apply filters
            df_filtered = df_clean.copy()
            if sel_mallas and malla_col:
                df_filtered = df_filtered[df_filtered[malla_col].isin(sel_mallas)]
            if sel_bancos and banco_col:
                df_filtered = df_filtered[df_filtered[banco_col].isin(sel_bancos)]
            if sel_len:
                df_filtered = df_filtered[(df_filtered['Len'] >= sel_len[0]) & (df_filtered['Len'] <= sel_len[1])]
            if sel_kg and kg_col:
                df_filtered = df_filtered[(df_filtered[kg_col].fillna(0) >= sel_kg[0]) & (df_filtered[kg_col].fillna(0) <= sel_kg[1])]

            if df_filtered.empty:
                st.warning("⚠️ No hay pozos que coincidan con los filtros seleccionados.")
            else:
                # Dynamic rendering metrics
                col1, col2, col3 = st.columns(3)
                col1.metric("Pozos filtrados", len(df_filtered), f"{len(df_filtered) - len(df_clean)} respecto al total")
                col2.metric(
                    "Elevación collar",
                    f"{df_filtered['Z_collar'].min():.1f} – {df_filtered['Z_collar'].max():.1f} m",
                )
                col3.metric(
                    "Profundidad promedio",
                    f"{df_filtered['Len'].mean():.1f} m",
                )

                # Custom 3D coloring option
                col_c1, col_c2 = st.columns(2)
                color_by = col_c1.selectbox(
                    "Colorear pozos en 3D por:",
                    ["Carga Explosiva (Kg)"] if kg_col else [] + ["Profundidad (m)", "Inclinación (°)", "Elevación Collar (m)"],
                    index=0
                )
                show_energy_grid = col_c2.checkbox("Mostrar Densidad de Energía 3D (Modelo de Daño)", value=False)

                # Reconstruct x_lines, y_lines, z_lines dynamically for filtered set
                import numpy as np
                n_filtered = len(df_filtered)
                filt_x = np.empty(n_filtered * 3, dtype=object)
                filt_y = np.empty(n_filtered * 3, dtype=object)
                filt_z = np.empty(n_filtered * 3, dtype=object)

                xc = df_filtered['X'].values
                yc = df_filtered['Y'].values
                zc = df_filtered['Z_collar'].values
                xt = df_filtered['X_toe'].values
                yt = df_filtered['Y_toe'].values
                zt = df_filtered['Z_toe'].values

                for i in range(n_filtered):
                    j = i * 3
                    filt_x[j] = xc[i]
                    filt_x[j + 1] = xt[i]
                    filt_x[j + 2] = None
                    filt_y[j] = yc[i]
                    filt_y[j + 1] = yt[i]
                    filt_y[j + 2] = None
                    filt_z[j] = zc[i]
                    filt_z[j + 1] = zt[i]
                    filt_z[j + 2] = None

                _render_3d(df_filtered, filt_x, filt_y, filt_z, color_by, show_energy_grid)

                with st.expander("📋 Datos procesados (Filtrados)", expanded=False):
                    st.dataframe(df_filtered, use_container_width=True)

        with tab_corr:
            df_filtered = df_clean.copy() # Base for correlation
            st.subheader("🔬 Análisis de Pasadura (Sub-drilling)")
            st.markdown("""
            La **pasadura** es la profundidad que el pozo se perfora por debajo de la pata teórica del banco diseñado.
            Un rango óptimo típico en minería a cielo abierto es de **0.5 a 1.5 metros** para asegurar que el piso se rompa bien sin dejar lomos.
            """)

            # Calculate Pasadura
            # target floor elevation is collar_elevation - BENCH_HEIGHT (15.0m)
            df_filtered['Pasadura'] = (df_filtered['Z_collar'] - 15.0) - df_filtered['Z_toe']

            p_mean = df_filtered['Pasadura'].mean()
            p_optimal = ((df_filtered['Pasadura'] >= 0.5) & (df_filtered['Pasadura'] <= 1.5)).sum()
            p_pct = p_optimal / len(df_filtered) * 100 if len(df_filtered) > 0 else 0

            col_p1, col_p2 = st.columns(2)
            col_p1.metric("Pasadura Promedio", f"{p_mean:.2f} m")
            col_p2.metric("Pozos en Rango Óptimo (0.5m - 1.5m)", f"{p_pct:.1f}%", f"{p_optimal}/{len(df_filtered)} pozos")

            import numpy as np
            fig_pas = go.Figure(go.Histogram(
                x=df_filtered['Pasadura'].values,
                nbinsx=20,
                marker_color='mediumpurple',
                opacity=0.75,
                name='Pasadura real'
            ))
            fig_pas.add_vline(x=0.5, line_dash="dash", line_color="green", annotation_text="Óptimo Mín (0.5m)")
            fig_pas.add_vline(x=1.5, line_dash="dash", line_color="green", annotation_text="Óptimo Máx (1.5m)")
            fig_pas.add_vline(x=0.0, line_solid="solid", line_color="red", annotation_text="Nivel Piso (0.0m)")
            fig_pas.update_layout(
                title="Distribución de Pasaduras (m)",
                xaxis_title="Pasadura (m)",
                yaxis_title="Cantidad de Pozos",
                height=350,
                margin=dict(l=40, r=20, t=40, b=40)
            )
            st.plotly_chart(fig_pas, use_container_width=True)

            st.markdown("---")
            st.subheader("💥 Correlación Geotécnica: Daño vs Explosivos")
            st.markdown("""
            Analiza si las secciones con mayor sobre-excavación (*overbreak*) coinciden espacialmente con mayor concentración de explosivos en las inmediaciones de esa sección.
            """)

            comparison = st.session_state.get('comparison_results', [])
            sections = st.session_state.get('sections', [])

            if not comparison or not sections:
                st.info("💡 Realiza la Conciliación Geotécnica primero (Paso 3 y Paso 4) para correlacionar el daño de los taludes con los explosivos.")
            else:
                from core.calculo_tronadura import proyectar_pozos_en_seccion
                kg_col = find_df_column(df_filtered, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'], raise_error=False)

                if not kg_col:
                    st.warning("⚠️ No se encontró columna de Kg de explosivos (`Kilos_Cargados_real`, etc.) para cruzar la energía.")
                else:
                    import pandas as pd
                    df_comp = pd.DataFrame(comparison)

                    dev_col = None
                    for col_name in ['delta_crest', 'height_dev', 'angle_dev']:
                        if col_name in df_comp.columns:
                            dev_col = col_name
                            break

                    if dev_col is None:
                        st.warning("⚠️ No se encontraron columnas de desviación (`delta_crest`, etc.) en la conciliación.")
                    else:
                        df_comp['abs_dev'] = df_comp[dev_col].abs()
                        sec_grouped = df_comp.groupby('section')['abs_dev'].mean().reset_index()

                        corr_data = []
                        for sec in sections:
                            sec_name = sec.name
                            match = sec_grouped[sec_grouped['section'] == sec_name]
                            if match.empty:
                                continue
                            avg_dev = match['abs_dev'].values[0]

                            # Project wells with tolerance=15m
                            proj_wells = proyectar_pozos_en_seccion(
                                df_filtered,
                                sec.start,
                                sec.azimuth,
                                sec.length,
                                tolerance=15.0
                            )

                            if not proj_wells.empty:
                                total_kg = proj_wells[kg_col].fillna(0).sum()
                                num_wells = len(proj_wells)
                            else:
                                total_kg = 0
                                num_wells = 0

                            corr_data.append({
                                'Sección': sec_name,
                                'Kg_Explosivo': total_kg,
                                'Pozos_Cercanos': num_wells,
                                'Desviacion_Media_m': avg_dev
                            })

                        df_corr = pd.DataFrame(corr_data)

                        if df_corr.empty or df_corr['Kg_Explosivo'].sum() == 0:
                            st.info("💡 No hay suficientes pozos con carga explosiva cercanos a las secciones para realizar la correlación.")
                        else:
                            st.dataframe(df_corr, use_container_width=True)

                            # Plot Scatter with Trendline
                            fig_scat = go.Figure()
                            fig_scat.add_trace(go.Scatter(
                                x=df_corr['Kg_Explosivo'].values,
                                y=df_corr['Desviacion_Media_m'].values,
                                mode='markers+text',
                                text=df_corr['Sección'].values,
                                textposition="top center",
                                marker=dict(size=10, color='crimson', symbol='circle'),
                                name='Secciones'
                            ))

                            xs = df_corr['Kg_Explosivo'].values.astype(float)
                            ys = df_corr['Desviacion_Media_m'].values.astype(float)
                            if len(xs) > 1 and np.var(xs) > 0:
                                m, b = np.polyfit(xs, ys, 1)
                                trend_x = np.array([xs.min(), xs.max()])
                                trend_y = m * trend_x + b
                                fig_scat.add_trace(go.Scatter(
                                    x=trend_x, y=trend_y,
                                    mode='lines',
                                    line=dict(color='darkblue', dash='dash'),
                                    name=f'Tendencia (m={m:.4f})'
                                ))

                            fig_scat.update_layout(
                                title=f"Correlación: Kg Explosivos (r=15m) vs Desviación Absoluta Media ({dev_col})",
                                xaxis_title="Carga Explosiva Acumulada (Kg)",
                                yaxis_title="Desviación Absoluta Media (m)",
                                height=450,
                                margin=dict(l=40, r=20, t=40, b=40)
                            )
                            st.plotly_chart(fig_scat, use_container_width=True)

                            r_coef = np.corrcoef(xs, ys)[0, 1] if len(xs) > 1 and np.var(xs) > 0 and np.var(ys) > 0 else 0
                            if r_coef > 0.5:
                                st.success(f"📈 **Correlación Fuerte Positiva (r = {r_coef:.2f})**: Los datos indican que las secciones con mayor carga explosiva acumulada experimentan un daño/desviación significativamente mayor en el talud final.")
                            elif r_coef < -0.5:
                                st.info(f"📉 **Correlación Negativa (r = {r_coef:.2f})**")
                            else:
                                st.info(f"⚖️ **Correlación Moderada o Débil (r = {r_coef:.2f})**: El daño geomecánico no parece estar fuertemente ligado de forma directa a la carga explosiva puntual de esta vecindad.")


def _read_uploaded(uploaded) -> "pd.DataFrame":
    import pandas as pd

    name = uploaded.name.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(uploaded.read()))
    content = uploaded.read().decode("utf-8")
    return pd.read_csv(io.StringIO(content))


def _render_3d(df, x_lines, y_lines, z_lines, color_by: str, show_energy_grid: bool = False) -> None:
    fig = go.Figure()

    add_ref_lines_3d(fig, z_value=float(df['Z_collar'].max()) + 5)

    fig.add_trace(go.Scatter3d(
        x=x_lines, y=y_lines, z=z_lines,
        mode='lines',
        line=dict(color='rgba(150,150,150,0.5)', width=2),
        name='Trayectorias',
        hoverinfo='skip',
    ))

    # Determine colors and scales based on choice
    kg_col = find_df_column(df, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'], raise_error=False)

    if color_by == "Carga Explosiva (Kg)" and kg_col:
        colors = df[kg_col].values.astype(float)
        colorscale = 'Hot'
        title = "kg"
    elif color_by == "Profundidad (m)":
        colors = df['Len'].values
        colorscale = 'Viridis'
        title = "m (Largo)"
    elif color_by == "Inclinación (°)":
        colors = df['Incl'].values
        colorscale = 'Portland'
        title = "Grados (°)"
    else:  # Elevación Collar
        colors = df['Z_collar'].values
        colorscale = 'Plasma'
        title = "Collar Z"

    marker = dict(
        size=4,
        color=colors,
        colorscale=colorscale,
        showscale=True,
        colorbar=dict(title=title, x=1.0, len=0.6),
    )

    fig.add_trace(go.Scatter3d(
        x=df['X'].values,
        y=df['Y'].values,
        z=df['Z_collar'].values,
        mode='markers',
        marker=marker,
        name='Collars',
        hovertemplate='X: %{x:.1f}<br>Y: %{y:.1f}<br>Z: %{z:.1f}<extra>Collar</extra>',
    ))

    # --- Volumetric Energy Density Grid (IDW 3D) ---
    if show_energy_grid:
        import numpy as np
        # 1. Bounding box
        x_min, x_max = float(df['X'].min()), float(df['X'].max())
        y_min, y_max = float(df['Y'].min()), float(df['Y'].max())
        z_min, z_max = float(df['Z_toe'].min()), float(df['Z_collar'].max())

        # 2. Build 3D mesh grid (10x10x4 = 400 points for real-time calculation)
        xs = np.linspace(x_min, x_max, 10)
        ys = np.linspace(y_min, y_max, 10)
        zs = np.linspace(z_min, z_max, 4)
        grid_x, grid_y, grid_z = np.meshgrid(xs, ys, zs)
        points = np.vstack([grid_x.ravel(), grid_y.ravel(), grid_z.ravel()]).T

        # 3. Vectorized IDW calculations
        C = df[['X', 'Y', 'Z_collar']].values.astype(float)
        T = df[['X_toe', 'Y_toe', 'Z_toe']].values.astype(float)
        V = T - C
        V_len_sq = np.sum(V**2, axis=1)
        V_len_sq[V_len_sq == 0] = 1e-6
        Q = df[kg_col].fillna(0).values if kg_col else np.ones(len(df))

        energies = []
        for gp in points:
            W = gp - C
            t = np.sum(W * V, axis=1) / V_len_sq
            t_c = np.clip(t, 0.0, 1.0)
            closest = C + t_c[:, np.newaxis] * V
            d_sq = np.sum((gp - closest)**2, axis=1)
            d_sq[d_sq < 1e-4] = 1e-4
            energy = np.sum(Q / d_sq)
            energies.append(energy)

        # 4. Draw transparent volumetric scatter trace
        fig.add_trace(go.Scatter3d(
            x=points[:, 0], y=points[:, 1], z=points[:, 2],
            mode='markers',
            marker=dict(
                size=7,
                color=energies,
                colorscale='YlOrRd',
                opacity=0.3,
                showscale=False,
            ),
            name='Densidad Energía',
            hoverinfo='skip',
            showlegend=True,
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



