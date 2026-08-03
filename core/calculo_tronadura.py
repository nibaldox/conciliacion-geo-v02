"""
Drill & Blast (Tronadura) processing logic.

Pure math functions — no Streamlit or Plotly dependencies.
Receives DataFrames, returns DataFrames and numpy arrays.

Columnas descartadas al procesar (según descripción ENAEX):
  id_rajo, id_malla_opit, numero, camion,
  holes_dateUpdated, mes_tronadura

Identificadores preservados (trazabilidad pozos→bancos):
  uniqid, id_pozo
"""
import numpy as np
import pandas as pd
from datetime import timedelta
from core.config import DEFAULTS
from core.geom_utils import find_df_column
from core.geometry_conventions import (
    AzimuthConvention,
    InclinationConvention,
    SignConvention,
    normalize_azimuth,
    normalize_inclination,
    normalize_vector_components,
)
from core.geometry_contract import (
    GEOMETRY_CONFIGURATION_VERSION,
    GeometryConfiguration,
    GeometryConfigurationError,
)
from core.processing_result import ProcessingResult

COLS_DROP = [
    'id_rajo', 'id_malla_opit', 'numero',
    'camion', 'holes_dateUpdated', 'mes_tronadura',
]

# Legacy alias for the configured default bench height (H-06): the
# productive paths resolve the height from the event or the visible
# configuration; this constant exists only for backward-compatible
# callers/tests of the original +15 m transformation.
BENCH_HEIGHT = DEFAULTS.blast_default_bench_height

# Semantics of the elevation source column (spec §4.2). ``bench_elevation``
# means the column holds the target bench elevation (Nombre_Banco) and the
# collar sits BENCH_HEIGHT above it; ``collar_elevation`` means the column
# already holds the real collar elevation (no transformation).
# Generic names (Z, Elevation, Elev, Cota) are deliberately NOT classified:
# their meaning cannot be guaranteed, so they block the pipeline (H-07).
_Z_BENCH_ALIASES = {"nombre_banco", "banco", "banco_cota", "cota_banco", "bench", "bench_elev"}
_Z_COLLAR_ALIASES = {"cota_collar", "collar_elev", "z_collar", "rl_collar", "collar_z", "z_collar_real", "cota_collar_real"}
_Z_AMBIGUOUS_ALIASES = {"z", "elevation", "elev", "cota", "altura", "nivel", "rango"}


_CANONICAL_COLUMN_ALIASES: dict[str, list[str]] = {
    "X": ["Latitud_Geo", "Latitud", "X", "Este"],
    "Y": ["Longitud_Geo", "Longitud", "Y", "Norte"],
    "Z_collar": ["Nombre_Banco", "Banco", "Cota_Collar", "Z", "Altura_Collar", "Elevacion_Collar", "Elevation", "Elev", "Cota"],
    "Incl": ["Inclinacion_real", "Inclinacion", "Inclination"],
    "Az": ["Azimuth_real", "Azimuth", "Azimut"],
    "Len": ["longitud_real", "Longitud", "Length", "Profundidad"],
    "Burden": ["Burden", "Burden_Real", "Burden_diseno", "B"],
    "Esp": ["Espaciamiento", "Espaciamiento_Real", "Espaciamiento_diseno", "S", "Esp"],
    "Diam_mm": ["Diametro", "Diametro_pozo", "Diametro_perforacion", "D_mm", "Diam_mm"],
    "Tipo_Explosivo": ["Tipo_Explosivo", "Explosivo", "Tipo_explosivo", "Nombre", "nombre"],
    "Taco_m": ["Taco", "Taco_m", "Stemming", "stemming_real"],
    "Secuencia": ["Secuencia", "Secuencia_Iniciacion", "Detonador_Nro"],
    "Retardo_ms": ["Retardo_ms", "Delay_ms", "Tiempo_Retardo"],
    "Fila": ["Numero_Fila", "Fila_Pozo", "Row"],
    "Carga_Fondo_kg": ["Carga_Fondo_kg", "Kilos_Fondo", "Bottom_Charge"],
    "Carga_Columna_kg": ["Carga_Columna_kg", "Kilos_Columna"],
    "Longitud_Carga_m": ["Longitud_Carga_m", "Charge_Length"],
    "Tipo_Pozo": ["Tipo_Pozo", "Hole_Type"],
    "Az_Diseno": ["Azimuth_Diseno", "Design_Azimuth"],
    "Incl_Diseno": ["Inclinacion_Diseno", "Design_Dip"],
}


def _resolve_column_aliases(df_work: pd.DataFrame) -> dict[str, str | None]:
    """Return {canonical: original_column_name | None} for each known field.

    ``find_df_column`` raises when no alias is found unless
    ``raise_error=False`` is passed. We pass it for every optional
    field so the same loop works for both required and optional.
    """
    out: dict[str, str | None] = {}
    _REQUIRED_CANONICAL = {"X", "Y", "Z_collar", "Incl", "Az", "Len"}
    for canonical, aliases in _CANONICAL_COLUMN_ALIASES.items():
        required = canonical in _REQUIRED_CANONICAL
        # raise_error=True means "raise if no match". Required fields
        # should raise, optional ones should return None silently.
        out[canonical] = find_df_column(
            df_work, aliases, raise_error=required,
        )
    return out


def _rename_to_canonical(
    df_work: pd.DataFrame, resolved: dict[str, str | None],
) -> pd.DataFrame:
    """Build the rename map from resolved aliases and apply it.

    Tracks the original Z_collar (Nombre_Banco) as Banco_Original so
    downstream modules can recover the target bench.
    """
    if resolved.get("Z_collar"):
        df_work["Banco_Original"] = df_work[resolved["Z_collar"]]

    rename_map: dict[str, str] = {
        resolved["X"]: "X",
        resolved["Y"]: "Y",
        resolved["Z_collar"]: "Z_collar",
        resolved["Incl"]: "Incl",
        resolved["Az"]: "Az",
        resolved["Len"]: "Len",
    }
    for canonical in _CANONICAL_COLUMN_ALIASES:
        if canonical in rename_map:
            continue
        orig = resolved.get(canonical)
        if orig:
            rename_map[orig] = canonical
    return df_work.rename(columns=rename_map)


