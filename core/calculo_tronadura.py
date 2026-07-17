"""
Drill & Blast (Tronadura) processing logic.

Pure math functions — no Streamlit or Plotly dependencies.
Receives DataFrames, returns DataFrames and numpy arrays.

Columnas descartadas al procesar (según descripción ENAEX):
  uniqid, id_rajo, id_malla_opit, id_pozo, numero, camion,
  holes_dateUpdated, mes_tronadura
"""
import numpy as np
import pandas as pd
from datetime import timedelta
from core.config import DEFAULTS
from core.geom_utils import find_df_column

COLS_DROP = [
    'uniqid', 'id_rajo', 'id_malla_opit', 'id_pozo', 'numero',
    'camion', 'holes_dateUpdated', 'mes_tronadura',
]

BENCH_HEIGHT = 15.0


_CANONICAL_COLUMN_ALIASES: dict[str, list[str]] = {
    "X": ["Latitud_Geo", "Latitud", "X", "Este"],
    "Y": ["Longitud_Geo", "Longitud", "Y", "Norte"],
    "Z_collar": ["Nombre_Banco", "Banco", "Cota_Collar", "Z"],
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


def _compute_hole_toes(df_work: pd.DataFrame) -> None:
    """Add X_toe / Y_toe / Z_toe columns using Incl/Az/Length vector math.

    The toe is ``BENCH_HEIGHT + offset`` where the offset is the
    directional vector of length L along the inclined hole.
    """
    incl_rad = np.radians(df_work["Incl"].values.astype(float))
    az_rad = np.radians(df_work["Az"].values.astype(float))
    length = df_work["Len"].values.astype(float)
    dz = -length * np.cos(incl_rad)
    dx = length * np.sin(incl_rad) * np.sin(az_rad)
    dy = length * np.sin(incl_rad) * np.cos(az_rad)
    df_work["X_toe"] = df_work["X"] + dx
    df_work["Y_toe"] = df_work["Y"] + dy
    df_work["Z_toe"] = df_work["Z_collar"] + dz


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
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """Process a blast-hole report DataFrame into collar/toe 3D coordinates.

    Coordinate correction applied:
        X = Latitud_Geo  (East)
        Y = Longitud_Geo (North)
        Z = Nombre_Banco + BENCH_HEIGHT (Collar elevation)

    Nombre_Banco indicates the target bench elevation; the actual collar
    (drilling start) is BENCH_HEIGHT metres above it, on the upper bench.

    Then computes the toe (bottom) of each hole using:
        Inclinacion_real : deviation from vertical in degrees (0 = vertical)
        Azimuth_real     : horizontal direction in degrees
        longitud_real    : measured hole length in metres

    Returns
    -------
    df_clean : pd.DataFrame
        Cleaned DataFrame with added columns:
        'X', 'Y', 'Z_collar', 'X_toe', 'Y_toe', 'Z_toe'.
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

    # If the caller provided an explicit column mapping (from the
    # column-mapper UI), apply it directly. Otherwise, fall back to the
    # legacy alias-based auto-detection.
    if column_map is not None:
        from core.column_mapping import apply_mapping
        df_work = apply_mapping(df_work, column_map)
    else:
        resolved = _resolve_column_aliases(df_work)
        df_work = _rename_to_canonical(df_work, resolved)
    _coerce_typed_columns(df_work)

    df_work["Z_collar"] = df_work["Z_collar"] + BENCH_HEIGHT
    df_work = df_work.dropna(subset=["X", "Y", "Z_collar", "Incl", "Az", "Len"])
    df_work = df_work[df_work["Len"] > 0]

    _compute_hole_toes(df_work)
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



