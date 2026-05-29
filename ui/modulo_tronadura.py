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
    st.dataframe(df.head(20), width="stretch")
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
                malla_col = find_df_column(df_clean, ['Nombre_Malla_Original'], raise_error=False)
                poligono_col = find_df_column(df_clean, ['holes_polygon'], raise_error=False)
                banco_col = find_df_column(df_clean, ['Banco_Original', 'Nombre_Banco', 'Banco'], raise_error=False)
                fase_col = find_df_column(df_clean, ['Nombre_Fase', 'Fase'], raise_error=False)
                kg_col = find_df_column(df_clean, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'], raise_error=False)

                # Determine dynamic column allocation for filters
                filter_cols = []
                if malla_col:
                    filter_cols.append("malla")
                if poligono_col:
                    filter_cols.append("poligono")
                if banco_col:
                    filter_cols.append("banco")
                if fase_col:
                    filter_cols.append("fase")
                filter_cols.append("len")
                if kg_col:
                    filter_cols.append("kg")

                f_cols = st.columns(len(filter_cols))
                col_idx = 0

                sel_mallas = []
                if malla_col:
                    all_mallas = sorted(df_clean[malla_col].dropna().astype(str).unique().tolist())
                    sel_mallas = f_cols[col_idx].multiselect("Filtrar por Malla (Grid):", all_mallas, default=[])
                    col_idx += 1

                sel_poligonos = []
                if poligono_col:
                    all_poligonos = sorted(df_clean[poligono_col].dropna().astype(str).unique().tolist())
                    sel_poligonos = f_cols[col_idx].multiselect("Filtrar por Polígono:", all_poligonos, default=[])
                    col_idx += 1

                sel_bancos = []
                if banco_col:
                    all_bancos = sorted(df_clean[banco_col].dropna().astype(str).unique().tolist())
                    sel_bancos = f_cols[col_idx].multiselect("Filtrar por Banco:", all_bancos, default=[])
                    col_idx += 1

                sel_fases = []
                if fase_col:
                    all_fases = sorted(df_clean[fase_col].dropna().astype(str).unique().tolist())
                    sel_fases = f_cols[col_idx].multiselect("Filtrar por Fase:", all_fases, default=[])
                    col_idx += 1

                min_len = float(df_clean['Len'].min())
                max_len = float(df_clean['Len'].max())
                if min_len < max_len:
                    sel_len = f_cols[col_idx].slider("Profundidad (m):", min_len, max_len, (min_len, max_len))
                else:
                    sel_len = (min_len, max_len)
                col_idx += 1

                sel_kg = None
                if kg_col:
                    min_kg = float(df_clean[kg_col].fillna(0).min())
                    max_kg = float(df_clean[kg_col].fillna(0).max())
                    if min_kg < max_kg:
                        sel_kg = f_cols[col_idx].slider("Explosivo (Kg):", min_kg, max_kg, (min_kg, max_kg))
                    else:
                        sel_kg = (min_kg, max_kg)

            # Apply filters
            df_filtered = df_clean.copy()
            if sel_mallas and malla_col:
                df_filtered = df_filtered[df_filtered[malla_col].astype(str).isin(sel_mallas)]
            if sel_poligonos and poligono_col:
                df_filtered = df_filtered[df_filtered[poligono_col].astype(str).isin(sel_poligonos)]
            if sel_bancos and banco_col:
                df_filtered = df_filtered[df_filtered[banco_col].astype(str).isin(sel_bancos)]
            if sel_fases and fase_col:
                df_filtered = df_filtered[df_filtered[fase_col].astype(str).isin(sel_fases)]
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

                # Custom 3D coloring and options expander
                with st.expander("🎨 Opciones de Visualización 3D", expanded=True):
                    col_v1, col_v2, col_v3 = st.columns(3)

                    color_options = []
                    if kg_col:
                        color_options.append("Carga Explosiva (Kg)")
                    if malla_col:
                        color_options.append("Mallas de Tronadura (Grid)")
                    if poligono_col:
                        color_options.append("Polígonos Tronados")
                    if fase_col:
                        color_options.append("Fase")
                    if banco_col:
                        color_options.append("Banco")
                    color_options.extend(["Profundidad (m)", "Inclinación (°)", "Elevación Collar (m)"])

                    color_by = col_v1.selectbox(
                        "Colorear pozos en 3D por:",
                        color_options,
                        index=0
                    )

                    # Expanded continuous colorscale selector
                    all_colorscales = [
                        "Inferno", "Hot", "Viridis", "Plasma", "Magma", "Cividis",
                        "Rainbow", "Jet", "Earth", "YlOrRd", "RdBu", "Spectral",
                        "Coolwarm", "Electric", "Bluered", "Greens", "Reds", "Blues"
                    ]
                    colorscale_disabled = (color_by in ["Mallas de Tronadura (Grid)", "Polígonos Tronados", "Fase", "Banco"])
                    sel_colorscale = col_v2.selectbox(
                        "Paleta de Colores (Continuos):",
                        all_colorscales,
                        index=0,
                        disabled=colorscale_disabled
                    )

                    show_energy_grid = col_v3.checkbox("⚡ Mostrar Densidad de Energía 3D (IDW)", value=False)

                    show_design_mesh = False
                    show_topo_mesh = False
                    has_d_mesh = st.session_state.get('mesh_design') is not None
                    has_t_mesh = st.session_state.get('mesh_topo') is not None

                    if has_d_mesh or has_t_mesh:
                        st.markdown("**Superficies 3D de Referencia:**")
                        col_m1, col_m2 = st.columns(2)
                        if has_d_mesh:
                            show_design_mesh = col_m1.checkbox("🔵 Mostrar Superficie de Diseño (Transparente)", value=False)
                        if has_t_mesh:
                            show_topo_mesh = col_m2.checkbox("🟢 Mostrar Topografía Real (As-Built Transparente)", value=False)

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

                _render_3d(
                    df_filtered, filt_x, filt_y, filt_z, color_by,
                    show_energy_grid, sel_colorscale,
                    show_design_mesh, show_topo_mesh
                )

                with st.expander("📋 Datos procesados (Filtrados)", expanded=False):
                    st.dataframe(df_filtered, width="stretch")

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
            fig_pas.add_vline(x=0.0, line_dash="solid", line_color="red", annotation_text="Nivel Piso (0.0m)")
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
                                sec.origin,
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
                            st.dataframe(df_corr, width="stretch")

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


def _render_3d(df, x_lines, y_lines, z_lines, color_by: str, show_energy_grid: bool = False, sel_colorscale: str = "Inferno", show_design_mesh: bool = False, show_topo_mesh: bool = False) -> None:
    fig = go.Figure()

    add_ref_lines_3d(fig, z_value=float(df['Z_collar'].max()) + 5)

    malla_col = find_df_column(df, ['Nombre_Malla_Original'], raise_error=False)
    poligono_col = find_df_column(df, ['holes_polygon'], raise_error=False)
    fase_col = find_df_column(df, ['Nombre_Fase', 'Fase'], raise_error=False)
    banco_col = find_df_column(df, ['Banco_Original', 'Nombre_Banco', 'Banco'], raise_error=False)

    # 1. Overlay 3D Meshes transparently if requested
    if show_design_mesh:
        md = st.session_state.get('decimated_mesh_design')
        if md is None and st.session_state.get('mesh_design') is not None:
            from core import decimate_mesh
            md = decimate_mesh(st.session_state.mesh_design, 30000)
            st.session_state.decimated_mesh_design = md
        if md is not None:
            from core import mesh_to_plotly
            fig.add_trace(mesh_to_plotly(md, "Superficie Diseño", "royalblue", 0.35))

    if show_topo_mesh:
        mt = st.session_state.get('decimated_mesh_topo')
        if mt is None and st.session_state.get('mesh_topo') is not None:
            from core import decimate_mesh
            mt = decimate_mesh(st.session_state.mesh_topo, 30000)
            st.session_state.decimated_mesh_topo = mt
        if mt is not None:
            from core import mesh_to_plotly
            fig.add_trace(mesh_to_plotly(mt, "Topografía Real", "forestgreen", 0.35))

    # 2. Render blast holes
    if color_by == "Mallas de Tronadura (Grid)" and malla_col:
        # --- Discrete Categorical Coloring by Malla (Grid) ---
        unique_vals = sorted(df[malla_col].dropna().astype(str).unique().tolist())
        _plot_discrete_traces(fig, df, malla_col, unique_vals, "Malla")
    elif color_by == "Polígonos Tronados" and poligono_col:
        # --- Discrete Categorical Coloring by Blasted Polygon ---
        unique_vals = sorted(df[poligono_col].dropna().astype(str).unique().tolist())
        _plot_discrete_traces(fig, df, poligono_col, unique_vals, "Polígono")
    elif color_by == "Fase" and fase_col:
        # --- Discrete Categorical Coloring by Fase ---
        unique_vals = sorted(df[fase_col].dropna().astype(str).unique().tolist())
        _plot_discrete_traces(fig, df, fase_col, unique_vals, "Fase")
    elif color_by == "Banco" and banco_col:
        # --- Discrete Categorical Coloring by Banco ---
        unique_vals = sorted(df[banco_col].dropna().astype(str).unique().tolist())
        _plot_discrete_traces(fig, df, banco_col, unique_vals, "Banco")
    else:
        # --- Continuous Parametric Coloring ---
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
            title = "kg"
        elif color_by == "Profundidad (m)":
            colors = df['Len'].values
            title = "m (Largo)"
        elif color_by == "Inclinación (°)":
            colors = df['Incl'].values
            title = "Grados (°)"
        else:  # Elevación Collar
            colors = df['Z_collar'].values
            title = "Collar Z"

        marker = dict(
            size=4,
            color=colors,
            colorscale=sel_colorscale,
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
        kg_col = find_df_column(df, ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'], raise_error=False)
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


def _plot_discrete_traces(fig: go.Figure, df, category_col: str, unique_vals: list[str], label_prefix: str) -> None:
    color_cycle = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52']
    import numpy as np

    for idx, val_name in enumerate(unique_vals):
        df_sub = df[df[category_col].astype(str) == val_name]
        color = color_cycle[idx % len(color_cycle)]

        # Reconstruct lines for just this subset
        n_s = len(df_sub)
        m_x = np.empty(n_s * 3, dtype=object)
        m_y = np.empty(n_s * 3, dtype=object)
        m_z = np.empty(n_s * 3, dtype=object)

        xc = df_sub['X'].values
        yc = df_sub['Y'].values
        zc = df_sub['Z_collar'].values
        xt = df_sub['X_toe'].values
        yt = df_sub['Y_toe'].values
        zt = df_sub['Z_toe'].values

        for i in range(n_s):
            j = i * 3
            m_x[j] = xc[i]
            m_x[j + 1] = xt[i]
            m_x[j + 2] = None
            m_y[j] = yc[i]
            m_y[j + 1] = yt[i]
            m_y[j + 2] = None
            m_z[j] = zc[i]
            m_z[j + 1] = zt[i]
            m_z[j + 2] = None

        # Add trajectories
        fig.add_trace(go.Scatter3d(
            x=m_x, y=m_y, z=m_z,
            mode='lines',
            line=dict(color=color, width=2),
            name=f"Trayectorias {val_name}",
            hoverinfo='skip',
            showlegend=False,
        ))

        # Add collars
        fig.add_trace(go.Scatter3d(
            x=df_sub['X'].values,
            y=df_sub['Y'].values,
            z=df_sub['Z_collar'].values,
            mode='markers',
            marker=dict(size=4, color=color),
            name=f"{label_prefix}: {val_name}",
            hovertemplate=f"{label_prefix}: {val_name}<br>X: %{{x:.1f}}<br>Y: %{{y:.1f}}<br>Z: %{{z:.1f}}<extra></extra>",
        ))



