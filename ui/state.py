"""ui.state — Centralized session_state initialization and access.

The `_DEFAULTS` block that used to live in app.py is here. Other
modules can call `ui.state.init_defaults()` once at app startup
(or import `get_default` for individual keys) to avoid
sprinkling magic strings and per-module key initialization.
"""
from __future__ import annotations

import streamlit as st

from ui.state_keys import StateKey as K


# Initial values for keys that should always exist in session_state.
# Keys created by feature modules (e.g. AI_V2_*) stay in their owners.
_DEFAULTS: dict[str, object] = {
    # Mesh data (populated by step1_upload.py)
    K.MESH_DESIGN: None,
    K.MESH_TOPO: None,
    K.BOUNDS_DESIGN: None,
    K.BOUNDS_TOPO: None,
    # Section + profile data (populated by step2_sections.py)
    K.SECTIONS: [],
    K.PROFILES_DESIGN: [],
    K.PROFILES_TOPO: [],
    K.PARAMS_DESIGN: [],
    K.PARAMS_TOPO: [],
    # Comparison results (populated by step3_analysis.py)
    K.COMPARISON_RESULTS: [],
    # Workflow step indicator
    K.STEP: 1,
    # Pending section names from upload
    K.PENDING_SECTION_NAMES: set(),
    # Reference line traces (sidebar uploader)
    K.REF_LINE_TRACES: {},
    # Blast holes dataframe (set by ui.modulo_tronadura.upload)
    K.BLAST_DF_CLEAN: None,
}


def init_defaults() -> None:
    """Idempotently populate session_state with default values.

    Safe to call multiple times — only sets keys that don't
    already exist (preserves user state across reruns).
    """
    for key, default in _DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default


def reset_all() -> None:
    """Reset session_state to defaults (used by 'Nueva sesión' button)."""
    for key, default in _DEFAULTS.items():
        st.session_state[key] = default


# Every key holding a result derived from a mesh/section analysis. They are
# invalidated together whenever the surfaces or the section list change so a
# stale profile can never be draped over the current geometry (HIGH: stale
# draped profiles after mesh/section changes).
_ANALYSIS_RESULT_KEYS: tuple[str, ...] = (
    K.PROFILES_DESIGN,
    K.PROFILES_TOPO,
    K.PARAMS_DESIGN,
    K.PARAMS_TOPO,
    K.COMPARISON_RESULTS,
    "processed_sections",
    "reconciled_design",
    "reconciled_topo",
    "area_fill_design",
    "area_fill_topo",
)

# Derived figure caches that must be dropped together with the analysis.
_ANALYSIS_CACHE_KEYS: tuple[str, ...] = (
    "_profile_figs",
)

_MISSING = object()


def invalidate_analysis_results() -> None:
    """Reset every result derived from a mesh/section analysis.

    Call whenever the surfaces change (new upload, surface cleanup) or the
    section list changes (add/clear/recreate) so stale profiles are never
    draped over the current geometry. Keys that already hold a value are
    reset to the default empty list and derived figure caches are emptied;
    surfaces, sections and the workflow step are left untouched.
    """
    for key in _ANALYSIS_RESULT_KEYS:
        if st.session_state.get(key, _MISSING) is not _MISSING:
            st.session_state[key] = []
    for key in _ANALYSIS_CACHE_KEYS:
        st.session_state[key] = {}


__all__ = ["init_defaults", "reset_all", "invalidate_analysis_results"]