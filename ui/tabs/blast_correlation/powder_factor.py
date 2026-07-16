"""Pure powder-factor damage model and recommendation helpers."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.blast_advisor import (
    format_recommendation_text,
    recommend_by_sector,
    recommend_pf_adjustment,
)
from core.blast_model import fit_powder_factor_damage_model, predict_damage_for_pf
from core.config import ADVISOR


def fit_pf_damage_model(df_filtered_sections: pd.DataFrame, use_pf_axis: bool) -> dict:
    """Fit the OLS powder-factor damage model.

    Returns a dict with keys ``model``, ``valid``, ``pf_min``, ``pf_max``,
    ``fig`` and ``error``. When the model cannot be fit, ``model`` is None
    and ``error`` describes why.
    """
    if not use_pf_axis:
        return {
            "model": None,
            "valid": None,
            "pf_min": None,
            "pf_max": None,
            "fig": None,
            "error": "pf_unavailable",
        }

    valid = df_filtered_sections.dropna(
        subset=["pf_vol_avg_kgm3", "avg_over_break"]
    ).copy()
    valid = valid[valid["pf_vol_avg_kgm3"] > 0]
    pf = valid["pf_vol_avg_kgm3"].values.astype(float)
    dmg = valid["avg_over_break"].values.astype(float)

    if len(pf) < 5:
        return {
            "model": None,
            "valid": valid,
            "pf_min": None,
            "pf_max": None,
            "fig": None,
            "error": "insufficient",
        }

    model = fit_powder_factor_damage_model(pf, dmg)
    if not model["is_significant"] and model["confidence"] == "INSUFFICIENT":
        return {
            "model": model,
            "valid": valid,
            "pf_min": None,
            "pf_max": None,
            "fig": None,
            "error": "unreliable",
        }

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=pf,
            y=dmg,
            mode="markers+text",
            text=valid["section"].astype(str).values,
            textposition="top center",
            marker=dict(size=10, color="crimson"),
            name="Secciones",
        )
    )

    xs_line = np.linspace(float(pf.min()), float(pf.max()), 50)
    ys_line = model["beta0"] + model["beta1"] * xs_line
    sse = float(np.sum((pf - model["mean_pf"]) ** 2))
    if sse > 0:
        se_band = 1.96 * model["std_err_beta1"] * np.sqrt(
            1.0 / model["n"] + (xs_line - model["mean_pf"]) ** 2 / sse
        )
        fig.add_trace(
            go.Scatter(
                x=np.concatenate([xs_line, xs_line[::-1]]),
                y=np.concatenate([ys_line + se_band, (ys_line - se_band)[::-1]]),
                fill="toself",
                fillcolor="rgba(220, 20, 60, 0.15)",
                line=dict(color="rgba(255, 255, 255, 0)"),
                hoverinfo="skip",
                showlegend=True,
                name="Banda IC 95%",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=xs_line,
            y=ys_line,
            mode="lines",
            line=dict(color="darkred", width=2),
            name=f'OLS (β₁ = {model["beta1"]:.3f})',
        )
    )

    fig.update_layout(
        title="Regresión OLS: PF (kg/m³) vs Sobre-excavación Media (m)",
        xaxis_title="Powder Factor Volumétrico (kg/m³)",
        yaxis_title="Sobre-excavación Media (m)",
        height=450,
        margin=dict(l=40, r=20, t=50, b=40),
    )

    pf_min = float(min(0.05, pf.min()))
    pf_max = float(max(2.0, pf.max()))

    return {
        "model": model,
        "valid": valid,
        "pf_min": pf_min,
        "pf_max": pf_max,
        "fig": fig,
        "error": None,
    }


def predict_pf_damage(model: dict, target_pf: float) -> dict:
    """Pure wrapper around :func:`core.blast_model.predict_damage_for_pf`."""
    return predict_damage_for_pf(model, target_pf)


def build_pf_recommendations(
    model: dict,
    valid: pd.DataFrame,
    df_filtered_sections: pd.DataFrame,
    target_overbreak_m: float,
) -> dict:
    """Build PF-adjustment recommendations for the UI block.

    Returns a dict with ``rec_global``, ``df_recs`` and ``valid_pf_mean``.
    If the model is not usable, returns ``{"error": ...}``.
    """
    if model is None or model.get("confidence") == "INSUFFICIENT":
        return {
            "error": "insufficient",
            "n": int(model.get("n", 0)) if model else 0,
            "p_value": float(model.get("p_value", float("nan"))) if model else float("nan"),
        }

    if valid is None or valid.empty:
        return {"error": "no_valid_data"}

    valid_pf_mean = float(valid["pf_vol_avg_kgm3"].mean())
    rec_global = recommend_pf_adjustment(
        model,
        current_pf=valid_pf_mean,
        target_overbreak_m=target_overbreak_m,
    )

    df_recs = pd.DataFrame()
    if "sector" in df_filtered_sections.columns:
        df_recs = recommend_by_sector(
            df_filtered_sections,
            model,
            group_col="sector",
            target_overbreak_m=target_overbreak_m,
        )

    return {
        "rec_global": rec_global,
        "df_recs": df_recs,
        "valid_pf_mean": valid_pf_mean,
    }
