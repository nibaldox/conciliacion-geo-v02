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

from core.column_utils import KILOS_CANDIDATES, first_present_column
from core.config import EXPLOSIVE


STEMMING_RATIO_OPTIMAL = (0.7, 1.0)
SUBDRILLING_RATIO_OPTIMAL = (0.2, 0.4)
SPACING_BURDEN_RATIO_OPTIMAL = (1.0, 1.5)
ROCK_DENSITY_DEFAULT_TM3 = 2.7

_LENGTH_CANDIDATES = ("Len", "longitud_real", "Longitud", "Length", "Profundidad")
_DIAM_CANDIDATES = ("Diam_mm", "Diametro", "Diametro_pozo", "Diametro_perforacion", "D_mm")
_BURDEN_CANDIDATES = ("Burden", "Burden_Real", "Burden_diseno", "B")
_ESP_CANDIDATES = ("Esp", "Espaciamiento", "Espaciamiento_Real", "Espaciamiento_diseno", "S")
_TACO_CANDIDATES = ("Taco_m", "Taco", "Stemming")
_INCL_CANDIDATES = ("Incl", "Inclinacion_real", "Inclinacion", "Inclination")
_AZ_CANDIDATES = ("Az", "Azimuth_real", "Azimuth", "Azimut")


def _col_or_nan(df: pd.DataFrame, candidates: tuple) -> pd.Series:
    col = first_present_column(df, candidates)
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
    kilos = _col_or_nan(df, KILOS_CANDIDATES)
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
    """In-hole volumetric charge density and standard coupling ratio (spec §4.6).

    Returns
    -------
    dict
        ``volume_load_kgm3`` : fill fraction of the hole volume occupied
            by explosive (kg per m of hole / (hole area × ρ_e)) —
            legacy metric, dimensionless despite its name.
        ``equivalent_charge_diameter_m`` : D_c = sqrt(4·q_l/(π·ρ_e))
            where q_l is the linear charge density (kg/m) and ρ_e the
            explosive density (kg/m³) — the diameter of an equivalent
            full column with the same linear density.
        ``coupling_ratio`` : R_c = D_c / D_h, the standard decoupling
            ratio (1.0 = fully coupled, <1 = decoupled). D_h is the
            drilled hole diameter in metres.
    """
    n = len(df)
    nan = pd.Series([np.nan] * n, index=df.index, dtype=float)
    empty = {
        "volume_load_kgm3": nan.copy(),
        "equivalent_charge_diameter_m": nan.copy(),
        "coupling_ratio": nan.copy(),
    }

    diam = _col_or_nan(df, _DIAM_CANDIDATES)
    if not diam.notna().any():
        return empty

    kg_col = well_kg_col or first_present_column(df, KILOS_CANDIDATES)
    if kg_col is None:
        return empty
    kilos = pd.to_numeric(df[kg_col], errors="coerce")

    length = _col_or_nan(df, _LENGTH_CANDIDATES)
    kg_per_m = pd.Series([np.nan] * n, index=df.index, dtype=float)
    valid_l = length.notna() & (length > 0) & kilos.notna()
    kg_per_m.loc[valid_l] = kilos[valid_l] / length[valid_l]

    if "Tipo_Explosivo" in df.columns:
        rho_e = pd.to_numeric(
            df["Tipo_Explosivo"].apply(EXPLOSIVE.density_g_per_cm3),
            errors="coerce",
        )
    else:
        rho_e = pd.Series(np.nan, index=df.index, dtype=float)

    diameter_m = diam / 1000.0
    hole_area_m2 = (np.pi / 4.0) * (diameter_m ** 2)
    rho_e_kgm3 = rho_e * 1000.0

    volume_load_kgm3 = pd.Series([np.nan] * n, index=df.index, dtype=float)
    valid = kg_per_m.notna() & (hole_area_m2 > 0) & (rho_e_kgm3 > 0)
    volume_load_kgm3.loc[valid] = kg_per_m[valid] / (hole_area_m2[valid] * rho_e_kgm3[valid])

    # Standard coupling (spec §4.6): D_c = sqrt(4·q_l/(π·ρ_e)); R_c = D_c/D_h.
    d_c = pd.Series([np.nan] * n, index=df.index, dtype=float)
    valid_dc = kg_per_m.notna() & (kg_per_m > 0) & (rho_e_kgm3 > 0)
    d_c.loc[valid_dc] = np.sqrt(
        (4.0 * kg_per_m[valid_dc]) / (np.pi * rho_e_kgm3[valid_dc])
    )
    coupling = pd.Series([np.nan] * n, index=df.index, dtype=float)
    valid_c = d_c.notna() & (diameter_m > 0)
    coupling.loc[valid_c] = d_c[valid_c] / diameter_m[valid_c]

    return {
        "volume_load_kgm3": volume_load_kgm3,
        "equivalent_charge_diameter_m": d_c,
        "coupling_ratio": coupling,
    }


