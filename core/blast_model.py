"""Quantitative models linking blast loading to geotechnical damage.

This module houses the regression and correlation machinery that turns the
PF vs. over-break scatter and the pasadura vs. toe-deviation relationship
into defensible quantitative results (slope, p-value, confidence interval,
Pearson r). The UI in ``ui/tabs/blast_correlation.py`` consumes these
helpers; the rest of the pipeline ignores them.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from core.blast_correlation import _pasadura
from core.blast_metrics import _BURDEN_CANDIDATES, _ESP_CANDIDATES, _TACO_CANDIDATES
from core.column_utils import first_present_column
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


_MULTIVARIATE_PREDICTOR_CANDIDATES: Dict[str, tuple] = {
    "pf_vol": ("pf_vol_kgm3", "pf_vol_avg_kgm3", "PF_vol"),
    "burden": _BURDEN_CANDIDATES,
    "spacing_burden_ratio": ("spacing_burden_ratio",),
    "stemming": _TACO_CANDIDATES,
}

_COLLINEARITY_CONDITION_THRESHOLD = 30.0

_COLLINEARITY_WARNING = "Posible colinealidad entre predictores (tipicamente PF-burden)."

_MULTIVARIATE_INSUFFICIENT_RESULT: Dict[str, Any] = {
    "beta0": 0.0,
    "beta1": 0.0,
    "coefficients": {},
    "std_errors": {},
    "t_stats": {},
    "p_values": {},
    "r_squared": 0.0,
    "r_squared_adj": 0.0,
    "p_value": float("nan"),
    "f_statistic": float("nan"),
    "f_pvalue": float("nan"),
    "n": 0,
    "dof": 0,
    "condition_number": float("nan"),
    "features_used": [],
    "feature_means": {},
    "collinearity_warning": "",
    "confidence": "INSUFFICIENT",
    "is_significant": False,
}


def _fresh_multivariate_insufficient(n: int = 0, features_used: Optional[List[str]] = None) -> Dict[str, Any]:
    result = copy.deepcopy(_MULTIVARIATE_INSUFFICIENT_RESULT)
    result["n"] = int(n)
    result["features_used"] = list(features_used) if features_used else []
    return result


def _classify_multivariate_confidence(
    n: int,
    f_pvalue: float,
    condition_number: float,
    rank_deficient: bool,
) -> str:
    base = _classify_confidence(n, float(f_pvalue))
    collinear = (
        rank_deficient
        or not np.isfinite(condition_number)
        or float(condition_number) >= _COLLINEARITY_CONDITION_THRESHOLD
    )
    if collinear and base != "INSUFFICIENT":
        return "CAUTION"
    return base


def _resolve_multivariate_predictors(df: pd.DataFrame) -> Dict[str, pd.Series]:
    resolved: Dict[str, pd.Series] = {}
    for name, candidates in _MULTIVARIATE_PREDICTOR_CANDIDATES.items():
        col = first_present_column(df, candidates)
        if col is not None:
            resolved[name] = pd.to_numeric(df[col], errors="coerce")
    if "spacing_burden_ratio" not in resolved:
        b_col = first_present_column(df, _BURDEN_CANDIDATES)
        s_col = first_present_column(df, _ESP_CANDIDATES)
        if b_col is not None and s_col is not None:
            burden = pd.to_numeric(df[b_col], errors="coerce")
            esp = pd.to_numeric(df[s_col], errors="coerce")
            resolved["spacing_burden_ratio"] = esp / burden.replace(0.0, np.nan)
    return resolved


def fit_multivariate_damage_model(
    df: pd.DataFrame,
    damage_col: str = "avg_over_break",
    min_samples: int = 12,
) -> Dict[str, Any]:
    """Fit multivariate OLS ``damage = beta0 + sum_i beta_i * x_i + epsilon``.

    Predictors are auto-resolved from ``df`` among powder factor, burden,
    spacing-to-burden ratio and stemming. Inference is derived from the
    residual covariance using ``numpy.linalg.lstsq`` (no scikit-learn) and
    ``scipy.stats`` for two-sided t and overall F probabilities.

    Parameters
    ----------
    df : pd.DataFrame
        Per-section table carrying the damage column and predictor columns.
    damage_col : str
        Column with mean over-break (signed, metres).
    min_samples : int
        Minimum number of complete rows required to fit.

    Returns
    -------
    dict
        Mirrors :func:`fit_powder_factor_damage_model` keys (``beta0``,
        ``beta1``, ``r_squared``, ``p_value``, ``n``, ``confidence``,
        ``is_significant``) plus multivariate extras: ``coefficients``,
        ``std_errors``, ``t_stats``, ``p_values`` (per-predictor dicts),
        ``r_squared_adj``, ``f_statistic``, ``f_pvalue``, ``dof``,
        ``condition_number``, ``features_used``, ``feature_means`` and
        ``collinearity_warning``. Insufficient or malformed input returns
        the ``confidence='INSUFFICIENT'`` skeleton without raising.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return _fresh_multivariate_insufficient()

    if damage_col not in df.columns:
        return _fresh_multivariate_insufficient()

    resolved = _resolve_multivariate_predictors(df)
    if not resolved:
        return _fresh_multivariate_insufficient()

    damage = pd.to_numeric(df[damage_col], errors="coerce")
    frame = pd.DataFrame({"__damage__": damage.to_numpy(dtype=float)})
    for name, series in resolved.items():
        frame[name] = np.asarray(series, dtype=float)

    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    n = int(len(frame))

    feature_names: List[str] = [
        name
        for name in resolved
        if name in frame.columns and float(np.var(frame[name].to_numpy(dtype=float))) > 1e-12
    ]

    if len(feature_names) < 2 or n < min_samples:
        return _fresh_multivariate_insufficient(n=n, features_used=feature_names)

    y = frame["__damage__"].to_numpy(dtype=float)
    predictor_cols = [frame[name].to_numpy(dtype=float) for name in feature_names]
    X = np.column_stack([np.ones(n)] + predictor_cols)
    p = X.shape[1]

    beta, _residuals, rank, _sv = np.linalg.lstsq(X, y, rcond=None)
    rank_deficient = bool(rank < p)

    xtx = X.T @ X
    try:
        xtx_inv = np.linalg.pinv(xtx) if rank_deficient else np.linalg.inv(xtx)
    except np.linalg.LinAlgError:
        xtx_inv = np.linalg.pinv(xtx)
        rank_deficient = True

    residuals = y - X @ beta
    dof = max(n - p, 1)
    sse = float(np.sum(residuals ** 2))
    sst = float(np.sum((y - float(np.mean(y))) ** 2))
    sigma2 = sse / dof
    se = np.sqrt(np.maximum(np.diag(xtx_inv) * sigma2, 0.0))

    from scipy import stats

    with np.errstate(divide="ignore", invalid="ignore"):
        t_stats = np.where(se > 0.0, beta / se, 0.0)
    p_values = 2.0 * stats.t.sf(np.abs(t_stats), dof)

    r_squared = 1.0 - sse / sst if sst > 0.0 else 0.0
    r_squared_adj = 1.0 - (1.0 - r_squared) * (n - 1) / dof if dof > 0 else 0.0

    k = p - 1
    ssr = sst - sse
    if k > 0 and sse > 0.0 and dof > 0:
        f_statistic = (ssr / k) / (sse / dof)
        f_pvalue = float(stats.f.sf(f_statistic, k, dof))
    else:
        f_statistic = float("nan")
        f_pvalue = float("nan")

    condition_number = float(np.linalg.cond(X))
    confidence = _classify_multivariate_confidence(n, f_pvalue, condition_number, rank_deficient)

    collinear = (
        rank_deficient
        or not np.isfinite(condition_number)
        or condition_number >= _COLLINEARITY_CONDITION_THRESHOLD
    )
    collinearity_warning = _COLLINEARITY_WARNING if collinear else ""

    coefficients = {name: float(beta[i + 1]) for i, name in enumerate(feature_names)}
    std_errors = {name: float(se[i + 1]) for i, name in enumerate(feature_names)}
    t_stats_out = {name: float(t_stats[i + 1]) for i, name in enumerate(feature_names)}
    p_values_out = {name: float(p_values[i + 1]) for i, name in enumerate(feature_names)}
    feature_means = {
        name: float(np.mean(predictor_cols[i])) for i, name in enumerate(feature_names)
    }

    beta1 = coefficients.get("pf_vol", coefficients[feature_names[0]])

    return {
        "beta0": float(beta[0]),
        "beta1": float(beta1),
        "coefficients": coefficients,
        "std_errors": std_errors,
        "t_stats": t_stats_out,
        "p_values": p_values_out,
        "r_squared": float(r_squared),
        "r_squared_adj": float(r_squared_adj),
        "p_value": float(f_pvalue),
        "f_statistic": float(f_statistic),
        "f_pvalue": float(f_pvalue),
        "n": n,
        "dof": int(dof),
        "condition_number": condition_number,
        "features_used": list(feature_names),
        "feature_means": feature_means,
        "collinearity_warning": collinearity_warning,
        "confidence": confidence,
        "is_significant": bool(np.isfinite(f_pvalue) and f_pvalue < 0.05),
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


def compute_stemming_crest_correlation(
    blast_df: pd.DataFrame,
    comparisons: List[dict],
    bench_height: float = 15.0,
    taco_column: Optional[str] = None,
) -> dict:
    """Test the hypothesis ``short stemming -> high |delta_crest|`` per bench.

    Structural twin of :func:`compute_pasadura_toe_correlation`: same return
    shape, same guards, same lazy ``scipy.stats.pearsonr`` pattern. The
    stemming (taco) column is auto-resolved via
    :data:`core.blast_metrics._TACO_CANDIDATES` unless the caller pins it
    with ``taco_column``.

    Parameters
    ----------
    blast_df : pd.DataFrame
        Processed blast holes (output of :func:`procesar_pozos`) with
        a stemming column (``Taco_m`` / ``Taco`` / ``Stemming``) and
        ``Z_collar``.
    comparisons : list of dict
        Per-bench reconciliation results. Each item is expected to expose
        ``level`` (design toe elevation as a string) and ``delta_crest``
        (m, signed).
    bench_height : float
        Bench height (m) used to derive the floor elevation from the
        collar.
    taco_column : str, optional
        Explicit name of the stemming column. When ``None`` the function
        picks the first present among ``_TACO_CANDIDATES``
        (``Taco_m``, ``Taco``, ``Stemming``).

    Returns
    -------
    dict
        - ``stemming_per_bench``: dict[float, float], mean stemming (m) per
          floor elevation.
        - ``crest_per_bench``: dict[float, float], mean ``delta_crest``
          (m) per floor elevation, for the matching level.
        - ``r``: float, Pearson correlation between the two per-bench
          series (``0.0`` when fewer than two paired samples).
        - ``p_value``: float, two-sided p-value for ``r == 0`` (``nan``
          when undefined).
        - ``n_benches``: int, count of paired benches used in the
          correlation.
        - ``interpretation``: str, one-sentence read of the result.
    """

    empty = {
        "stemming_per_bench": {},
        "crest_per_bench": {},
        "r": 0.0,
        "p_value": float("nan"),
        "n_benches": 0,
        "interpretation": "Sin datos suficientes para correlacionar stemming y delta_crest.",
    }

    if (
        blast_df is None
        or blast_df.empty
        or not comparisons
        or "Z_collar" not in blast_df.columns
    ):
        return empty

    resolved_taco = taco_column if taco_column else first_present_column(blast_df, _TACO_CANDIDATES)
    if resolved_taco is None or resolved_taco not in blast_df.columns:
        return empty

    df = blast_df.copy()
    df["_taco"] = pd.to_numeric(df[resolved_taco], errors="coerce")
    if not df["_taco"].notna().any():
        return empty

    df["_floor"] = (df["Z_collar"] - bench_height).round(0)

    stemming_per_bench: Dict[float, float] = (
        df.groupby("_floor")["_taco"].mean().to_dict()
    )

    df_comps = pd.DataFrame(comparisons)
    if "level" not in df_comps.columns or "delta_crest" not in df_comps.columns:
        return empty

    df_comps = df_comps.dropna(subset=["level", "delta_crest"])
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

    crest_per_bench_raw: Dict[int, float] = (
        df_comps.groupby("_level_int")["delta_crest"].mean().to_dict()
    )

    paired_taco: List[float] = []
    paired_crest: List[float] = []
    matched_stemming: Dict[float, float] = {}
    matched_crest: Dict[float, float] = {}
    for level, stemming_mean in stemming_per_bench.items():
        try:
            level_int = int(round(float(level)))
        except (TypeError, ValueError):
            continue
        if level_int in crest_per_bench_raw:
            matched_stemming[float(level_int)] = float(stemming_mean)
            matched_crest[float(level_int)] = float(crest_per_bench_raw[level_int])
            paired_taco.append(float(stemming_mean))
            paired_crest.append(float(crest_per_bench_raw[level_int]))

    n = len(paired_taco)
    if n < 2:
        return {
            "stemming_per_bench": matched_stemming,
            "crest_per_bench": matched_crest,
            "r": 0.0,
            "p_value": float("nan"),
            "n_benches": n,
            "interpretation": (
                "Solo hay " + str(n) + " banco(s) pareado(s); se necesitan al menos 2."
            ),
        }

    taco_arr = np.asarray(paired_taco, dtype=float)
    crest_arr = np.asarray(paired_crest, dtype=float)

    if float(np.var(taco_arr)) <= 0.0 or float(np.var(crest_arr)) <= 0.0:
        r_val = 0.0
        p_val = float("nan")
    else:
        from scipy import stats

        r_res = stats.pearsonr(taco_arr, crest_arr)
        r_val = float(r_res.statistic)
        p_val = float(r_res.pvalue)

    if r_val < -0.3:
        interpretation = (
            f"Correlacion negativa (r={r_val:.2f}): bancos con taco corto "
            "se asocian a mayor sobre-excavacion de la cresta. "
            "Consistente con gases venteando hacia arriba (banco soplado)."
        )
    elif r_val > 0.3:
        interpretation = (
            f"Correlacion positiva (r={r_val:.2f}): taco mayor se asocia "
            "a mayor sobre-excavacion de la cresta. "
            "Sugiere energia baja / taco excesivo reteniendo gases."
        )
    else:
        interpretation = (
            f"Correlacion debil/nula (r={r_val:.2f}): stemming y delta_crest "
            "no muestran relacion lineal clara con estos datos."
        )

    return {
        "stemming_per_bench": matched_stemming,
        "crest_per_bench": matched_crest,
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
