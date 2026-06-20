"""Geotechnical data loading and lookup helpers.

Loads Rock Mass Rating (RMR, Bieniawski 1989) and Geological Strength
Index (GSI, Hoek 1995) from CSV files. Provides lookup by sector/level
with tolerance for fuzzy matching, the empirical RMR→GSI conversion,
and a simplified Hoek-Brown estimator for cohesion and friction angle
from GSI + UCS. E.1 + E.2 from the audit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class RockMassEntry:
    sector: str
    level: float
    rmr: float
    rqd: Optional[float] = None
    ucs_mpa: Optional[float] = None
    lithology: Optional[str] = None


REQUIRED_RMR_COLS = ['sector', 'level', 'rmr']
OPTIONAL_RMR_COLS = ['rqd', 'ucs_mpa', 'lithology', 'j1_dip', 'j1_dipdir']


def load_rmr_table(csv_path: str) -> pd.DataFrame:
    """Load RMR table from CSV. Required cols: sector, level, rmr.

    Returns DataFrame with normalized column names. Raises ValueError
    if required cols are missing.
    """
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_RMR_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"RMR table missing required columns: {missing}")
    df['level'] = pd.to_numeric(df['level'], errors='coerce')
    df['rmr'] = pd.to_numeric(df['rmr'], errors='coerce')
    df = df.dropna(subset=['level', 'rmr'])
    return df.reset_index(drop=True)


def lookup_rmr(
    rmr_df: pd.DataFrame,
    sector: str,
    level: float,
    level_tolerance_m: float = 5.0,
) -> Optional[RockMassEntry]:
    """Find the closest RMR entry for a sector + level.

    Returns None if no entry within tolerance.
    """
    if rmr_df is None or rmr_df.empty:
        return None
    sub = rmr_df[rmr_df['sector'].astype(str) == str(sector)].copy()
    if sub.empty:
        return None
    sub['level_diff'] = (sub['level'] - float(level)).abs()
    sub = sub[sub['level_diff'] <= float(level_tolerance_m)]
    if sub.empty:
        return None
    row = sub.loc[sub['level_diff'].idxmin()]
    rqd = float(row['rqd']) if 'rqd' in row and pd.notna(row['rqd']) else None
    ucs = float(row['ucs_mpa']) if 'ucs_mpa' in row and pd.notna(row['ucs_mpa']) else None
    lith = str(row['lithology']) if 'lithology' in row and pd.notna(row['lithology']) else None
    return RockMassEntry(
        sector=str(row['sector']),
        level=float(row['level']),
        rmr=float(row['rmr']),
        rqd=rqd,
        ucs_mpa=ucs,
        lithology=lith,
    )


def rmr_to_gsi(rmr: float) -> float:
    """Empirical conversion RMR → GSI (Hoek & Brown 1997, approximate).

    GSI = RMR - 5 (clamped to [0, 100]).

    For Bieniawski's RMR89 (uses groundwater + orientation adjustments)
    the offset is approximately 5.
    """
    return max(0.0, min(100.0, float(rmr) - 5.0))


def estimate_rock_strength_from_gsi(
    gsi: float,
    ucs_mpa: float,
    mi: float = 25.0,
    disturbance_factor_d: float = 0.7,
) -> tuple:
    """Estimate cohesion (kPa) and friction angle (degrees) from GSI+UCS via
    Hoek-Brown (simplified).

    Uses the simplified Hoek-Brown-Marinos formula for c and phi:

        mb / mi = exp((GSI - 100) / 28)
        s = exp((GSI - 100) / 9)
        a = 0.5

    Then fits a Mohr-Coulomb envelope across a range of sigma_3 to
    derive equivalent c and phi via least squares.

    Parameters
    ----------
    gsi : float
        Geological Strength Index (0-100).
    ucs_mpa : float
        Unconfined compressive strength of intact rock (MPa).
    mi : float
        Hoek-Brown material constant for intact rock (typical 25 ± 5).
    disturbance_factor_d : float
        Disturbance factor (0 = undisturbed, 1 = very disturbed).
        Default 0.7 for production blasting.

    Returns
    -------
    (c_kpa, phi_deg) : tuple of float
        Cohesion in kPa and friction angle in degrees.

    If gsi <= 0 or ucs <= 0, returns (0.0, 30.0) as conservative fallback.
    """
    if gsi <= 0 or ucs_mpa <= 0:
        return 0.0, 30.0
    mb_over_mi = math.exp((gsi - 100) / 28.0)
    mb = mb_over_mi * mi
    s = math.exp((gsi - 100) / 9.0)
    a = 0.5
    sigma_ci = ucs_mpa * 1000.0

    sample_sigmas = [sigma_ci * x for x in [0.001, 0.01, 0.05, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0]]
    pairs = []
    for sigma3 in sample_sigmas:
        sigma1 = sigma3 + sigma_ci * (mb * sigma3 / sigma_ci + s) ** a
        pairs.append((sigma3, sigma1))

    c_kpa = 0.0
    phi_rad = math.radians(30.0)
    if len(pairs) >= 2:
        n = float(len(pairs))
        sum_x = sum(p[0] for p in pairs)
        sum_y = sum(p[1] for p in pairs)
        sum_xy = sum(p[0] * p[1] for p in pairs)
        sum_x2 = sum(p[0] ** 2 for p in pairs)
        denom = n * sum_x2 - sum_x ** 2
        if abs(denom) > 1e-9:
            m_best = (n * sum_xy - sum_x * sum_y) / denom
            b_best = (sum_y - m_best * sum_x) / n
            if m_best > 0:
                phi_rad = math.atan(m_best)
            phi_rad = max(math.radians(15.0), min(math.radians(60.0), phi_rad))
            c_kpa = max(0.0, b_best)
    phi_deg = math.degrees(phi_rad)
    return float(c_kpa), float(phi_deg)