def compute_collar_deviation(
    df: pd.DataFrame,
    design_incl_convention: str = "from_vertical",
) -> pd.Series:
    """3D angle (degrees) between the as-built and design hole vectors.

    Requires design columns ``Az_Diseno`` and ``Incl_Diseno``. When
    those columns are absent the function returns a Series of NaN (it
    does not raise) so callers can still pipe the output safely.

    Both the as-built and the design inclination are normalized to the
    canonical convention (deviation from vertical, 0 = vertical) before
    the angle is computed. Design sources that report dip from the
    horizontal (e.g. a ``Design_Dip`` column) must pass
    ``design_incl_convention="dip_from_horizontal"``; the original
    values are never reinterpreted silently (spec §4.1).
    """
    n = len(df)
    if "Az_Diseno" not in df.columns or "Incl_Diseno" not in df.columns:
        return pd.Series([np.nan] * n, index=df.index, dtype=float)

    from core.geometry_conventions import InclinationConvention, normalize_inclination

    az_r = _col_or_nan(df, _AZ_CANDIDATES)
    incl_r = _col_or_nan(df, _INCL_CANDIDATES)
    az_d = pd.to_numeric(df["Az_Diseno"], errors="coerce")
    incl_d, _ = normalize_inclination(
        pd.to_numeric(df["Incl_Diseno"], errors="coerce"),
        InclinationConvention(design_incl_convention),
    )

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
    rws: Optional[pd.Series] = None,
) -> pd.Series:
    """Kuznetsov mean fragment size X50 (cm) per hole — auxiliary estimator.

    Formula (Kuznetsov 1973, as compiled by Konya & Walter 1991)
    -------
    X50 = A * (V/Q)^0.8 * Q^(1/6) * RWS^(-0.633)

    where V = volume broken per hole (m^3) = Burden * Esp * bench_h,
    Q = mass of explosive (kg) per hole, RWS = relative weight strength
    of the explosive relative to ANFO (= 1.0 for ANFO), and A is a
    rock-structure factor (~10-12 for medium rock).

    RWS handling (spec §4.5):
    - ``rws`` (explicit, ANFO-relative) is used when provided.
    - Otherwise RWS is ESTIMATED as the ratio of the product's specific
      energy to ANFO's (3.72 MJ/kg). This is an explicit estimate — the
      project has no official RWS datasheet values yet — and never a
      silent ANFO fallback: unknown products produce NaN, not ANFO.

    Units: V in m³, Q in kg, RWS dimensionless, X50 in cm.
    Valid range: empirical, typically V/Q in 2-8 m³/kg, A in 7-13.
    Limitations: single Kuznetsov mean size — no Rosin-Rammler index;
      auxiliary fragmentation estimator only, not an energy-field
      validator (spec §4.5).
    """
    n = len(df)
    nan = pd.Series([np.nan] * n, index=df.index, dtype=float)
    burden = _col_or_nan(df, _BURDEN_CANDIDATES)
    esp = _col_or_nan(df, _ESP_CANDIDATES)
    if not burden.notna().any() or not esp.notna().any():
        return nan

    kg_col = first_present_column(df, KILOS_CANDIDATES)
    if kg_col is None:
        return nan
    kilos = pd.to_numeric(df[kg_col], errors="coerce")

    volume_per_hole = burden * esp * float(bench_height)
    valid_v = volume_per_hole > 0
    if not valid_v.any():
        return nan

    if rws is not None:
        rws_series = pd.to_numeric(rws, errors="coerce")
    else:
        if explosive_energy_mj_kg is None:
            if "Tipo_Explosivo" in df.columns:
                mj_per_kg = df["Tipo_Explosivo"].apply(EXPLOSIVE.energy_mj_per_kg)
            else:
                mj_per_kg = pd.Series(np.nan, index=df.index, dtype=float)
            # Unknown products resolve to None (spec §4.4) → NaN, never ANFO.
            explosive_energy_mj_kg = pd.to_numeric(mj_per_kg, errors="coerce")
        rws_series = pd.to_numeric(explosive_energy_mj_kg, errors="coerce") / 3.72

    valid = valid_v & kilos.notna() & (kilos > 0) & rws_series.notna() & (rws_series > 0)
    out = pd.Series([np.nan] * n, index=df.index, dtype=float)
    if not valid.any():
        return out

    v = volume_per_hole[valid]
    q = kilos[valid]
    r = rws_series[valid]
    ratio_vq = v / q
    x50 = float(rock_factor) * (ratio_vq ** 0.8) * (q ** (1.0 / 6.0)) * (r ** (-0.633))
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

    kg_col = first_present_column(blast_df, KILOS_CANDIDATES)
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


