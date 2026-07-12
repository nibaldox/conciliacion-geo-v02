"""Single source of truth for filtering comparison results in the UI.

Replaces two divergent implementations:
- ui.tabs.table._apply_filters (streamlit-coupled, multiselect-driven)
- ui.tabs.ai_report._apply_table_filters (session_state-driven)

Both now delegate here. The function is pure (no streamlit imports)
so it can be unit-tested without mocking.

See docs/BARRIDO_2026-06-21.md issue B1.
"""
from __future__ import annotations

from typing import Iterable


def apply_comparison_filters(
    comparisons: list[dict],
    active_filters: dict[str, list],
) -> list[dict]:
    """Return comparisons matching all active filters.

    Parameters
    ----------
    comparisons
        List of comparison dicts (from core.profile_compliance.compare_design_vs_asbuilt).
    active_filters
        Dict with optional keys 'sector', 'level', 'section', 'bench'.
        Each value is a list of allowed values. Empty / missing lists
        mean 'no filter on this field'.

    Returns
    -------
    list[dict]
        Filtered subset. Each bank passes the filter iff it matches
        every active dimension (intersection, not union).

    Notes
    -----
    Banks with type='EXTRA' (no design) have bench_num=999 by
    convention; they will be filtered out unless bench 999 is
    explicitly selected. Banks with type='MISSING' have no
    bench_real so bench filtering applies to their design number
    if present.
    """
    sel_sectors = _as_list(active_filters.get("sector"))
    sel_levels = _as_list(active_filters.get("level"))
    sel_sections = _as_list(active_filters.get("section"))
    sel_benches = _as_list(active_filters.get("bench"))

    if not any([sel_sectors, sel_levels, sel_sections, sel_benches]):
        return list(comparisons)

    out: list[dict] = []
    for r in comparisons:
        if sel_sectors and r.get("sector") not in sel_sectors:
            continue
        if sel_levels and r.get("level") not in sel_levels:
            continue
        if sel_sections and r.get("section") not in sel_sections:
            continue
        if sel_benches and r.get("bench_num") not in sel_benches:
            continue
        out.append(r)
    return out


def filters_summary(active: dict[str, list]) -> str:
    """Return a human-readable summary of the active filter set."""
    parts: list[str] = []
    if active.get("sector"):
        parts.append(f"sector={','.join(map(str, active['sector']))}")
    if active.get("section"):
        parts.append(f"sección={','.join(map(str, active['section']))}")
    if active.get("level"):
        parts.append(f"cota={','.join(map(str, active['level']))}")
    if active.get("bench"):
        parts.append(f"banco={','.join(map(str, active['bench']))}")
    return "; ".join(parts) if parts else "ninguno"


def _as_list(value) -> list:
    """Coerce an optional iterable into a list (None -> [])."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (set, tuple, Iterable)):
        return list(value)
    return [value]


def collect_active_filters_from_session_state(
    prefix: str = "table_filter",
) -> dict[str, list]:
    """Build the 4-key active-filter dict from the multiselect session_state
    widgets identified by ``prefix``.

    Parameters
    ----------
    prefix
        The session_state key prefix used by the calling tab's filter
        widgets. ``"table_filter"`` (default) is shared by the table,
        export, and AI tabs; ``"dash_filter"`` is used by the dashboard
        tab (independent widget set because Streamlit forbids duplicate
        widget keys across fragments).

    Returns
    -------
    dict
        ``{"sector", "level", "section", "bench"}`` mapped to lists of
        selected values. Empty / missing widgets become empty lists —
        they mean "no filter on this field".

    Notes
    -----
    This is the single source of truth for the filter *logic*: every tab
    delegates here instead of reimplementing the ``.isin()`` loop. The
    filter *state* is per-tab (dashboard keeps its own widget keys so it
    can render inside its own ``@st.fragment`` without colliding with the
    table tab's keys).
    """
    import streamlit as st

    return {
        "sector": list(st.session_state.get(f"{prefix}_sector") or []),
        "level": list(st.session_state.get(f"{prefix}_level") or []),
        "section": list(st.session_state.get(f"{prefix}_section") or []),
        "bench": list(st.session_state.get(f"{prefix}_bench") or []),
    }


__all__ = ["apply_comparison_filters", "filters_summary", "collect_active_filters_from_session_state"]
