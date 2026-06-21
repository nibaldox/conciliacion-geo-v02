"""OpenBlast CSV format library — v1.0.0.

Provides:
- Validation against the OpenBlast JSON Schema (Draft-07)
- Format detection (OpenBlast vs ENAEX vs Datamine)
- Conversion from common vendor formats to OpenBlast CSV

Public API:
- load(path) -> list[dict]
- validate(rows) -> ValidationResult
- detect_format(path) -> Format
- convert_from_enaex(path) -> list[dict] in OpenBlast format
- write_csv(rows, path)

See openblast/README.md for the format specification.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Format(str, Enum):
    OPENBLAST = "openblast"
    ENAEX = "enaex"
    DATAMINE = "datamine"
    SURPAC = "surpac"
    UNKNOWN = "unknown"


SUPPORTED_OPENBLAST_MAJOR = "1"
MIN_OPENBLAST_VERSION = "1.0.0"


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    n_rows: int = 0


def _schema_path() -> Path:
    return Path(__file__).resolve().parent.parent / "schema" / "openblast-1.0.0.schema.json"


def _load_schema() -> dict:
    with _schema_path().open(encoding="utf-8") as f:
        return json.load(f)


def _row_schema() -> dict:
    return _load_schema()["items"]


REQUIRED_FIELDS = (
    "hole_id", "blast_id", "sequence",
    "easting", "northing", "elevation",
    "dip", "azimuth",
    "hole_length_actual", "diameter_mm",
    "burden", "spacing",
    "explosive_type", "explosive_kg_actual",
    "stemming_length_m",
    "mine_site", "bench_id", "shot_at",
)


_NUMERIC_FIELDS = (
    "sequence", "easting", "northing", "elevation", "dip", "azimuth",
    "hole_length_planned", "hole_length_actual", "diameter_mm",
    "burden", "spacing", "subdrill",
    "explosive_kg_actual", "explosive_kg_planned", "explosive_density_g_cc",
    "emulsion_kg", "anfo_kg", "bulk_kg", "stemming_length_m",
    "rock_mass_rating", "density_rock_t_m3", "delay_ms",
    "bottom_hole_x", "bottom_hole_y", "bottom_hole_z", "decoupling_ratio",
)

_RANGE_CONSTRAINTS = {
    "dip": (-90.0, 90.0),
    "azimuth": (0.0, 360.0),
    "explosive_density_g_cc": (0.0, 2.0),
    "density_rock_t_m3": (1.5, 4.0),
    "rock_mass_rating": (0.0, 100.0),
}

_ENUM_CONSTRAINTS = {
    "explosive_type": {"ANFO", "Heavy ANFO", "Emulsion", "Bulk emulsion", "ANFO + Emulsion", "Other"},
    "initiation_system": {"Nonel", "Electronic", "Detonating cord", "Other"},
    "anomaly_flag": {"loaded", "misfire", "cutoff", "wet_hole", "bootleg", "refilled", "empty"},
}


def load(path: str | Path) -> list[dict[str, Any]]:
    """Load an OpenBlast CSV file into a list of row dicts."""
    with Path(path).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(rows: list[dict[str, Any]], path: str | Path) -> None:
    """Write OpenBlast rows to CSV, preserving all columns."""
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _coerce_numeric(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        if "." in str(value) or "e" in str(value).lower():
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        return value


def _validate_row(row: dict[str, Any], row_index: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for field_name in REQUIRED_FIELDS:
        if field_name not in row or row[field_name] in (None, ""):
            errors.append(f"row {row_index}: missing required field '{field_name}'")

    for field_name in _NUMERIC_FIELDS:
        if field_name in row and row[field_name] not in (None, ""):
            coerced = _coerce_numeric(row[field_name])
            if coerced is None or not isinstance(coerced, (int, float)):
                errors.append(
                    f"row {row_index}: field '{field_name}' must be numeric, got {row[field_name]!r}"
                )
            else:
                row[field_name] = coerced
                if field_name in _RANGE_CONSTRAINTS:
                    lo, hi = _RANGE_CONSTRAINTS[field_name]
                    if not (lo <= coerced <= hi):
                        errors.append(
                            f"row {row_index}: field '{field_name}'={coerced} out of range [{lo}, {hi}]"
                        )

    for field_name, allowed in _ENUM_CONSTRAINTS.items():
        if field_name in row and row[field_name] not in (None, ""):
            if str(row[field_name]) not in allowed:
                errors.append(
                    f"row {row_index}: field '{field_name}'={row[field_name]!r} not in {sorted(allowed)}"
                )

    shot_at = row.get("shot_at")
    if shot_at:
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$", str(shot_at)):
            warnings.append(
                f"row {row_index}: shot_at={shot_at!r} does not match ISO-8601 (YYYY-MM-DDTHH:MM:SS±HH:MM)"
            )

    return errors, warnings


def validate(rows: list[dict[str, Any]]) -> ValidationResult:
    """Validate a list of OpenBlast rows against the v1.0 schema."""
    errors: list[str] = []
    warnings: list[str] = []
    for i, row in enumerate(rows, start=1):
        row_errors, row_warnings = _validate_row(row, i)
        errors.extend(row_errors)
        warnings.extend(row_warnings)
    return ValidationResult(
        valid=(not errors),
        errors=errors,
        warnings=warnings,
        n_rows=len(rows),
    )


def validate_file(path: str | Path) -> ValidationResult:
    """Convenience: load + validate a CSV file."""
    return validate(load(path))


_OPENBLAST_MARKERS = {
    "hole_id", "blast_id", "sequence",
    "easting", "northing", "elevation",
    "explosive_kg_actual", "stemming_length_m",
}

_ENAEX_MARKERS = {
    "Kilos_Cargados_real", "Longitud_Geo", "Latitud_Geo",
    "Inclinacion_real", "Azimuth_real", "longitud_real",
    "stemming_real", "Nombre_Malla_Original",
}

_DATAMINE_MARKERS = {"BHID", "XCOLLAR", "YCOLLAR", "ZCOLLAR"}


def detect_format(path: str | Path) -> Format:
    """Heuristically detect the CSV format by inspecting the header."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return Format.UNKNOWN
    cols = set(header)
    if _OPENBLAST_MARKERS.issubset(cols):
        return Format.OPENBLAST
    if _ENAEX_MARKERS.issubset(cols):
        return Format.ENAEX
    if _DATAMINE_MARKERS.issubset(cols):
        return Format.DATAMINE
    if "HoleID" in cols and "XCOLLAR" in cols:
        return Format.SURPAC
    return Format.UNKNOWN