def _polygon_area(verts: np.ndarray) -> float:
    """Shoelace-formula area of a polygon given its ordered vertices."""
    if verts is None or len(verts) < 3:
        return 0.0
    x = verts[:, 0]
    y = verts[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


def _voronoi_finite_polygons_2d(vor, radius: float) -> tuple:
    """Close infinite Voronoi ridges with far points at ``radius``.

    Adapted from the SciPy cookbook recipe. Returns ``(regions, vertices)``
    where every region is a finite closed polygon and ``vertices`` is the
    (possibly extended) vertex array.
    """
    new_regions: list[list[int]] = []
    new_vertices = vor.vertices.tolist()
    center = vor.points.mean(axis=0)
    all_ridges: dict[int, list[tuple[int, int, int]]] = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2))
        all_ridges.setdefault(p2, []).append((p1, v1, v2))

    for p1, region_idx in enumerate(vor.point_region):
        vertices = vor.regions[region_idx]
        if all(v >= 0 for v in vertices):
            new_regions.append(vertices)
            continue
        ridges = all_ridges[p1]
        new_region = [v for v in vertices if v >= 0]
        for p2, v1, v2 in ridges:
            if v2 < 0:
                v1, v2 = v2, v1
            if v1 >= 0:
                continue
            t = vor.points[p2] - vor.points[p1]
            t /= np.linalg.norm(t)
            n = np.array([-t[1], t[0]])
            midpoint = vor.points[[p1, p2]].mean(axis=0)
            direction = np.sign(np.dot(midpoint - center, n)) * n
            if np.all(direction == 0):
                direction = n
            far_point = vor.vertices[v2] + direction * radius
            new_region.append(len(new_vertices))
            new_vertices.append(far_point.tolist())
        vs = np.asarray([new_vertices[v] for v in new_region])
        c = vs.mean(axis=0)
        angles = np.arctan2(vs[:, 1] - c[1], vs[:, 0] - c[0])
        new_region = [v for _, v in sorted(zip(angles, new_region))]
        new_regions.append(new_region)
    return new_regions, np.asarray(new_vertices)


