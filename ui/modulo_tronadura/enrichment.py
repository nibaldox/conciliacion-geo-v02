"""Pure blast-hole enrichment pipeline.

All functions here are independent of Streamlit UI calls. They operate on
bytes / DataFrames and return DataFrames or tuples.
"""
from __future__ import annotations

import io
import logging
from typing import Any

import pandas as pd

from core.calculo_tronadura import procesar_pozos
from core.drill_compliance import compute_drill_compliance
from core.drill_hardness_processor import (
    enrich_blast_with_hardness,
    load_drilling_csv,
)
from core.blast_metrics import enrich_blast_dataframe

logger = logging.getLogger(__name__)


def read_uploaded_bytes(data: bytes, name: str) -> pd.DataFrame:
    """Parse an uploaded file (CSV / Excel) from bytes into a DataFrame."""
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data))
    return pd.read_csv(io.StringIO(data.decode("utf-8")))


def run_process_holes(df: pd.DataFrame, progress=None) -> tuple:
    """Worker that processes blast holes off the main thread.

    Returns the canonical ``(df_clean, x_lines, y_lines, z_lines)`` tuple
    produced by ``core.calculo_tronadura.procesar_pozos``.
    """
    if progress is not None:
        try:
            progress.progress(0.1, text="Calculando trayectorias (toe)…")
        except Exception:
            pass
    result = procesar_pozos(df)
    if progress is not None:
        try:
            progress.progress(0.9, text="Empacando resultados…")
        except Exception:
            pass
    return result


def enrich_processed(
    df_clean: pd.DataFrame,
    hardness_bytes: bytes | None = None,
) -> pd.DataFrame:
    """Apply post-processing enrichment (blast metrics + optional hardness)."""
    df_clean = enrich_blast_dataframe(df_clean)

    if hardness_bytes is not None:
        try:
            hardness_buf = io.BytesIO(hardness_bytes)
            hardness_df_clean = load_drilling_csv(hardness_buf)
            if not hardness_df_clean.empty:
                df_clean = enrich_blast_with_hardness(df_clean, hardness_df_clean)
        except Exception:
            logger.exception("Failed to enrich blast with hardness")

    return df_clean


def load_and_enrich(
    blast_bytes: bytes,
    blast_name: str = "blast.csv",
    hardness_bytes: bytes | None = None,
) -> tuple[pd.DataFrame, Any, Any, Any]:
    """Pure: bytes -> enriched DataFrame plus 3D line arrays.

    Raises any parsing / processing exception to the caller.
    """
    df = read_uploaded_bytes(blast_bytes, blast_name)
    df_clean, x_lines, y_lines, z_lines = run_process_holes(df)
    df_clean = enrich_processed(df_clean, hardness_bytes)
    return df_clean, x_lines, y_lines, z_lines


def compute_drill_compliance_if_design(
    design_df: pd.DataFrame,
    actual_df: pd.DataFrame,
) -> dict:
    """Pure wrapper around ``core.drill_compliance.compute_drill_compliance``.

    The caller must decide whether a design file was provided.
    """
    from core.geom_utils import find_df_column

    malla_col = find_df_column(
        actual_df, ["Nombre_Malla_Original", "malla"], raise_error=False
    )
    return compute_drill_compliance(design_df, actual_df, group_by=malla_col)

