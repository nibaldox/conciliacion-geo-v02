"""Shared cache for unique filter values derived from comparison_results."""
import streamlit as st


def _ensure_filter_values() -> dict:
    """Compute unique sectors/levels/sections/benches once and stash in session state.

    Invalidated whenever the comparison_results object identity changes.
    """
    comparison_results = st.session_state.get('comparison_results') or []
    results_id = id(comparison_results) if comparison_results else None

    cached = st.session_state.get('_filter_values')
    if cached and cached.get('results_id') == results_id:
        return cached

    sectors = sorted({r.get('sector') for r in comparison_results if r.get('sector') is not None})
    sections = sorted({r.get('section') for r in comparison_results if r.get('section') is not None})
    benches = sorted(
        {r.get('bench_num') for r in comparison_results if r.get('bench_num') is not None},
        key=lambda x: (x is None, x if isinstance(x, (int, float)) else str(x)))
    unique_levels = {r.get('level') for r in comparison_results if r.get('level') is not None}
    levels = sorted(
        unique_levels,
        key=lambda x: (float(x) if str(x).replace('.', '', 1).isdigit() else -9999, x),
        reverse=True)

    payload = {
        'results_id': results_id,
        'sectors': sectors,
        'levels': levels,
        'sections': sections,
        'benches': benches,
    }
    st.session_state['_filter_values'] = payload
    return payload
