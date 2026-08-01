"""Regression tests for the tronadura module session-state handling.

Covers the bug where ``reset_blast_processed_state`` wiped the cached
file name, making the new-file guard in ``upload.py`` re-trigger on every
Streamlit rerun — clearing the confirmed column mapping and showing
"Confirma el mapeo" instead of processing.
"""
import streamlit as st

from ui.modulo_tronadura.state import (
    get_blast_cached_name,
    get_blast_df,
    get_blast_processed,
    reset_blast_processed_state,
    set_blast_cached_name,
    set_blast_df,
    set_blast_processed,
)


def test_reset_keeps_cached_name():
    set_blast_cached_name("pozos.xlsx")
    set_blast_processed(True)
    set_blast_df(object())

    reset_blast_processed_state()

    assert get_blast_cached_name() == "pozos.xlsx"
    assert get_blast_processed() is False
    assert get_blast_df() is None


def test_rerun_guard_does_not_clear_confirmed_mapping():
    from ui.modulo_tronadura.column_mapper import (
        _STATE_KEY_CONFIRMED,
        get_confirmed_mapping,
    )

    uploaded_name = "enaex_pozos_tronadura_2026.xlsx"

    # First rerun: new file detected -> name set, state reset, mapping cleared.
    if get_blast_cached_name() != uploaded_name:
        set_blast_cached_name(uploaded_name)
        reset_blast_processed_state()
        st.session_state[_STATE_KEY_CONFIRMED.format(prefix="blast")] = None

    # User confirms the column mapping (as render_column_mapper does).
    st.session_state[_STATE_KEY_CONFIRMED.format(prefix="blast")] = {
        "X": "Latitud_Geo",
        "Y": "Longitud_Geo",
        "Tipo_Explosivo": "Nombre",
    }

    # Second rerun (e.g. the click on "Procesar Pozos"): the cached name
    # matches, so the reset block must NOT run again and the confirmed
    # mapping must survive.
    if get_blast_cached_name() != uploaded_name:
        reset_blast_processed_state()
        st.session_state[_STATE_KEY_CONFIRMED.format(prefix="blast")] = None

    assert get_confirmed_mapping("blast") == {
        "X": "Latitud_Geo",
        "Y": "Longitud_Geo",
        "Tipo_Explosivo": "Nombre",
    }
