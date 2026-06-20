"""Shared helpers for resolving blast-hole columns across vendor naming variants.

ENAEX / Vulcan exports rename the same physical quantity (kg of explosive
loaded, hole length, ...) under several column headers. Several core
modules need to locate those columns; the kilogram column in particular
was hardcoded inline in three places (blast_metrics, blast_correlation,
excel_writer). Centralised here so the candidate list and the
first-match lookup live in one place.
"""
from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd


KILOS_CANDIDATES = ("Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg")


def first_present_column(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """Return the first column name from ``candidates`` present in ``df``.

    Case-sensitive, never raises. Returns ``None`` when no candidate is
    found. Shared by the blast-metrics and blast-correlation modules,
    which previously each carried a private copy of this lookup.
    """
    for c in candidates:
        if c in df.columns:
            return c
    return None


def kilos_column(df: pd.DataFrame) -> Optional[str]:
    """Locate the kilograms-of-explosive column via :data:`KILOS_CANDIDATES`."""
    return first_present_column(df, KILOS_CANDIDATES)
