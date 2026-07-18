"""Quantitative PF-adjustment recommendation engine.

Closes the loop started by :mod:`core.blast_model`: given the fitted
``damage = beta0 + beta1 * PF`` regression and a per-section / per-sector
current powder factor, invert the line to solve for the PF that would
yield a target overbreak and produce a single Spanish-neutral sentence
summarising the change.

All helpers in this module are pure functions: no Streamlit, no Plotly,
no FastAPI. They can be unit-tested in isolation and consumed by either
the legacy Streamlit UI or the new web frontend via thin wrappers.
"""
from __future__ import annotations

import math
import warnings
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from core.compliance_status import (
    FEASIBILITY_APPLICABLE,
    FEASIBILITY_CAUTION,
    FEASIBILITY_INFEASIBLE,
    FEASIBILITY_INSUFFICIENT,
    STATUS_NO_CUMPLE,
)
from core.config import ADVISOR, POWDER_FACTOR


DIRECTION_REDUCE = "REDUCE"
DIRECTION_INCREASE = "INCREASE"
DIRECTION_NONE = "NONE"


_BETA1_EPSILON = 1e-9


def _safe_pct_change(new_value: float, old_value: float) -> float:
    if not np.isfinite(old_value) or abs(float(old_value)) < _BETA1_EPSILON:
        return float("nan")
    return float((new_value - old_value) / old_value * 100.0)


def _invert_pf(model: Dict[str, Any], target_damage: float) -> Optional[float]:
    beta0 = float(model.get("beta0", 0.0))
    beta1 = float(model.get("beta1", 0.0))
    if not np.isfinite(beta1) or abs(beta1) < _BETA1_EPSILON:
        return None
    if not np.isfinite(target_damage):
        return None
    return float((target_damage - beta0) / beta1)


def _classify_feasibility(
    delta_pf_pct: float,
    target_pf: float,
    pf_optimal: float,
    has_model: bool,
) -> str:
    if not has_model or not np.isfinite(target_pf):
        return FEASIBILITY_INSUFFICIENT
    if target_pf < 0.0:
        return FEASIBILITY_CAUTION
    upper_bound = pf_optimal * ADVISOR.pf_upper_bound_factor
    if upper_bound > 0.0 and target_pf > upper_bound:
        return FEASIBILITY_CAUTION
    if np.isfinite(delta_pf_pct) and abs(delta_pf_pct) > ADVISOR.max_recommendation_pct:
        return FEASIBILITY_CAUTION
    return FEASIBILITY_APPLICABLE


def _build_message(
    feasibility: str,
    current_pf: float,
    target_pf: float,
    delta_pf: float,
    delta_pf_pct: float,
    predicted_current_damage: float,
    target_overbreak_m: float,
    confidence: str,
    n: int,
    p_value: float,
) -> str:
    cur = float(current_pf)
    tgt = float(target_pf)
    dpf = float(delta_pf)
    dmg = float(predicted_current_damage)
    pct = float(delta_pf_pct) if np.isfinite(delta_pf_pct) else 0.0
    p_str = f"{p_value:.3f}" if np.isfinite(float(p_value)) else "n/a"
    n_str = str(int(n))

    if feasibility == FEASIBILITY_INSUFFICIENT:
        return (
            "Modelo sin confianza estadistica suficiente "
            f"(n={n_str}, p={p_str}); no se puede emitir recomendacion cuantitativa."
        )

    if feasibility == FEASIBILITY_CAUTION:
        if np.isfinite(delta_pf_pct) and abs(delta_pf_pct) > ADVISOR.max_recommendation_pct:
            return (
                f"Delta PF requerido ({pct:+.0f}%) excede el {ADVISOR.max_recommendation_pct:.0f}% "
                "permitido; revisar patron de carga o subdividir la voladura."
            )
        if tgt < 0.0:
            return (
                f"PF objetivo ({tgt:.2f} kg/m3) resulta fisicamente imposible (negativo); "
                "revisar beta1 y beta0 del modelo antes de recomendar."
            )
        upper = POWDER_FACTOR.pf_optimal_kgm3 * ADVISOR.pf_upper_bound_factor
        return (
            f"PF objetivo ({tgt:.2f} kg/m3) supera {ADVISOR.pf_upper_bound_factor:g}x el optimo de diseno ({upper:.2f} kg/m3); "
            "revisar patron de carga antes de aplicar."
        )

    sign = "+" if pct >= 0 else "-"
    if dpf < 0:
        verb = "Reducir"
        outcome = "acotar sobre-excavacion"
    elif dpf > 0:
        verb = "Aumentar"
        outcome = "elevar el dano"
    else:
        verb = "Mantener"
        outcome = "mantener el dano"
    return (
        f"{verb} PF de {cur:.2f} a {tgt:.2f} kg/m3 ({sign}{abs(pct):.0f}%) proyecta "
        f"{outcome} de {dmg:.2f} m al objetivo de {target_overbreak_m:.2f} m "
        f"(modelo p={p_str}, n={n_str}, confianza {confidence})."
    )


