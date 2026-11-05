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
import hashlib
import json
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

import api.database as db
import api.schemas as schemas
from api.blast_identity import blast_hole_id, blast_row_ids
from core.calculo_tronadura import procesar_pozos
from core.column_utils import KILOS_CANDIDATES, first_present_column
from core.geometry_contract import (
    GEOMETRY_CONFIGURATION_VERSION,
    GeometryConfiguration,
    GeometryConfigurationError,
)

logger = logging.getLogger(__name__)


def _run_in_executor(func, *args):
    """Schedule a CPU/IO-bound callable on the default executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, func, *args)


router = APIRouter(prefix="/blast", tags=["blast"])

from api.blast_import import mapping_errors, preview_payload, read_blast_file

_LENGTH_CANDIDATES = ("Len", "longitud_real", "Longitud", "Length", "Profundidad")
_TACO_CANDIDATES = ("Taco_m", "Taco", "Stemming")


def _decode_csv_bytes(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return file_bytes.decode("cp1252")
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1")


def _resolve_design_xy_columns(
    df: pd.DataFrame,
) -> tuple[str, str]:
    from core.column_mapping import CANONICAL_FIELDS
    alias_map = {field.name: field.aliases for field in CANONICAL_FIELDS if field.name in {"X", "Y"}}
    legacy_aliases = {"X": ("Latitud_Geo", "Latitud", "X", "Este"), "Y": ("Longitud_Geo", "Longitud", "Y", "Norte")}
    by_lower = {str(column).lower(): column for column in df.columns}

    def resolve(canonical: str) -> Optional[str]:
        candidates = tuple(dict.fromkeys((*alias_map[canonical], *legacy_aliases[canonical])))
        return next((column for candidate in candidates if (column := by_lower.get(candidate.lower())) is not None), None)

    resolved_x, resolved_y = resolve("X"), resolve("Y")
    if resolved_x is None or resolved_y is None:
        raise ValueError("required X/Y coordinate columns absent")
    return resolved_x, resolved_y


def _sample_uploaded_design_surface(content: bytes, mesh_id: str, filename: str = "upload.csv", sheet_name: Optional[str] = None, column_map: Optional[dict[str, str | None]] = None):
    from core.design_surface_sampling import sample_design_surface

    csv_df, headers, _, _ = read_blast_file(content, filename, sheet_name)
    if column_map:
        x_column, y_column = column_map.get("X"), column_map.get("Y")
        if not x_column or not y_column or x_column not in headers or y_column not in headers:
            raise ValueError("El mapeo confirmado debe incluir columnas existentes para X e Y.")
    else:
        x_column, y_column = _resolve_design_xy_columns(csv_df)
    design_mesh = db.get_trimesh_by_id(mesh_id)
    samples = sample_design_surface(design_mesh, csv_df[[x_column, y_column]].to_numpy())
    mesh_info = db.get_mesh_by_id(mesh_id)
    if not mesh_info or not mesh_info.get("data"):
        raise ValueError("design mesh blob unavailable")
    return samples, {"X": x_column, "Y": y_column}, hashlib.sha256(mesh_info["data"]).hexdigest()


@router.post("/preview")
async def preview_blast_file(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
):
    content = await file.read()
    try:
        frame, headers, sheets, encoding = read_blast_file(content, file.filename or "", sheet_name, preview=True)
    except ValueError as exc:
        raise HTTPException(400, detail={"error_code": "BLAST_FILE_INVALID", "message": str(exc)}) from exc
    if frame.empty:
        raise HTTPException(400, detail={"error_code": "BLAST_FILE_EMPTY", "message": "El archivo no contiene filas."})
    if len(headers) != len(set(headers)):
        raise HTTPException(400, detail={"error_code": "DUPLICATE_COLUMNS", "message": "El archivo contiene encabezados duplicados."})
    return preview_payload(frame, headers, sheets, sheet_name or (sheets[0] if sheets else None), encoding)


def _read_uploaded_csv(file: UploadFile) -> pd.DataFrame:
    """Read an uploaded CSV file into a DataFrame (HTTP 400 on parse error)."""
    try:
        content = file.file.read()
    except Exception as exc:
        raise HTTPException(400, f"Could not read uploaded file: {exc}")

    if isinstance(content, bytes):
        content = _decode_csv_bytes(content)

    try:
        df = pd.read_csv(io.StringIO(content), engine="python", on_bad_lines="warn")
    except Exception as exc:
        raise HTTPException(400, f"Invalid CSV: {exc}")

    if df.empty:
        raise HTTPException(400, "CSV file is empty")

    return df


def _resolve_carga_column(df: pd.DataFrame) -> Optional[str]:
    if "kg_per_meter" in df.columns:
        return "kg_per_meter"
    return None


def _resolve_descarga_column(df: pd.DataFrame) -> Optional[str]:
    if "altura_carga_m" in df.columns:
        return "altura_carga_m"
    return None


def _compute_carga_series(df: pd.DataFrame) -> pd.Series:
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
    cleaned = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    value = float(cleaned.mean()) if not cleaned.empty else 0.0
    return value if math.isfinite(value) else 0.0


def _hardness_distribution(df: pd.DataFrame) -> Dict[str, int]:
    distribution: Dict[str, int] = {}
    if "dureza" not in df.columns:
        return distribution
    for value in df["dureza"].dropna().astype(str):
        distribution[value] = distribution.get(value, 0) + 1
    return distribution


def _hole_id_for_row(row: pd.Series, index: int, df: pd.DataFrame) -> str:
    for candidate in ("pozo", "hole_id", "id_pozo", "Hole_ID"):
        if candidate in df.columns:
            value = row.get(candidate)
            if value is not None and str(value) != "nan":
                return str(value)
    return str(index)


def _df_to_hole_records(df: pd.DataFrame) -> List[Dict[str, object]]:
    """Convert a processed blast DataFrame to plain dicts for persistence."""
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

    hole_id = _str_or_none("hole_id") or str(int(record.get("index", 0)))

    return schemas.BlastHoleSummary(
        hole_id=hole_id,
        x=_float_or_zero("X"),
        y=_float_or_zero("Y"),
        z=_float_or_zero("Z_collar"),
        carga=_float_or_zero("carga"),
        descarga=_float_or_zero("descarga"),
        hardness=hardness,
        bench=bench,
        length=_float_or_zero("Len"),
        inclination=_float_or_zero("Incl"),
        azimuth=_float_or_zero("Az"),
        z_collar_semantic=_str_or_none("Z_collar_semantic"),
        surface_sample_status=_str_or_none("surface_sample_status"),
        surface_sample_reason=_str_or_none("surface_sample_reason"),
        surface_sample_method=_str_or_none("surface_sample_method"),
        surface_sample_mesh_id=_str_or_none("surface_sample_mesh_id"),
        surface_sample_mesh_sha256=_str_or_none("surface_sample_mesh_sha256"),
        surface_sample_unit=_str_or_none("surface_sample_unit"),
        surface_sample_assumption=_str_or_none("surface_sample_assumption"),
    )


# ---------------------------------------------------------------------------
# Geometric configuration builder (remediación 4.1 — single source of truth)
# ---------------------------------------------------------------------------


def _build_geometry_configuration(
    *,
    geometry_configuration_version: Optional[str],
    geometry_user_confirmed: Optional[bool],
    inclination_convention: Optional[str],
    inclination_sign_convention: Optional[str],
    inclination_source_rule: Optional[str],
    inclination_unit: Optional[str],
    azimuth_convention: Optional[str],
    azimuth_unit: Optional[str],
    inclination_source_column: str = "",
    azimuth_source_column: str = "",
) -> GeometryConfiguration:
    """Translate the API Form fields into a validated GeometryConfiguration.

    No defaults are invented: any missing required field propagates as
    ``None``/empty and the contract's ``validate()`` raises a structured
    error. The API never calls ``procesar_pozos`` without this object.

    Canonical values (spec §4.1):
      * inclination_convention: ``FROM_VERTICAL`` | ``DIP_FROM_HORIZONTAL``
        (accepted case-insensitively; normalized to uppercase by the contract)
      * inclination_sign_convention: ``ABSOLUTE_VALUE`` |
        ``NEGATIVE_IS_DOWNWARD_DIP`` | ``SOURCE_DEFINED``
      * inclination_unit / azimuth_unit: ``DEGREES`` | ``RADIANS``
      * azimuth_convention: ``CLOCKWISE_FROM_NORTH`` |
        ``COUNTERCLOCKWISE_FROM_NORTH`` | ``CLOCKWISE_FROM_EAST`` |
        ``COUNTERCLOCKWISE_FROM_EAST``
    """
    def _upper(v: Optional[str]) -> Optional[str]:
        return v.upper() if v else None

    return GeometryConfiguration(
        geometry_configuration_version=geometry_configuration_version or "",
        geometry_user_confirmed=geometry_user_confirmed,
        inclination_source_column=inclination_source_column,
        inclination_convention=_upper(inclination_convention),
        inclination_sign_convention=_upper(inclination_sign_convention),
        inclination_unit=_upper(inclination_unit),
        inclination_source_rule=inclination_source_rule or "",
        azimuth_source_column=azimuth_source_column,
        azimuth_convention=_upper(azimuth_convention),
        azimuth_unit=_upper(azimuth_unit),
    )


# ---------------------------------------------------------------------------
# Structured upload result (remediación 4.2 — direct processor output)
# ---------------------------------------------------------------------------


def _build_upload_payload(
    file_bytes: bytes,
    config: GeometryConfiguration,
    bench_height_m: Optional[float],
    design_surface_samples=None,
    design_surface_mesh_id: Optional[str] = None,
    design_surface_sha256: Optional[str] = None,
    coordinate_column_map: Optional[dict[str, str]] = None,
    filename: str = "upload.csv",
    sheet_name: Optional[str] = None,
    column_map: Optional[dict[str, str | None]] = None,
) -> dict:
    """Run the full blast-upload pipeline off the event-loop thread.

    Returns the STRUCTURED processor result directly — never reconstructed
    from scalar summary strings. ``rejected_rows`` is the authoritative
    per-row rejection list coming from ``procesar_pozos``.

    When zero rows are accepted the payload is still fully populated with
    the structured rejections and a blocking summary; the caller decides
    whether to map that to a 4xx status code, but the body never loses
    the rejection detail (remediación 3.2).
    """
    try:
        df, headers, _, _ = read_blast_file(file_bytes if isinstance(file_bytes, bytes) else file_bytes.encode(), filename, sheet_name)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid upload: {exc}") from exc

    if df.empty:
        raise HTTPException(400, "CSV file is empty")

    if coordinate_column_map and not column_map:
        for canonical, source in coordinate_column_map.items():
            compatibility_alias = {"X": "Latitud_Geo", "Y": "Longitud_Geo"}.get(canonical)
            if compatibility_alias and compatibility_alias not in df.columns:
                df[compatibility_alias] = df[source]
    processing_map = column_map
    if column_map and design_surface_samples is not None and not column_map.get("Z_collar"):
        df["__design_surface_z_pending"] = 0.0
        processing_map = {**column_map, "Z_collar": "__design_surface_z_pending"}

    n_rows_input = len(df)

    # Integración §5.7: invoke the processor with return_result=True so
    # the canonical ProcessingResult (accepted_rows + rejected_rows +
    # warnings + diagnostics) is born in the core. The router no longer
    # reconstructs accepted_rows from the DataFrame — it consumes the
    # core's structured output directly.
    from core.processing_result import ProcessingResult
    blocking_errors: list[dict] = []
    result: ProcessingResult
    try:
        result = procesar_pozos(
            df,
            geometry_configuration=config,
            bench_height_m=bench_height_m,
            return_result=True,
            design_surface_samples=design_surface_samples,
            design_surface_mesh_id=design_surface_mesh_id,
            design_surface_sha256=design_surface_sha256,
            column_map=processing_map,
            preserve_invalid_mapped_rows=column_map is not None,
        )
    except KeyError as exc:
        blocking_errors.append({
            "error_code": "MISSING_REQUIRED_COLUMN",
            "message": f"Columna requerida ausente en el CSV: {exc}",
            "recommended_action": "Mapee o renombre las columnas fuente y reprocese.",
        })
        result = ProcessingResult(
            geometry_configuration=config.to_dict(),
            accepted_rows=[],
            rejected_rows=[],
            rows_received=n_rows_input,
        )
        result.blocking_errors = list(blocking_errors)
    except GeometryConfigurationError as exc:
        blocking_errors.append({
            "error_code": exc.error_code,
            "message": str(exc),
            "details": exc.details,
            "recommended_action": "Confirme y complete la configuración geométrica.",
        })
        result = ProcessingResult(
            geometry_configuration=config.to_dict(),
            accepted_rows=[],
            rejected_rows=[],
            rows_received=n_rows_input,
        )
        result.blocking_errors = list(blocking_errors)

    source_inclination = config.inclination_source_column
    if source_inclination in df.columns and not df.empty:
        inclination_values = pd.to_numeric(df[source_inclination], errors="coerce")
        if inclination_values.notna().all() and (inclination_values == 0).all():
            result.event_warnings.append({
                "warning_code": "INCLINATION_ALL_ZERO",
                "message": (
                    "La columna de inclinación declarada contiene cero en todas las filas. "
                    "Verifique el dato y la convención confirmada; no se asumió una orientación."
                ),
                "hole_id": None,
                "source_row_index": None,
                "context": {
                    "source_column": source_inclination,
                    "row_count": int(len(inclination_values)),
                    "inclination_convention": config.inclination_convention,
                },
            })

    # Enrichment runs over the accepted frame only. Failures here are
    # non-fatal — the canonical result is preserved either way. The
    # enriched data is merged BACK into result.accepted_rows so the
    # canonical list reflects the additional carga/descarga columns.
    df_clean = result.accepted_dataframe
    if df_clean is not None and not df_clean.empty:
        carga_mean = _safe_mean(_compute_carga_series(df_clean))
        descarga_mean = _safe_mean(_compute_descarga_series(df_clean))
        hardness_dist = _hardness_distribution(df_clean)
        data_warnings_text = " | ".join(w["message"] for w in result.event_warnings)
    else:
        carga_mean = 0.0
        descarga_mean = 0.0
        hardness_dist = {}
        data_warnings_text = ""

    accepted_rows = result.accepted_rows
    rejected_rows = result.rejected_rows
    records = accepted_rows  # deprecated alias of the SAME list
    n_holes = len(accepted_rows)
    n_rows_skipped = result.rejected_source_rows

    summary = result.processing_summary()

    return {
        "n_holes": n_holes,
        "n_rows_loaded": n_holes,
        "n_rows_skipped": n_rows_skipped,
        "carga_mean": round(carga_mean, 3),
        "descarga_mean": round(descarga_mean, 3),
        "hardness_distribution": hardness_dist,
        "accepted_rows": accepted_rows,
        "records": records,  # deprecated alias of accepted_rows
        "data_warnings": data_warnings_text,
        "processing_summary": summary,
        "rejected_rows": rejected_rows,
        "event_warnings": result.event_warnings,
        "blocking_errors": result.blocking_errors,
        "spatial_diagnostics": result.spatial_diagnostics,
    }


# ---------------------------------------------------------------------------
# POST /blast/upload
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_blast_csv(
    request: Request,
    file: UploadFile = File(..., description="Blast-hole CSV"),
    session_id: str = Form(..., description="Session UUID"),
    compact: bool = Query(False, description="Omit accepted_rows from successful responses"),
    geometry_configuration_version: Optional[str] = Form(
        None, description="OBLIGATORIO v2: versión exacta del contrato geométrico"
    ),
    geometry_user_confirmed: Optional[bool] = Form(
        None,
        description="OBLIGATORIO: el evento debe declarar true (confirmado por el operador). "
        "false/ausente/None bloquean la geometría.",
    ),
    inclination_convention: Optional[str] = Form(
        None,
        description="OBLIGATORIO: from_vertical | dip_from_horizontal (sin default)",
    ),
    bench_height_m: Optional[float] = Form(
        None, description="Altura de banco confirmada del evento (m)"
    ),
    azimuth_convention: Optional[str] = Form(
        None,
        description="OBLIGATORIO: CLOCKWISE_FROM_NORTH | COUNTERCLOCKWISE_FROM_NORTH | "
        "CLOCKWISE_FROM_EAST | COUNTERCLOCKWISE_FROM_EAST (sin default)",
    ),
    inclination_sign_convention: Optional[str] = Form(
        None,
        description="OBLIGATORIO: ABSOLUTE_VALUE | NEGATIVE_IS_DOWNWARD_DIP | SOURCE_DEFINED (sin default)",
    ),
    inclination_source_rule: Optional[str] = Form(
        None, description="Regla explícita para SOURCE_DEFINED (obligatoria en ese caso)"
    ),
    inclination_unit: Optional[str] = Form(
        None,
        description="OBLIGATORIO v2: degrees | radians — unidad INDEPENDIENTE de inclinación",
    ),
    azimuth_unit: Optional[str] = Form(
        None,
        description="OBLIGATORIO v2: degrees | radians — unidad INDEPENDIENTE de azimut",
    ),
    angle_unit: Optional[str] = Form(
        None,
        description="LEGACY: unidad compartida. Si se envía junto con inclination_unit/"
        "azimuth_unit, los campos v2 tienen prioridad. Nunca habilita geometría por sí solo.",
    ),
    inclination_source_column: str = Form(
        "",
        description="OBLIGATORIO v2: columna fuente de inclinación (nombre exacto del CSV)",
    ),
    azimuth_source_column: str = Form(
        "",
        description="OBLIGATORIO v2: columna fuente de azimut (nombre exacto del CSV)",
    ),
    # ── Alias legacy (deprecados) — aceptados por compatibilidad ──
    incl_source_column: Optional[str] = Form(
        None, description="LEGACY: alias de inclination_source_column"
    ),
    az_source_column: Optional[str] = Form(
        None, description="LEGACY: alias de azimuth_source_column"
    ),
    incl_convention: Optional[str] = Form(None, description="LEGACY"),
    incl_sign_convention: Optional[str] = Form(None, description="LEGACY"),
    sign_source_rule: Optional[str] = Form(None, description="LEGACY"),
    az_convention: Optional[str] = Form(None, description="LEGACY"),
    design_surface_mode: Optional[str] = Form(None, description="Opt-in: sample_design"),
    sheet_name: Optional[str] = Form(None),
    column_map: Optional[str] = Form(None),
    collar_elevation_source: Optional[str] = Form(None),
    spatial_reference_confirmed: Optional[bool] = Form(None),
) -> schemas.BlastUploadResponse:
    """Accept a blast-hole CSV, parse it, compute charge metrics, and persist.

    Remediación 3.1/4.1: the geometric configuration MUST be declared and
    confirmed explicitly by the caller. ``geometry_user_confirmed=true`` is
    the only value that enables geometry; ``false``/absent/``None`` and any
    missing required convention field produce a structured error payload
    (no silent defaults).
    Remediación 3.2/4.2: even when zero rows are accepted, the response
    carries the structured ``rejected_rows`` so the operator sees what to
    fix — never a bare HTTP 400 that hides the diagnosis.
    """
    form = await request.form()
    allowed_fields = {
        "file", "session_id", "bench_height_m", "sheet_name", "column_map",
        "geometry_configuration_version", "geometry_user_confirmed",
        "inclination_source_column", "inclination_convention",
        "inclination_sign_convention", "inclination_unit",
        "inclination_source_rule", "azimuth_source_column",
        "azimuth_convention", "azimuth_unit", "angle_unit",
        "incl_source_column", "incl_convention", "incl_sign_convention",
        "sign_source_rule", "az_source_column", "az_convention",
        "design_surface_mode", "collar_elevation_source", "spatial_reference_confirmed",
    }
    unknown_fields = sorted(set(form.keys()) - allowed_fields)
    if unknown_fields:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "UNKNOWN_MULTIPART_FIELDS",
                "message": "El formulario contiene campos no reconocidos.",
                "details": {"unknown_fields": unknown_fields},
            },
        )
    duplicate_fields = sorted(
        key for key in set(form.keys()) if key != "file" and len(form.getlist(key)) > 1
    )
    if duplicate_fields:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "DUPLICATE_MULTIPART_FIELDS",
                "message": "El formulario contiene campos duplicados.",
                "details": {"duplicate_fields": duplicate_fields},
            },
        )

    if not session_id.strip():
        raise HTTPException(422, "session_id is required")

    try:
        canonical_keys = {
            "geometry_configuration_version", "geometry_user_confirmed",
            "inclination_source_column",
            "inclination_convention", "inclination_sign_convention",
            "inclination_unit", "inclination_source_rule",
            "azimuth_source_column", "azimuth_convention", "azimuth_unit",
        }
        is_v2 = bool({
            "geometry_configuration_version",
            "inclination_convention",
            "inclination_sign_convention",
            "inclination_source_rule",
            "azimuth_convention",
        } & set(form.keys()))
        if is_v2:
            missing = sorted(canonical_keys - set(form.keys()))
            if missing:
                raise GeometryConfigurationError(
                    "El contrato multipart v2 está incompleto.",
                    error_code="GEOMETRY_INCOMPLETE",
                    details={"missing_fields": missing},
                )
            legacy_pairs = {
                "incl_source_column": (incl_source_column, inclination_source_column),
                "incl_convention": (incl_convention, inclination_convention),
                "incl_sign_convention": (incl_sign_convention, inclination_sign_convention),
                "sign_source_rule": (sign_source_rule, inclination_source_rule),
                "az_source_column": (az_source_column, azimuth_source_column),
                "az_convention": (az_convention, azimuth_convention),
            }
            conflicts = {
                key: {"legacy": legacy, "v2": canonical}
                for key, (legacy, canonical) in legacy_pairs.items()
                if legacy is not None and str(legacy).upper() != str(canonical or "").upper()
            }
            if angle_unit is not None and (
                str(angle_unit).upper() != str(inclination_unit or "").upper()
                or str(angle_unit).upper() != str(azimuth_unit or "").upper()
            ):
                conflicts["angle_unit"] = {
                    "legacy": angle_unit,
                    "inclination_unit": inclination_unit,
                    "azimuth_unit": azimuth_unit,
                }
            if conflicts:
                raise GeometryConfigurationError(
                    "Los campos legacy contradicen el contrato v2.",
                    error_code="LEGACY_V2_CONFLICT",
                    details={"conflicts": conflicts},
                )
            final_version = geometry_configuration_version
            final_incl_col = inclination_source_column
            final_incl_convention = inclination_convention
            final_incl_sign = inclination_sign_convention
            final_source_rule = inclination_source_rule
            final_incl_unit = inclination_unit
            final_az_col = azimuth_source_column
            final_az_convention = azimuth_convention
            final_az_unit = azimuth_unit
        else:
            final_version = GEOMETRY_CONFIGURATION_VERSION
            final_incl_col = inclination_source_column or incl_source_column or ""
            final_incl_convention = incl_convention
            final_incl_sign = incl_sign_convention
            final_source_rule = sign_source_rule
            final_incl_unit = inclination_unit or angle_unit
            final_az_col = azimuth_source_column or az_source_column or ""
            final_az_convention = az_convention
            final_az_unit = azimuth_unit or angle_unit
            if angle_unit is not None and (
                (inclination_unit is not None and str(angle_unit).upper() != str(inclination_unit).upper())
                or (azimuth_unit is not None and str(angle_unit).upper() != str(azimuth_unit).upper())
            ):
                raise GeometryConfigurationError(
                    "La unidad legacy contradice las unidades migradas.",
                    error_code="LEGACY_V2_CONFLICT",
                    details={
                        "angle_unit": angle_unit,
                        "inclination_unit": inclination_unit,
                        "azimuth_unit": azimuth_unit,
                    },
                )
        config = _build_geometry_configuration(
            geometry_configuration_version=final_version,
            geometry_user_confirmed=geometry_user_confirmed,
            inclination_convention=final_incl_convention,
            inclination_sign_convention=final_incl_sign,
            inclination_source_rule=final_source_rule,
            inclination_unit=final_incl_unit,
            azimuth_convention=final_az_convention,
            azimuth_unit=final_az_unit,
            inclination_source_column=final_incl_col,
            azimuth_source_column=final_az_col,
        )
        config.validate()
    except GeometryConfigurationError as exc:
        # Surface the structured contract error in the response body.
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": exc.error_code,
                "message": str(exc),
                "details": exc.details,
            },
        )

    db.get_or_create_session(session_id)

    try:
        content = file.file.read()
    except Exception as exc:
        raise HTTPException(400, f"Could not read uploaded file: {exc}")

    confirmed_map = None
    if column_map is not None:
        try:
            confirmed_map = json.loads(column_map)
        except (TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(400, detail={"error_code": "COLUMN_MAP_INVALID", "message": "column_map debe ser JSON válido."}) from exc
        if not isinstance(confirmed_map, dict):
            raise HTTPException(400, detail={"error_code": "COLUMN_MAP_INVALID", "message": "column_map debe ser un objeto JSON."})
        try:
            _, headers, _, _ = await _run_in_executor(
                read_blast_file, content, file.filename or "", sheet_name, True
            )
        except ValueError as exc:
            raise HTTPException(400, detail={"error_code": "BLAST_FILE_INVALID", "message": str(exc)}) from exc
        errors = mapping_errors(confirmed_map, headers, allow_missing_z=design_surface_mode == "sample_design" or collar_elevation_source == "design_surface")
        if errors:
            raise HTTPException(400, detail={"error_code": "COLUMN_MAP_INVALID", "message": "El mapeo no es válido.", "details": {"errors": errors}})
        confirmed_map = {key: (value or None) for key, value in confirmed_map.items()}
        if confirmed_map.get("Incl") != final_incl_col or confirmed_map.get("Az") != final_az_col:
            raise HTTPException(400, detail={"error_code": "GEOMETRY_COLUMN_MAP_CONFLICT", "message": "Las columnas geométricas confirmadas deben coincidir con el mapeo de inclinación y azimut."})

    design_samples = None
    design_mesh_id = None
    design_sha256 = None
    coordinate_column_map = None
    use_design_surface = design_surface_mode is not None or collar_elevation_source is not None
    if use_design_surface:
        if design_surface_mode not in (None, "sample_design") or collar_elevation_source != "design_surface":
            raise HTTPException(400, detail={"error_code": "DESIGN_SURFACE_MODE_INVALID"})
        if spatial_reference_confirmed is not True:
            raise HTTPException(400, detail={"error_code": "DESIGN_SURFACE_CONFIRMATION_REQUIRED", "message": "Confirme que CSV y diseño comparten CRS, datum y coordenadas en metros."})
        if session_id != getattr(request.state, "session_id", None):
            raise HTTPException(403, detail={"error_code": "SESSION_ID_MISMATCH"})
        mesh_info = await _run_in_executor(db.get_mesh, session_id, "design")
        if not mesh_info or not mesh_info.get("data"):
            raise HTTPException(404, detail={"error_code": "DESIGN_SURFACE_NOT_FOUND"})
        try:
            design_samples, coordinate_column_map, design_sha256 = await _run_in_executor(
                _sample_uploaded_design_surface, content, mesh_info["id"], file.filename or "", sheet_name, confirmed_map
            )
            design_mesh_id = mesh_info["id"]
        except Exception as exc:
            raise HTTPException(400, detail={"error_code": "DESIGN_SURFACE_SAMPLING_FAILED", "message": str(exc)}) from exc

    try:
        payload = await _run_in_executor(_build_upload_payload, content, config, bench_height_m, design_samples, design_mesh_id, design_sha256, coordinate_column_map, file.filename or "upload.csv", sheet_name, confirmed_map)
    except GeometryConfigurationError as exc:
        # The processor may raise GEOMETRY errors after the contract check
        # (e.g. declared source column not found in dataset).
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": exc.error_code,
                "message": str(exc),
                "details": exc.details,
            },
        )

    surface_summary = None
    if design_samples is not None:
        counts = {status: sum(sample.status == status for sample in design_samples) for status in ("sampled", "outside", "ambiguous", "invalid")}
        surface_summary = {
            "mode": "sample_design",
            "mesh_id": design_mesh_id,
            "mesh_sha256": design_sha256,
            "spatial_reference_confirmed": True,
            "unit": "m",
            "method": "vertical_triangle_intersection",
            "x_source_column": coordinate_column_map["X"],
            "y_source_column": coordinate_column_map["Y"],
            "rows": len(design_samples),
            "coverage": counts["sampled"] / len(design_samples) if design_samples else 0.0,
            "counts": counts,
        }

    db.save_blast_upload(
        session_id,
        {
            "accepted_rows": payload["accepted_rows"],
            "holes": payload["accepted_rows"],  # legacy alias
            "n_holes": payload["n_holes"],
            "n_rows_loaded": payload["n_rows_loaded"],
            "n_rows_skipped": payload["n_rows_skipped"],
            "rejected_rows": payload["rejected_rows"],
            "processing_summary": payload["processing_summary"],
            "data_warnings": payload["data_warnings"],
            "event_warnings": payload.get("event_warnings", []),
            "blocking_errors": payload.get("blocking_errors", []),
            "spatial_diagnostics": payload.get("spatial_diagnostics", {}),
            "geometry_configuration": config.to_dict(),
            "design_surface": surface_summary,
        },
    )

    # Remediación 3.2: when zero rows are accepted, return HTTP 422 with the
    # structured payload in the body — never a bare 400 that loses the
    # rejection detail. The Pydantic response model still validates.
    from fastapi.responses import JSONResponse

    response_body = schemas.BlastUploadResponse(
        session_id=session_id,
        n_holes=payload["n_holes"],
        n_rows_loaded=payload["n_rows_loaded"],
        n_rows_skipped=payload["n_rows_skipped"],
        data_warnings=payload.get("data_warnings", ""),
        processing_summary=payload.get("processing_summary", {}),
        accepted_rows=payload.get("accepted_rows", []),
        rejected_rows=payload.get("rejected_rows", []),
        event_warnings=payload.get("event_warnings", []),
        blocking_errors=payload.get("blocking_errors", []),
        geometry_configuration=config.to_dict(),
        spatial_diagnostics=payload.get("spatial_diagnostics", {}),
        design_surface=surface_summary,
        carga_mean=payload["carga_mean"],
        descarga_mean=payload["descarga_mean"],
        hardness_distribution=payload["hardness_distribution"],
    )

    # Remediación 3.2: when zero rows are accepted OR a blocking error
    # occurred, return HTTP 422 with the structured payload in the body —
    # never a bare 400 that hides the rejection detail.
    if payload["n_holes"] == 0 or payload.get("blocking_errors"):
        return JSONResponse(
            status_code=422,
            content=response_body.model_dump(),
        )
    if compact:
        return JSONResponse(
            content=response_body.model_dump(mode="json", exclude={"accepted_rows"}),
        )
    return response_body


def _build_hole_summaries(records: List[Dict[str, object]]) -> List[schemas.BlastHoleSummary]:
    return [_record_to_summary(record) for record in records]


# ---------------------------------------------------------------------------
# GET /blast/{session_id}/holes
# ---------------------------------------------------------------------------


@router.get("/{session_id}/summary")
async def get_blast_holes_summary(session_id: str, request: Request) -> dict[str, int]:
    if session_id != request.state.session_id:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "SESSION_ID_MISMATCH"},
        )
    settings = db.get_settings(session_id) or {}
    records = settings.get("blast_holes", [])
    n_holes = len(records) if isinstance(records, list) else 0
    return {"n_holes": n_holes}


@router.get("/{session_id}/holes")
async def get_blast_holes(
    session_id: str,
    section_name: Optional[str] = None,
) -> schemas.BlastHolesResponse:
    _ = section_name  # reserved

    settings = db.get_settings(session_id) or {}
    raw = settings.get("blast_holes", [])
    if not isinstance(raw, list):
        return schemas.BlastHolesResponse(session_id=session_id, holes=[])

    holes = await _run_in_executor(_build_hole_summaries, raw)
    return schemas.BlastHolesResponse(session_id=session_id, holes=holes)


def _finite_number(value: object) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rejected_source_row_count(
    settings: Dict[str, object], rejected_rows: List[Dict[str, object]],
) -> int:
    processing_summary = settings.get("processing_summary")
    if isinstance(processing_summary, dict):
        count = processing_summary.get("rejected_source_rows")
        if count is None:
            count = processing_summary.get("rows_rejected")
        try:
            parsed_count = int(count)
            if parsed_count >= 0:
                return parsed_count
        except (TypeError, ValueError, OverflowError):
            pass
    source_indices = {
        row.get("source_row_index")
        for row in rejected_rows
        if row.get("source_row_index") is not None
    }
    return len(source_indices) if source_indices else len(rejected_rows)


def _build_holes_3d(
    settings: Dict[str, object],
    session_id: str,
    section=None,
    corridor_m: Optional[float] = None,
    section_id: Optional[int] = None,
) -> schemas.BlastHoles3DResponse:
    records = settings.get("blast_holes", [])
    records = records if isinstance(records, list) else []
    records = [record if isinstance(record, dict) else {} for record in records]
    row_ids = blast_row_ids(session_id, records)
    rejected = settings.get("rejected_rows", [])
    rejected = rejected if isinstance(rejected, list) else []
    output = []
    counts = {"complete_geometry": 0, "collar_only": 0, "without_geometry": 0}
    for ordinal, (record, row_id) in enumerate(zip(records, row_ids)):
        hole_id = blast_hole_id(record, ordinal)
        raw_index = record.get("source_row_index")
        try:
            source_index = int(raw_index) if raw_index is not None else None
        except (TypeError, ValueError):
            source_index = None
        xyz = [_finite_number(record.get(key)) for key in ("X", "Y", "Z_collar")]
        collar = xyz if all(value is not None for value in xyz) else None
        toe_values = [_finite_number(record.get(key)) for key in ("X_toe", "Y_toe", "Z_toe")]
        toe = toe_values if all(value is not None for value in toe_values) else None
        state = "complete" if collar is not None and toe is not None else "collar_only" if collar is not None else "none"
        counts[{"complete": "complete_geometry", "collar_only": "collar_only", "none": "without_geometry"}[state]] += 1
        provenance_keys = (
            "z_collar_semantic", "surface_sample_status", "surface_sample_reason",
            "surface_sample_method", "surface_sample_mesh_id", "surface_sample_mesh_sha256",
            "surface_sample_unit", "surface_sample_assumption", "geometry_configuration",
        )
        provenance = {key: record[key] for key in provenance_keys if record.get(key) is not None}
        z_semantic = record.get("z_collar_semantic", record.get("Z_collar_semantic"))
        if z_semantic is not None:
            provenance["z_collar_semantic"] = z_semantic
        attributes = {
            key: record[key] for key in (
                "Banco_Original", "bench", "bench_num", "bench_num_topo", "sector",
                "fecha", "fecha_tronadura", "Fecha", "Fecha_Tronadura", "event_id",
                "uniqid", "id_pozo", "label_pozo",
                "Len", "longitud_real", "Incl", "Inclinacion_real", "Az",
                "Azimuth_real", "Diam_mm", "hole_type",
                "Nombre_Malla_Original", "holes_polygon", "Malla", "Nombre_Fase", "Fase",
                "Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg", "carga",
                "PF", "pf_g_per_ton", "PF_g_per_ton", "pf_g_per_ton_net", "pf_g_per_ton_inf",
                "Banco", "banco", "Banco_Diseno", "Nombre_Banco",
                "Diametro", "Diametro_pozo", "Diametro_mm", "Diameter", "D_mm", "diameter_mm",
                "dureza", "Dureza", "hardness",
                "indice_dureza", "Indice_Dureza", "hardness_index",
                "tasa_penetracion", "Tasa_Penetracion", "penetration_rate",
                "Longitud_real", "depth_m", "Inclinacion", "inclination",
            ) if key in record
        }
        attributes = {
            key: None if isinstance(value, float) and not math.isfinite(value) else value
            for key, value in attributes.items()
        }
        relation = None
        section_distance = None
        if section is not None:
            from core.hole_section_geometry import classify_hole_segment_to_section

            classification = classify_hole_segment_to_section(
                collar, toe, section, corridor_m=float(corridor_m)
            )
            relation = classification.relation
            section_distance = classification.min_distance_to_section_m
        output.append(schemas.BlastHole3D(
            row_id=row_id, hole_id=hole_id, source_row_index=source_index,
            collar=collar, toe=toe, geometry_status=state,
            provenance=provenance, attributes=attributes,
            section_relation=relation, section_distance_m=section_distance,
        ))
    return schemas.BlastHoles3DResponse(
        session_id=session_id,
        section_id=section_id,
        corridor_m=corridor_m if section_id is not None else None,
        holes=output,
        rejected_rows=rejected,
        summary=schemas.BlastHoles3DSummary(
            total_loaded=len(records), drawable=counts["complete_geometry"] + counts["collar_only"],
            complete_geometry=counts["complete_geometry"], collar_only=counts["collar_only"],
            without_geometry=counts["without_geometry"],
            rejected=_rejected_source_row_count(settings, rejected),
        ),
    )


@router.get("/holes/3d", response_model=schemas.BlastHoles3DResponse)
async def get_blast_holes_3d(
    request: Request,
    section_id: Optional[int] = Query(default=None, ge=0),
    corridor_m: float = Query(default=10.0, ge=0.0, le=10000.0),
) -> schemas.BlastHoles3DResponse:
    """Return compact collar/toe coordinates and provenance for the session."""
    session_id = request.state.session_id
    settings = db.get_settings(session_id) or {}
    section = None
    if section_id is not None:
        section_rows = db.get_sections(session_id)
        if section_id >= len(section_rows):
            raise HTTPException(404, detail={"error_code": "SECTION_NOT_FOUND"})
        try:
            from api.routers.process import _section_from_dict

            section = _section_from_dict(section_rows[section_id])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(400, detail={"error_code": "SECTION_INVALID"}) from exc
    return await _run_in_executor(
        _build_holes_3d, settings, session_id, section, corridor_m, section_id
    )
