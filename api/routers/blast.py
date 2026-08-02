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
from core.geometry_contract import (
    GeometryConfiguration,
    GeometryConfigurationError,
)

logger = logging.getLogger(__name__)


def _run_in_executor(func, *args):
    """Schedule a CPU/IO-bound callable on the default executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, func, *args)


router = APIRouter(prefix="/blast", tags=["blast"])

_LENGTH_CANDIDATES = ("Len", "longitud_real", "Longitud", "Length", "Profundidad")
_TACO_CANDIDATES = ("Taco_m", "Taco", "Stemming")


def _read_uploaded_csv(file: UploadFile) -> pd.DataFrame:
    """Read an uploaded CSV file into a DataFrame (HTTP 400 on parse error)."""
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
    )


# ---------------------------------------------------------------------------
# Geometric configuration builder (remediación 4.1 — single source of truth)
# ---------------------------------------------------------------------------


def _build_geometry_configuration(
    *,
    geometry_user_confirmed: Optional[bool],
    incl_convention: Optional[str],
    incl_sign_convention: Optional[str],
    sign_source_rule: Optional[str],
    incl_unit: Optional[str],
    az_convention: Optional[str],
    az_unit: Optional[str],
    incl_source_column: str = "",
    az_source_column: str = "",
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
        geometry_user_confirmed=geometry_user_confirmed,
        inclination_source_column=incl_source_column,
        inclination_convention=_upper(incl_convention),
        inclination_sign_convention=_upper(incl_sign_convention),
        inclination_unit=_upper(incl_unit),
        inclination_source_rule=sign_source_rule or "",
        azimuth_source_column=az_source_column,
        azimuth_convention=_upper(az_convention),
        azimuth_unit=_upper(az_unit),
    )


# ---------------------------------------------------------------------------
# Structured upload result (remediación 4.2 — direct processor output)
# ---------------------------------------------------------------------------


def _build_upload_payload(
    file_bytes: bytes,
    config: GeometryConfiguration,
    bench_height_m: Optional[float],
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

    # Enrichment runs over the accepted frame only. Failures here are
    # non-fatal — the canonical result is preserved either way. The
    # enriched data is merged BACK into result.accepted_rows so the
    # canonical list reflects the additional carga/descarga columns.
    df_clean = result.accepted_dataframe
    if df_clean is not None and not df_clean.empty:
        try:
            df_clean = enrich_blast_dataframe(df_clean)
        except Exception as exc:
            logger.warning("Blast enrichment failed: %s", exc)
        try:
            from ui.modulo_tronadura.warnings import collect_data_warnings
            df_clean = collect_data_warnings(df_clean, attach=True)
        except Exception as exc:
            logger.warning("Blast warnings attachment failed: %s", exc)
        # Re-build accepted_rows with the enriched columns and refresh
        # structured warnings (integración §5.9 — warnings survive as
        # structured objects, never as a collapsed string).
        from core.calculo_tronadura import (
            _df_to_accepted_records,
            _collect_structured_warnings,
        )
        result.accepted_rows = _df_to_accepted_records(df_clean)
        result.event_warnings = _collect_structured_warnings(df_clean)
        carga_mean = _safe_mean(_compute_carga_series(df_clean))
        descarga_mean = _safe_mean(_compute_descarga_series(df_clean))
        hardness_dist = _hardness_distribution(df_clean)
        data_warnings_text = (
            str(df_clean["data_warnings"].iloc[0]) if "data_warnings" in df_clean.columns else ""
        )
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
    summary["geometry_configuration"] = config.to_dict()
    summary["blocking_errors"] = result.blocking_errors


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
    file: UploadFile = File(..., description="Blast-hole CSV"),
    session_id: str = Form(..., description="Session UUID"),
    geometry_user_confirmed: Optional[bool] = Form(
        None,
        description="OBLIGATORIO: el evento debe declarar true (confirmado por el operador). "
        "false/ausente/None bloquean la geometría.",
    ),
    incl_convention: Optional[str] = Form(
        None,
        description="OBLIGATORIO: from_vertical | dip_from_horizontal (sin default)",
    ),
    bench_height_m: Optional[float] = Form(
        None, description="Altura de banco confirmada del evento (m)"
    ),
    az_convention: Optional[str] = Form(
        None,
        description="OBLIGATORIO: CLOCKWISE_FROM_NORTH | COUNTERCLOCKWISE_FROM_NORTH | "
        "CLOCKWISE_FROM_EAST | COUNTERCLOCKWISE_FROM_EAST (sin default)",
    ),
    incl_sign_convention: Optional[str] = Form(
        None,
        description="OBLIGATORIO: ABSOLUTE_VALUE | NEGATIVE_IS_DOWNWARD_DIP | SOURCE_DEFINED (sin default)",
    ),
    sign_source_rule: Optional[str] = Form(
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
    if not session_id.strip():
        raise HTTPException(422, "session_id is required")

    try:
        # Resolución de aliases legacy: inclination_source_column y
        # azimuth_source_column son los nombres v2 canónicos; los alias
        # incl_source_column / az_source_column se aceptan como fallback
        # documentado pero NUNCA sobrescriben a los v2.
        final_incl_col = inclination_source_column or (incl_source_column or "")
        final_az_col = azimuth_source_column or (az_source_column or "")
        # Unidades v2 independientes; angle_unit es legacy y sólo aplica
        # cuando ambos campos v2 están ausentes.
        final_incl_unit = inclination_unit
        final_az_unit = azimuth_unit
        if inclination_unit is None and azimuth_unit is None and angle_unit is not None:
            final_incl_unit = angle_unit
            final_az_unit = angle_unit
        config = _build_geometry_configuration(
            geometry_user_confirmed=geometry_user_confirmed,
            incl_convention=incl_convention,
            incl_sign_convention=incl_sign_convention,
            sign_source_rule=sign_source_rule,
            incl_unit=final_incl_unit,
            az_convention=az_convention,
            az_unit=final_az_unit,
            incl_source_column=final_incl_col,
            az_source_column=final_az_col,
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

    try:
        payload = await _run_in_executor(_build_upload_payload, content, config, bench_height_m)
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
    return response_body


def _build_hole_summaries(records: List[Dict[str, object]]) -> List[schemas.BlastHoleSummary]:
    return [_record_to_summary(record) for record in records]


# ---------------------------------------------------------------------------
# GET /blast/{session_id}/holes
# ---------------------------------------------------------------------------


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