def recommend_pf_adjustment(
    model: Dict[str, Any],
    current_pf: float,
    target_overbreak_m: Optional[float] = None,
) -> Dict[str, Any]:
    """Invert the PF vs. damage regression to suggest a load adjustment.

    Given the model ``damage = beta0 + beta1 * PF`` produced by
    :func:`core.blast_model.fit_powder_factor_damage_model`, solve for the
    PF that would yield ``target_overbreak_m`` metres of damage and
    compare it against ``current_pf``.

    Parameters
    ----------
    model : dict
        Output of :func:`core.blast_model.fit_powder_factor_damage_model`.
    current_pf : float
        Powder factor currently in use (kg/m^3).
    target_overbreak_m : float, optional
        Desired over-excavation target in metres. Defaults to
        ``ADVISOR.target_overbreak_m``.

    Returns
    -------
    dict
        Keys: ``target_pf``, ``current_pf``, ``delta_pf``, ``delta_pf_pct``,
        ``predicted_current_damage``, ``predicted_target_damage``,
        ``feasibility``, ``message``, ``confidence``.
    """
    if model is None:
        model = {}

    if target_overbreak_m is None:
        target_overbreak_m = ADVISOR.target_overbreak_m

    target_overbreak_m = float(target_overbreak_m)
    current_pf = float(current_pf)

    confidence = str(model.get("confidence", "INSUFFICIENT"))
    beta1 = float(model.get("beta1", 0.0))
    beta0 = float(model.get("beta0", 0.0))
    n = int(model.get("n", 0))
    p_value = float(model.get("p_value", float("nan")))

    has_signal = (
        confidence != "INSUFFICIENT"
        and n >= ADVISOR.min_samples_for_advice
        and np.isfinite(beta1)
        and abs(beta1) > _BETA1_EPSILON
    )

    predicted_current_damage = float(beta0 + beta1 * current_pf)
    predicted_target_damage = float(target_overbreak_m)

    if has_signal:
        target_pf = _invert_pf(model, target_overbreak_m)
    else:
        target_pf = None

    if target_pf is None or not np.isfinite(target_pf):
        delta_pf = 0.0
        delta_pf_pct = 0.0
        feasibility = FEASIBILITY_INSUFFICIENT
        target_pf_out: float = current_pf
    else:
        delta_pf = float(target_pf - current_pf)
        delta_pf_pct = _safe_pct_change(target_pf, current_pf)
        if not np.isfinite(delta_pf_pct):
            delta_pf_pct = 0.0
        feasibility = _classify_feasibility(
            delta_pf_pct=delta_pf_pct,
            target_pf=float(target_pf),
            pf_optimal=float(POWDER_FACTOR.pf_optimal_kgm3),
            has_model=True,
        )
        target_pf_out = float(target_pf)

    message = _build_message(
        feasibility=feasibility,
        current_pf=current_pf,
        target_pf=target_pf_out,
        delta_pf=delta_pf,
        delta_pf_pct=delta_pf_pct,
        predicted_current_damage=predicted_current_damage,
        target_overbreak_m=target_overbreak_m,
        confidence=confidence if has_signal else "INSUFFICIENT",
        n=n,
        p_value=p_value,
    )

    return {
        "target_pf": target_pf_out,
        "current_pf": current_pf,
        "delta_pf": float(delta_pf),
        "delta_pf_pct": float(delta_pf_pct),
        "predicted_current_damage": float(predicted_current_damage),
        "predicted_target_damage": float(predicted_target_damage),
        "feasibility": feasibility,
        "message": message,
        "confidence": confidence if has_signal else "INSUFFICIENT",
    }


_MULTIVARIATE_DISPATCH_MIN_SAMPLES = 12
_MULTIVARIATE_DISPATCH_MIN_FEATURES = 3


_MULTIVARIATE_INSUFFICIENT: Dict[str, Any] = {
    "target_burden": 0.0,
    "current_burden": 0.0,
    "delta_burden": 0.0,
    "delta_burden_pct": 0.0,
    "predicted_current_damage": 0.0,
    "predicted_target_damage": 0.0,
    "feasibility": FEASIBILITY_INSUFFICIENT,
    "message": "",
    "confidence": "INSUFFICIENT",
}


