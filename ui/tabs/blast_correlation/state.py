"""Streamlit session_state access for the blast-correlation tab."""

import streamlit as st


def get_blast_df() -> object:
    return st.session_state.get("blast_df_clean")


def get_comparison_results() -> object:
    return st.session_state.get("comparison_results")


def get_sections() -> list:
    return st.session_state.get("sections", [])


def get_mesh_design() -> object:
    return st.session_state.get("mesh_design")


def get_mesh_topo() -> object:
    return st.session_state.get("mesh_topo")


def get_cached_sections_data(full_cache_key: tuple):
    cache = st.session_state.get("blast_corr_sections_cache")
    if cache and cache[0] == full_cache_key:
        return cache[1]
    return None


def set_sections_cache(full_cache_key: tuple, df: object) -> None:
    st.session_state.blast_corr_sections_cache = (full_cache_key, df)


def get_cached_cuts(cut_cache_key: tuple):
    cache = st.session_state.get("blast_corr_cuts_cache")
    if cache and cache[0] == cut_cache_key:
        return cache[1]
    return None


def set_cuts_cache(cut_cache_key: tuple, cuts: dict) -> None:
    st.session_state.blast_corr_cuts_cache = (cut_cache_key, cuts)