def parse_diameter_mm(s: str | float | int | None) -> float | None:
    """Parse a diameter value that may be in inches (e.g. '10 5/8') or mm."""
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        val = float(s)
        if val <= 0:
            return None
        if val < 50:
            return val * 25.4
        return val
    text = str(s).strip().replace('"', '').replace("'", "")
    if "/" in text:
        try:
            parts = text.split()
            if len(parts) == 2:
                whole = float(parts[0])
                frac = parts[1].split("/")
                frac_val = float(frac[0]) / float(frac[1])
                return (whole + frac_val) * 25.4
        except (ValueError, ZeroDivisionError, IndexError):
            return None
    try:
        val = float(text)
        if val <= 0:
            return None
        if val < 50:
            return val * 25.4
        return val
    except ValueError:
        return None


_EXPLOSIVE_TYPE_MAP = {
    "pirex-930": "Heavy ANFO",
    "pirex-920": "Heavy ANFO",
    "pirex-950": "Heavy ANFO",
    "pirex-970": "Heavy ANFO",
    "enaline": "Emulsion",
    "anfo": "ANFO",
}


def classify_explosive(name: str | None) -> str:
    """Map a vendor-specific explosive name to an OpenBlast enum."""
    if not name:
        return "Other"
    n = str(name).strip().lower()
    if n in _EXPLOSIVE_TYPE_MAP:
        return _EXPLOSIVE_TYPE_MAP[n]
    for prefix, mapped in _EXPLOSIVE_TYPE_MAP.items():
        if n.startswith(prefix):
            return mapped
    return "Other"


