"""
Derived Drill & Blast metrics.

Centralises the standard ratios and indices used in the D&B literature
(Konya & Walter 1991, Workman 1993, ICI Explosives, Dyno Nobel) and
promotes the columns already collected by ``procesar_pozos`` to useful
quality-control signals.

All public functions are pure: they receive a ``pandas.DataFrame`` (or
Series) and return a Series (or a small dict of Series). They never
mutate the input frame. The convenience entry point
:func:`enrich_blast_dataframe` stitches the individual helpers together
so callers can apply the full enrichment in one call.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from core.config import EXPLOSIVE


STEMMING_RATIO_OPTIMAL = (0.7, 1.0)
SUBDRILLING_RATIO_OPTIMAL = (0.2, 0.4)
SPACING_BURDEN_RATIO_OPTIMAL = (1.0, 1.5)
ROCK_DENSITY_DEFAULT_TM3 = 2.7

_MJ_PER_KG_TO_CAL_PER_G = 1000.0 / 4.184

_KILOS_CANDIDATES = ("Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg")
_LENGTH_CANDIDATES = ("Len", "longitud_real", "Longitud", "Length", "Profundidad")
_DIAM_CANDIDATES = ("Diam_mm", "Diametro", "Diametro_pozo", "Diametro_perforacion", "D_mm")
_BURDEN_CANDIDATES = ("Burden", "Burden_Real", "Burden_diseno", "B")
_ESP_CANDIDATES = ("Esp", "Espaciamiento", "Espaciamiento_Real", "Espaciamiento_diseno", "S")
_TACO_CANDIDATES = ("Taco_m", "Taco", "Stemming")
_INCL_CANDIDATES = ("Incl", "Inclinacion_real", "Inclinacion", "Inclination")
_AZ_CANDIDATES = ("Az", "Azimuth_real", "Azimuth", "Azimut")


def _first_present(df: pd.DataFrame, candidates: tuple) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _col_or_nan(df: pd.DataFrame, candidates: tuple) -> pd.Series:
    col = _first_present(df, candidates)
    if col is None:
        return pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def compute_stemming_ratio(df: pd.DataFrame) -> pd.Series:
    """Stemming/Burden ratio. Optimal range 0.7-1.0 (Konya)."""
    burden = _col_or_nan(df, _BURDEN_CANDIDATES)
    taco = _col_or_nan(df, _TACO_CANDIDATES)
    out = pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    valid = burden.notna() & taco.notna() & (burden > 0)
    out.loc[valid] = taco[valid] / burden[valid]
    return out


def compute_subdrilling_ratio(df: pd.DataFrame, bench_height: float = 15.0) -> pd.Series:
    """Sub-drilling/Burden ratio. Optimal range 0.2-0.4.

    pasadura = (Z_collar - bench_height) - Z_toe.
    """
    burden = _col_or_nan(df, _BURDEN_CANDIDATES)
    if "Z_collar" not in df.columns or "Z_toe" not in df.columns:
        return pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    z_collar = pd.to_numeric(df["Z_collar"], errors="coerce")
    z_toe = pd.to_numeric(df["Z_toe"], errors="coerce")
    pasadura = (z_collar - float(bench_height)) - z_toe
    out = pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    valid = burden.notna() & pasadura.notna() & (burden > 0)
    out.loc[valid] = pasadura[valid] / burden[valid]
    return out


def compute_spacing_burden_ratio(df: pd.DataFrame) -> pd.Series:
    """Spacing/Burden ratio. Optimal range 1.0-1.5 (square to rectangular)."""
    burden = _col_or_nan(df, _BURDEN_CANDIDATES)
    esp = _col_or_nan(df, _ESP_CANDIDATES)
    out = pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    valid = burden.notna() & esp.notna() & (burden > 0)
    out.loc[valid] = esp[valid] / burden[valid]
    return out


def compute_kg_per_meter(df: pd.DataFrame) -> pd.Series:
    """Kilograms of explosive per metre of hole length."""
    kilos = _col_or_nan(df, _KILOS_CANDIDATES)
    length = _col_or_nan(df, _LENGTH_CANDIDATES)
    out = pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    valid = kilos.notna() & length.notna() & (length > 0)
    out.loc[valid] = kilos[valid] / length[valid]
    return out


def compute_altura_carga_m(
    longitud_real_m: pd.Series,
    stemming_real_m: pd.Series,
) -> pd.Series:
    """Compute charge height (m) per well = longitud_real - stemming_real.

    In ENAEX reports:
      - longitud_real: total hole length (drilled)
      - stemming_real: stemming (taco) at the top of the hole
      - altura_carga = longitud_real - stemming_real (the explosive column)

    Negative values (stemming > drilled) indicate data error; clamp to 0.
    NaN inputs propagate as NaN.

    Parameters
    ----------
    longitud_real_m : pd.Series
        Total hole length in metres (renamed to 'Len' by procesar_pozos).
    stemming_real_m : pd.Series
        Stemming (taco) length in metres (renamed to 'Taco_m' by procesar_pozos).

    Returns
    -------
    pd.Series
        Charge height per well in metres (>= 0, or NaN if inputs NaN).
    """
    out = longitud_real_m.astype(float) - stemming_real_m.astype(float)
    return out.clip(lower=0.0)


def compute_decoupling_ratio(
    df: pd.DataFrame,
    well_kg_col: Optional[str] = None,
    rock_density_tm3: float = ROCK_DENSITY_DEFAULT_TM3,
) -> dict:
    """In-hole volumetric charge density and coupling ratio.

    Returns
    -------
    dict
        ``volume_load_kgm3`` : kg of explosive per m^3 of hole volume
        ``coupling_ratio``   : volume_load_kgm3 / rock_density (relative
                               charge density vs intact rock).
    """
    n = len(df)
    nan = pd.Series([np.nan] * n, index=df.index, dtype=float)
    empty = {"volume_load_kgm3": nan.copy(), "coupling_ratio": nan.copy()}

    diam = _col_or_nan(df, _DIAM_CANDIDATES)
    if not diam.notna().any():
        return empty

    kg_col = well_kg_col or _first_present(df, _KILOS_CANDIDATES)
    if kg_col is None:
        return empty
    kilos = pd.to_numeric(df[kg_col], errors="coerce")

    length = _col_or_nan(df, _LENGTH_CANDIDATES)
    kg_per_m = pd.Series([np.nan] * n, index=df.index, dtype=float)
    valid_l = length.notna() & (length > 0) & kilos.notna()
    kg_per_m.loc[valid_l] = kilos[valid_l] / length[valid_l]

    if "Tipo_Explosivo" in df.columns:
        rho_e = df["Tipo_Explosivo"].apply(EXPLOSIVE.density_g_per_cm3)
    else:
        rho_e = pd.Series([EXPLOSIVE.density_g_per_cm3("")] * n, index=df.index, dtype=float)

    diameter_m = diam / 1000.0
    hole_area_m2 = (np.pi / 4.0) * (diameter_m ** 2)
    rho_e_kgm3 = rho_e * 1000.0

    volume_load_kgm3 = pd.Series([np.nan] * n, index=df.index, dtype=float)
    valid = kg_per_m.notna() & (hole_area_m2 > 0) & (rho_e_kgm3 > 0)
    volume_load_kgm3.loc[valid] = kg_per_m[valid] / (hole_area_m2[valid] * rho_e_kgm3[valid])

    rho_rock_kgm3 = float(rock_density_tm3) * 1000.0
    coupling_ratio = pd.Series([np.nan] * n, index=df.index, dtype=float)
    valid_c = volume_load_kgm3.notna() & (rho_rock_kgm3 > 0)
    coupling_ratio.loc[valid_c] = volume_load_kgm3[valid_c] / rho_rock_kgm3

    return {"volume_load_kgm3": volume_load_kgm3, "coupling_ratio": coupling_ratio}


def compute_collar_deviation(df: pd.DataFrame) -> pd.Series:
    """3D angle (degrees) between the as-built and design hole vectors.

    Requires design columns ``Az_Diseno`` and ``Incl_Diseno``. When
    those columns are absent the function returns a Series of NaN (it
    does not raise) so callers can still pipe the output safely.
    """
    n = len(df)
    if "Az_Diseno" not in df.columns or "Incl_Diseno" not in df.columns:
        return pd.Series([np.nan] * n, index=df.index, dtype=float)

    az_r = _col_or_nan(df, _AZ_CANDIDATES)
    incl_r = _col_or_nan(df, _INCL_CANDIDATES)
    az_d = pd.to_numeric(df["Az_Diseno"], errors="coerce")
    incl_d = pd.to_numeric(df["Incl_Diseno"], errors="coerce")

    az_r_rad = np.radians(az_r)
    incl_r_rad = np.radians(incl_r)
    az_d_rad = np.radians(az_d)
    incl_d_rad = np.radians(incl_d)

    v_real = np.stack([
        np.sin(az_r_rad) * np.sin(incl_r_rad),
        np.cos(az_r_rad) * np.sin(incl_r_rad),
        np.cos(incl_r_rad),
    ], axis=1)
    v_design = np.stack([
        np.sin(az_d_rad) * np.sin(incl_d_rad),
        np.cos(az_d_rad) * np.sin(incl_d_rad),
        np.cos(incl_d_rad),
    ], axis=1)

    dot = np.einsum("ij,ij->i", v_real, v_design)
    dot = np.clip(dot, -1.0, 1.0)
    angle_rad = np.arccos(dot)

    out = pd.Series(np.degrees(angle_rad), index=df.index, dtype=float)
    valid = az_r.notna() & incl_r.notna() & az_d.notna() & incl_d.notna()
    out.loc[~valid] = np.nan
    return out


def compute_kuznetsov_x50(
    df: pd.DataFrame,
    explosive_energy_mj_kg: Optional[pd.Series] = None,
    bench_height: float = 15.0,
    rock_factor: float = 11.0,
) -> pd.Series:
    """Kuznetsov mean fragment size X50 (cm) per hole (Konya & Walter 1991).

    Formula
    -------
    X50 = A * (V/Q)^0.8 * Q^(1/6) * (E/115)^(-0.633)

    where V = volume broken per hole (m^3) = Burden * Esp * bench_h,
    Q = mass of explosive (kg) per hole, E = explosive specific energy
    in cal/g, and A is a rock-structure factor (~10-12 for medium rock).
    The ``explosive_energy_mj_kg`` argument is in MJ/kg (the same unit
    that :func:`core.config.ExplosiveEnergy.energy_mj_per_kg` returns);
    the function converts it to cal/g internally.
    """
    n = len(df)
    nan = pd.Series([np.nan] * n, index=df.index, dtype=float)
    burden = _col_or_nan(df, _BURDEN_CANDIDATES)
    esp = _col_or_nan(df, _ESP_CANDIDATES)
    if not burden.notna().any() or not esp.notna().any():
        return nan

    kg_col = _first_present(df, _KILOS_CANDIDATES)
    if kg_col is None:
        return nan
    kilos = pd.to_numeric(df[kg_col], errors="coerce")

    volume_per_hole = burden * esp * float(bench_height)
    valid_v = volume_per_hole > 0
    if not valid_v.any():
        return nan

    if explosive_energy_mj_kg is None:
        if "Tipo_Explosivo" in df.columns:
            mj_per_kg = df["Tipo_Explosivo"].apply(EXPLOSIVE.energy_mj_per_kg)
        else:
            mj_per_kg = pd.Series(
                [EXPLOSIVE.energy_mj_per_kg("")] * n, index=df.index, dtype=float
            )
        explosive_energy_mj_kg = mj_per_kg

    e_cal_per_g = pd.to_numeric(explosive_energy_mj_kg, errors="coerce") * _MJ_PER_KG_TO_CAL_PER_G

    valid = valid_v & kilos.notna() & (kilos > 0) & e_cal_per_g.notna() & (e_cal_per_g > 0)
    out = pd.Series([np.nan] * n, index=df.index, dtype=float)
    if not valid.any():
        return out

    v = volume_per_hole[valid]
    q = kilos[valid]
    e = e_cal_per_g[valid]
    ratio_vq = v / q
    x50 = float(rock_factor) * (ratio_vq ** 0.8) * (q ** (1.0 / 6.0)) * ((e / 115.0) ** (-0.633))
    out.loc[valid] = x50
    return out


def compute_ispu(
    blast_df: pd.DataFrame,
    ucs_mpa: Optional[float] = pd.NA,
    rock_density_tm3: float = ROCK_DENSITY_DEFAULT_TM3,
    bench_height: float = 15.0,
) -> pd.Series:
    """ISPU (Índice Schwimmbeck / Powder Utilization) per hole.

    Formula
    -------
    ISPU = (V * rho_rock * UCS) / E_total

    where V is broken volume per hole (m^3), rho_rock is in t/m^3,
    UCS in MPa and E_total is total explosive energy per hole in MJ.
    If ``ucs_mpa`` is None (or NaN) the function returns a Series of NaN.
    """
    n = len(blast_df)
    nan = pd.Series([np.nan] * n, index=blast_df.index, dtype=float)
    if ucs_mpa is None or (isinstance(ucs_mpa, float) and np.isnan(ucs_mpa)):
        return nan

    burden = _col_or_nan(blast_df, _BURDEN_CANDIDATES)
    esp = _col_or_nan(blast_df, _ESP_CANDIDATES)
    if not burden.notna().any() or not esp.notna().any():
        return nan

    kg_col = _first_present(blast_df, _KILOS_CANDIDATES)
    if kg_col is None or "energy_mj" not in blast_df.columns:
        return nan
    energy_mj = pd.to_numeric(blast_df["energy_mj"], errors="coerce")
    kilos = pd.to_numeric(blast_df[kg_col], errors="coerce")

    volume = burden * esp * float(bench_height)
    if isinstance(ucs_mpa, pd.Series):
        ucs = pd.to_numeric(ucs_mpa, errors="coerce").reindex(blast_df.index)
    else:
        ucs = pd.Series([float(ucs_mpa)] * n, index=blast_df.index, dtype=float)

    valid = (
        volume.notna() & (volume > 0)
        & energy_mj.notna() & (energy_mj > 0)
        & ucs.notna()
    )
    out = pd.Series([np.nan] * n, index=blast_df.index, dtype=float)
    out.loc[valid] = (
        volume[valid] * float(rock_density_tm3) * ucs[valid]
    ) / energy_mj[valid]
    return out


def _bottom_column_ratio(df: pd.DataFrame) -> Optional[pd.Series]:
    if "Carga_Fondo_kg" not in df.columns or "Carga_Columna_kg" not in df.columns:
        return None
    fondo = pd.to_numeric(df["Carga_Fondo_kg"], errors="coerce")
    columna = pd.to_numeric(df["Carga_Columna_kg"], errors="coerce")
    out = pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    valid = fondo.notna() & columna.notna() & (columna > 0)
    out.loc[valid] = fondo[valid] / columna[valid]
    return out


def enrich_blast_dataframe(
    df: pd.DataFrame,
    ucs_mpa: Optional[float] = None,
) -> pd.DataFrame:
    """Add all derived D&B metrics columns to a processed blast DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Output of ``procesar_pozos`` (and optionally
        ``compute_powder_factor``). Missing source columns are skipped
        silently so the function never raises on partial inputs.
    ucs_mpa : float, optional
        Uniaxial compressive strength (MPa) used by ``compute_ispu``.
        When omitted or None, the ``ispu`` column is left as NaN.

    Returns
    -------
    pd.DataFrame
        A copy of ``df`` augmented with whichever of the following
        columns can be computed from the available inputs:

        * ``stemming_ratio``
        * ``subdrilling_ratio``
        * ``spacing_burden_ratio``
        * ``kg_per_meter``
        * ``volume_load_kgm3``, ``coupling_ratio``
        * ``collar_deviation_deg``
        * ``kuznetsov_x50_cm``
        * ``ispu``
        * ``bottom_column_ratio`` (only when both Carga_Fondo_kg and
          Carga_Columna_kg are present)
        * ``altura_carga_m`` (charge column length = Len - Taco_m)
    """
    if df is None or df.empty:
        return df.copy() if df is not None else df

    out = df.copy()

    if "Burden" in out.columns and "Taco_m" in out.columns:
        out["stemming_ratio"] = compute_stemming_ratio(out)

    if (
        "Burden" in out.columns
        and "Z_collar" in out.columns
        and "Z_toe" in out.columns
    ):
        out["subdrilling_ratio"] = compute_subdrilling_ratio(out)

    if "Burden" in out.columns and "Esp" in out.columns:
        out["spacing_burden_ratio"] = compute_spacing_burden_ratio(out)

    has_kilos = _first_present(out, _KILOS_CANDIDATES) is not None
    has_len = _first_present(out, _LENGTH_CANDIDATES) is not None
    if has_kilos and has_len:
        out["kg_per_meter"] = compute_kg_per_meter(out)

    if _first_present(out, _DIAM_CANDIDATES) is not None:
        decoupling = compute_decoupling_ratio(out)
        out["volume_load_kgm3"] = decoupling["volume_load_kgm3"]
        out["coupling_ratio"] = decoupling["coupling_ratio"]

    if "Az_Diseno" in out.columns and "Incl_Diseno" in out.columns:
        out["collar_deviation_deg"] = compute_collar_deviation(out)

    if (
        "Burden" in out.columns
        and "Esp" in out.columns
        and has_kilos
    ):
        out["kuznetsov_x50_cm"] = compute_kuznetsov_x50(out)

    if (
        ucs_mpa is not None
        and "Burden" in out.columns
        and "Esp" in out.columns
        and has_kilos
        and "energy_mj" in out.columns
    ):
        out["ispu"] = compute_ispu(out, ucs_mpa=ucs_mpa)

    bottom_ratio = _bottom_column_ratio(out)
    if bottom_ratio is not None:
        out["bottom_column_ratio"] = bottom_ratio

    has_len = _first_present(out, _LENGTH_CANDIDATES) is not None
    has_taco = _first_present(out, _TACO_CANDIDATES) is not None
    if has_len and has_taco:
        out["altura_carga_m"] = compute_altura_carga_m(
            pd.to_numeric(out[_first_present(out, _LENGTH_CANDIDATES)], errors="coerce"),
            pd.to_numeric(out[_first_present(out, _TACO_CANDIDATES)], errors="coerce"),
        )

    return out
