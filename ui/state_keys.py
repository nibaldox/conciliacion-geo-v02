"""Centralized streamlit session_state keys.

Replaces magic strings spread across ui/tabs/*.py (B5). Using a
constant catches typos at import time and makes key collisions
visible at code review.

Prefix convention:
- ``AI_V2_*`` — keys created by the AI agent v2 tab
- ``TABLE_FILTER_*`` — keys created by the Tabla Detallada tab
- No prefix — keys shared across the app (comparison results, etc.)

See docs/BARRIDO_2026-06-21.md issue B5.
"""
from __future__ import annotations

from typing import Final


class StateKey:
    """All session_state key strings, in one place."""

    # Shared across the app (no prefix)
    MESH_DESIGN: Final[str] = "mesh_design"
    MESH_TOPO: Final[str] = "mesh_topo"
    BOUNDS_DESIGN: Final[str] = "bounds_design"
    BOUNDS_TOPO: Final[str] = "bounds_topo"
    COMPARISON_RESULTS: Final[str] = "comparison_results"
    BLAST_DATA: Final[str] = "blast_data"
    BLAST_DF_CLEAN: Final[str] = "blast_df_clean"
    SECTIONS: Final[str] = "sections"
    PROFILES_DESIGN: Final[str] = "profiles_design"
    PROFILES_TOPO: Final[str] = "profiles_topo"
    PARAMS_DESIGN: Final[str] = "params_design"
    PARAMS_TOPO: Final[str] = "params_topo"
    PROJECT_NAME: Final[str] = "project_name"
    ACTIVE_SECTION: Final[str] = "active_section"
    PENDING_SECTION_NAMES: Final[str] = "pending_section_names"
    REF_LINE_TRACES: Final[str] = "ref_line_traces"
    STEP: Final[str] = "step"

    # Tabla Detallada filter widgets (Sprint 0 B1)
    TABLE_FILTER_SECTOR: Final[str] = "table_filter_sector"
    TABLE_FILTER_LEVEL: Final[str] = "table_filter_level"
    TABLE_FILTER_SECTION: Final[str] = "table_filter_section"
    TABLE_FILTER_BENCH: Final[str] = "table_filter_bench"
    TABLE_SORT: Final[str] = "table_sort"

    # AI agent v2 settings
    AI_V2_PROVIDER: Final[str] = "ai_v2_provider"
    AI_V2_MODEL: Final[str] = "ai_v2_model"
    AI_V2_TEMPERATURE: Final[str] = "ai_v2_temperature"
    AI_V2_MAX_TOKENS: Final[str] = "ai_v2_max_tokens"
    AI_V2_TIMEOUT: Final[str] = "ai_v2_timeout"
    AI_V2_CACHE: Final[str] = "ai_v2_cache"
    AI_V2_KEY_PREFIX: Final[str] = "ai_v2_key_"  # f"ai_v2_key_{provider.value}"
    AI_V2_KEY_INPUT_PREFIX: Final[str] = "ai_v2_key_input_"  # f"ai_v2_key_input_{provider.value}"
    AI_V2_GENERATE: Final[str] = "ai_v2_generate"
    AI_V2_FULL_REPORT: Final[str] = "ai_v2_full_report"


def ai_v2_key_for(provider_value: str) -> str:
    """Build the per-provider API key session_state key."""
    return f"{StateKey.AI_V2_KEY_PREFIX}{provider_value}"


def ai_v2_key_input_for(provider_value: str) -> str:
    """Build the per-provider API key input widget session_state key."""
    return f"{StateKey.AI_V2_KEY_INPUT_PREFIX}{provider_value}"


__all__ = ["StateKey", "ai_v2_key_for", "ai_v2_key_input_for"]
