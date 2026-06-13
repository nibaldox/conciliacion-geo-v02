"""
Step 4: Results viewer — routes to the five result tabs.
"""
import streamlit as st

from ui.tabs.profiles import render_tab_profiles
from ui.tabs.table import render_tab_table
from ui.tabs.dashboard import render_tab_dashboard
from ui.tabs.ai_report import render_tab_ai
from ui.tabs.export import render_tab_export
from ui.tabs.blast_correlation import render_tab_blast_correlation


@st.fragment
def _profiles_tab(config: dict) -> None:
    render_tab_profiles(config)


@st.fragment
def _table_tab() -> None:
    render_tab_table()


@st.fragment
def _dashboard_tab(config: dict) -> None:
    render_tab_dashboard(config)


@st.fragment
def _blast_tab(config: dict) -> None:
    render_tab_blast_correlation(config)


@st.fragment
def _ai_tab(config: dict) -> None:
    render_tab_ai(config)


@st.fragment
def _export_tab(config: dict) -> None:
    render_tab_export(config)


def render_step4(config: dict) -> None:
    st.header("📊 Paso 4: Resultados")

    tab_profiles, tab_table, tab_dash, tab_corr, tab_ai, tab_export = st.tabs([
        "📈 Perfiles", "📋 Tabla Detallada", "📊 Dashboard",
        "💥 Correlación Voladura", "🤖 Analista IA", "💾 Exportar"])

    with tab_profiles:
        _profiles_tab(config)
    with tab_table:
        _table_tab()
    with tab_dash:
        _dashboard_tab(config)
    with tab_corr:
        _blast_tab(config)
    with tab_ai:
        _ai_tab(config)
    with tab_export:
        _export_tab(config)
