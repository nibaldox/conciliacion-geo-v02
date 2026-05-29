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
from core.geom_utils import find_df_column

COLS_DROP = [
    'uniqid', 'id_rajo', 'id_malla_opit', 'id_pozo', 'numero',
    'camion', 'holes_dateUpdated', 'mes_tronadura',
]

BENCH_HEIGHT = 15.0


def procesar_pozos(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
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

    if 'fecha_tronadura' in df_work.columns:
        df_work['fecha_tronadura'] = pd.to_datetime(
            df_work['fecha_tronadura'], errors='coerce').dt.date

    x_col = find_df_column(df_work, ['Latitud_Geo', 'Latitud', 'X', 'Este'])
    y_col = find_df_column(df_work, ['Longitud_Geo', 'Longitud', 'Y', 'Norte'])
    z_col = find_df_column(df_work, ['Nombre_Banco', 'Banco', 'Cota_Collar', 'Z'])
    incl_col = find_df_column(df_work, ['Inclinacion_real', 'Inclinacion', 'Inclination'])
    az_col = find_df_column(df_work, ['Azimuth_real', 'Azimuth', 'Azimut'])
    len_col = find_df_column(df_work, ['longitud_real', 'Longitud', 'Length', 'Profundidad'])

    df_work = df_work.rename(columns={
        x_col: 'X', y_col: 'Y', z_col: 'Z_collar',
        incl_col: 'Incl', az_col: 'Az', len_col: 'Len',
    })

    for col in ('X', 'Y', 'Z_collar', 'Incl', 'Az', 'Len'):
        df_work[col] = pd.to_numeric(df_work[col], errors='coerce')

    df_work['Z_collar'] = df_work['Z_collar'] + BENCH_HEIGHT

    df_work = df_work.dropna(subset=['X', 'Y', 'Z_collar', 'Incl', 'Az', 'Len'])
    df_work = df_work[df_work['Len'] > 0]

    incl_rad = np.radians(df_work['Incl'].values.astype(float))
    az_rad = np.radians(df_work['Az'].values.astype(float))
    length = df_work['Len'].values.astype(float)

    dz = -length * np.cos(incl_rad)
    dx = length * np.sin(incl_rad) * np.sin(az_rad)
    dy = length * np.sin(incl_rad) * np.cos(az_rad)

    df_work['X_toe'] = df_work['X'] + dx
    df_work['Y_toe'] = df_work['Y'] + dy
    df_work['Z_toe'] = df_work['Z_collar'] + dz

    x_collar = df_work['X'].values.astype(float)
    y_collar = df_work['Y'].values.astype(float)
    z_collar = df_work['Z_collar'].values.astype(float)
    x_toe = df_work['X_toe'].values.astype(float)
    y_toe = df_work['Y_toe'].values.astype(float)
    z_toe = df_work['Z_toe'].values.astype(float)

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

    return df_work, x_lines, y_lines, z_lines


def proyectar_pozos_en_seccion(
    df_pozos: pd.DataFrame,
    origin: np.ndarray,
    azimuth: float,
    length: float,
    tolerance: float = 10.0,
) -> pd.DataFrame:
    """Project blast holes onto a section's coordinate system.

    For each hole, computes:
      - dist_perp: perpendicular distance to the section line (metres)
      - dist_along: distance along the section axis from origin (metres)

    Only holes within `tolerance` metres perpendicular distance are returned.

    Parameters
    ----------
    df_pozos : DataFrame with columns X, Y, Z_collar, Z_toe, Len (from procesar_pozos)
    origin   : np.ndarray [X, Y] section origin
    azimuth  : degrees from North, clockwise
    length   : section total length in metres
    tolerance: max perpendicular distance to include a hole (default 10 m)

    Returns
    -------
    DataFrame filtered and augmented with 'dist_along' and 'dist_perp'.
    """
    if df_pozos.empty:
        return df_pozos

    direction = np.array([np.sin(np.radians(azimuth)),
                          np.cos(np.radians(azimuth))])
    normal = np.array([direction[1], -direction[0]])

    dx = df_pozos['X'].values - origin[0]
    dy = df_pozos['Y'].values - origin[1]

    dist_along = dx * direction[0] + dy * direction[1]
    dist_perp = np.abs(dx * normal[0] + dy * normal[1])

    half_len = length / 2
    mask = (dist_perp <= tolerance) & (dist_along >= -half_len) & (dist_along <= half_len)

    result = df_pozos.loc[mask].copy()
    result['dist_along'] = dist_along[mask]
    result['dist_perp'] = dist_perp[mask]

    return result.sort_values('dist_along').reset_index(drop=True)