def _invert_burden(model: Dict[str, Any], target_damage: float) -> Optional[float]:
    coefficients = model.get("coefficients", {}) or {}
    feature_means = model.get("feature_means", {}) or {}
    beta_burden = float(coefficients.get("burden", 0.0))
    if not np.isfinite(beta_burden) or abs(beta_burden) < _BETA1_EPSILON:
        return None
    if not np.isfinite(target_damage):
        return None
    base = float(model.get("beta0", 0.0))
    for name, coef in coefficients.items():
        if name == "burden":
            continue
        base += float(coef) * float(feature_means.get(name, 0.0))
    return float((target_damage - base) / beta_burden)


def _predict_damage_at_burden(model: Dict[str, Any], burden: float) -> float:
    coefficients = model.get("coefficients", {}) or {}
    feature_means = model.get("feature_means", {}) or {}
    value = float(model.get("beta0", 0.0))
    for name, coef in coefficients.items():
        x = float(burden) if name == "burden" else float(feature_means.get(name, 0.0))
        value += float(coef) * x
    return float(value)


def _build_burden_message(
    feasibility: str,
    current_burden: float,
    target_burden: float,
    delta_burden: float,
    delta_burden_pct: float,
    predicted_current_damage: float,
    target_overbreak_m: float,
    confidence: str,
    n: int,
    f_pvalue: float,
) -> str:
    cur = float(current_burden)
    tgt = float(target_burden)
    dpct = float(delta_burden_pct) if np.isfinite(delta_burden_pct) else 0.0
    dmg = float(predicted_current_damage)
    p_str = f"{f_pvalue:.3f}" if np.isfinite(float(f_pvalue)) else "n/a"
    n_str = str(int(n))

    if feasibility == FEASIBILITY_INSUFFICIENT:
        return (
            "Modelo multivariado sin confianza estadistica suficiente "
            f"(n={n_str}, p={p_str}); no se puede recomendar ajuste de burden."
        )

    if feasibility == FEASIBILITY_CAUTION:
        return (
            f"Burden objetivo ({tgt:.2f} m) queda fuera del rango operativo "
            f"[0.5x, 2x] del burden actual ({cur:.2f} m); revisar diseno de malla "
            "antes de aplicar."
        )

    verb = "Reducir" if delta_burden < 0 else "Aumentar" if delta_burden > 0 else "Mantener"
    sign = "+" if dpct >= 0 else "-"
    return (
        f"{verb} burden de {cur:.2f} a {tgt:.2f} m ({sign}{abs(dpct):.0f}%) proyecta "
        f"acotar sobre-excavacion de {dmg:.2f} m al objetivo de {target_overbreak_m:.2f} m "
        f"(modelo p={p_str}, n={n_str}, confianza {confidence})."
    )


def recommend_burden_adjustment(
    model: Dict[str, Any],
    current_burden: float,
    target_overbreak_m: Optional[float] = None,
) -> Dict[str, Any]:
    """Invert the multivariate model for burden, holding other predictors fixed.

    Solve ``target = beta0 + sum_i beta_i * mean_i + beta_burden * target_burden``
    for ``target_burden`` while every non-burden predictor is held at
    ``model['feature_means']``. Targets outside ``[0.5 * B, 2 * B]`` of the
    current burden are flagged ``CAUTION``.

    Parameters
    ----------
    model : dict
        Output of :func:`core.blast_model.fit_multivariate_damage_model`.
    current_burden : float
        Burden currently in use (m).
    target_overbreak_m : float, optional
        Desired over-excavation target (m). Defaults to
        ``ADVISOR.target_overbreak_m``.

    Returns
    -------
    dict
        Keys: ``target_burden``, ``current_burden``, ``delta_burden``,
        ``delta_burden_pct``, ``predicted_current_damage``,
        ``predicted_target_damage``, ``feasibility``, ``message``,
        ``confidence``.
    """
    if model is None:
        model = {}

    if target_overbreak_m is None:
        target_overbreak_m = ADVISOR.target_overbreak_m

    target_overbreak_m = float(target_overbreak_m)
    current_burden = float(current_burden)

    confidence = str(model.get("confidence", "INSUFFICIENT"))
    coefficients = model.get("coefficients", {}) or {}
    beta_burden = float(coefficients.get("burden", 0.0))
    n = int(model.get("n", 0))
    f_pvalue = float(model.get("f_pvalue", model.get("p_value", float("nan"))))

    has_signal = (
        confidence != "INSUFFICIENT"
        and n >= ADVISOR.min_samples_for_advice
        and np.isfinite(beta_burden)
        and abs(beta_burden) > _BETA1_EPSILON
    )

    predicted_current_damage = _predict_damage_at_burden(model, current_burden)
    target_burden = _invert_burden(model, target_overbreak_m) if has_signal else None

    if target_burden is None or not np.isfinite(target_burden):
        result = dict(_MULTIVARIATE_INSUFFICIENT)
        result["current_burden"] = current_burden
        result["target_burden"] = current_burden
        result["predicted_current_damage"] = float(predicted_current_damage)
        result["predicted_target_damage"] = target_overbreak_m
        result["message"] = _build_burden_message(
            FEASIBILITY_INSUFFICIENT, current_burden, current_burden, 0.0, 0.0,
            predicted_current_damage, target_overbreak_m, "INSUFFICIENT", n, f_pvalue,
        )
        return result

    delta_burden = float(target_burden - current_burden)
    delta_burden_pct = _safe_pct_change(target_burden, current_burden)
    if not np.isfinite(delta_burden_pct):
        delta_burden_pct = 0.0

    feasibility = _classify_feasibility(
        delta_pf_pct=delta_burden_pct,
        target_pf=float(target_burden),
        pf_optimal=current_burden * (2.0 / ADVISOR.pf_upper_bound_factor),
        has_model=True,
    )
    if current_burden > 0.0 and (
        target_burden < 0.5 * current_burden or target_burden > 2.0 * current_burden
    ):
        feasibility = FEASIBILITY_CAUTION

    message = _build_burden_message(
        feasibility, current_burden, float(target_burden), delta_burden, delta_burden_pct,
        predicted_current_damage, target_overbreak_m, confidence, n, f_pvalue,
    )

    return {
        "target_burden": float(target_burden),
        "current_burden": current_burden,
        "delta_burden": delta_burden,
        "delta_burden_pct": float(delta_burden_pct),
        "predicted_current_damage": float(predicted_current_damage),
        "predicted_target_damage": target_overbreak_m,
        "feasibility": feasibility,
        "message": message,
        "confidence": confidence,
    }


