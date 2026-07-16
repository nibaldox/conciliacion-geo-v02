"""Session-state helpers for step 2."""
from typing import List

import streamlit as st

from core.section_cutter import SectionLine


def ensure_sections_list() -> None:
    """Ensure st.session_state.sections is a list."""
    if not st.session_state.get('sections'):
        st.session_state.sections = []


def get_sections() -> List[SectionLine]:
    """Return the current section list."""
    return st.session_state.get('sections', [])


def get_pending_names() -> set:
    """Return the set of pending section names."""
    return st.session_state.get('pending_section_names', set())


def add_sections(new_sections: List[SectionLine]) -> List[SectionLine]:
    """Append new sections to session state, suffixing names on collision."""
    ensure_sections_list()
    existing_names = {s.name for s in st.session_state.sections}
    added: List[SectionLine] = []
    for sec in new_sections:
        target_name = sec.name
        if target_name in existing_names:
            col_idx = 1
            while f"{target_name}_{col_idx}" in existing_names:
                col_idx += 1
            sec.name = f"{target_name}_{col_idx}"
        st.session_state.sections.append(sec)
        existing_names.add(sec.name)
        st.session_state.pending_section_names.add(sec.name)
        added.append(sec)
    return added


def clear_pending_sections() -> None:
    """Remove pending sections and clear the pending set."""
    st.session_state.sections = [
        s for s in st.session_state.sections
        if s.name not in st.session_state.pending_section_names
    ]
    st.session_state.pending_section_names.clear()


def clear_all_sections() -> None:
    """Remove all sections and clear the pending set."""
    st.session_state.sections = []
    st.session_state.pending_section_names.clear()


def advance_step() -> None:
    """Advance the wizard step to at least 3."""
    st.session_state.step = max(st.session_state.step, 3)


def invalidate_profile_cache() -> None:
    """Evict the cached profile figures."""
    st.session_state.pop('_profile_figs', None)


def append_interactive_section(section: SectionLine) -> None:
    """Append a single interactive section and mark it pending."""
    st.session_state.sections.append(section)
    st.session_state.pending_section_names.add(section.name)
    invalidate_profile_cache()


def clear_pending_names() -> None:
    """Clear the pending names set."""
    st.session_state.pending_section_names.clear()
