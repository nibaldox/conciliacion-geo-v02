"""Forward predictor of expected back-break before drilling.

This module adds a *prospective* estimator that answers "¿cuánto back-break
espero si ejecuto esta tronadura?" using one of two paths:

- **Multivariate**: when a fitted :func:`core.blast_model.fit_multivariate_damage_model`
  dict is supplied (with sufficient confidence), the prediction follows the
  fitted coefficients with a pooled-SE confidence interval.
- **Empirical fallback**: a transparent heuristic
  ``empirical_k · burden · (pf / pf_optimal) · rock_factor`` plus a
  Holmberg-Persson cross-check appended to ``notes`` as a sanity number.

The function never raises; malformed inputs degrade the ``confidence``
field (HIGH → MEDIUM → LOW → INSUFFICIENT) and substitute defaults from
:class:`core.config.BackbreakDefaults`. Legacy forensic fits
(``fit_multivariate_damage_model``, ``predict_damage_for_pf``, the advisor
helpers) are deliberately left untouched.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.config import BACKBREAK, BackbreakDefaults


@dataclass(frozen=True)
class BackbreakPrediction:
    predicted_m: float
    ci_low_m: float
    ci_high_m: float
    method: str
    confidence: str
    notes: List[str] = field(default_factory=list)


_MULTIVARIATE_FEATURE_MAP: Dict[str, str] = {
    "pf_vol": "pf_kgm3",
    "burden": "burden_m",
    "spacing_burden_ratio": "spacing_burden_ratio",
    "stemming": "stemming_m",
}


def _is_finite_number(value: Any) -> bool:
    if value is None:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def _coerce(value: Any, default: float, label: str, notes: List[str]) -> float:
    """Coerce ``value`` to a finite non-negative float, substituting on failure."""
    if not _is_finite_number(value):
        notes.append(f"substituted:{label}")
        return float(default)
    v = float(value)
    if v < 0.0:
        notes.append(f"substituted:{label}")
        return float(default)
    return v


def _estimate_residual_variance(model: Dict[str, Any]) -> float:
    """Estimate residual variance ``σ²`` from the model's per-coefficient SE.

    The fitted model only stores ``std_errors[f]² = σ² · (XᵀX)⁻¹[f, f]``.
    Without ``XᵀX`` in the dict we approximate the per-feature leverage as
    ``1/n`` (true for centred, unit-variance orthogonal predictors), giving
    ``σ² ≈ mean(se²) · n``. This is intentionally a heuristic — the model
    explicitly does not carry ``σ²`` and CI coverage remains approximate.
    """
    n = int(model.get("n", 0)) or 1
    ses = model.get("std_errors", {}) or {}
    vals = [float(se) * float(se) for se in ses.values() if _is_finite_number(se)]
    if not vals:
        return 0.0
    return float(sum(vals) / len(vals)) * float(n)


def _build_feature_row(
    burden: float,
    spacing: float,
    pf: float,
    stemming: float,
) -> Dict[str, float]:
    return {
        "pf_vol": float(pf),
        "burden": float(burden),
        "spacing_burden_ratio": float(spacing) / float(burden) if burden > 0.0 else 1.0,
        "stemming": float(stemming),
    }


def _model_features_overlap(model: Dict[str, Any], feature_row: Dict[str, float]) -> List[str]:
    coeffs = model.get("coefficients") or {}
    return [name for name in feature_row if name in coeffs]


def _multivariate_confidence(
    model: Dict[str, Any],
    feature_row: Dict[str, float],
    any_substitution: bool,
) -> str:
    base = model.get("confidence", "INSUFFICIENT")
    if base == "INSUFFICIENT":
        return "INSUFFICIENT"
    if any_substitution:
        return "LOW"
    feature_means = model.get("feature_means", {}) or {}
    in_range = True
    for feat, x in feature_row.items():
        m = feature_means.get(feat)
        if not _is_finite_number(m) or float(m) <= 0.0:
            continue
        ratio = float(x) / float(m)
        if ratio < 0.5 or ratio > 2.0:
            in_range = False
            break
    if base == "HIGH" and in_range:
        return "HIGH"
    if base == "HIGH":
        return "MEDIUM"
    return base


def _multivariate_predict(
    model: Dict[str, Any],
    feature_row: Dict[str, float],
    alpha: float,
    matching: List[str],
) -> tuple[float, float, float]:
    coeffs = model.get("coefficients", {}) or {}
    ses = model.get("std_errors", {}) or {}
    beta0 = float(model.get("beta0", 0.0))
    n = int(model.get("n", 0))
    p = max(len(coeffs), 1)
    dof = max(int(model.get("dof", n - p - 1)), 1)

    predicted = beta0
    pooled_var = 0.0
    for feat in matching:
        x = float(feature_row[feat])
        predicted += float(coeffs[feat]) * x
        if feat in ses:
            se = float(ses[feat])
            pooled_var += se * se * x * x

    sigma2 = _estimate_residual_variance(model)
    se_pred = math.sqrt(max(pooled_var + sigma2, 0.0))

    try:
        from scipy import stats
        z = float(stats.t.ppf(1.0 - alpha / 2.0, dof))
    except Exception:
        z = 1.959963984540054

    ci_low = predicted - z * se_pred
    ci_high = predicted + z * se_pred
    return predicted, ci_low, ci_high


def _empirical_predict(
    burden: float,
    spacing: float,
    pf: float,
    rock_factor: float,
    bench_height: float,
    defaults: BackbreakDefaults,
) -> tuple[float, float, float, float]:
    pf_opt = defaults.pf_optimal_default_kgm3
    ratio = (pf / pf_opt) if pf > 0.0 else 1.0
    predicted = max(defaults.empirical_k * burden * ratio * rock_factor, 0.0)
    band = defaults.ci_band_pct
    ci_low = max(predicted * (1.0 - band), 0.0)
    ci_high = predicted * (1.0 + band)

    kg_per_hole = max(pf, 0.0) * max(burden, 0.0) * max(spacing, 0.0) * max(bench_height, 0.0)
    r_damage = defaults.hp_constant * math.sqrt(kg_per_hole)
    r_damage = max(
        min(r_damage, defaults.clamp_high_factor_b * max(burden, 0.0)),
        defaults.clamp_low_factor_b * max(burden, 0.0),
    )
    return predicted, ci_low, ci_high, r_damage


def _hp_note(burden: float, r_damage: float, defaults: BackbreakDefaults) -> str:
    low = defaults.clamp_low_factor_b * burden
    high = defaults.clamp_high_factor_b * burden
    return (
        f"Holmberg-Persson cross-check: {r_damage:.2f} m "
        f"(clamped to [{defaults.clamp_low_factor_b}·B, {defaults.clamp_high_factor_b}·B]"
        f"=[{low:.2f}, {high:.2f}] m)"
    )


def predict_backbreak(
    burden_m: Any,
    spacing_m: Any,
    pf_kgm3: Any,
    stemming_m: Any,
    diameter_mm: Any,
    model: Optional[Dict[str, Any]] = None,
    rock_factor: Any = 1.0,
    *,
    alpha: float = 0.05,
    bench_height_m: Any = 15.0,
    defaults: Optional[BackbreakDefaults] = None,
) -> BackbreakPrediction:
    """Return a :class:`BackbreakPrediction` for the supplied design point.

    Parameters
    ----------
    burden_m, spacing_m, pf_kgm3, stemming_m, diameter_mm
        Five-point design row. ``diameter_mm`` is reserved for future
        per-diameter energy scaling; currently informational only.
    model : dict, optional
        Output of :func:`core.blast_model.fit_multivariate_damage_model`.
        When ``None`` or its ``confidence`` is ``"INSUFFICIENT"``, the
        empirical fallback path is used.
    rock_factor : float
        Rock-mass stiffness multiplier; clamped to
        ``[defaults.rock_factor_min, defaults.rock_factor_max]``.
    alpha : float
        Miscoverage for the CI; default 0.05 → 95% CI.
    bench_height_m : float
        Bench height used by the Holmberg-Persson cross-check.
    defaults : BackbreakDefaults, optional
        Override defaults; falls back to the ``BACKBREAK`` singleton.

    Returns
    -------
    BackbreakPrediction
        Frozen dataclass with ``predicted_m``, ``ci_low_m``, ``ci_high_m``,
        ``method``, ``confidence`` and a ``notes`` list of audit strings.
    """
    if defaults is None:
        defaults = BACKBREAK
    notes: List[str] = []

    burden = _coerce(burden_m, defaults.default_burden_m, "burden_m", notes)
    spacing = _coerce(spacing_m, defaults.default_spacing_m, "spacing_m", notes)
    pf = _coerce(pf_kgm3, defaults.pf_optimal_default_kgm3, "pf_kgm3", notes)
    stemming = _coerce(stemming_m, defaults.default_stemming_m, "stemming_m", notes)
    bench_height = (
        float(bench_height_m)
        if _is_finite_number(bench_height_m) and float(bench_height_m) > 0.0
        else defaults.bench_height_m
    )

    if _is_finite_number(rock_factor):
        rf = float(rock_factor)
    else:
        rf = 1.0
        notes.append("substituted:rock_factor")
    if rf < defaults.rock_factor_min:
        notes.append(f"clamped:rock_factor {rf}→{defaults.rock_factor_min}")
        rf = defaults.rock_factor_min
    elif rf > defaults.rock_factor_max:
        notes.append(f"clamped:rock_factor {rf}→{defaults.rock_factor_max}")
        rf = defaults.rock_factor_max

    substituted_count = sum(1 for n in notes if n.startswith("substituted:"))
    all_original_unusable = not any(
        _is_finite_number(v) for v in (burden_m, spacing_m, pf_kgm3, stemming_m)
    )
    any_substitution = substituted_count > 0

    use_multivariate = (
        model is not None
        and isinstance(model, dict)
        and model.get("confidence") not in (None, "", "INSUFFICIENT")
        and bool(model.get("coefficients"))
    )

    if use_multivariate:
        feature_row = _build_feature_row(burden, spacing, pf, stemming)
        matching = _model_features_overlap(model, feature_row)
        if not matching:
            notes.append("multivariate_not_available, using empirical_fallback")
            use_multivariate = False
        else:
            try:
                predicted, ci_low, ci_high = _multivariate_predict(
                    model, feature_row, alpha, matching
                )
                method = "multivariate"
                confidence = _multivariate_confidence(model, feature_row, any_substitution)
                if predicted < 0.0:
                    notes.append("clamped_nonnegative")
                    predicted = 0.0
                    ci_low = min(ci_low, 0.0)
                    ci_high = max(ci_high, 0.0)
            except Exception as exc:
                notes.append(
                    f"multivariate_failed:{type(exc).__name__}, using empirical_fallback"
                )
                use_multivariate = False

    if not use_multivariate:
        if model is not None and isinstance(model, dict):
            notes.append("multivariate_not_available, using empirical_fallback")
        predicted, ci_low, ci_high, r_damage = _empirical_predict(
            burden, spacing, pf, rf, bench_height, defaults
        )
        method = "empirical_fallback"
        if all_original_unusable:
            confidence = "INSUFFICIENT"
            predicted = 0.0
            ci_low = 0.0
            ci_high = 0.0
        elif any_substitution:
            confidence = "LOW"
        else:
            confidence = "MEDIUM"
        notes.append(_hp_note(burden, r_damage, defaults))

    if predicted < ci_low:
        ci_low = predicted
    if predicted > ci_high:
        ci_high = predicted

    return BackbreakPrediction(
        predicted_m=float(predicted),
        ci_low_m=float(ci_low),
        ci_high_m=float(ci_high),
        method=method,
        confidence=confidence,
        notes=list(notes),
    )


def predict_backbreak_from_design(
    design: Optional[Dict[str, Any]],
    model: Optional[Dict[str, Any]] = None,
    *,
    alpha: float = 0.05,
    defaults: Optional[BackbreakDefaults] = None,
) -> BackbreakPrediction:
    """Thin wrapper that accepts the ``design_params`` dict form from the spec.

    Missing keys fall back to ``None`` so :func:`predict_backbreak` can
    substitute defaults uniformly. ``rock_factor`` and ``bench_height_m``
    may be embedded in the dict.
    """
    if not design or not isinstance(design, dict):
        design = {}
    return predict_backbreak(
        design.get("burden_m"),
        design.get("spacing_m"),
        design.get("pf_kgm3"),
        design.get("stemming_m"),
        design.get("diameter_mm"),
        model=model,
        rock_factor=design.get("rock_factor", 1.0),
        alpha=alpha,
        bench_height_m=design.get("bench_height_m", 15.0),
        defaults=defaults,
    )