def recommend_multivariate(
    model: Dict[str, Any],
    current_burden: float,
    target_overbreak_m: Optional[float] = None,
) -> Dict[str, Any]:
    """Dispatch to :func:`recommend_burden_adjustment` when the model qualifies.

    Routes to the burden-aware path only when the multivariate model has at
    least ``12`` samples, at least ``3`` fitted features and a confidence
    other than ``INSUFFICIENT``. Otherwise returns an INSUFFICIENT skeleton.
    """
    if model is None:
        model = {}

    n = int(model.get("n", 0))
    features = model.get("features_used", []) or []
    confidence = str(model.get("confidence", "INSUFFICIENT"))

    qualifies = (
        n >= _MULTIVARIATE_DISPATCH_MIN_SAMPLES
        and len(features) >= _MULTIVARIATE_DISPATCH_MIN_FEATURES
        and confidence != "INSUFFICIENT"
    )

    if qualifies:
        return recommend_burden_adjustment(model, current_burden, target_overbreak_m)

    current_burden = float(current_burden)
    target = ADVISOR.target_overbreak_m if target_overbreak_m is None else float(target_overbreak_m)
    result = dict(_MULTIVARIATE_INSUFFICIENT)
    result["current_burden"] = current_burden
    result["target_burden"] = current_burden
    result["predicted_target_damage"] = target
    result["message"] = _build_burden_message(
        FEASIBILITY_INSUFFICIENT, current_burden, current_burden, 0.0, 0.0,
        0.0, target, "INSUFFICIENT", n, float(model.get("f_pvalue", float("nan"))),
    )
    return result


def recommend_charge_change_pct(
    model: Dict[str, Any],
    current_pf: float,
    target_overbreak_m: Optional[float] = None,
) -> Dict[str, Any]:
    """Shortcut returning only the percentage change and direction.

    Parameters
    ----------
    model : dict
        Output of :func:`core.blast_model.fit_powder_factor_damage_model`.
    current_pf : float
        Current powder factor (kg/m^3).
    target_overbreak_m : float, optional
        Damage target. Defaults to ``ADVISOR.target_overbreak_m``.

    Returns
    -------
    dict
        ``delta_pct`` (signed float, %), ``direction`` (``'REDUCE'`` /
        ``'INCREASE'`` / ``'NONE'``) and ``feasibility`` (mirrors
        :func:`recommend_pf_adjustment`).
    """
    rec = recommend_pf_adjustment(model, current_pf, target_overbreak_m)

    delta_pct = float(rec["delta_pf_pct"])
    if not np.isfinite(delta_pct) or abs(delta_pct) < 1e-6:
        direction = DIRECTION_NONE
        delta_pct = 0.0
    elif delta_pct < 0.0:
        direction = DIRECTION_REDUCE
    else:
        direction = DIRECTION_INCREASE

    return {
        "delta_pct": delta_pct,
        "direction": direction,
        "feasibility": rec["feasibility"],
    }


