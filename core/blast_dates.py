"""Explicit blast-date normalization for uploaded blast-hole files.

Pure helpers: no I/O, no framework dependencies. The API invokes these only
when the caller declares a date source column and an explicit date format.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

import pandas as pd

DATE_FORMATS: tuple[str, ...] = ("ISO", "DMY", "MDY")
DATE_STATUS_VALID = "VALID"
DATE_STATUS_MISSING = "MISSING"
DATE_STATUS_INVALID = "INVALID"

_ISO_PATTERN = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?"
    r"(Z|[+-]\d{2}(?::\d{2}|\d{2}))?)?$"
)
_SLASH_PATTERN = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value)) if not isinstance(value, (str, bytes)) else False
    except (TypeError, ValueError):
        return False


def _original_text(value: Any) -> str:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    return str(value)


def _as_iso(value: date) -> str:
    return value.isoformat()


def _valid_offset(offset: str | None) -> bool:
    if offset is None or offset == "Z":
        return True
    digits = offset[1:].replace(":", "")
    return int(digits[:2]) <= 23 and int(digits[2:4]) <= 59


def _parse_iso_text(text: str) -> date | None:
    match = _ISO_PATTERN.match(text)
    if match is None:
        return None
    year, month, day, hour, minute, second, offset = match.groups()
    if hour is not None and not (int(hour) <= 23 and int(minute) <= 59 and (second is None or int(second) <= 59)):
        return None
    if not _valid_offset(offset):
        return None
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _parse_slash_text(text: str, fmt: str) -> date | None:
    match = _SLASH_PATTERN.match(text)
    if match is None:
        return None
    first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    day, month = (first, second) if fmt == "DMY" else (second, first)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def normalize_blast_date(value: Any, date_format: str) -> tuple[str | None, str | None, str]:
    """Return ``(iso_date_or_None, original_text_or_None, status)``.

    ``status`` is one of VALID / MISSING / INVALID. Native datetime objects
    carry no ambiguity and are accepted for every format. Numbers are never
    interpreted as Excel serials. Ambiguous text requires ``date_format``.
    """
    if date_format not in DATE_FORMATS:
        raise ValueError(f"date_format must be one of {DATE_FORMATS}")
    if _is_missing(value):
        return None, None, DATE_STATUS_MISSING
    original = _original_text(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        parsed = value.date() if isinstance(value, (datetime, pd.Timestamp)) else value
        return _as_iso(parsed), original, DATE_STATUS_VALID
    if not isinstance(value, str):
        return None, original, DATE_STATUS_INVALID
    text = value.strip()
    parsed = _parse_iso_text(text) if date_format == "ISO" else _parse_slash_text(text, date_format)
    if parsed is None:
        return None, original, DATE_STATUS_INVALID
    return _as_iso(parsed), original, DATE_STATUS_VALID


def normalize_blast_dates(series: pd.Series, date_format: str) -> pd.DataFrame:
    """Normalize a whole column; returns fecha_tronadura / date_original_value / date_status."""
    rows = [normalize_blast_date(value, date_format) for value in series.tolist()]
    return pd.DataFrame(
        {
            "fecha_tronadura": pd.Series([row[0] for row in rows], index=series.index, dtype=object),
            "date_original_value": pd.Series([row[1] for row in rows], index=series.index, dtype=object),
            "date_status": pd.Series([row[2] for row in rows], index=series.index, dtype=object),
        },
    )


class BlastDateContractError(ValueError):
    def __init__(self, error_code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


def validate_date_contract(
    date_source_column: str | None,
    date_format: str | None,
    headers: list[str],
    column_map: dict[str, str | None] | None = None,
) -> None:
    """Validate an explicit date source/format declaration before any work.

    Called only when a date source column was selected. Raises
    BlastDateContractError with a stable error_code on the first violation.
    """
    if not date_format:
        raise BlastDateContractError("DATE_FORMAT_REQUIRED", "Declare el formato de fecha (ISO, DMY o MDY).")
    if date_format not in DATE_FORMATS:
        raise BlastDateContractError(
            "DATE_FORMAT_INVALID",
            "El formato de fecha debe ser ISO, DMY o MDY.",
            {"date_format": date_format},
        )
    if date_source_column not in headers:
        raise BlastDateContractError(
            "DATE_COLUMN_NOT_FOUND",
            "La columna de fecha seleccionada no existe en el archivo.",
            {"date_source_column": date_source_column},
        )
    if column_map and date_source_column in {value for value in column_map.values() if value}:
        raise BlastDateContractError(
            "DATE_COLUMN_MAP_CONFLICT",
            "La columna de fecha no puede estar asignada también a un campo del mapeo.",
            {"date_source_column": date_source_column},
        )


def apply_date_column(df: pd.DataFrame, date_source_column: str, date_format: str) -> dict[str, int]:
    """Write canonical fecha_tronadura plus provenance columns onto ``df`` in place.

    Returns per-status counts. Missing/invalid dates stay null; no row is dropped.
    """
    frame = normalize_blast_dates(df[date_source_column], date_format)
    df["fecha_tronadura"] = frame["fecha_tronadura"].to_numpy(dtype=object)
    df["date_source_column"] = date_source_column
    df["date_format"] = date_format
    df["date_original_value"] = frame["date_original_value"].to_numpy(dtype=object)
    df["date_status"] = frame["date_status"].to_numpy(dtype=object)
    statuses = frame["date_status"]
    return {
        "total": int(len(statuses)),
        "valid": int((statuses == DATE_STATUS_VALID).sum()),
        "missing": int((statuses == DATE_STATUS_MISSING).sum()),
        "invalid": int((statuses == DATE_STATUS_INVALID).sum()),
    }


def date_event_warnings(counts: dict[str, int], date_source_column: str, date_format: str) -> list[dict]:
    warnings: list[dict] = []
    for status, code, label in (
        (DATE_STATUS_MISSING, "DATE_MISSING", "sin fecha"),
        (DATE_STATUS_INVALID, "DATE_INVALID", "con fecha inválida"),
    ):
        count = counts.get(status.lower(), 0)
        if count <= 0:
            continue
        warnings.append({
            "warning_code": code,
            "message": (
                f"{count} de {counts.get('total', 0)} filas {label} en la columna '{date_source_column}' "
                f"(formato {date_format}). No se asignó fecha; las filas se conservan."
            ),
            "hole_id": None,
            "source_row_index": None,
            "context": {
                "source_column": date_source_column,
                "date_format": date_format,
                "row_count": count,
                "total_rows": counts.get("total", 0),
            },
        })
    return warnings