def _coerce_typed_columns(df_work: pd.DataFrame) -> None:
    """Mutate ``df_work`` in place, coercing numeric and int columns.

    Numeric columns get ``pd.to_numeric(errors='coerce')`` so that
    unparseable values become NaN instead of raising. Sequence/row
    columns become Int64 (nullable integer) for the typical IDs.
    """
    numeric = (
        "X", "Y", "Z_collar", "Incl", "Az", "Len",
        "Burden", "Esp", "Diam_mm", "Taco_m",
        "Retardo_ms", "Carga_Fondo_kg", "Carga_Columna_kg",
        "Longitud_Carga_m", "Az_Diseno", "Incl_Diseno",
    )
    for col in numeric:
        if col in df_work.columns:
            df_work[col] = pd.to_numeric(df_work[col], errors="coerce")
    for col in ("Secuencia", "Fila"):
        if col in df_work.columns:
            df_work[col] = pd.to_numeric(df_work[col], errors="coerce").astype("Int64")
    for col in ("uniqid", "id_pozo"):
        if col in df_work.columns:
            df_work[col] = df_work[col].astype(str)


def _hole_id_for_row(df_work: pd.DataFrame, idx) -> str:
    """Resolve a stable hole_id for a row (used by rejection tracking)."""
    for col in ("label_pozo", "id_pozo", "uniqid", "hole_id", "Hole_ID"):
        if col in df_work.columns:
            v = df_work.loc[idx, col]
            if v is not None and str(v) != "nan":
                return str(v)
    return str(idx)


def _collect_rejected_rows(
    df_work: pd.DataFrame,
    source_map: dict[str, str] | None = None,
) -> list[dict]:
    """Build structured per-row rejection records BEFORE any dropna().

    Remediación 3.2 / 4.2: each rejection preserves the full diagnosis
    (hole_id, source_row_index, source_column, original_value, error_code,
    rejection_reason, affected_calculations, recommended_action,
    row_processing_status). Multiple errors per row are emitted as
    multiple records. The original frame is NOT mutated and rows are NOT
    dropped here — the caller drops them after collecting this list.

    ``source_map`` (optional) maps canonical → original column names so
    the ``source_column`` field cites the column the operator sees in
    their source file (e.g. ``Latitud_Geo`` instead of ``X``).

    The legacy scalar summary (``processing_rejected_ids`` /
    ``processing_rejected_reasons``) is still produced for backward
    compatibility with older consumers, but the authoritative structure
    is the list returned here.
    """
    src_map = source_map or {}
    rejections: list[dict] = []

    def _source_col(canonical: str) -> str:
        return src_map.get(canonical, canonical)

    def _sanitized(value) -> object:
        # NaN/inf are not JSON-compliant; numpy types are not JSON-serializable.
        # Surface them as None / native Python so the structured rejection
        # always serializes cleanly (remediación 4.2).
        if value is None:
            return None
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            f = float(value)
            return f if np.isfinite(f) else None
        try:
            f = float(value)
        except (TypeError, ValueError):
            # Non-numeric string values: keep as-is when JSON-safe.
            return value if isinstance(value, (str, bool)) else str(value)
        return f if np.isfinite(f) else None

    seen: dict[tuple, int] = {}

    def _add(idx, column, original, error_code, reason, affected, action):
        key = (idx, column, error_code)
        if key in seen:
            return
        seen[key] = 1
        rejections.append({
            "hole_id": _hole_id_for_row(df_work, idx),
            "source_row_index": int(idx) if isinstance(idx, (np.integer, int)) else str(idx),
            "source_column": column,
            "original_value": _sanitized(original),
            "error_code": error_code,
            "rejection_reason": reason,
            "affected_calculations": affected,
            "recommended_action": action,
            "row_processing_status": "rejected",
        })

    # Required canonical columns checked for NaN / non-numeric values.
    # ``Incl`` is normalized before this function runs; a row whose
    # original inclination is out of range ends up with Incl=NaN after
    # normalization. To avoid duplicating the rejection (INVALID_Incl +
    # INCL_OUT_OF_RANGE for the same row), the Incl NaN check excludes
    # rows whose ``Incl_original`` is already flagged as out-of-range.
    incl_oob: set = set()
    if "Incl_original" in df_work.columns:
        incl_orig = pd.to_numeric(df_work["Incl_original"], errors="coerce")
        incl_oob = set(df_work.index[incl_orig.abs() > 90.0].tolist())

    for col in ("X", "Y", "Z_collar", "Incl", "Az", "Len"):
        if col not in df_work.columns:
            continue
        vals = pd.to_numeric(df_work[col], errors="coerce")
        for idx in df_work.index[vals.isna()]:
            if col == "Incl" and idx in incl_oob:
                continue  # already flagged as INCL_OUT_OF_RANGE below
            orig = df_work.loc[idx, col]
            _add(
                idx, _source_col(col), orig,
                error_code=f"INVALID_{col}",
                reason=f"valor no numérico o ausente en {col} (original: {orig!r})",
                affected="toe, PF, geometría dependiente",
                action="Corrija el dato original y reprocese.",
            )
    if "Len" in df_work.columns:
        lens = pd.to_numeric(df_work["Len"], errors="coerce")
        for idx in df_work.index[(lens <= 0) & lens.notna()]:
            _add(
                idx, "Len", lens.loc[idx],
                error_code="INVALID_LEN_NON_POSITIVE",
                reason=f"longitud inválida (Len={lens.loc[idx]} <= 0)",
                affected="toe, PF, geometría dependiente",
                action="Corrija la longitud y reprocese.",
            )
    if "Incl_original" in df_work.columns:
        incls = pd.to_numeric(df_work["Incl_original"], errors="coerce")
        for idx in df_work.index[incls.abs() > 90.0]:
            _add(
                idx, "Incl", incls.loc[idx],
                error_code="INCL_OUT_OF_RANGE",
                reason=(
                    f"inclinación fuera de rango (original: {incls.loc[idx]}°); "
                    "fila excluida de la geometría (cálculos bloqueados)"
                ),
                affected="toe, PF, geometría dependiente",
                action="Corrija la inclinación y reprocese.",
            )
    return rejections