def compute_influence_area_m2(
    df: pd.DataFrame,
    max_area_factor: float = 3.0,
    clip_radius_factor: float = 2.0,
) -> pd.Series:
    """Per-hole Voronoi (Thiessen) influence area in m².

    Each hole's area of influence is the 2-D Voronoi cell of its collar
    position (X, Y). Cells whose ridges extend to infinity (holes on the
    convex hull) are closed by projecting their infinite ridge rays to a
    radius of ``clip_radius_factor × point spread`` from the region
    centroid, and the resulting polygon area is capped at
    ``max_area_factor × median(cell area)`` to avoid absurd edge cells.

    Holes sharing the same collar coordinates share the cell of their
    unique location. Returns NaN for inputs with fewer than 4 distinct
    collars (Qhull needs at least 4 sites) or non-finite coordinates.

    Parameters
    ----------
    df : DataFrame with ``X`` / ``Y`` columns (collar East/North).
    max_area_factor : float
        Cap factor over the median cell area (default 3×).
    clip_radius_factor : float
        Multiplier of the point spread used to close infinite ridges.

    Returns
    -------
    pd.Series
        Influence area per hole in m², aligned with ``df.index``.
    """
    n = len(df)
    nan = pd.Series([np.nan] * n, index=df.index, dtype=float)
    if n < 4 or "X" not in df.columns or "Y" not in df.columns:
        return nan
    coords = df[["X", "Y"]].to_numpy(dtype=float)
    if not np.isfinite(coords).all():
        return nan

    uniq, inverse = np.unique(coords, axis=0, return_inverse=True)
    if len(uniq) < 4:
        return nan

    try:
        from scipy.spatial import QhullError, Voronoi, cKDTree
        vor = Voronoi(uniq)
        # Local spacing: median distance to the 3 nearest neighbours. The
        # infinite-ridge clip radius scales with this instead of the global
        # point spread so edge cells stay proportional to the local grid.
        tree = cKDTree(uniq)
        dists, _ = tree.query(uniq, k=min(4, len(uniq)))
        if dists.ndim == 1:
            nn_med = float(np.median(dists[1:]))
        else:
            nn_med = float(np.median(dists[:, 1:]))
        radius = max(nn_med * clip_radius_factor, 1.0)
        regions, vertices = _voronoi_finite_polygons_2d(vor, radius)
        areas = np.array([_polygon_area(vertices[r]) for r in regions], dtype=float)
    except (QhullError, ValueError, IndexError):
        return nan

    if len(areas) == 0:
        return nan
    # Cap absurd edge cells against the first quartile of cell areas (the
    # median itself can be inflated when most holes sit on the hull).
    ref = float(np.percentile(areas, 25))
    if ref > 0:
        areas = np.minimum(areas, ref * max_area_factor)
    return pd.Series(areas[inverse], index=df.index, dtype=float)


