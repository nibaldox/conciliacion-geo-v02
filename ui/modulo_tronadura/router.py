"""Módulo de Análisis de Tronadura (Drill & Blast) — router.

The actual logic lives in ``ui/modulo_tronadura/`` (package). This file
only dispatches to sub-sections.
"""
from __future__ import annotations

import streamlit as st

from ui.modulo_tronadura.sections import render_tabs_section
from ui.modulo_tronadura.state import get_blast_df
from ui.modulo_tronadura.upload import render_upload_section


def render_modulo_tronadura() -> None:
    """Render the drill & blast analysis module."""
    st.header("💥 Análisis de Tronadura — Pozos de Voladura")
    render_upload_section()

    df_clean = get_blast_df()
    if df_clean is not None:
        render_tabs_section(df_clean)
