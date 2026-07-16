"""Pure multivariate damage model helpers."""

import pandas as pd

from core.blast_advisor import recommend_multivariate
from core.blast_model import fit_multivariate_damage_model


def build_multivariate_model(df_filtered_sections: pd.DataFrame) -> dict:
    """Fit and summarize the multivariate damage model.

    Returns a dict with ``model``, ``coef_rows`` (DataFrame), ``rec`` and
    ``error``. When the model is insufficient, ``rec`` is None and
    ``error`` describes why.
    """
    model = fit_multivariate_damage_model(df_filtered_sections)
    features = model.get("features_used", [])

    if model.get("confidence") == "INSUFFICIENT" or len(features) < 2:
        return {
            "model": model,
            "coef_rows": pd.DataFrame(),
            "rec": None,
            "error": "insufficient",
        }

    coef_rows = pd.DataFrame(
        [
            {
                "Predictor": feat,
                "Coeficiente": round(float(model["coefficients"].get(feat, 0.0)), 4),
                "Error estándar": round(float(model["std_errors"].get(feat, 0.0)), 4),
                "p-valor": round(float(model["p_values"].get(feat, float("nan"))), 4),
            }
            for feat in features
        ]
    )

    current_burden = float(model.get("feature_means", {}).get("burden", 0.0))
    if current_burden <= 0.0:
        return {
            "model": model,
            "coef_rows": coef_rows,
            "rec": None,
            "error": "no_burden",
        }

    rec = recommend_multivariate(model, current_burden=current_burden)
    return {
        "model": model,
        "coef_rows": coef_rows,
        "rec": rec,
        "error": None,
    }
