"""Tab dispatcher for the tronadura module."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.modulo_tronadura.state import get_blast_processed
from ui.modulo_tronadura.three_d import render_three_d_tab
from ui.modulo_tronadura.tabular import render_correlation_tab


def render_tabs_section(df_clean: pd.DataFrame) -> None:
    """Render the two analysis tabs after a file has been processed."""
    if not get_blast_processed():
        return

    tab_3d, tab_corr = st.tabs(["📊 Visualización 3D y Filtros", "🔬 Correlación Geotécnica"])

    with tab_3d:
        render_three_d_tab(df_clean)

    with tab_corr:
        render_correlation_tab(df_clean)
