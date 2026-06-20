"""Quantitative models linking blast loading to geotechnical damage.

This module houses the regression and correlation machinery that turns the
PF vs. over-break scatter and the pasadura vs. toe-deviation relationship
into defensible quantitative results (slope, p-value, confidence interval,
Pearson r). The UI in ``ui/tabs/blast_correlation.py`` consumes these
helpers; the rest of the pipeline ignores them.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from core.blast_correlation import _pasadura
from core.config import DEFAULTS


_INSUFFICIENT_RESULT: Dict[str, Any] = {
    "beta0": 0.0,
    "beta1": 0.0,
    "r_squared": 0.0,
    "p_value": float("nan"),
    "n": 0,
    "std_err_beta1": 0.0,
    "ci_beta1_low": 0.0,
    "ci_beta1_high": 0.0,
    "mean_pf": 0.0,
    "confidence": "INSUFFICIENT",
    "is_significant": False,
}


def _classify_confidence(n: int, p_value: float) -> str:
    if n >= 15 and p_value < 0.05:
        return "HIGH"
    if n >= 8 and p_value < 0.10:
        return "MEDIUM"
    if n >= 5 and p_value < 0.05:
        return "LOW"
    return "INSUFFICIENT"


def fit_powder_factor_damage_model(
    pf_values: np.ndarray,
    damage_values: np.ndarray,
    min_samples: int = 5,
) -> dict:
    """Fit OLS regression ``damage = beta0 + beta1 * PF + epsilon``.

    Parameters
    ----------
    pf_values : np.ndarray
        Powder factor (kg/m^3) per cross-section.
    damage_values : np.ndarray
        Mean overbreak per cross-section (signed, metres).
    min_samples : int
        Minimum number of valid (non-NaN) samples required to fit.

    Returns
    -------
    dict
        - ``beta0``: float, intercept (m of damage at PF=0).
        - ``beta1``: float, slope (m of damage per kg/m^3 of PF).
        - ``r_squared``: float, coefficient of determination.
        - ``p_value``: float, two-sided p-value testing ``beta1 == 0``.
        - ``n``: int, samples used.
        - ``std_err_beta1``: float, standard error of the slope.
        - ``ci_beta1_low`` / ``ci_beta1_high``: float, 95% confidence
          interval for ``beta1`` based on the t-distribution with n-2 d.f.
        - ``mean_pf``: float, mean of the (filtered) PF sample, used by
          :func:`predict_damage_for_pf` to compute extrapolation
          uncertainty.
        - ``confidence``: str, one of ``'HIGH'`` / ``'MEDIUM'`` / ``'LOW'`` /
          ``'INSUFFICIENT'``.
        - ``is_significant``: bool, ``p_value < 0.05``.

    When ``n < min_samples`` (or the inputs are empty / non-finite) the
    result has ``confidence='INSUFFICIENT'`` and zero-valued scalars so
    downstream code can render a single-shot message without conditionals.
    """
    empty = dict(_INSUFFICIENT_RESULT)
    empty["n"] = 0

    if pf_values is None or damage_values is None:
        return empty

    pf = np.asarray(pf_values, dtype=float)
    dmg = np.asarray(damage_values, dtype=float)

    if pf.shape != dmg.shape or pf.size == 0:
        return empty

    mask = np.isfinite(pf) & np.isfinite(dmg) & (pf > 0)
    pf = pf[mask]
    dmg = dmg[mask]
    n = int(pf.size)

    if n < min_samples:
        result = dict(_INSUFFICIENT_RESULT)
        result["n"] = n
        return result

    if float(np.var(pf)) <= 0.0:
        result = dict(_INSUFFICIENT_RESULT)
        result["n"] = n
        return result

    from scipy import stats

    slope, intercept, r_value, p_value, std_err = stats.linregress(pf, dmg)

    n_dof = max(n - 2, 1)
    t_crit = float(stats.t.ppf(0.975, n_dof))
    ci_low = float(slope - t_crit * std_err)
    ci_high = float(slope + t_crit * std_err)

    confidence = _classify_confidence(n, float(p_value))

    return {
        "beta0": float(intercept),
        "beta1": float(slope),
        "r_squared": float(r_value ** 2),
        "p_value": float(p_value),
        "n": n,
        "std_err_beta1": float(std_err),
        "ci_beta1_low": ci_low,
        "ci_beta1_high": ci_high,
        "mean_pf": float(np.mean(pf)),
        "confidence": confidence,
        "is_significant": bool(p_value < 0.05),
    }


def predict_damage_for_pf(model: dict, target_pf: float) -> dict:
    """Apply a fitted :func:`fit_powder_factor_damage_model` to ``target_pf``.

    Parameters
    ----------
    model : dict
        Output of :func:`fit_powder_factor_damage_model`.
    target_pf : float
        Hypothetical powder factor (kg/m^3) to evaluate.

    Returns
    -------
    dict
        - ``predicted_damage``: float, ``beta0 + beta1 * target_pf``.
        - ``delta_from_current``: float, ``predicted_damage - 0``. Positive
          means predicted overbreak, negative means predicted underbreak.
        - ``uncertainty_m``: float, ``std_err_beta1 * |target_pf - mean_pf|``
          (zero when the model carries ``confidence='INSUFFICIENT'``).
    """
    if not model or model.get("confidence") == "INSUFFICIENT":
        return {
            "predicted_damage": 0.0,
            "delta_from_current": 0.0,
            "uncertainty_m": 0.0,
        }

    predicted = float(model["beta0"] + model["beta1"] * target_pf)
    mean_pf = float(model.get("mean_pf", 0.0))
    uncertainty = float(model.get("std_err_beta1", 0.0)) * abs(target_pf - mean_pf)
    return {
        "predicted_damage": predicted,
        "delta_from_current": predicted,
        "uncertainty_m": uncertainty,
    }


def compute_pasadura_toe_correlation(
    blast_df: pd.DataFrame,
    comparisons: List[dict],
    bench_height: float = 15.0,
    tolerance: float = 5.0,
) -> dict:
    """Test the hypothesis ``short pasadura -> high |delta_toe|`` per bench.

    Parameters
    ----------
    blast_df : pd.DataFrame
        Processed blast holes (output of :func:`procesar_pozos`) with
        ``Z_collar`` and ``Z_toe`` columns.
    comparisons : list of dict
        Per-bench reconciliation results. Each item is expected to expose
        ``level`` (design toe elevation as a string) and ``delta_toe`` (m,
        signed).
    bench_height : float
        Bench height (m) used to derive the floor elevation from the
        collar.
    tolerance : float
        Not used directly; reserved so the signature mirrors other bench
        aggregations and can be extended without breaking callers.

    Returns
    -------
    dict
        - ``pasadura_per_bench``: dict[float, float], mean pasadura (m) per
          floor elevation.
        - ``toe_per_bench``: dict[float, float], mean ``delta_toe`` (m) per
          floor elevation, for the matching level.
        - ``r``: float, Pearson correlation between the two per-bench
          series (``0.0`` when fewer than two paired samples).
        - ``p_value``: float, two-sided p-value for ``r == 0`` (``nan``
          when undefined).
        - ``n_benches``: int, count of paired benches used in the
          correlation.
        - ``interpretation``: str, one-sentence read of the result.
    """
    del tolerance

    empty = {
        "pasadura_per_bench": {},
        "toe_per_bench": {},
        "r": 0.0,
        "p_value": float("nan"),
        "n_benches": 0,
        "interpretation": "Sin datos suficientes para correlacionar pasadura y delta_toe.",
    }

    if (
        blast_df is None
        or blast_df.empty
        or not comparisons
        or "Z_collar" not in blast_df.columns
        or "Z_toe" not in blast_df.columns
    ):
        return empty

    pas = _pasadura(blast_df, bench_height)
    df = blast_df.copy()
    df["_pasadura"] = pas
    df["_floor"] = (df["Z_collar"] - bench_height).round(0)

    pasadura_per_bench: Dict[float, float] = (
        df.groupby("_floor")["_pasadura"].mean().to_dict()
    )

    df_comps = pd.DataFrame(comparisons)
    if "level" not in df_comps.columns or "delta_toe" not in df_comps.columns:
        return empty

    df_comps = df_comps.dropna(subset=["level", "delta_toe"])
    if df_comps.empty:
        return empty

    def _to_int(v: Any) -> Optional[int]:
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return None

    df_comps["_level_int"] = df_comps["level"].apply(_to_int)
    df_comps = df_comps.dropna(subset=["_level_int"])
    if df_comps.empty:
        return empty

    toe_per_bench_raw: Dict[int, float] = (
        df_comps.groupby("_level_int")["delta_toe"].mean().to_dict()
    )

    paired_pas: List[float] = []
    paired_toe: List[float] = []
    matched_pasadura: Dict[float, float] = {}
    matched_toe: Dict[float, float] = {}
    for level, pas_mean in pasadura_per_bench.items():
        try:
            level_int = int(round(float(level)))
        except (TypeError, ValueError):
            continue
        if level_int in toe_per_bench_raw:
            matched_pasadura[float(level_int)] = float(pas_mean)
            matched_toe[float(level_int)] = float(toe_per_bench_raw[level_int])
            paired_pas.append(float(pas_mean))
            paired_toe.append(float(toe_per_bench_raw[level_int]))

    n = len(paired_pas)
    if n < 2:
        return {
            "pasadura_per_bench": matched_pasadura,
            "toe_per_bench": matched_toe,
            "r": 0.0,
            "p_value": float("nan"),
            "n_benches": n,
            "interpretation": (
                "Solo hay " + str(n) + " banco(s) pareado(s); se necesitan al menos 2."
            ),
        }

    pas_arr = np.asarray(paired_pas, dtype=float)
    toe_arr = np.asarray(paired_toe, dtype=float)

    if float(np.var(pas_arr)) <= 0.0 or float(np.var(toe_arr)) <= 0.0:
        r_val = 0.0
        p_val = float("nan")
    else:
        from scipy import stats

        r_res = stats.pearsonr(pas_arr, toe_arr)
        r_val = float(r_res.statistic)
        p_val = float(r_res.pvalue)

    if r_val < -0.3:
        interpretation = (
            f"Correlacion negativa (r={r_val:.2f}): pozos con menor pasadura "
            "se asocian a mayor sobre-excavacion de la pata. "
            "Consistente con hipotesis de lomo duro."
        )
    elif r_val > 0.3:
        interpretation = (
            f"Correlacion positiva (r={r_val:.2f}): pasadura mayor se asocia "
            "a mayor sobre-excavacion de la pata. "
            "Sugiere sobreperforacion (exceso de pasadura)."
        )
    else:
        interpretation = (
            f"Correlacion debil/nula (r={r_val:.2f}): pasadura y delta_toe "
            "no muestran relacion lineal clara con estos datos."
        )

    return {
        "pasadura_per_bench": matched_pasadura,
        "toe_per_bench": matched_toe,
        "r": r_val,
        "p_value": p_val,
        "n_benches": n,
        "interpretation": interpretation,
    }


def compute_energy_density_along_profile(
    blast_df: pd.DataFrame,
    profile_distances: np.ndarray,
    profile_xs: np.ndarray,
    profile_ys: np.ndarray,
    z_sample: float = 0.0,
    search_radius: float = 30.0,
    well_kg_column: Optional[str] = None,
) -> np.ndarray:
    """Inverse-distance-weighted energy density sampled along a profile.

    For each point ``(profile_xs[i], profile_ys[i], z_sample)`` the value
    returned is the sum over nearby wells of ``Q_j / d_ij^2``, where
    ``Q_j`` is the kilograms of explosive loaded in well ``j`` and
    ``d_ij`` is the horizontal distance from the well's collar to the
    sample point. Wells farther than ``search_radius`` are excluded.

    Parameters
    ----------
    blast_df : pd.DataFrame
        Processed blast holes. Must include ``X``, ``Y`` and a kilograms
        column (auto-detected unless ``well_kg_column`` is given).
    profile_distances : np.ndarray
        1D, along-profile coordinate in metres. Returned array is aligned
        with this vector (same length, same order).
    profile_xs, profile_ys : np.ndarray
        1D, planar coordinates of the sample points (metres).
    z_sample : float
        Z elevation where the IDW is sampled. Not used for the distance
        calculation (horizontal only) but kept in the signature so the
        caller can document the sampling horizon.
    search_radius : float
        Metres; only wells whose collar is within this distance contribute.
    well_kg_column : str, optional
        Explicit name of the kilograms column. When ``None`` the function
        looks for the first present among
        ``Kilos_Cargados_real`` / ``Kilos_Cargados`` / ``Carga_kg`` /
        ``Explosivo_kg`` and falls back to 1 kg per well (constant
        contribution) when none of them is present.

    Returns
    -------
    np.ndarray
        1D array of energy density values (kg/m^2) aligned with
        ``profile_distances``. Empty inputs return an empty array.
    """
    del z_sample

    n_points = int(np.size(profile_distances))
    if n_points == 0:
        return np.array([], dtype=float)

    if blast_df is None or blast_df.empty or "X" not in blast_df.columns or "Y" not in blast_df.columns:
        return np.zeros(n_points, dtype=float)

    well_x = np.asarray(blast_df["X"].values, dtype=float)
    well_y = np.asarray(blast_df["Y"].values, dtype=float)

    if well_kg_column and well_kg_column in blast_df.columns:
        well_q = pd.to_numeric(blast_df[well_kg_column], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    else:
        for cand in ("Kilos_Cargados_real", "Kilos_Cargados", "Carga_kg", "Explosivo_kg"):
            if cand in blast_df.columns:
                well_q = pd.to_numeric(blast_df[cand], errors="coerce").fillna(0.0).to_numpy(dtype=float)
                break
        else:
            well_q = np.ones(well_x.size, dtype=float)

    px = np.asarray(profile_xs, dtype=float).reshape(-1)
    py = np.asarray(profile_ys, dtype=float).reshape(-1)

    dx = px[:, None] - well_x[None, :]
    dy = py[:, None] - well_y[None, :]
    d2 = dx * dx + dy * dy
    radius2 = float(search_radius) ** 2
    within = d2 <= radius2

    floor_d2 = np.where(d2 < 1e-4, 1e-4, d2)
    q_matrix = np.broadcast_to(well_q[None, :], d2.shape)
    contributions = np.zeros_like(d2)
    contributions[within] = q_matrix[within] / floor_d2[within]

    return contributions.sum(axis=1)