def convert_from_enaex(
    path: str | Path,
    operator: str = "ENAEX-Zalivar",
    crs: str = "EPSG:32719",
) -> list[dict[str, Any]]:
    """Convert an ENAEX-format file (.xlsx or .csv) to OpenBlast rows.

    Uses heuristic field detection (find_df_column-style) so the
    converter works across ENAEX schemas without requiring a strict
    column match.
    """
    from core.calculo_tronadura import procesar_pozos
    from core.explosive_properties import get_explosive_density_g_cm3
    from core.geom_utils import find_df_column
    import pandas as pd

    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df_raw = pd.read_excel(path)
    else:
        df_raw = pd.read_csv(path)

    df_clean, *_ = procesar_pozos(df_raw)

    hole_id_col = find_df_column(df_clean, ["Nombre", "label_pozo", "id_pozo"], raise_error=False)
    if not hole_id_col:
        raise ValueError("ENAEX file missing hole identifier (Nombre/label_pozo/id_pozo)")
    pit_col = find_df_column(df_clean, ["Nombre_Rajo"], raise_error=False)
    date_col = find_df_column(df_clean, ["fecha_tronadura"], raise_error=False)
    bench_col = find_df_column(df_clean, ["Nombre_Banco", "Banco_Original"], raise_error=False)
    east_col = find_df_column(df_clean, ["X", "Longitud_Geo"], raise_error=False)
    north_col = find_df_column(df_clean, ["Y", "Latitud_Geo"], raise_error=False)
    elev_col = find_df_column(df_clean, ["Z_collar"], raise_error=False)
    dip_col = find_df_column(df_clean, ["Incl", "Inclinacion_real"], raise_error=False)
    az_col = find_df_column(df_clean, ["Az", "Azimuth_real"], raise_error=False)
    len_col = find_df_column(df_clean, ["Len", "longitud_real"], raise_error=False)
    diam_col = find_df_column(df_clean, ["diametro", "Diam_mm"], raise_error=False)
    expl_col = find_df_column(df_clean, ["Tipo_Explosivo", "Nombre"], raise_error=False)
    kg_col = find_df_column(df_clean, ["Kilos_Cargados_real"], raise_error=False)
    stem_col = find_df_column(df_clean, ["Taco_m", "stemming_real"], raise_error=False)
    seq_col = find_df_column(df_clean, ["Secuencia"], raise_error=False)
    ret_col = find_df_column(df_clean, ["Retardo_ms"], raise_error=False)
    plan_kg_col = find_df_column(df_clean, ["Longitud_teo"], raise_error=False)

    rows: list[dict[str, Any]] = []
    for _, row in df_clean.iterrows():
        sequence_val = row.get(seq_col) if seq_col else None
        delay_val = row.get(ret_col) if ret_col else None
        delay_ms: float | None = None
        if pd.notna(sequence_val) and pd.notna(delay_val):
            delay_ms = float(sequence_val) * 1000.0 + float(delay_val)
        elif pd.notna(sequence_val):
            delay_ms = float(sequence_val) * 1000.0
        elif pd.notna(delay_val):
            delay_ms = float(delay_val)

        explosive_name = row.get(expl_col) if expl_col else None
        explosive_type = classify_explosive(explosive_name)
        density = get_explosive_density_g_cm3(explosive_name) if explosive_name else None

        shot_at_val = row.get(date_col) if date_col else None
        if pd.notna(shot_at_val):
            try:
                shot_at_str = pd.Timestamp(shot_at_val).isoformat()
            except (ValueError, TypeError):
                shot_at_str = str(shot_at_val)
        else:
            shot_at_str = ""

        openblast_row: dict[str, Any] = {
            "hole_id": str(row.get(hole_id_col, "")),
            "blast_id": f"{row.get(pit_col, 'unknown')}_{shot_at_str[:10]}" if pit_col and shot_at_str else "unknown",
            "sequence": int(row.get(seq_col)) if seq_col and pd.notna(row.get(seq_col)) else 0,
            "easting": float(row.get(east_col)) if east_col and pd.notna(row.get(east_col)) else None,
            "northing": float(row.get(north_col)) if north_col and pd.notna(row.get(north_col)) else None,
            "elevation": float(row.get(elev_col)) if elev_col and pd.notna(row.get(elev_col)) else None,
            "dip": float(row.get(dip_col)) if dip_col and pd.notna(row.get(dip_col)) else 0.0,
            "azimuth": float(row.get(az_col)) if az_col and pd.notna(row.get(az_col)) else 0.0,
            "hole_length_actual": float(row.get(len_col)) if len_col and pd.notna(row.get(len_col)) else None,
            "diameter_mm": parse_diameter_mm(row.get(diam_col)) if diam_col else None,
            "burden": 6.5,
            "spacing": 7.5,
            "explosive_type": explosive_type,
            "explosive_kg_actual": float(row.get(kg_col)) if kg_col and pd.notna(row.get(kg_col)) else 0.0,
            "stemming_length_m": float(row.get(stem_col)) if stem_col and pd.notna(row.get(stem_col)) else 0.0,
            "mine_site": str(row.get(pit_col, "")) if pit_col else "",
            "bench_id": str(row.get(bench_col, "")) if bench_col else "",
            "shot_at": shot_at_str,
        }
        if delay_ms is not None:
            openblast_row["delay_ms"] = delay_ms
        if density is not None:
            openblast_row["explosive_density_g_cc"] = density
        rows.append(openblast_row)

    return rows


def get_version() -> str:
    """Return the current OpenBlast version (from VERSION file)."""
    candidates = [
        Path(__file__).resolve().parent.parent / "VERSION",
        Path(__file__).resolve().parent.parent.parent / "VERSION",
    ]
    for version_file in candidates:
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0+unknown"