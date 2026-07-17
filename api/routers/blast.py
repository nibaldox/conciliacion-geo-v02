"""Blast-hole upload router.

Endpoints:
    POST /blast/upload              Accept a blast-hole CSV, process it, and
                                    persist per-hole charge/hardness data.
    GET  /blast/{session_id}/holes  Return persisted blast holes for a session.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

import api.database as db
import api.schemas as schemas
from core.blast_metrics import enrich_blast_dataframe
from core.calculo_tronadura import procesar_pozos
from core.column_utils import KILOS_CANDIDATES, first_present_column

logger = logging.getLogger(__name__)


def _run_in_executor(func, *args):
    """Schedule a CPU/IO-bound callable on the default executor.

    Keeps handlers ``async def`` while still letting pandas / trimesh /
    file-IO work run off the event-loop thread.
    """
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, func, *args)

router = APIRouter(prefix="/blast", tags=["blast"])

_LENGTH_CANDIDATES = ("Len", "longitud_real", "Longitud", "Length", "Profundidad")
_TACO_CANDIDATES = ("Taco_m", "Taco", "Stemming")


def _read_uploaded_csv(file: UploadFile) -> pd.DataFrame:
    """Read an uploaded CSV file into a DataFrame.

    Raises :class:`HTTPException` (400) when the file cannot be parsed or is
    empty.
    """
    try:
        content = file.file.read()
    except Exception as exc:
        raise HTTPException(400, f"Could not read uploaded file: {exc}")

    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    try:
        df = pd.read_csv(io.StringIO(content), engine="python", on_bad_lines="warn")
    except Exception as exc:
        raise HTTPException(400, f"Invalid CSV: {exc}")

    if df.empty:
        raise HTTPException(400, "CSV file is empty")

    return df


def _process_blast_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Run the canonical blast-hole processing pipeline.

    Applies :func:`core.calculo_tronadura.procesar_pozos` to resolve collar/toe
    coordinates and then :func:`core.blast_metrics.enrich_blast_dataframe` for
    charge-derived metrics.

    Raises :class:`HTTPException` (400) on processing failure.
    """
    try:
        df_clean, _x_lines, _y_lines, _z_lines = procesar_pozos(df)
    except KeyError as exc:
        raise HTTPException(400, f"Missing required blast-hole column: {exc}")
    except Exception as exc:
        raise HTTPException(400, f"Failed to process blast holes: {exc}")

    try:
        df_clean = enrich_blast_dataframe(df_clean)
    except Exception as exc:
        logger.warning("Blast enrichment failed: %s", exc)

    if df_clean is None or df_clean.empty:
        raise HTTPException(400, "No valid blast holes found in CSV")

    return df_clean


def _resolve_carga_column(df: pd.DataFrame) -> Optional[str]:
    """Return the column that holds kg of explosive per metre, if any."""
    if "kg_per_meter" in df.columns:
        return "kg_per_meter"
    return None


def _resolve_descarga_column(df: pd.DataFrame) -> Optional[str]:
    """Return the column that holds charge column length, if any."""
    if "altura_carga_m" in df.columns:
        return "altura_carga_m"
    return None


def _compute_carga_series(df: pd.DataFrame) -> pd.Series:
    """Compute kg/m per hole, returning a Series of floats (NaN when unknown)."""
    col = _resolve_carga_column(df)
    if col is not None:
        return pd.to_numeric(df[col], errors="coerce")

    kg_col = first_present_column(df, KILOS_CANDIDATES)
    len_col = first_present_column(df, _LENGTH_CANDIDATES)
    if kg_col is None or len_col is None:
        return pd.Series([np.nan] * len(df), index=df.index, dtype=float)

    kilos = pd.to_numeric(df[kg_col], errors="coerce")
    length = pd.to_numeric(df[len_col], errors="coerce")
    out = pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    valid = kilos.notna() & length.notna() & (length > 0)
    out.loc[valid] = kilos.loc[valid] / length.loc[valid]
    return out


def _compute_descarga_series(df: pd.DataFrame) -> pd.Series:
    """Compute charge column length per hole, returning NaN when unknown."""
    col = _resolve_descarga_column(df)
    if col is not None:
        return pd.to_numeric(df[col], errors="coerce")

    len_col = first_present_column(df, _LENGTH_CANDIDATES)
    taco_col = first_present_column(df, _TACO_CANDIDATES)
    if len_col is None or taco_col is None:
        return pd.Series([np.nan] * len(df), index=df.index, dtype=float)

    length = pd.to_numeric(df[len_col], errors="coerce")
    taco = pd.to_numeric(df[taco_col], errors="coerce")
    out = length - taco
    return out.clip(lower=0.0)


