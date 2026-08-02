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
    normalize_azimuth,
    normalize_inclination,
    normalize_vector_components,
)

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
    az_convention: AzimuthConvention | str = AzimuthConvention.FROM_NORTH_CW,
    incl_sign_convention: str = "abs",
    angle_unit: str = "degrees",
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """Process a blast-hole report DataFrame into collar/toe 3D coordinates.

    Coordinate handling (spec §4.2):
        X = Latitud_Geo  (East)
        Y = Longitud_Geo (North)
        Z = elevation column, transformed only when its semantic is
            known:
            - bench_elevation (e.g. Nombre_Banco): the column holds the
              target bench elevation; the collar sits ``bench_height_m``
              metres above it (default 15 m, configurable per event).
              The applied height is recorded in ``bench_height_m`` and
              the transformation in ``Z_collar_semantic``.
            - collar_elevation (e.g. Cota_Collar): the column already
              holds the real collar elevation; no transformation.
            Ambiguous source names raise ValueError (the pipeline stops
            instead of guessing) unless ``z_collar_semantic`` is given.

    Inclination / azimuth (spec §4.1): every input is normalized to the
    canonical convention — inclination = deviation from vertical (0 =
    vertical), azimuth = degrees clockwise from North. The original
    values and the convention applied are preserved in ``Incl_original``
    / ``Az_original`` / ``Incl_convention`` / ``Az_convention``; negative
    inclinations (sign-as-orientation) are absolutized and flagged in
    ``incl_anomaly``.

    Then computes the toe (bottom) of each hole using:
        Inclinacion_real : deviation from vertical in degrees (0 = vertical)
        Azimuth_real     : horizontal direction in degrees
        longitud_real    : measured hole length in metres

    Returns
    -------
    df_clean : pd.DataFrame
        Cleaned DataFrame with added columns:
        'X', 'Y', 'Z_collar', 'X_toe', 'Y_toe', 'Z_toe',
        'Z_collar_semantic', ('bench_height_m' when bench semantic),
        'Incl_original', 'Az_original', 'Incl_convention', 'Az_convention'.
        When present in the input, also captures:
        'Burden', 'Esp', 'Diam_mm', 'Tipo_Explosivo', 'Taco_m',
        'Secuencia', 'Retardo_ms', 'Fila', 'Carga_Fondo_kg',
        'Carga_Columna_kg', 'Longitud_Carga_m', 'Tipo_Pozo',
        'Az_Diseno', 'Incl_Diseno'
        (numeric fields coerced; missing columns skipped silently).
        Columns marked "no usar" are dropped.
        fecha_tronadura is normalized to date-only.
    x_lines, y_lines, z_lines : np.ndarray
        1-D arrays where each hole is represented by three consecutive
        values (collar_x, toe_x, None) — the None separator allows a
        single Scatter3d trace to render all trajectories efficiently.
    """
    df_work = df.copy()

    drop_present = [c for c in COLS_DROP if c in df_work.columns]
    df_work.drop(columns=drop_present, inplace=True)

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

    # Trazabilidad pozos→bancos en conciliación geométrica:
    # conservamos ``uniqid`` e ``id_pozo`` para enlazar cada
    # pozo del reporte de tronadura con su banco reconciliado.
    # Si el input no trae ``uniqid``, fabricamos uno sintético
    # a partir del índice de fila (1-based, string).
    if "uniqid" not in df_work.columns:
        df_work["uniqid"] = (df_work.index + 1).astype(str)

    _coerce_typed_columns(df_work)

    # Canonical inclination / azimuth normalization (spec §4.1, H-05,
    # cierre final §2.2). The inclination convention is MANDATORY: without
    # an explicit argument or a data-declared column, the geometry is
    # BLOCKED (raise) — there is no default and no silent assumption.
    az_conv = AzimuthConvention(az_convention)
    if "Incl" in df_work.columns:
        df_work["Incl_original"] = df_work["Incl"]
        if incl_convention is not None:
            incl_conv = InclinationConvention(incl_convention)
            source, user_confirmed = "explicit", True
        elif "Incl_convention" in df_work.columns:
            incl_conv = InclinationConvention(df_work["Incl_convention"].iloc[0])
            source, user_confirmed = "data", True
        else:
            raise ValueError(
                "Convención de inclinación no confirmada: no se puede calcular "
                "toe ni geometría dependiente sin declarar la convención. "
                "Especifique incl_convention='from_vertical' o "
                "'dip_from_horizontal' (o declare la columna Incl_convention "
                "en el evento)."
            )
        # Angular unit conversion before normalization (cierre §2.2).
        if angle_unit == "radians":
            incl_raw = np.degrees(df_work["Incl"].astype(float))
            conversion_unit = "radians->degrees"
        elif angle_unit == "degrees":
            incl_raw = df_work["Incl"]
            conversion_unit = "none"
        else:
            raise ValueError(f"angle_unit inválido: {angle_unit!r} (use 'degrees' o 'radians')")
        incl_norm, incl_meta = normalize_inclination(incl_raw, incl_conv)
        df_work["Incl"] = incl_norm
        df_work["Incl_convention"] = incl_conv.value
        df_work["Incl_convention_source"] = source
        df_work["incl_convention_warning"] = False
        # Cierre final §2.2: complete angular provenance columns.
        df_work["inclination_original"] = df_work["Incl_original"]
        df_work["inclination_source_column"] = incl_src or ""
        df_work["inclination_convention_original"] = incl_conv.value
        df_work["inclination_sign_convention"] = incl_sign_convention
        df_work["inclination_unit_original"] = angle_unit
        df_work["inclination_normalized_from_vertical"] = incl_norm
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
        if angle_unit == "radians":
            az_raw = np.degrees(df_work["Az"].astype(float))
            az_conversion_unit = "radians->degrees"
        else:
            az_raw = df_work["Az"]
            az_conversion_unit = "none"
        az_norm, az_meta = normalize_azimuth(az_raw, az_conv)
        df_work["Az"] = az_norm
        df_work["Az_convention"] = az_conv.value
        # Cierre final §2.2: azimuth provenance columns.
        df_work["azimuth_original"] = df_work["Az_original"]
        df_work["azimuth_source_column"] = az_src or ""
        df_work["azimuth_convention_original"] = az_conv.value
        df_work["azimuth_unit_original"] = angle_unit
        df_work["azimuth_normalized_clockwise_from_north"] = az_norm
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

    df_work = df_work.dropna(subset=["X", "Y", "Z_collar", "Incl", "Az", "Len"])
    df_work = df_work[df_work["Len"] > 0]

    _compute_hole_toes(df_work)
    if _Z_TRANSFORM_BLOCKED:
        blocked = df_work["Z_collar_semantic"] == "bench_elevation_untransformed"
        df_work.loc[blocked, ["X_toe", "Y_toe", "Z_toe"]] = np.nan
    return df_work, *_build_scatter_lines(df_work)


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



