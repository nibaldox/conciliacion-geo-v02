"""
Sidebar configuration panel.
Returns a config dict consumed by all UI steps.
"""
import streamlit as st

from core.config import DETECTION, TOLERANCES, VISUALIZATION


def render_sidebar() -> dict:
    """Render the sidebar and return a configuration dictionary."""
    with st.sidebar:
        st.header("⚙️ Configuración")

        # --- IA ---
        st.subheader("🤖 Asistente IA")
        st.caption("Agente IA v2 en reconstrucción. Ver pestaña '🤖 Analista IA' para más info.")

        api_key = ""
        model_name = ""
        base_url = None

        st.divider()

        # --- Tolerancias ---
        st.subheader("📐 Tolerancias")
        tol_h_neg = st.number_input("Altura banco: Tol. (-) m", value=TOLERANCES.bench_height['neg'], step=0.5, key="tol_h_neg")
        tol_h_pos = st.number_input("Altura banco: Tol. (+) m", value=TOLERANCES.bench_height['pos'], step=0.5, key="tol_h_pos")
        tol_a_neg = st.number_input("Ángulo cara: Tol. (-) °", value=TOLERANCES.face_angle['neg'], step=1.0, key="tol_a_neg")
        tol_a_pos = st.number_input("Ángulo cara: Tol. (+) °", value=TOLERANCES.face_angle['pos'], step=1.0, key="tol_a_pos")
        min_berm_width = st.number_input("Berma mínima (m)", value=TOLERANCES.berm_width['min'], step=0.5, key="min_berm")
        tol_ir_neg = st.number_input("Áng. Inter-Rampa: Tol. (-) °", value=TOLERANCES.inter_ramp_angle['neg'], step=1.0, key="tol_ir_neg")
        tol_ir_pos = st.number_input("Áng. Inter-Rampa: Tol. (+) °", value=TOLERANCES.inter_ramp_angle['pos'], step=1.0, key="tol_ir_pos")

        # --- Detección ---
        st.subheader("🔧 Detección de Bancos")
        face_threshold = st.slider("Ángulo mínimo cara (°)", 0, 90, int(DETECTION.face_threshold))
        berm_threshold = st.slider("Ángulo máximo berma (°)", 0, 30, int(DETECTION.berm_threshold))
        resolution = st.slider("Resolución de perfil (m)", 0.1, 2.0, 0.5)

        # --- Visualización ---
        st.subheader("📊 Visualización")
        grid_height = st.number_input(
            "Grilla Vertical (m)", value=VISUALIZATION.grid_height, min_value=1.0, step=1.0,
            help="Define la separación de líneas horizontales en los perfiles")
        grid_ref = st.number_input(
            "Cota Referencia (m)", value=VISUALIZATION.grid_ref, step=1.0,
            help="Altura base para alinear la grilla (ej: pata del banco)")

        # --- Proyecto ---
        st.subheader("📋 Información del Proyecto")
        project_name = st.text_input("Proyecto", "")
        operation = st.text_input("Operación", "")
        phase = st.text_input("Fase / Pit", "")
        author = st.text_input("Elaborado por", "")

    tolerances = {
        'bench_height': {'neg': tol_h_neg, 'pos': tol_h_pos},
        'face_angle': {'neg': tol_a_neg, 'pos': tol_a_pos},
        'berm_width': {'min': min_berm_width},
        'inter_ramp_angle': {'neg': tol_ir_neg, 'pos': tol_ir_pos},
        'overall_angle': {'neg': TOLERANCES.overall_angle['neg'], 'pos': TOLERANCES.overall_angle['pos']},
    }

    return {
        'ai_enabled': False,
        'api_key': api_key,
        'model_name': model_name,
        'base_url': base_url,
        'tolerances': tolerances,
        'tol_h_neg': tol_h_neg,
        'tol_h_pos': tol_h_pos,
        'tol_a_neg': tol_a_neg,
        'tol_a_pos': tol_a_pos,
        'min_berm_width': min_berm_width,
        'face_threshold': face_threshold,
        'berm_threshold': berm_threshold,
        'resolution': resolution,
        'grid_height': grid_height,
        'grid_ref': grid_ref,
        'project_name': project_name,
        'operation': operation,
        'phase': phase,
        'author': author,
    }
