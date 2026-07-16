"""Streamlit widgets for step 2."""
from typing import Tuple

import numpy as np
import streamlit as st

from ui.step2_sections.cutting import compute_manual_azimuth


def file_config_inputs() -> Tuple[float, float, float, str, str]:
    """Inputs for the file-based section tab."""
    cols = st.columns(5)
    spacing = cols[0].number_input(
        "Distancia entre perfiles (m)", value=20.0, min_value=1.0, step=5.0, key="spacing_file")
    len_up = cols[1].number_input(
        "Long. Arriba (m)", value=100.0, min_value=5.0, key="len_up_file")
    len_down = cols[2].number_input(
        "Long. Abajo (m)", value=100.0, min_value=5.0, key="len_down_file")
    sector = cols[3].text_input("Sector", "Principal", key="sector_file")
    az_mode = cols[4].selectbox(
        "Azimut",
        ["Perpendicular a la línea (Recomendado)", "Auto (pendiente local - Ruidoso)"],
        key="az_mode_file")
    return spacing, len_up, len_down, sector, az_mode


def interactive_config_inputs() -> Tuple[float, float, str, str, float]:
    """Inputs for the interactive click-on-plan tab."""
    cols_cfg = st.columns(4)
    len_up = cols_cfg[0].number_input(
        "Long. Arriba (m)", value=100.0, min_value=5.0, key="len_up_int")
    len_down = cols_cfg[1].number_input(
        "Long. Abajo (m)", value=100.0, min_value=5.0, key="len_down_int")
    sector = cols_cfg[2].text_input("Sector", "Principal", key="sector_int")
    az_mode = cols_cfg[3].selectbox(
        "Azimut", ["Auto (pendiente local)", "Manual"], key="az_mode_int")
    manual_az = 0.0
    if az_mode == "Manual":
        manual_az = st.number_input(
            "Azimut manual (°)", 0.0, 360.0, 0.0, key="man_az_int")
    return len_up, len_down, sector, az_mode, manual_az


def manual_top_inputs() -> Tuple[int, bool]:
    """Top-level inputs for the manual section tab."""
    cols_top = st.columns(2)
    n_sections = cols_top[0].number_input(
        "Número de secciones a definir", min_value=1, max_value=50, value=5)
    auto_az_manual = cols_top[1].checkbox(
        "Auto-detectar azimut desde diseño", value=False, key="auto_az_manual")
    return int(n_sections), auto_az_manual


def manual_section_inputs(
    i: int,
    cx: float,
    cy: float,
    auto_az_manual: bool,
    mesh_design,
) -> Tuple[str, str, float, float, float, float, float]:
    """Per-section inputs for the manual tab."""
    with st.expander(f"Sección S-{i+1:02d}", expanded=(i == 0)):
        cols = st.columns(5)
        name = cols[0].text_input("Nombre", f"S-{i+1:02d}", key=f"sname_{i}")
        sector = cols[1].text_input("Sector", "", key=f"ssector_{i}")

        cols2 = st.columns(5)
        ox = cols2[0].number_input(
            "Origen X", value=float(cx), format="%.1f", key=f"sox_{i}")
        oy = cols2[1].number_input(
            "Origen Y", value=float(cy), format="%.1f", key=f"soy_{i}")

        az = compute_manual_azimuth(mesh_design, ox, oy, auto_az_manual)
        if auto_az_manual:
            cols2[2].text_input(
                "Azimut (°)", value=f"{az:.1f}", disabled=True, key=f"saz_{i}")
        else:
            az = cols2[2].number_input(
                "Azimut (°)", value=0.0, min_value=0.0,
                max_value=360.0, key=f"saz_{i}")

        len_up = cols2[3].number_input(
            "Long. Arriba (m)", value=100.0, min_value=5.0, key=f"slen_up_{i}")
        len_down = cols2[4].number_input(
            "Long. Abajo (m)", value=100.0, min_value=5.0, key=f"slen_down_{i}")

    return name, sector, ox, oy, float(az), len_up, len_down


def auto_config_inputs(bounds_design) -> Tuple[float, float, float, float, int, float, float, str, str, float]:
    """Inputs for the automatic section generation tab."""
    cols = st.columns(4)
    x1 = cols[0].number_input(
        "Punto inicio X", value=float(bounds_design['xmin']), format="%.1f")
    y1 = cols[1].number_input(
        "Punto inicio Y", value=float(bounds_design['center'][1]), format="%.1f")
    x2 = cols[2].number_input(
        "Punto fin X", value=float(bounds_design['xmax']), format="%.1f")
    y2 = cols[3].number_input(
        "Punto fin Y", value=float(bounds_design['center'][1]), format="%.1f")

    cols2 = st.columns(4)
    n_auto = cols2[0].number_input(
        "N° de secciones", min_value=2, max_value=50, value=5)
    len_up_auto = cols2[1].number_input(
        "Long. Arriba (m)", value=100.0, min_value=5.0)
    len_down_auto = cols2[2].number_input(
        "Long. Abajo (m)", value=100.0, min_value=5.0)
    sector_auto = cols2[3].text_input(
        "Sector", "Sector Principal", key="sector_auto_txt")

    az_method = st.radio(
        "Método de Azimut",
        ["Perpendicular a la línea (Recomendado)", "Fijo", "Auto (pendiente local - Ruidoso)"],
        index=0, horizontal=True)

    fixed_az = 0.0
    if az_method == "Fijo":
        fixed_az = st.number_input(
            "Azimut fijo (°)", value=0.0, min_value=0.0, max_value=360.0)

    return x1, y1, x2, y2, int(n_auto), len_up_auto, len_down_auto, sector_auto, az_method, fixed_az


def interactive_apply_buttons() -> Tuple[bool, bool]:
    """Apply / Clear buttons for the interactive tab."""
    cols_btn = st.columns(2)
    apply_clicked = cols_btn[0].button(
        "✅ Aplicar Secciones", type="primary", key="apply_int")
    clear_clicked = cols_btn[1].button(
        "🗑️ Limpiar", key="clear_int")
    return apply_clicked, clear_clicked


def file_apply_button() -> bool:
    """Apply button for the file tab."""
    return st.button(
        "✅ Aplicar Secciones desde Archivo", type="primary", key="apply_file")


def manual_apply_button() -> bool:
    """Apply button for the manual tab."""
    return st.button("✅ Aplicar Secciones Manuales", type="primary")


def auto_generate_button() -> bool:
    """Generate button for the automatic tab."""
    return st.button("🔄 Generar Secciones Automáticas", type="primary")


def table_action_buttons(col_pending, col_all) -> Tuple[bool, bool]:
    """Render clear-pending / clear-all buttons inside the supplied columns."""
    with col_pending:
        clear_pending = st.button(
            "🗑️ Limpiar Pendientes", key="clear_pending_btn", type="secondary")
    with col_all:
        clear_all = st.button(
            "🗑️ Limpiar Todas", key="clear_all_sections_btn", type="secondary")
    return clear_pending, clear_all
