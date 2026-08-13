"""Tab dispatcher for the tronadura module."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.geometry_contract import GEOMETRY_CONFIGURATION_VERSION
from ui.modulo_tronadura.state import get_blast_processed
from ui.modulo_tronadura.three_d import render_three_d_tab
from ui.modulo_tronadura.tabular import render_correlation_tab
from ui.modulo_tronadura.energy_simulation import render_energy_simulation_section


def render_tabs_section(df_clean: pd.DataFrame) -> None:
    """Render the analysis tabs after a file has been processed."""
    if not get_blast_processed():
        return

    tab_3d, tab_corr, tab_sim = st.tabs(
        [
            "📊 Visualización 3D y Filtros",
            "🔬 Correlación Geotécnica",
            "⚡ Simulador Energía 3D",
        ]
    )

    with tab_3d:
        render_three_d_tab(df_clean)

    with tab_corr:
        render_correlation_tab(df_clean)

    with tab_sim:
        accepted_rows = (
            df_clean.to_dict(orient="records") if df_clean is not None else None
        )
        render_energy_simulation_section(
            accepted_rows=accepted_rows,
            geometry_configuration_version=GEOMETRY_CONFIGURATION_VERSION,
        )
