"""
Sidebar configuration panel.
Returns a config dict consumed by all UI steps.
"""
import streamlit as st

# Preset tolerance values by mining type
_TOLERANCE_PRESETS = {
    "Personalizado": None,
    "Minería cobre (estándar)": {
        'tol_h_neg': 1.0, 'tol_h_pos': 1.5,
        'tol_a_neg': 5.0, 'tol_a_pos': 5.0,
        'min_berm': 9.0, 'tol_ir_neg': 3.0, 'tol_ir_pos': 2.0,
        'max_berm_width': 50.0, 'design_ramp_grad': 10.0,
        'tol_rg_neg': 0.0, 'tol_rg_pos': 2.0,
    },
    "Minería hierro": {
        'tol_h_neg': 1.5, 'tol_h_pos': 2.0,
        'tol_a_neg': 7.0, 'tol_a_pos': 7.0,
        'min_berm': 7.0, 'tol_ir_neg': 4.0, 'tol_ir_pos': 3.0,
        'max_berm_width': 60.0, 'design_ramp_grad': 8.0,
        'tol_rg_neg': 0.0, 'tol_rg_pos': 2.0,
    },
    "Agregados / Canteras": {
        'tol_h_neg': 0.5, 'tol_h_pos': 1.0,
        'tol_a_neg': 3.0, 'tol_a_pos': 3.0,
        'min_berm': 5.0, 'tol_ir_neg': 2.0, 'tol_ir_pos': 2.0,
        'max_berm_width': 40.0, 'design_ramp_grad': 10.0,
        'tol_rg_neg': 0.0, 'tol_rg_pos': 3.0,
    },
}


def render_sidebar() -> dict:
    """Render the sidebar and return a configuration dictionary."""
    with st.sidebar:
        st.header("⚙️ Configuración")

        # --- IA ---
        st.subheader("🤖 Asistente IA")
        ai_enabled = st.checkbox("Habilitar IA", value=False)

        api_key = ""
        model_name = "gpt-3.5-turbo"
        base_url = None

        if ai_enabled:
            ai_provider = st.selectbox("Proveedor", ["OpenAI", "Local (LM Studio/Ollama)"])
            if ai_provider == "OpenAI":
                api_key = st.text_input("OpenAI API Key", type="password")
                model_name = st.selectbox("Modelo", ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"])
            else:
                base_url = st.text_input("Base URL", value="http://localhost:1234/v1")
                api_key = "lm-studio"
                model_name = st.text_input("Nombre del Modelo", value="local-model")

        st.divider()

        # --- Tolerancias ---
        st.subheader("📐 Tolerancias")

        # Preset selector — applies values to session_state keys before widgets render
        preset_name = st.selectbox(
            "Preset", list(_TOLERANCE_PRESETS.keys()), key="tol_preset_select",
            help="Carga valores típicos por tipo de minería. Selecciona 'Personalizado' para editar manualmente.")
        preset = _TOLERANCE_PRESETS[preset_name]
        prev_preset = st.session_state.get('_last_tol_preset')
        if preset and prev_preset != preset_name:
            for k, v in preset.items():
                st.session_state[k] = v
        st.session_state['_last_tol_preset'] = preset_name

        tol_h_neg = st.number_input("Altura banco: Tol. (-) m", value=1.0, step=0.5, key="tol_h_neg")
        tol_h_pos = st.number_input("Altura banco: Tol. (+) m", value=1.5, step=0.5, key="tol_h_pos")
        tol_a_neg = st.number_input("Ángulo cara: Tol. (-) °", value=5.0, step=1.0, key="tol_a_neg")
        tol_a_pos = st.number_input("Ángulo cara: Tol. (+) °", value=5.0, step=1.0, key="tol_a_pos")
        min_berm_width = st.number_input("Berma mínima (m)", value=6.0, step=0.5, key="min_berm")
        tol_ir_neg = st.number_input("Áng. Inter-Rampa: Tol. (-) °", value=3.0, step=1.0, key="tol_ir_neg")
        tol_ir_pos = st.number_input("Áng. Inter-Rampa: Tol. (+) °", value=2.0, step=1.0, key="tol_ir_pos")

        with st.expander("Gradiente de Rampa"):
            design_ramp_grad = st.number_input(
                "Gradiente diseño (%)", value=10.0, step=0.5, key="design_ramp_grad",
                help="Valor de referencia del diseño (ej: 10%)")
            tol_rg_neg = st.number_input(
                "Tol. (-) %", value=0.0, step=0.5, key="tol_rg_neg",
                help="La rampa no debe ser menos inclinada que el diseño")
            tol_rg_pos = st.number_input(
                "Tol. (+) %", value=2.0, step=0.5, key="tol_rg_pos",
                help="La rampa puede ser hasta X% más inclinada")

        # --- Detección ---
        st.subheader("🔧 Detección de Bancos")
        face_threshold = st.slider("Ángulo mínimo cara (°)", 0, 90, 40, key="cfg_face_threshold")
        berm_threshold = st.slider("Ángulo máximo berma (°)", 0, 10, 5, key="cfg_berm_threshold")
        resolution = st.slider("Resolución de perfil (m)", 0.1, 2.0, 0.5, key="cfg_resolution")
        max_berm_width = st.number_input(
            "Ancho máx. berma (m)", value=50.0, min_value=5.0, step=5.0, key="max_berm_width",
            help="Bermas más anchas se consideran pit floor y se descartan del análisis")

        # --- Visualización ---
        st.subheader("📊 Visualización")
        grid_height = st.number_input(
            "Grilla Vertical (m)", value=15.0, min_value=1.0, step=1.0,
            help="Define la separación de líneas horizontales en los perfiles")
        grid_ref = st.number_input(
            "Cota Referencia (m)", value=0.0, step=1.0,
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
        'overall_angle': {'neg': 2.0, 'pos': 2.0},
        'ramp_gradient': {
            'design': design_ramp_grad,
            'neg': tol_rg_neg,
            'pos': tol_rg_pos,
        },
    }

    return {
        'ai_enabled': ai_enabled,
        'api_key': api_key,
        'model_name': model_name,
        'base_url': base_url,
        'tolerances': tolerances,
        'tol_h_neg': tol_h_neg,
        'tol_h_pos': tol_h_pos,
        'tol_a_neg': tol_a_neg,
        'tol_a_pos': tol_a_pos,
        'min_berm_width': min_berm_width,
        'max_berm_width': max_berm_width,
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