def _record_rejected_rows(df_work: pd.DataFrame) -> None:
    """Backward-compatible scalar rejection summary.

    Remediación 3.2 / 4.2: this is now a THIN legacy adapter over
    :func:`_collect_rejected_rows`. New consumers read the structured list
    returned by ``procesar_pozos`` directly; this scalar summary exists
    only so older code that reads ``processing_rejected_ids`` keeps
    working.
    """
    rejections = _collect_rejected_rows(df_work)
    n_received = len(df_work)
    ids = [r["hole_id"] for r in rejections]
    reasons = [r["rejection_reason"] for r in rejections]
    df_work["processing_rows_received"] = n_received
    df_work["processing_rows_accepted"] = n_received - len(set(ids))
    df_work["processing_rows_rejected"] = len(set(ids))
    df_work["processing_rejected_ids"] = ",".join(ids)
    df_work["processing_rejected_reasons"] = " | ".join(reasons)


def _resolve_z_collar_semantic(source_col: str | None, explicit: str | None) -> str:
    """Classify the elevation column semantics (spec §4.2).

    Returns 'bench_elevation' (column holds target bench elevation, add
    bench height) or 'collar_elevation' (column already holds the real
    collar elevation, no transformation).

    When the source column name is not recognised and no explicit
    semantic is given, raises ValueError: the pipeline must stop and ask
    for confirmation instead of guessing.
    """
    if explicit is not None:
        if explicit not in ("bench_elevation", "collar_elevation"):
            raise ValueError(
                f"z_collar_semantic inválido: {explicit!r}. Use 'bench_elevation' "
                "o 'collar_elevation'."
            )
        return explicit
    if source_col is None:
        raise ValueError(
            "No se pudo determinar la semántica de la columna de elevación: "
            "no hay columna fuente. Especifique z_collar_semantic."
        )
    key = source_col.strip().lower()
    if key in _Z_BENCH_ALIASES:
        return "bench_elevation"
    if key in _Z_COLLAR_ALIASES:
        return "collar_elevation"
    if key in _Z_AMBIGUOUS_ALIASES:
        raise ValueError(
            f"La columna de elevación '{source_col}' es ambigua (puede ser cota "
            "de banco, piso o diseño): no se determina su semántica y no se "
            "convierte a collar automáticamente (H-07). Especifique "
            "z_collar_semantic='bench_elevation' o 'collar_elevation'."
        )
    raise ValueError(
        f"No se pudo determinar la semántica de la columna de elevación "
        f"'{source_col}': no sé si es cota de banco o cota real de collar. "
        "Especifique z_collar_semantic='bench_elevation' o 'collar_elevation'."
    )


def _compute_hole_toes(df_work: pd.DataFrame) -> None:
    """Add X_toe / Y_toe / Z_toe columns using canonical Incl/Az/Length.

    ``Incl`` / ``Az`` must already be normalized (see
    :func:`core.geometry_conventions`). The unit vector points from the
    collar to the toe (downwards along the hole axis), so the toe is
    ``collar + length × dir``.
    """
    length = df_work["Len"].values.astype(float)
    vx, vy, vz = normalize_vector_components(df_work["Incl"], df_work["Az"])
    df_work["X_toe"] = df_work["X"] + length * vx
    df_work["Y_toe"] = df_work["Y"] + length * vy
    df_work["Z_toe"] = df_work["Z_collar"] + length * vz


