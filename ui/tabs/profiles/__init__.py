"""Profiles tab package.

Public entrypoint preserved for ``ui/step4_results.py`` and tests.
A backward-compatible ``_build_profile_figure`` wrapper is also kept so
legacy callers/tests that relied on the function reading
``st.session_state`` internally continue to work.
"""
import streamlit as st

from ui.tabs.profiles.figure import build_profile_figure
from ui.tabs.profiles.tab import render_tab_profiles


def _build_profile_figure(
    i, section, pd_prof, pt_prof,
    show_areas=False, show_spill_areas=False, show_semaphore=False, show_reconciled=False,
    show_pozos=False, blast_tolerance=None, config=None, show_sector_areas=False,
    **kwargs,
):
    """Backward-compatible wrapper that fills session-state inputs."""
    if config is None:
        config = {}
    kwargs.setdefault('area_fill_design', st.session_state.get('area_fill_design') or [])
    kwargs.setdefault('params_topo', st.session_state.get('params_topo') or [])
    kwargs.setdefault('comparison_results', st.session_state.get('comparison_results') or [])
    kwargs.setdefault('reconciled_design', st.session_state.get('reconciled_design') or [])
    kwargs.setdefault('reconciled_topo', st.session_state.get('reconciled_topo') or [])
    kwargs.setdefault('blast_df_clean', st.session_state.get('blast_df_clean'))
    kwargs.setdefault('pozos_cache', st.session_state.setdefault('proyectar_pozos_cache', {}))
    return build_profile_figure(
        i, section, pd_prof, pt_prof,
        show_areas=show_areas,
        show_spill_areas=show_spill_areas,
        show_semaphore=show_semaphore,
        show_reconciled=show_reconciled,
        show_pozos=show_pozos,
        blast_tolerance=blast_tolerance,
        config=config,
        show_sector_areas=show_sector_areas,
        **kwargs,
    )


__all__ = ["render_tab_profiles", "build_profile_figure", "_build_profile_figure"]