def _safe_mean(series: pd.Series) -> float:
    """Return the finite mean of ``series`` or ``0.0``."""
    cleaned = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    value = float(cleaned.mean()) if not cleaned.empty else 0.0
    return value if math.isfinite(value) else 0.0


def _hardness_distribution(df: pd.DataFrame) -> Dict[str, int]:
    """Count hardness categories from the ``dureza`` column."""
    distribution: Dict[str, int] = {}
    if "dureza" not in df.columns:
        return distribution
    for value in df["dureza"].dropna().astype(str):
        distribution[value] = distribution.get(value, 0) + 1
    return distribution


def _hole_id_for_row(row: pd.Series, index: int, df: pd.DataFrame) -> str:
    """Extract or synthesise a hole identifier for a row."""
    for candidate in ("pozo", "hole_id", "id_pozo", "Hole_ID"):
        if candidate in df.columns:
            value = row.get(candidate)
            if value is not None and str(value) != "nan":
                return str(value)
    return str(index)


def _df_to_hole_records(df: pd.DataFrame) -> List[Dict[str, object]]:
    """Convert a processed blast DataFrame to plain dicts for persistence.

    Records retain the uppercase column names produced by ``procesar_pozos``
    (``X``, ``Y``, ``Z_collar`` …) so existing endpoints that read from the
    ``blast_holes`` settings key continue to work.
    """
    carga_series = _compute_carga_series(df)
    descarga_series = _compute_descarga_series(df)

    records: List[Dict[str, object]] = []
    for idx, row in df.iterrows():
        record: Dict[str, object] = {}
        for col in df.columns:
            value = row[col]
            if isinstance(value, (np.integer, np.floating)):
                value = value.item()
            record[col] = value

        record["hole_id"] = _hole_id_for_row(row, idx, df)
        record["carga"] = float(carga_series.loc[idx]) if pd.notna(carga_series.loc[idx]) else 0.0
        record["descarga"] = float(descarga_series.loc[idx]) if pd.notna(descarga_series.loc[idx]) else 0.0
        records.append(record)

    return records


def _record_to_summary(record: Dict[str, object]) -> schemas.BlastHoleSummary:
    """Map a persisted record to the public ``BlastHoleSummary`` schema."""
    def _float_or_zero(key: str) -> float:
        value = record.get(key)
        if value is None:
            return 0.0
        try:
            number = float(value)
            return number if math.isfinite(number) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _str_or_none(key: str) -> Optional[str]:
        value = record.get(key)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return str(value)

    hardness = _str_or_none("dureza")
    bench = _str_or_none("Banco_Original")

    x = _float_or_zero("X")
    y = _float_or_zero("Y")
    z = _float_or_zero("Z_collar")
    carga = _float_or_zero("carga")
    descarga = _float_or_zero("descarga")
    length = _float_or_zero("Len")
    inclination = _float_or_zero("Incl")
    azimuth = _float_or_zero("Az")

    hole_id = _str_or_none("hole_id") or str(int(record.get("index", 0)))

    return schemas.BlastHoleSummary(
        hole_id=hole_id,
        x=x,
        y=y,
        z=z,
        carga=carga,
        descarga=descarga,
        hardness=hardness,
        bench=bench,
        length=length,
        inclination=inclination,
        azimuth=azimuth,
    )