def _build_scatter_lines(
    df_work: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (x_lines, y_lines, z_lines) where each hole is encoded
    as 3 points: (collar, toe, None). Plotly treats the None as a
    line break, so a single trace draws all trajectories."""
    x_collar = df_work["X"].values.astype(float)
    y_collar = df_work["Y"].values.astype(float)
    z_collar = df_work["Z_collar"].values.astype(float)
    x_toe = df_work["X_toe"].values.astype(float)
    y_toe = df_work["Y_toe"].values.astype(float)
    z_toe = df_work["Z_toe"].values.astype(float)

    n = len(df_work)
    x_lines = np.empty(n * 3, dtype=object)
    y_lines = np.empty(n * 3, dtype=object)
    z_lines = np.empty(n * 3, dtype=object)
    for i in range(n):
        j = i * 3
        x_lines[j] = x_collar[i]
        x_lines[j + 1] = x_toe[i]
        x_lines[j + 2] = None
        y_lines[j] = y_collar[i]
        y_lines[j + 1] = y_toe[i]
        y_lines[j + 2] = None
        z_lines[j] = z_collar[i]
        z_lines[j + 1] = z_toe[i]
        z_lines[j + 2] = None
    return x_lines, y_lines, z_lines


def procesar_pozos(
    df: pd.DataFrame,
    column_map: dict[str, str | None] | None = None,
    *,
    bench_height_m: float | None = None,
    z_collar_semantic: str | None = None,
    incl_convention: InclinationConvention | str | None = None,
    az_convention: AzimuthConvention | str = AzimuthConvention.CLOCKWISE_FROM_NORTH,
    incl_sign_convention: SignConvention | str = SignConvention.ABSOLUTE_VALUE,
    sign_source_rule: str | None = None,
    angle_unit: str = "degrees",
    geometry_user_confirmed: bool | None = None,
    geometry_configuration: GeometryConfiguration | None = None,
    return_rejections: bool = False,
    return_result: bool = False,
):
    """Process a blast-hole report DataFrame into collar/toe 3D coordinates.

    Coordinate handling (spec §4.2):
        X = Latitud_Geo  (East)
        Y = Longitud_Geo (North)
        Z = elevation column, transformed only when its semantic is
            known:
            - bench_elevation (e.g. Nombre_Banco): the column holds the
              target bench elevation; the collar sits ``bench_height_m``
              metres above it ONLY when a valid, user-confirmed height
              is provided (event value, validated dataset column, or an
              authorised explicit assumption). There is NO automatic
              default: without a confirmed height the elevation is left
              untransformed (``bench_elevation_untransformed``) and the
              dependent geometry (toe) is blocked.
            - collar_elevation (e.g. Cota_Collar): the column already
              holds the real collar elevation; no transformation.
            Ambiguous source names raise ValueError (the pipeline stops
            instead of guessing) unless ``z_collar_semantic`` is given.

    Geometric configuration (remediación 4.1): callers SHOULD pass a
    validated :class:`GeometryConfiguration`. When provided, it takes
    precedence over the legacy keyword arguments and is the single
    source of truth. When absent, the legacy ``geometry_user_confirmed``
    argument is still honored for backward compatibility, but no silent
    defaults are applied — incomplete configuration raises.

    Returns
    -------
    df_clean : pd.DataFrame
        Accepted rows with all derived geometry columns.
    x_lines, y_lines, z_lines : np.ndarray
        1-D arrays encoding (collar, toe, None) per hole.
    rejected_rows : list[dict], optional (when ``return_rejections=True``)
        Structured per-row rejection records preserved BEFORE dropna().
        Each record carries hole_id / source_row_index / source_column /
        original_value / error_code / rejection_reason /
        affected_calculations / recommended_action / row_processing_status.
    """
    df_work = df.copy()

    drop_present = [c for c in COLS_DROP if c in df_work.columns]
    df_work.drop(columns=drop_present, inplace=True)

    # Remediación 4.1 + integración 3.3/3.4/3.5: single source of truth.
    # When a GeometryConfiguration is provided it takes precedence and is
    # validated centrally (version + non-empty source columns + independent
    # units). Otherwise we honor the legacy keyword arguments, but NEVER
    # invent a default: geometry_user_confirmed is None/False or missing
    # required fields ⇒ BLOCK.
    if geometry_configuration is not None:
        geometry_configuration.validate()
        geometry_user_confirmed = geometry_configuration.geometry_user_confirmed
        # Translate the canonical contract values back to the enum-accepted
        # lowercase strings consumed by the existing normalization code.
        _INCL_CONTRACT_TO_ENUM = {
            "FROM_VERTICAL": "from_vertical",
            "DIP_FROM_HORIZONTAL": "dip_from_horizontal",
        }
        if geometry_configuration.inclination_convention:
            incl_convention = _INCL_CONTRACT_TO_ENUM[
                geometry_configuration.inclination_convention
            ]
        if geometry_configuration.inclination_sign_convention:
            incl_sign_convention = geometry_configuration.inclination_sign_convention
        sign_source_rule = geometry_configuration.inclination_source_rule or None
        if geometry_configuration.azimuth_convention:
            az_convention = geometry_configuration.azimuth_convention
        # INTEGRACIÓN 3.5: inclination and azimuth units are INDEPENDENT.
        # Resolve each one separately; the legacy ``angle_unit`` kwarg is
        # only kept for backward compatibility with callers that do not
        # pass a contract and is NEVER applied to confirmed v2 contracts.
        incl_angle_unit = geometry_configuration.inclination_unit_canonical()
        az_angle_unit = geometry_configuration.azimuth_unit_canonical()
        angle_unit = incl_angle_unit  # kept as a hint for legacy code paths
    else:
        # Remediación 3.1: legacy path still enforces explicit confirmation.
        # No dataset column is treated as implicit confirmation: only
        # ``geometry_user_confirmed is True`` enables geometry.
        if geometry_user_confirmed is False:
            raise GeometryConfigurationError(
                "Configuración geométrica rechazada (geometry_user_confirmed=False): "
                "el cálculo de toe y geometría dependiente está bloqueado.",
                error_code="GEOMETRY_REJECTED",
                details={"state": "REJECTED"},
            )
        if geometry_user_confirmed is None:
            raise GeometryConfigurationError(
                "Configuración geométrica no confirmada (geometry_user_confirmed=None): "
                "el cálculo de toe y geometría dependiente está bloqueado. "
                "Construya y valide un GeometryConfiguration antes de procesar.",
                error_code="GEOMETRY_NOT_CONFIRMED",
                details={"state": "LEGACY_UNCONFIRMED"},
            )

    if "fecha_tronadura" in df_work.columns:
        df_work["fecha_tronadura"] = pd.to_datetime(
            df_work["fecha_tronadura"], errors="coerce"
        ).dt.date

    # The elevation source column is captured BEFORE any rename so the
    # bench/collar semantics can be classified (spec §4.2).
    if column_map is not None:
        z_src = column_map.get("Z_collar")
        incl_src = column_map.get("Incl")
        az_src = column_map.get("Az")
        from core.column_mapping import apply_mapping
        df_work = apply_mapping(df_work, column_map)
    else:
        resolved = _resolve_column_aliases(df_work)
        z_src = resolved.get("Z_collar")
        incl_src = resolved.get("Incl")
        az_src = resolved.get("Az")
        df_work = _rename_to_canonical(df_work, resolved)

    # INTEGRACIÓN 3.4: when a v2 contract is provided the source columns
    # declared in it MUST exist in the dataset (no autodetection after
    # confirmation). The autodetected ``incl_src``/``az_src`` above are
    # only kept as a SUGGESTION — never used as a value source unless the
    # contract explicitly accepts them (by declaring the same column name).
    if geometry_configuration is not None:
        cfg_incl_col = geometry_configuration.inclination_source_column
        cfg_az_col = geometry_configuration.azimuth_source_column
        if cfg_incl_col and cfg_incl_col not in df.columns:
            raise GeometryConfigurationError(
                f"La columna fuente de inclinación declarada "
                f"{cfg_incl_col!r} no existe en el dataset.",
                error_code="INCLINATION_SOURCE_COLUMN_NOT_FOUND",
                details={"declared": cfg_incl_col, "available": list(df.columns)},
            )
        if cfg_az_col and cfg_az_col not in df.columns:
            raise GeometryConfigurationError(
                f"La columna fuente de azimut declarada "
                f"{cfg_az_col!r} no existe en el dataset.",
                error_code="AZIMUTH_SOURCE_COLUMN_NOT_FOUND",
                details={"declared": cfg_az_col, "available": list(df.columns)},
            )
        # The declared column is the value source — override the
        # autodetected alias so the persisted provenance matches what the
        # operator selected in the UI.
        incl_src = cfg_incl_col
        az_src = cfg_az_col

    # Trazabilidad pozos→bancos en conciliación geométrica:
    if "uniqid" not in df_work.columns:
        df_work["uniqid"] = (df_work.index + 1).astype(str)

    _coerce_typed_columns(df_work)

    # Canonical inclination / azimuth normalization (spec §4.1, H-05,
    # cierre final §2.2 + integración 3.5). The inclination convention is
    # MANDATORY and must come from the contract or the legacy kwarg; a
    # data-declared ``Incl_convention`` column is only honored when the
    # operator already confirmed the geometry via ``geometry_user_confirmed
    # is True`` (this is NOT implicit confirmation).
    az_conv = AzimuthConvention(az_convention)
    if "Incl" in df_work.columns:
        df_work["Incl_original"] = df_work["Incl"]
        if incl_convention is not None:
            incl_conv = InclinationConvention(incl_convention)
            source, user_confirmed = "explicit", True
        elif (
            geometry_user_confirmed is True
            and "Incl_convention" in df_work.columns
        ):
            incl_conv = InclinationConvention(df_work["Incl_convention"].iloc[0])
            source, user_confirmed = "data", True
        else:
            raise GeometryConfigurationError(
                "Convención de inclinación no declarada explícitamente: no se "
                "puede calcular toe ni geometría dependiente. Construya y valide "
                "un GeometryConfiguration con inclination_convention.",
                error_code="INCL_CONVENTION_MISSING",
                details={"missing": "inclination_convention"},
            )
        # INTEGRACIÓN 3.5: the INDEPENDENT inclination unit is used here.
        # When the contract is present we read its own unit; otherwise we
        # fall back to the legacy ``angle_unit`` kwarg (kept for callers
        # that haven't migrated to the contract yet).
        _incl_unit = (
            geometry_configuration.inclination_unit_canonical()
            if geometry_configuration is not None
            else angle_unit
        )
        if _incl_unit == "radians":
            incl_raw = np.degrees(df_work["Incl"].astype(float))
            conversion_unit = "radians->degrees"
        elif _incl_unit == "degrees":
            incl_raw = df_work["Incl"]
            conversion_unit = "none"
        else:
            raise GeometryConfigurationError(
                f"angle_unit inválido: {_incl_unit!r} (use 'degrees' o 'radians')",
                error_code="GEOMETRY_INCOMPLETE",
                details={"invalid_unit": _incl_unit},
            )
        incl_norm, incl_meta = normalize_inclination(
            incl_raw, incl_conv,
            sign_convention=incl_sign_convention,
            sign_source_rule=sign_source_rule,
        )
        df_work["Incl"] = incl_norm
        df_work["Incl_convention"] = incl_conv.value
        df_work["Incl_convention_source"] = source
        df_work["incl_convention_warning"] = False
        # Provenance columns carry the v2 contract version (single source
        # of truth) and the ACTUAL source column declared by the operator.
        df_work["inclination_original"] = df_work["Incl_original"]
        df_work["inclination_source_column"] = incl_src or ""
        df_work["inclination_convention_original"] = incl_conv.value
        df_work["inclination_sign_convention"] = incl_meta.get("sign_convention", str(incl_sign_convention))
        df_work["inclination_sign_applied"] = incl_meta.get("sign_applied", "none")
        df_work["inclination_source_rule"] = sign_source_rule or ""
        df_work["inclination_unit_original"] = _incl_unit
        df_work["inclination_normalized_from_vertical"] = incl_norm
        df_work["inclination_normalized_from_vertical_deg"] = incl_norm
        _conv_meta = incl_meta.get("conversion", "none")
        df_work["inclination_conversion_applied"] = (
            f"{conversion_unit}+{_conv_meta}" if conversion_unit != "none" and _conv_meta != "none"
            else (conversion_unit if conversion_unit != "none" else _conv_meta)
        )
        df_work["inclination_assumption_flag"] = False
        df_work["inclination_user_confirmed"] = bool(user_confirmed)
        if source == "data":
            df_work["inclination_validation_status"] = "DATA_DECLARED"
            df_work["inclination_validation_message"] = (
                "Convención declarada por el evento (columna Incl_convention)."
            )
        else:
            df_work["inclination_validation_status"] = "EXPLICIT"
            df_work["inclination_validation_message"] = (
                "Convención confirmada explícitamente por el caller."
            )
        df_work["inclination_validation_status"] = np.where(
            pd.to_numeric(df_work["Incl_original"], errors="coerce").abs() > 90.0,
            "OUT_OF_RANGE",
            df_work["inclination_validation_status"],
        )
        df_work["inclination_validation_message"] = np.where(
            pd.to_numeric(df_work["Incl_original"], errors="coerce").abs() > 90.0,
            "Valor fuera de rango (|inclinación| > 90°): fila marcada y descartada en "
            "los cálculos geométricos dependientes.",
            df_work["inclination_validation_message"],
        )
        orientation = np.asarray(incl_meta.get("orientation_sign", [0] * len(df_work)))
        df_work["incl_orientation"] = np.where(
            pd.to_numeric(df_work["Incl_original"], errors="coerce").notna(),
            orientation,
            0,
        )
        df_work["incl_anomaly"] = np.where(
            pd.to_numeric(df_work["Incl_original"], errors="coerce") < 0,
            "negative_wrapped",
            "",
        )
    if "Az" in df_work.columns:
        df_work["Az_original"] = df_work["Az"]
        # INTEGRACIÓN 3.5: the INDEPENDENT azimuth unit is used here.
        _az_unit = (
            geometry_configuration.azimuth_unit_canonical()
            if geometry_configuration is not None
            else angle_unit
        )
        if _az_unit == "radians":
            az_raw = np.degrees(df_work["Az"].astype(float))
            az_conversion_unit = "radians->degrees"
        else:
            az_raw = df_work["Az"]
            az_conversion_unit = "none"
        az_norm, az_meta = normalize_azimuth(az_raw, az_conv)
        df_work["Az"] = az_norm
        df_work["Az_convention"] = az_conv.value
        df_work["azimuth_original"] = df_work["Az_original"]
        df_work["azimuth_source_column"] = az_src or ""
        df_work["azimuth_convention_original"] = az_conv.value
        df_work["azimuth_unit_original"] = _az_unit
        df_work["azimuth_normalized_clockwise_from_north"] = az_norm
        df_work["azimuth_normalized_clockwise_from_north_deg"] = az_norm
        df_work["azimuth_conversion_applied"] = (
            f"{az_conversion_unit}+{az_meta.get('conversion', 'none')}"
            if az_conversion_unit != "none"
            else az_meta.get("conversion", "none")
        )
        df_work["azimuth_user_confirmed"] = bool(user_confirmed)
        df_work["azimuth_validation_status"] = (
            "DATA_DECLARED" if source == "data" else "EXPLICIT"
        )
        df_work["azimuth_validation_message"] = (
            "Azimut en grados horarios desde el Norte (canónico)."
        )

    if "Incl" in df_work.columns or "Az" in df_work.columns:
        # Auditoría §3.3 + integración 3.3: el contrato de configuración
        # geométrica serializable usa la ÚNICA versión canónica definida
        # en core.geometry_contract.GEOMETRY_CONFIGURATION_VERSION.
        df_work["geometry_user_confirmed"] = bool(geometry_user_confirmed)
        df_work["geometry_configuration_version"] = GEOMETRY_CONFIGURATION_VERSION

    # Elevation transformation driven by the column semantic (spec §4.2).
    # Cierre final §2.1: the transformation NEVER applies an unconfirmed
    # height — no automatic 15 m. Without a confirmed height the collar
    # elevation is left untransformed and dependent geometry is blocked.
    semantic = _resolve_z_collar_semantic(z_src, z_collar_semantic)
    _Z_TRANSFORM_BLOCKED = False
    if semantic == "bench_elevation":
        bh_from_col = (
            "bench_height_m" in df_work.columns
            and pd.to_numeric(df_work["bench_height_m"], errors="coerce").notna().any()
        )
        if bench_height_m is not None and float(bench_height_m) > 0:
            bench_h = float(bench_height_m)
            bh_status, bh_source, bh_assumed, bh_confirmed = (
                "PROVIDED", "event_provided", False, True,
            )
            bh_message = ""
        elif bh_from_col:
            bh_col = pd.to_numeric(df_work["bench_height_m"], errors="coerce")
            bench_h = bh_col
            bh_status, bh_source, bh_assumed, bh_confirmed = (
                "PROVIDED", "data_column", False, True,
            )
            bh_message = ""
        else:
            # No confirmed height: BLOCK the transformation (no automatic
            # value, no silent default). Z_collar stays as the source value
            # and the dependent geometry (toe) is not computed.
            _Z_TRANSFORM_BLOCKED = True
            df_work["bench_height_m"] = np.nan
            df_work["bench_height_status"] = "MISSING"
            df_work["bench_height_source"] = ""
            df_work["bench_height_assumption_flag"] = True
            df_work["bench_height_user_confirmed"] = False
            df_work["bench_height_validation_message"] = (
                "Altura de banco no confirmada: la cota de banco NO se transformó "
                "a collar (sin supuesto automático) y la geometría dependiente "
                "(toe) quedó bloqueada. Declare bench_height_m o autorice un "
                "supuesto explícito."
            )
        if not _Z_TRANSFORM_BLOCKED:
            df_work["Z_collar"] = df_work["Z_collar"] + bench_h
            df_work["Z_collar_semantic"] = "bench_elevation_plus_height"
            df_work["bench_height_m"] = bench_h
            df_work["bench_height_status"] = bh_status
            df_work["bench_height_source"] = bh_source
            df_work["bench_height_assumption_flag"] = bh_assumed
            df_work["bench_height_user_confirmed"] = bh_confirmed
            df_work["bench_height_validation_message"] = bh_message
        else:
            df_work["Z_collar_semantic"] = "bench_elevation_untransformed"
    else:
        df_work["Z_collar_semantic"] = "collar_elevation"

    # Auditoría §3.4 + remediación 3.2/4.2: structured per-row rejections
    # captured BEFORE dropna(). The legacy scalar summary is still written
    # for backward compatibility, but the structured list is the authority.
    src_map: dict[str, str] = {}
    if column_map is not None:
        for canon, orig in (column_map or {}).items():
            if orig:
                src_map[canon] = orig
    else:
        # ``resolved`` holds canonical → original-name captured before rename.
        for canon, orig in (resolved or {}).items():
            if orig:
                src_map[canon] = orig
    rejected_rows = _collect_rejected_rows(df_work, source_map=src_map)
    _record_rejected_rows(df_work)

    df_work = df_work.dropna(subset=["X", "Y", "Z_collar", "Incl", "Az", "Len"])
    df_work = df_work[df_work["Len"] > 0]

    _compute_hole_toes(df_work)
    if _Z_TRANSFORM_BLOCKED:
        blocked = df_work["Z_collar_semantic"] == "bench_elevation_untransformed"
        df_work.loc[blocked, ["X_toe", "Y_toe", "Z_toe"]] = np.nan
    df_work["row_processing_status"] = "accepted"
    df_work["row_rejection_reason"] = ""

    # Canonical ProcessingResult — born in the core, not the router. The
    # accepted_rows/rejected_rows dicts are the authority consumed by
    # API/UI/persistence/export. ``return_result=True`` is the v2 path;
    # ``return_rejections`` and the positional return stay as a thin
    # deprecated adapter for legacy callers (integración §5.7).
    if return_result:
        from core.blast_correlation import compute_powder_factor
        from core.blast_metrics import enrich_blast_dataframe
        df_work = compute_powder_factor(df_work, bench_height_m=bench_height_m)
        df_work = enrich_blast_dataframe(df_work)
        accepted_rows = _df_to_accepted_records(df_work)
        event_warnings = _collect_structured_warnings(df_work)
        spatial_diagnostics = _collect_spatial_diagnostics(df_work)
        cfg_dict = (
            geometry_configuration.to_dict()
            if geometry_configuration is not None
            else {
                "geometry_configuration_version": GEOMETRY_CONFIGURATION_VERSION,
                "geometry_user_confirmed": bool(geometry_user_confirmed),
            }
        )
        result = ProcessingResult.from_rejections(
            accepted_dataframe=df_work,
            accepted_rows=accepted_rows,
            rejected_rows=rejected_rows,
            event_warnings=event_warnings,
            spatial_diagnostics=spatial_diagnostics,
            geometry_configuration=cfg_dict,
            rows_received=len(df),
            scatter_lines=_build_scatter_lines(df_work),
        )
        return result
    if return_rejections:
        return df_work, *_build_scatter_lines(df_work), rejected_rows
    return df_work, *_build_scatter_lines(df_work)


def _df_to_accepted_records(df_work: pd.DataFrame) -> list[dict]:
    """Convert accepted rows to plain JSON-serializable dicts.

    This is the canonical accepted_rows list born in the core. Numpy
    scalars are coerced to native Python types; non-finite floats
    become None so the records always serialize cleanly.

    Integración §5.7: carga/descarga are computed HERE so the canonical
    list carries every derived field consumed by the API/UI/export.
    """
    if df_work is None or df_work.empty:
        return []
    import math
    from core.column_utils import KILOS_CANDIDATES, first_present_column

    _LENGTH_CANDIDATES_LOCAL = ("Len", "longitud_real", "Longitud", "Length", "Profundidad")
    _TACO_CANDIDATES_LOCAL = ("Taco_m", "Taco", "Stemming")

    def _carga_series(df: pd.DataFrame) -> "pd.Series":
        if "kg_per_meter" in df.columns:
            return pd.to_numeric(df["kg_per_meter"], errors="coerce")
        kg_col = first_present_column(df, KILOS_CANDIDATES)
        len_col = first_present_column(df, _LENGTH_CANDIDATES_LOCAL)
        if kg_col is None or len_col is None:
            import pandas as _pd
            return _pd.Series([float("nan")] * len(df), index=df.index, dtype=float)
        kilos = pd.to_numeric(df[kg_col], errors="coerce")
        length = pd.to_numeric(df[len_col], errors="coerce")
        import pandas as _pd
        out = _pd.Series([float("nan")] * len(df), index=df.index, dtype=float)
        valid = kilos.notna() & length.notna() & (length > 0)
        out.loc[valid] = kilos.loc[valid] / length.loc[valid]
        return out

    def _descarga_series(df: pd.DataFrame) -> "pd.Series":
        if "altura_carga_m" in df.columns:
            return pd.to_numeric(df["altura_carga_m"], errors="coerce")
        len_col = first_present_column(df, _LENGTH_CANDIDATES_LOCAL)
        taco_col = first_present_column(df, _TACO_CANDIDATES_LOCAL)
        if len_col is None or taco_col is None:
            import pandas as _pd
            return _pd.Series([float("nan")] * len(df), index=df.index, dtype=float)
        length = pd.to_numeric(df[len_col], errors="coerce")
        taco = pd.to_numeric(df[taco_col], errors="coerce")
        return (length - taco).clip(lower=0.0)

    carga_series = _carga_series(df_work)
    descarga_series = _descarga_series(df_work)

    out: list[dict] = []
    for idx, row in df_work.iterrows():
        record: dict = {}
        for col in df_work.columns:
            value = row[col]
            if isinstance(value, (np.integer,)):
                value = int(value)
            elif isinstance(value, (np.floating,)):
                f = float(value)
                value = f if math.isfinite(f) else None
            elif isinstance(value, float):
                value = value if math.isfinite(value) else None
            record[col] = value
        # Derived metrics required by BlastHoleSummary downstream.
        carga_val = carga_series.loc[idx] if idx in carga_series.index else float("nan")
        descarga_val = descarga_series.loc[idx] if idx in descarga_series.index else float("nan")
        record["carga"] = float(carga_val) if pd.notna(carga_val) else 0.0
        record["descarga"] = float(descarga_val) if pd.notna(descarga_val) else 0.0
        record["source_row_index"] = int(idx) if isinstance(idx, (np.integer, int)) else str(idx)
        record["row_processing_status"] = "accepted"
        out.append(record)
    return out


def _collect_structured_warnings(df_work: pd.DataFrame) -> list[dict]:
    """Build structured warnings directly from canonical diagnostic columns."""
    if df_work is None or df_work.empty:
        return []
    warnings: list[dict] = []

    def add(code: str, message: str, *, context: dict | None = None) -> None:
        warnings.append({
            "warning_code": code,
            "message": message,
            "hole_id": None,
            "source_row_index": None,
            "context": context or {},
        })

    if "bench_height_status" in df_work.columns:
        status = str(df_work["bench_height_status"].iloc[0])
        if status in {"MISSING", "INVALID", "EXPLICIT_ASSUMPTION"}:
            add(
                f"BENCH_HEIGHT_{status}",
                "La altura de banco requiere revisión antes de usar indicadores dependientes.",
                context={
                    "status": status,
                    "validation_message": str(
                        df_work.get("bench_height_validation_message", pd.Series([""])).iloc[0]
                    ),
                },
            )
    if "inclination_validation_status" in df_work.columns:
        invalid = df_work["inclination_validation_status"].astype(str) == "OUT_OF_RANGE"
        for idx in df_work.index[invalid]:
            add(
                "INCLINATION_OUT_OF_RANGE",
                "La inclinación está fuera del dominio geométrico permitido.",
                context={"value": df_work.loc[idx, "Incl_original"]},
            )
            warnings[-1]["source_row_index"] = int(idx) if isinstance(idx, (int, np.integer)) else str(idx)
    if "voronoi_conservation_ok" in df_work.columns and not bool(
        df_work["voronoi_conservation_ok"].iloc[0]
    ):
        add(
            "VORONOI_CONSERVATION_FAILED",
            "La conservación de área Voronoi falló; el PF por influencia está bloqueado.",
            context={
                "area_residual_pct": df_work.get("area_residual_pct", pd.Series([None])).iloc[0]
            },
        )
    if "explosive_status" in df_work.columns:
        counts = df_work["explosive_status"].astype(str).value_counts().to_dict()
        for status in ("UNKNOWN", "UNVALIDATED_REFERENCE"):
            count = int(counts.get(status, 0))
            if count:
                add(
                    f"EXPLOSIVE_{status}",
                    f"{count} pozo(s) tienen explosivo con estado {status}.",
                    context={"status": status, "count": count},
                )
    return warnings


def _collect_spatial_diagnostics(df_work: pd.DataFrame) -> dict:
    """Surface the actual spatial diagnostics columns from the accepted frame."""
    if df_work is None or df_work.empty:
        return {}
    diag: dict = {}
    for key in (
        "area_influence_m2",
        "area_status",
        "collar_domain_status",
        "domain_area_m2",
        "voronoi_conservation_ok",
        "area_residual_m2",
        "area_residual_pct",
        "clip_warning",
        "domain_error_code",
        "domain_validation_reason",
    ):
        if key in df_work.columns:
            series = df_work[key].dropna()
            if not series.empty:
                value = series.iloc[0]
                diag[key] = value.item() if isinstance(value, np.generic) else value
    row_fields = (
        "area_influence_m2",
        "area_status",
        "collar_domain_status",
    )
    present = [key for key in row_fields if key in df_work.columns]
    if present:
        rows = []
        for idx, row in df_work[present].iterrows():
            record = {
                "source_row_index": int(idx) if isinstance(idx, (int, np.integer)) else str(idx)
            }
            for key in present:
                value = row[key]
                if isinstance(value, np.generic):
                    value = value.item()
                if isinstance(value, float) and not np.isfinite(value):
                    value = None
                record[key] = value
            rows.append(record)
        diag["rows"] = rows
    return diag


def proyectar_pozos_en_seccion(
    df_pozos: pd.DataFrame,
    origin: np.ndarray,
    azimuth: float,
    length: float,
    tolerance: float = 10.0,
    fecha_corte: "str | None" = None,
) -> pd.DataFrame:
    """Project blast holes onto a section's coordinate system.

    For each hole, computes:
      - dist_perp: perpendicular distance to the section line at the collar (metres)
      - dist_perp_toe: perpendicular distance to the section line at the toe (metres)
      - dist_along: distance along the section axis from origin (metres)
      - closest_point: 'collar' or 'toe', whichever is closer to the section

    A hole is included when **either** its collar or its toe (or the
    midpoint between them) falls within `tolerance` metres perpendicular
    distance. The collar along-axis position is still used to filter the
    along-section range.

    Parameters
    ----------
    df_pozos  : DataFrame with columns X, Y, Z_collar, Z_toe, Len
                (output of procesar_pozos).
    origin    : np.ndarray [X, Y] section origin.
    azimuth   : degrees from North, clockwise.
    length    : section total length in metres.
    tolerance : max perpendicular distance to include a hole (default 10 m).
    fecha_corte : ISO date string (YYYY-MM-DD) of the topographic survey.
                If provided, holes whose ``fecha_tronadura`` is missing or
                strictly later than this date are dropped from the result
                (they cannot have caused damage captured by that survey).

    Returns
    -------
    DataFrame filtered and augmented with 'dist_along', 'dist_along_toe',
    'dist_perp', 'dist_perp_toe' and 'closest_point'.
    """
    if df_pozos.empty:
        return df_pozos

    if fecha_corte is not None and 'fecha_tronadura' in df_pozos.columns:
        try:
            cutoff = pd.to_datetime(fecha_corte).date()
            buffer_days = getattr(DEFAULTS, 'blast_temporal_filter_days', 7)
            cutoff = cutoff - timedelta(days=buffer_days)
            fecha_series = pd.to_datetime(
                df_pozos['fecha_tronadura'], errors='coerce'
            ).dt.date
            df_pozos = df_pozos[fecha_series.notna() & (fecha_series <= cutoff)]

            if df_pozos.empty:
                return df_pozos
        except (ValueError, TypeError):
            pass

    direction = np.array([np.sin(np.radians(azimuth)),
                          np.cos(np.radians(azimuth))])
    normal = np.array([direction[1], -direction[0]])

    dx_collar = df_pozos['X'].values - origin[0]
    dy_collar = df_pozos['Y'].values - origin[1]

    dist_along_collar = dx_collar * direction[0] + dy_collar * direction[1]
    dist_perp_collar = np.abs(dx_collar * normal[0] + dy_collar * normal[1])

    x_toe_vals = df_pozos['X_toe'].values if 'X_toe' in df_pozos.columns else df_pozos['X'].values
    y_toe_vals = df_pozos['Y_toe'].values if 'Y_toe' in df_pozos.columns else df_pozos['Y'].values

    dx_toe = x_toe_vals - origin[0]
    dy_toe = y_toe_vals - origin[1]
    dist_along_toe = dx_toe * direction[0] + dy_toe * direction[1]
    dist_perp_toe = np.abs(dx_toe * normal[0] + dy_toe * normal[1])

    dist_perp_mid = (dist_perp_collar + dist_perp_toe) / 2.0

    half_len = length / 2
    perp_eps = 1e-6
    mask = (
        ((dist_perp_collar <= tolerance + perp_eps) | (dist_perp_toe <= tolerance + perp_eps) | (dist_perp_mid <= tolerance + perp_eps))
        & (dist_along_collar >= -half_len)
        & (dist_along_collar <= half_len)
    )

    result = df_pozos.loc[mask].copy()
    result['dist_along'] = dist_along_collar[mask]
    result['dist_along_toe'] = dist_along_toe[mask]
    result['dist_perp'] = dist_perp_collar[mask]
    result['dist_perp_toe'] = dist_perp_toe[mask]
    closest = np.where(
        dist_perp_collar[mask] <= dist_perp_toe[mask],
        'collar',
        'toe',
    )
    result['closest_point'] = closest

    return result.sort_values('dist_along').reset_index(drop=True)