def recommend_by_sector(
    df_sections: pd.DataFrame,
    model: Dict[str, Any],
    group_col: str = "sector",
    pf_col: str = "pf_vol_avg_kgm3",
    damage_col: str = "avg_over_break",
    target_overbreak_m: Optional[float] = None,
) -> pd.DataFrame:
    """Apply :func:`recommend_pf_adjustment` to each group in ``df_sections``.

    Parameters
    ----------
    df_sections : pd.DataFrame
        Per-section (or per-group) table with at least ``pf_col``,
        ``damage_col`` and the grouping column.
    model : dict
        Output of :func:`core.blast_model.fit_powder_factor_damage_model`.
    group_col : str
        Column to group by (default ``'sector'``).
    pf_col : str
        Column holding the current powder factor (kg/m^3).
    damage_col : str
        Column with mean over-break (signed, metres). Currently unused
        beyond the column-presence check, but documented for symmetry
        with future per-group re-fit strategies.
    target_overbreak_m : float, optional
        Forwarded to :func:`recommend_pf_adjustment`.

    Returns
    -------
    pd.DataFrame
        One row per group with columns ``group_value``, ``n_wells``,
        ``current_pf``, ``current_damage_pred``, ``target_pf``,
        ``delta_pf``, ``delta_pf_pct``, ``feasibility``, ``message``.
        Returns an empty DataFrame (with a ``message`` row carrying a
        warning) when ``group_col`` is missing.
    """
    del damage_col

    columns = [
        "group_value",
        "n_wells",
        "current_pf",
        "current_damage_pred",
        "target_pf",
        "delta_pf",
        "delta_pf_pct",
        "feasibility",
        "message",
    ]

    if df_sections is None or not isinstance(df_sections, pd.DataFrame):
        warnings.warn("df_sections is not a DataFrame; returning empty result.", stacklevel=2)
        return pd.DataFrame(columns=columns)

    if group_col not in df_sections.columns:
        warnings.warn(
            f"Column '{group_col}' not found in df_sections; returning empty result.",
            stacklevel=2,
        )
        return pd.DataFrame(columns=columns)

    if pf_col not in df_sections.columns:
        warnings.warn(
            f"Column '{pf_col}' not found in df_sections; returning empty result.",
            stacklevel=2,
        )
        return pd.DataFrame(columns=columns)

    rows = []
    for group_value, group_df in df_sections.groupby(group_col, dropna=False):
        current_pf_raw = group_df[pf_col].dropna()
        if current_pf_raw.empty:
            current_pf_value = float(ADVISOR.pf_optimal_default_kgm3)
            n_wells = 0
        else:
            current_pf_value = float(current_pf_raw.mean())
            n_wells = int(current_pf_raw.size)

        rec = recommend_pf_adjustment(
            model=model,
            current_pf=current_pf_value,
            target_overbreak_m=target_overbreak_m,
        )

        rows.append(
            {
                "group_value": group_value,
                "n_wells": n_wells,
                "current_pf": float(rec["current_pf"]),
                "current_damage_pred": float(rec["predicted_current_damage"]),
                "target_pf": float(rec["target_pf"]),
                "delta_pf": float(rec["delta_pf"]),
                "delta_pf_pct": float(rec["delta_pf_pct"]),
                "feasibility": rec["feasibility"],
                "message": rec["message"],
            }
        )

    return pd.DataFrame(rows, columns=columns)