def _build_upload_payload(
    file_bytes: bytes,
) -> dict:
    """Run the full blast-upload pipeline off the event-loop thread.

    Returns a plain dict with everything the async handler still needs:

    - ``df_clean``: processed DataFrame (used to derive mean / distribution).
    - ``n_rows_input``: length of the raw parsed CSV.
    - ``records``: hole dicts ready for ``db.save_blast_upload``.
    - ``carga_mean``, ``descarga_mean``: scalar metrics.
    - ``hardness_distribution``: ``Dict[str, int]``.
    """
    if isinstance(file_bytes, bytes):
        content = file_bytes.decode("utf-8", errors="replace")
    else:
        content = file_bytes

    try:
        df = pd.read_csv(io.StringIO(content), engine="python", on_bad_lines="warn")
    except Exception as exc:
        raise HTTPException(400, f"Invalid CSV: {exc}")

    if df.empty:
        raise HTTPException(400, "CSV file is empty")

    n_rows_input = len(df)

    try:
        df_clean, _x_lines, _y_lines, _z_lines = procesar_pozos(df)
    except KeyError as exc:
        raise HTTPException(400, f"Missing required blast-hole column: {exc}")
    except Exception as exc:
        raise HTTPException(400, f"Failed to process blast holes: {exc}")

    try:
        df_clean = enrich_blast_dataframe(df_clean)
    except Exception as exc:
        logger.warning("Blast enrichment failed: %s", exc)

    if df_clean is None or df_clean.empty:
        raise HTTPException(400, "No valid blast holes found in CSV")

    n_holes = len(df_clean)
    n_rows_skipped = max(0, n_rows_input - n_holes)

    carga_series = _compute_carga_series(df_clean)
    descarga_series = _compute_descarga_series(df_clean)
    carga_mean = _safe_mean(carga_series)
    descarga_mean = _safe_mean(descarga_series)
    hardness_dist = _hardness_distribution(df_clean)
    records = _df_to_hole_records(df_clean)

    return {
        "n_holes": n_holes,
        "n_rows_loaded": n_holes,
        "n_rows_skipped": n_rows_skipped,
        "carga_mean": round(carga_mean, 3),
        "descarga_mean": round(descarga_mean, 3),
        "hardness_distribution": hardness_dist,
        "records": records,
    }


# ---------------------------------------------------------------------------
# POST /blast/upload
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_blast_csv(
    file: UploadFile = File(..., description="Blast-hole CSV (CSV/Excel-style columns)"),
    session_id: str = Form(..., description="Session UUID"),
) -> schemas.BlastUploadResponse:
    """Accept a blast-hole CSV, parse it, compute charge metrics, and persist.

    The CSV is processed with :func:`core.calculo_tronadura.procesar_pozos` and
    enriched with :func:`core.blast_metrics.enrich_blast_dataframe`, exactly as
    the Streamlit reference does. The resulting hole records are stored under
    the session's ``blast_holes`` settings key so existing blast endpoints can
    consume them.

    CPU/IO work (pandas parsing + procesar_pozos + enrichment + metrics) runs
    on the default executor so the event-loop stays responsive.
    """
    if not session_id.strip():
        raise HTTPException(422, "session_id is required")

    db.get_or_create_session(session_id)

    try:
        content = file.file.read()
    except Exception as exc:
        raise HTTPException(400, f"Could not read uploaded file: {exc}")

    payload = await _run_in_executor(_build_upload_payload, content)

    db.save_blast_upload(
        session_id,
        {
            "holes": payload["records"],
            "n_holes": payload["n_holes"],
            "n_rows_loaded": payload["n_rows_loaded"],
            "n_rows_skipped": payload["n_rows_skipped"],
        },
    )

    return schemas.BlastUploadResponse(
        session_id=session_id,
        n_holes=payload["n_holes"],
        n_rows_loaded=payload["n_rows_loaded"],
        n_rows_skipped=payload["n_rows_skipped"],
        carga_mean=payload["carga_mean"],
        descarga_mean=payload["descarga_mean"],
        hardness_distribution=payload["hardness_distribution"],
    )


def _build_hole_summaries(records: List[Dict[str, object]]) -> List[schemas.BlastHoleSummary]:
    """Map a list of persisted records to ``BlastHoleSummary`` schemas (sync)."""
    return [_record_to_summary(record) for record in records]


# ---------------------------------------------------------------------------
# GET /blast/{session_id}/holes
# ---------------------------------------------------------------------------


@router.get("/{session_id}/holes")
async def get_blast_holes(
    session_id: str,
    section_name: Optional[str] = None,
) -> schemas.BlastHolesResponse:
    """Return persisted blast holes for the session.

    ``section_name`` is reserved for future filtering; it currently does not
    narrow the result set because the persisted store contains global 3D hole
    data rather than per-section projections.
    """
    _ = section_name  # reserved for future section-scoped filtering

    settings = db.get_settings(session_id) or {}
    raw = settings.get("blast_holes", [])
    if not isinstance(raw, list):
        return schemas.BlastHolesResponse(session_id=session_id, holes=[])

    holes = await _run_in_executor(_build_hole_summaries, raw)
    return schemas.BlastHolesResponse(session_id=session_id, holes=holes)
