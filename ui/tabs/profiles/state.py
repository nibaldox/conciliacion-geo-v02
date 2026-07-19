"""Streamlit-bound control and state helpers for the Profiles tab.

This module is allowed to call Streamlit APIs. It keeps the pure Plotly
builders in sibling modules free of ``st.*``.
"""
import streamlit as st


BLAST_HOLE_DISPLAY_RADIUS_M = 10.0


def get_profile_controls():
    """Render the profile controls and return the selected values.

    Returns a dict with the same keys used by the original tab so the
    orchestrator stays thin.
    """
    ctrl_cols = st.columns(5)

    with ctrl_cols[0]:
        show_reconciled = st.checkbox(
            "Mostrar perfil conciliado",
            value=True, key="show_reconciled",
            help="Muestra la geometría idealizada detectada")

    with ctrl_cols[1]:
        show_areas = st.checkbox(
            "Mostrar Áreas",
            value=True, key="show_areas",
            help="Rellena áreas de sobre-excavación y deuda de material")
        show_spill_areas = st.checkbox(
            "Mostrar Área de Derrame",
            value=False, key="show_spill_areas",
            help="Muestra el área del material de derrame en la base de los bancos")
        show_sector_areas = st.checkbox(
            "🎯 Sectores coloreados por desviación",
            value=False, key="profile_show_sector_areas",
            help="Rellena el área entre diseño y topografía clasificada por sector: rojo=sobre-excavación, amarillo=deuda, verde=cumple.")

    with ctrl_cols[2]:
        show_semaphore = st.checkbox(
            "Semáforo (Cumplimiento)",
            value=False, key="show_semaphore",
            help="Verde=Cumple, Amarillo=Alerta, Rojo=No Cumple")

    with ctrl_cols[3]:
        show_pozos = st.checkbox(
            "Mostrar Pozos de Tronadura",
            value=False, key="show_pozos_profile",
            help="Superpone los pozos de perforación y tronadura")
        blast_tolerance = None
        if show_pozos and st.session_state.get('blast_df_clean') is not None:
            blast_tolerance = st.number_input(
                "Tolerancia pozos (m)",
                value=BLAST_HOLE_DISPLAY_RADIUS_M, min_value=1.0, max_value=50.0, step=1.0,
                key="blast_tol_profile",
                help="Distancia máxima a la línea de sección")

    with ctrl_cols[4]:
        num_cols = st.selectbox(
            "Columnas en pantalla",
            [1, 2, 3],
            index=2,
            key="profile_grid_cols",
            help="Ajusta el número de columnas para optimizar el espacio")

    return {
        "show_reconciled": show_reconciled,
        "show_areas": show_areas,
        "show_spill_areas": show_spill_areas,
        "show_sector_areas": show_sector_areas,
        "show_semaphore": show_semaphore,
        "show_pozos": show_pozos,
        "blast_tolerance": blast_tolerance,
        "num_cols": num_cols,
    }


def get_profile_figure_inputs():
    """Read the session-state values needed by ``build_profile_figure``."""
    return {
        "area_fill_design": st.session_state.get('area_fill_design') or [],
        "params_topo": st.session_state.get('params_topo') or [],
        "comparison_results": st.session_state.get('comparison_results') or [],
        "reconciled_design": st.session_state.get('reconciled_design') or [],
        "reconciled_topo": st.session_state.get('reconciled_topo') or [],
        "blast_df_clean": st.session_state.get('blast_df_clean'),
    }


def get_pozos_cache():
    """Return the caller-owned blast-hole projection cache."""
    return st.session_state.setdefault('proyectar_pozos_cache', {})


def render_face_angle_suggestion(section, i):
    """Render the FS objective face-angle suggestion expander."""
    from core.stability_analysis import suggest_face_angle_for_fs
    with st.expander("🎯 Sugerencia de ángulo de cara (FS objetivo)", expanded=False):
        c1, c2, c3 = st.columns(3)
        fs = c1.slider("Factor de seguridad objetivo", 1.0, 2.5, 1.3, 0.05, key=f"fs_target_{i}")
        rmr = c2.number_input("RMR del macizo (0-100)", 0, 100, 60, key=f"fs_rmr_{i}")
        h = c3.number_input("Altura de banco objetivo (m)", 5, 30, 15, key=f"fs_h_{i}")
        if st.button(f"Calcular ángulo sugerido para {section.name}", key=f"fs_btn_{i}"):
            try:
                angle = suggest_face_angle_for_fs(fs_target=fs, rock_mass_rating=rmr if rmr > 0 else None, bench_height_m=float(h))
                st.success(f"Ángulo de cara máximo sugerido: **{angle:.1f}°** (FS ≥ {fs})")
            except Exception as e:
                st.error(f"No se pudo calcular: {e}")