def format_recommendation_text(rec: Dict[str, Any], section_name: str = "") -> str:
    """Render a recommendation dict as a short Spanish-neutral sentence.

    Parameters
    ----------
    rec : dict
        Output of :func:`recommend_pf_adjustment` (or a row from
        :func:`recommend_by_sector`).
    section_name : str, optional
        Section or sector label to prefix the message with.

    Returns
    -------
    str
        A 1-2 sentence Spanish-neutral message. The numeric
        ``delta_pf`` is always rendered (e.g. ``"-0.17 kg/m3"``) so
        downstream tests can assert on its presence.
    """
    if not isinstance(rec, dict):
        return ""

    feasibility = str(rec.get("feasibility", FEASIBILITY_INSUFFICIENT))
    current_pf = float(rec.get("current_pf", 0.0))
    target_pf = float(rec.get("target_pf", 0.0))
    delta_pf = float(rec.get("delta_pf", 0.0))
    delta_pf_pct = float(rec.get("delta_pf_pct", 0.0))
    predicted_damage = float(rec.get("predicted_current_damage", 0.0))
    target_damage = float(rec.get("predicted_target_damage", ADVISOR.target_overbreak_m))
    n = int(rec.get("n", 0)) if "n" in rec else 0

    delta_str = f"{delta_pf:+.2f} kg/m3"
    pct_str = f"{delta_pf_pct:+.0f}%" if np.isfinite(delta_pf_pct) else "0%"

    prefix = f"[{section_name}] " if section_name else ""

    if feasibility == FEASIBILITY_INSUFFICIENT:
        return (
            f"{prefix}No se puede emitir recomendacion cuantitativa para este sector "
            f"(n={n}); recolectar mas datos de voladura y topografia."
        ).strip()

    if feasibility == FEASIBILITY_CAUTION:
        return (
            f"{prefix}Ajuste requerido {pct_str} ({delta_str}) excede el rango operativo; "
            "revisar patron de carga antes de modificar el explosivo."
        ).strip()

    return (
        f"{prefix}Ajustar PF de {current_pf:.2f} a {target_pf:.2f} kg/m3 ({delta_str}, "
        f"{pct_str}) proyecta acotar sobre-excavacion de {predicted_damage:.2f} m al "
        f"objetivo de {target_damage:.2f} m."
    ).strip()