def compute_influence_area_report(
    df: pd.DataFrame,
    boundary_polygon: Optional[list] = None,
    max_area_factor: float = 3.0,
    clip_radius_factor: float = 2.0,
) -> pd.DataFrame:
    """Per-hole Voronoi influence area with provenance (spec §4.8).

    Unlike :func:`compute_influence_area_m2` (which returns a bare
    Series), this reports how each area was obtained:

    - ``voronoi_cell``: full 2-D Voronoi cell of a unique interior site
      (real, exact).
    - ``edge_clipped``: cell on the convex hull whose infinite ridges
      were closed with the heuristic clip radius (estimate).
    - ``capped``: cell area capped by ``max_area_factor × Q1`` to avoid
      absurd edge cells (estimate).
    - ``duplicate_shared``: hole sharing collar coordinates with another
      (the shared cell area is assigned to each copy).
    - ``clipped_to_blast_polygon``: cell intersected with the real blast
      polygon (needs shapely; requires ``boundary_polygon``).
    - ``invalid``: NaN area (fewer than 4 distinct collars, non-finite
      coordinates, or Qhull failure).

    ``boundary_polygon`` is a list of (x, y) vertices of the blast
    polygon. When provided and shapely is available, cells are
    intersected with it and the report includes ``domain_area_m2`` (the
    polygon area) so callers can verify ``sum(area) <= domain``. When
    shapely is unavailable the polygon is ignored and a warning is
    recorded in ``clip_warning``.

    Returns
    -------
    pd.DataFrame aligned with ``df.index`` with columns ``area_m2``,
    ``area_status`` and (only when ``boundary_polygon`` is given)
    ``domain_area_m2`` / ``clip_warning``.
    """
    n = len(df)
    report = df.copy()
    report["area_m2"] = np.nan
    report["area_status"] = "invalid"

    if n < 4 or "X" not in df.columns or "Y" not in df.columns:
        return report
    coords = df[["X", "Y"]].to_numpy(dtype=float)
    finite = np.isfinite(coords).all(axis=1)
    if int(finite.sum()) < 4:
        return report
    coords_f = coords[finite]

    uniq, inverse = np.unique(coords_f, axis=0, return_inverse=True)
    if len(uniq) < 4:
        return report

    try:
        from scipy.spatial import QhullError, Voronoi, cKDTree
        vor = Voronoi(uniq)
        tree = cKDTree(uniq)
        dists, _ = tree.query(uniq, k=min(4, len(uniq)))
        if dists.ndim == 1:
            nn_med = float(np.median(dists[1:]))
        else:
            nn_med = float(np.median(dists[:, 1:]))
        radius = max(nn_med * clip_radius_factor, 1.0)
        regions, vertices = _voronoi_finite_polygons_2d(vor, radius)
        raw_areas = np.array([_polygon_area(vertices[r]) for r in regions], dtype=float)
    except (QhullError, ValueError, IndexError):
        return report

    cell_polys = [vertices[r] for r in regions]

    hull_idx: set = set()
    try:
        from scipy.spatial import ConvexHull
        hull = ConvexHull(uniq)
        hull_idx = set(hull.vertices.tolist())
    except Exception:  # noqa: BLE001 — degenerate hull
        pass

    counts = np.bincount(inverse, minlength=len(uniq))

    clip_warning = ""
    domain_area = None
    polys_for_clip = None
    clip_status_label = "clipped_to_blast_polygon"

    try:
        import shapely.geometry as sg
        if boundary_polygon is not None and len(boundary_polygon) >= 3:
            poly = sg.Polygon([(float(x), float(y)) for x, y in boundary_polygon])
            if poly.area <= 0:
                raise ValueError("degenerate blast polygon")
        else:
            # Default evaluation domain: the collar bounding box, so the
            # reported areas can be verified against it (spec §4.8).
            xmin, ymin = uniq.min(axis=0)
            xmax, ymax = uniq.max(axis=0)
            poly = sg.box(xmin, ymin, xmax, ymax)
            clip_status_label = "edge_clipped"
        domain_area = float(poly.area)
        polys_for_clip = [sg.Polygon(p) for p in cell_polys]
    except ImportError:
        clip_warning = "shapely_unavailable"
        if boundary_polygon is not None:
            clip_warning = "polygon_clip_unavailable: shapely not installed"
    except Exception as exc:  # noqa: BLE001
        clip_warning = f"polygon_clip_unavailable: {exc}"

    finite_idx = np.flatnonzero(finite)
    finite_labels = report.index[finite]  # actual index labels (may be non-contiguous)
    for site in range(len(uniq)):
        mask = inverse == site
        idx = finite_labels[mask]
        if polys_for_clip is not None and not polys_for_clip[site].is_empty:
            clipped = polys_for_clip[site].intersection(poly)
            if clipped.is_empty or clipped.area <= 0:
                continue  # stays invalid
            a = float(clipped.area)
            if poly.contains(polys_for_clip[site]):
                # Cell fully inside the domain: untouched by the clip.
                st = clip_status_label if boundary_polygon is not None else "voronoi_cell"
            else:
                st = clip_status_label
        else:
            a = float(raw_areas[site])
            if not np.isfinite(a) or a <= 0:
                continue
            if site in hull_idx:
                st = "edge_clipped"
            else:
                st = "voronoi_cell"
        report.loc[idx, "area_m2"] = a
        report.loc[idx, "area_status"] = st

    if counts[inverse].max() > 1:
        dup = counts[inverse] > 1
        idx = finite_labels[dup]
        report.loc[idx, "area_status"] = "duplicate_shared"

    if domain_area is not None:
        report["domain_area_m2"] = float(domain_area)
        report["clip_warning"] = clip_warning
    return report


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

    has_kilos = first_present_column(out, KILOS_CANDIDATES) is not None
    has_len = first_present_column(out, _LENGTH_CANDIDATES) is not None
    if has_kilos and has_len:
        out["kg_per_meter"] = compute_kg_per_meter(out)

    if first_present_column(out, _DIAM_CANDIDATES) is not None:
        decoupling = compute_decoupling_ratio(out)
        out["volume_load_kgm3"] = decoupling["volume_load_kgm3"]
        out["equivalent_charge_diameter_m"] = decoupling["equivalent_charge_diameter_m"]
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

    has_len = first_present_column(out, _LENGTH_CANDIDATES) is not None
    has_taco = first_present_column(out, _TACO_CANDIDATES) is not None
    if has_len and has_taco:
        out["altura_carga_m"] = compute_altura_carga_m(
            pd.to_numeric(out[first_present_column(out, _LENGTH_CANDIDATES)], errors="coerce"),
            pd.to_numeric(out[first_present_column(out, _TACO_CANDIDATES)], errors="coerce"),
        )

    return out
