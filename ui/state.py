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


__all__ = ["init_defaults", "reset_all"]