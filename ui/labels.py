"""Single source of truth for UI labels and status colors.

Replaces duplicated display-column dicts (B3) and status-to-CSS
mappings (B4) scattered across ui/tabs/*.py.

See docs/BARRIDO_2026-06-21.md issues B3 and B4.
"""
from __future__ import annotations

from typing import Mapping


# Display-column mapping. Each entry maps a database/comparison field
# name to its Spanish UI label. Tabs that need only a subset pick
# from this dict; adding a new field requires only one place to edit.
# Mutable (not Final) so callers can pass to APIs that mutate.
DISPLAY_COLUMNS: Mapping[str, str] = {
    "sector": "Sector",
    "section": "Sección",
    "bench_num": "Banco",
    "level": "Nivel",
    "height_design": "H. Diseño",
    "height_real": "H. Real",
    "height_dev": "Desv. H",
    "height_status": "Cumpl. H",
    "angle_design": "Á. Diseño",
    "angle_real": "Á. Real",
    "angle_dev": "Desv. Á",
    "angle_status": "Cumpl. Á",
    "berm_design": "B. Diseño",
    "berm_real": "B. Real",
    "berm_min": "B. Mínima",
    "berm_status": "Cumpl. B",
    "spill_width": "B. Derrame",
    "effective_berm": "B. Efectiva",
    "delta_crest": "Δ Cresta",
    "delta_toe": "Δ Pata",
}


# Status → CSS (background, foreground). Used by st.dataframe.style.map.
STATUS_COLORS: dict[str, str] = {
    "CUMPLE": "background-color: #C6EFCE; color: #006100",
    "FUERA DE TOLERANCIA": "background-color: #FFEB9C; color: #9C5700",
    "NO CUMPLE": "background-color: #FFC7CE; color: #9C0006",
    "NO CONSTRUIDO": "background-color: #E0E0E0; color: #555555",
    "EXTRA": "background-color: #E6E6FA; color: #4B0082",
    "FALTA BANCO": "background-color: #E0E0E0; color: #555555",
    "BANCO ADICIONAL": "background-color: #E6E6FA; color: #4B0082",
    "RAMPA OK": "background-color: #C6EFCE; color: #006100",
}


def highlight_status(val: object) -> str:
    """Return the CSS for ``val`` based on STATUS_COLORS, or empty string.

    Safe to call with any value (None, non-string) — returns "" instead
    of raising. Substring matching is used for compound statuses like
    'RAMPA OK' and 'BANCO ADICIONAL' (kept for backward compatibility
    with the previous ad-hoc _highlight_status in ui/tabs/table.py).
    """
    text = str(val) if val is not None else ""
    if not text:
        return ""
    if text in STATUS_COLORS:
        return STATUS_COLORS[text]
    for key, css in STATUS_COLORS.items():
        if key in text:
            return css
    return ""


def select_display_columns(available: list[str]) -> list[str]:
    """Return the subset of DISPLAY_COLUMNS keys present in ``available``,
    preserving the canonical order."""
    return [k for k in DISPLAY_COLUMNS if k in available]


__all__ = [
    "DISPLAY_COLUMNS",
    "STATUS_COLORS",
    "highlight_status",
    "select_display_columns",
]
