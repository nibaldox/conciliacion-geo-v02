"""ui.layout — CSS patterns shared across the app.

Centralizes the `.metric-card`, `.status-ok`, etc. classes that
were previously inlined in `app.py`'s st.markdown(...).
"""
from __future__ import annotations

import streamlit as st


def inject_global_css() -> None:
    """Inject the global CSS used across the Conciliación app."""
    st.markdown(
        """
<style>
.main-title { font-size: 2rem; font-weight: bold; color: #2F5496; text-align: center; margin-bottom: 0.5rem; }
.subtitle { font-size: 1.1rem; color: #666; text-align: center; margin-bottom: 1.5rem; }
.metric-card {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    padding: 1rem; border-radius: 10px; text-align: center; margin: 0.5rem 0;
    border-left: 4px solid #2F5496;
}
.status-ok  { background-color: #C6EFCE; color: #006100; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
.status-warn{ background-color: #FFEB9C; color: #9C5700; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
.status-nok { background-color: #FFC7CE; color: #9C0006; padding: 4px 12px; border-radius: 4px; font-weight: bold; }
</style>
""",
        unsafe_allow_html=True,
    )


__all__ = ["inject_global_css"]