def validate_recommendation(
    rec: Dict[str, Any],
    constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate a recommendation against operational constraints.

    Parameters
    ----------
    rec : dict
        Output of :func:`recommend_pf_adjustment` or a row from
        :func:`recommend_by_sector`.
    constraints : dict, optional
        Operational limits. Defaults to those declared in
        :class:`core.config.BlastAdvisorDefaults`
        (``max_recommendation_pct``). Supported keys:
        - max_recommendation_pct : float (default from ADVISOR)
        - min_pf_kgm3 : float (default 0.10)
        - max_pf_kgm3 : float (default ``ADVISOR.pf_max_operational_kgm3``)

    Returns
    -------
    dict
        - ``valid`` : bool (no critical violations)
        - ``warnings`` : list[str] (human-readable, Spanish-neutral)
        - ``adjusted_feasibility`` : str (may equal rec['feasibility']
          or be degraded to 'CAUTION' on critical violation)
        - ``message`` : str (Spanish-neutral summary)
    """
    if not isinstance(rec, dict):
        return {
            "valid": False,
            "warnings": ["Recomendacion invalida: se esperaba un diccionario."],
            "adjusted_feasibility": FEASIBILITY_INSUFFICIENT,
            "message": "Recomendacion invalida.",
        }

    if constraints is None:
        constraints = {}

    max_pct = float(constraints.get("max_recommendation_pct", ADVISOR.max_recommendation_pct))
    min_pf = float(constraints.get("min_pf_kgm3", 0.10))
    max_pf = float(constraints.get("max_pf_kgm3", ADVISOR.pf_max_operational_kgm3))

    warnings: List[str] = []
    feasibility = str(rec.get("feasibility", FEASIBILITY_INSUFFICIENT))
    delta_pf_pct = float(rec.get("delta_pf_pct", 0.0))
    target_pf = float(rec.get("target_pf", 0.0))

    if abs(delta_pf_pct) > max_pct:
        warnings.append(
            f"Cambio propuesto {delta_pf_pct:+.1f}% excede el maximo operativo permitido ({max_pct:.0f}%)."
        )
        if feasibility == FEASIBILITY_APPLICABLE:
            feasibility = FEASIBILITY_CAUTION

    if np.isfinite(target_pf) and target_pf > 0:
        if target_pf < min_pf:
            warnings.append(
                f"PF objetivo {target_pf:.3f} kg/m3 esta por debajo del minimo operativo ({min_pf:.2f})."
            )
            feasibility = FEASIBILITY_CAUTION
        elif target_pf > max_pf:
            warnings.append(
                f"PF objetivo {target_pf:.3f} kg/m3 excede el maximo operativo ({max_pf:.2f}); explosivo o burden insuficientes."
            )
            feasibility = FEASIBILITY_CAUTION

    if warnings:
        message = " | ".join(warnings)
    else:
        message = "Recomendacion dentro de los limites operativos."

    return {
        "valid": len(warnings) == 0,
        "warnings": warnings,
        "adjusted_feasibility": feasibility,
        "message": message,
    }


# -----------------------------------------------------------------------------
# Causal explanation engine for bench non-compliance
# -----------------------------------------------------------------------------


EXPLAIN_SEVERITY_CRITICAL = "CRITICAL"
EXPLAIN_SEVERITY_HIGH = "HIGH"
EXPLAIN_SEVERITY_MEDIUM = "MEDIUM"

# Bench-score thresholds. bench_score is 0-100 where >=70 means CUMPLE.
_BENCH_SCORE_HIGH_MAX = 60.0
_BENCH_SCORE_CRIT_MAX = 40.0

# Blast-cause thresholds (industry-typical).
_PF_HIGH = 0.9
_PF_LOW = 0.5
_STEMMING_LOW = 0.7
_SUBDRILL_HIGH = 2.0
_BURDEN_HIGH = 4.0


def explain_non_compliance(
    comp_row: dict,
    blast_context: Optional[dict] = None,
    tolerances: Optional[dict] = None,
) -> dict:
    """Explica por que un banco NO CUMPLE, combinando datos geometricos y de tronadura.

    Parameters
    ----------
    comp_row : dict
        Fila de comparacion geometrica para un banco. Se esperan campos como
        ``section``, ``bench_num``, ``height_status``, ``angle_status``,
        ``berm_status``, ``height_real``, ``height_design``, ``height_dev``,
        ``angle_real``, ``angle_design``, ``angle_dev``, ``berm_real``,
        ``berm_min`` y ``bench_score`` (0-100).
    blast_context : dict, optional
        Contexto de tronadura para el banco (p.ej. el resultado de
        ``attribute_failure_to_holes``). Se esperan campos ``pf_avg``,
        ``stemming_ratio_avg``, ``subdrill_avg``, ``burden_avg`` y
        ``n_holes``. Si es ``None`` el analisis es solo geometrico.
    tolerances : dict, optional
        Tolerancias operativas. Reservado para uso futuro (limites
        geometricos personalizados); no se usa todavia en la salida.

    Returns
    -------
    dict
        Reporte estructurado con claves ``section``, ``bench``, ``bench_score``,
        ``geometry_issues``, ``blast_causes``, ``recommendations`` y
        ``severity`` (``CRITICAL`` | ``HIGH`` | ``MEDIUM``).
    """
    geometry_issues: List[str] = []
    blast_causes: List[str] = []
    recommendations: List[str] = []

    # 1) Geometric deviations --------------------------------------------------
    _emit_geometry_issues(comp_row, geometry_issues)

    # 2) Blast-related causes (optional) --------------------------------------
    if blast_context is not None:
        _emit_blast_causes(blast_context, blast_causes, recommendations)
    else:
        blast_causes.append(
            "Sin contexto de tronadura disponible para este banco; "
            "analisis limitado a geometria."
        )

    # 3) Geometry-only recommendations ----------------------------------------
    _emit_geometry_recommendations(geometry_issues, recommendations)

    # 4) Severity classification ----------------------------------------------
    bench_score = _extract_bench_score(comp_row)
    n_holes = _extract_n_holes(blast_context)
    severity = _classify_severity(bench_score, n_holes)

    return {
        "section": comp_row.get("section"),
        "bench": comp_row.get("bench_num", comp_row.get("bench")),
        "bench_score": bench_score,
        "geometry_issues": geometry_issues,
        "blast_causes": blast_causes,
        "recommendations": recommendations,
        "severity": severity,
    }


def _emit_geometry_issues(comp_row: dict, geometry_issues: List[str]) -> None:
    """Append geometric-deviation messages for any NO-CUMPLE status."""
    if comp_row.get("height_status") == STATUS_NO_CUMPLE:
        h_real = _safe_float(comp_row.get("height_real"))
        h_design = _safe_float(comp_row.get("height_design"))
        h_dev = _safe_float(comp_row.get("height_dev"))
        if h_dev is None and h_real is not None and h_design is not None:
            h_dev = h_real - h_design
        geometry_issues.append(
            "Altura real {h_r}m vs diseno {h_d}m (Δ {h_dev:+.1f}m)".format(
                h_r=_nf(h_real),
                h_d=_nf(h_design),
                h_dev=h_dev if h_dev is not None else 0.0,
            )
        )

    if comp_row.get("angle_status") == STATUS_NO_CUMPLE:
        a_real = _safe_float(comp_row.get("angle_real"))
        a_design = _safe_float(comp_row.get("angle_design"))
        a_dev = _safe_float(comp_row.get("angle_dev"))
        if a_dev is None and a_real is not None and a_design is not None:
            a_dev = a_real - a_design
        geometry_issues.append(
            "Angulo real {a_r}° vs diseno {a_d}° (Δ {a_dev:+.1f}°)".format(
                a_r=_nf(a_real),
                a_d=_nf(a_design),
                a_dev=a_dev if a_dev is not None else 0.0,
            )
        )

    if comp_row.get("berm_status") == STATUS_NO_CUMPLE:
        b_real = _safe_float(comp_row.get("berm_real"))
        b_min = _safe_float(comp_row.get("berm_min"))
        geometry_issues.append(
            "Berma real {b_r}m vs minimo {b_min}m".format(
                b_r=_nf(b_real),
                b_min=_nf(b_min),
            )
        )


def _emit_blast_causes(
    blast_context: dict,
    blast_causes: List[str],
    recommendations: List[str],
) -> None:
    """Append blast-related cause messages and matching recommendations."""
    pf = _safe_float(blast_context.get("pf_avg"))
    stemming = _safe_float(blast_context.get("stemming_ratio_avg"))
    subdrill = _safe_float(blast_context.get("subdrill_avg"))
    burden = _safe_float(blast_context.get("burden_avg"))
    n_holes = _safe_float(blast_context.get("n_holes"))

    if n_holes == 0 or (
        blast_context.get("n_holes") is not None
        and blast_context.get("n_holes") == 0
    ):
        blast_causes.append("Sin pozos de tronadura detectados en este banco")
        return

    if pf is not None and np.isfinite(pf) and pf > _PF_HIGH:
        blast_causes.append(
            f"PF elevado ({pf} kg/m3) puede causar sobre-excavacion"
        )
        recommendations.append(
            "Reducir PF a 0.7-0.8 kg/m3 disminuyendo carga de columna"
        )

    if pf is not None and np.isfinite(pf) and pf < _PF_LOW:
        blast_causes.append(
            f"PF insuficiente ({pf} kg/m3) puede causar fragmentacion pobre"
        )
        recommendations.append(
            "Aumentar PF a 0.6-0.8 kg/m3 ajustando burden o carga de fondo"
        )

    if stemming is not None and np.isfinite(stemming) and stemming < _STEMMING_LOW:
        blast_causes.append(
            f"Stemming insuficiente ({stemming:.0%}) puede causar "
            "voladura de taco (fly-rock, berma danada)"
        )
        recommendations.append(
            "Aumentar taco a >=70% de la altura del banco"
        )

    if subdrill is not None and np.isfinite(subdrill) and subdrill > _SUBDRILL_HIGH:
        blast_causes.append(
            f"Pasadura excesiva ({subdrill}m) puede causar sobre-rotura del piso"
        )
        recommendations.append("Controlar pasadura a <=1.5m")

    if burden is not None and np.isfinite(burden) and burden > _BURDEN_HIGH:
        blast_causes.append(
            f"Burden elevado ({burden}m) puede causar poor breakage y toes duros"
        )
        recommendations.append("Reducir burden o ajustar spacing para mejorar fragmentacion")


def _emit_geometry_recommendations(
    geometry_issues: List[str], recommendations: List[str]
) -> None:
    """Produce geometry-driven recommendations when no blast causes exist."""
    if not geometry_issues:
        return
    if not recommendations:
        recommendations.append(
            "Revisar diseno geometrico del banco contra el perfil replanteado"
        )
    recommendations.append(
        "Verificar replanteo topografico y marcacion de limites de banco"
    )


def _classify_severity(bench_score: Optional[float], n_holes: Optional[float]) -> str:
    """Map bench score and blast availability to a severity tier.

    - CRITICAL: bench_score < 40 OR n_holes == 0 (no blast data)
    - HIGH: bench_score in [40, 60)
    - MEDIUM: bench_score in [60, 70)  (still failing the >=70 CUMPLE threshold)
    """
    if bench_score is None or not np.isfinite(bench_score):
        # If we cannot score the bench but there is no blast data, escalate.
        if n_holes is None or n_holes == 0:
            return EXPLAIN_SEVERITY_CRITICAL
        return EXPLAIN_SEVERITY_HIGH

    if bench_score < _BENCH_SCORE_CRIT_MAX or (n_holes is not None and n_holes == 0):
        return EXPLAIN_SEVERITY_CRITICAL
    if bench_score < _BENCH_SCORE_HIGH_MAX:
        return EXPLAIN_SEVERITY_HIGH
    return EXPLAIN_SEVERITY_MEDIUM


def _extract_bench_score(comp_row: dict) -> Optional[float]:
    score = comp_row.get("bench_score")
    if score is None:
        return None
    try:
        v = float(score)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return v


def _extract_n_holes(blast_context: Optional[dict]) -> Optional[float]:
    if not blast_context:
        return None
    raw = blast_context.get("n_holes")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _nf(value: Optional[float], default: str = "?") -> str:
    """Format a finite numeric value to 2 decimals; otherwise return ``default``."""
    if value is None:
        return default
    return f"{value:.2f}"


def _safe_float(value: Any) -> Optional[float]:
    """Coerce ``value`` to ``float``; return ``None`` if not finite/coercible."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return v
