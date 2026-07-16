"""Pure back-break predictor helpers."""

from core.backbreak_prediction import predict_backbreak
from core.config import BACKBREAK


def compute_backbreak_prediction(
    burden: float,
    spacing: float,
    pf: float,
    stemming: float,
    diameter: float,
    rock_factor: float,
    multivariate_model: dict | None,
) -> object:
    """Predict back-break using the multivariate model when available.

    Falls back to the empirical Holmberg-Persson-aware heuristic when the
    multivariate model is not usable.
    """
    model_for_pred = (
        multivariate_model
        if isinstance(multivariate_model, dict)
        and multivariate_model.get("confidence") not in (None, "", "INSUFFICIENT")
        else None
    )
    return predict_backbreak(
        burden,
        spacing,
        pf,
        stemming,
        diameter,
        model=model_for_pred,
        rock_factor=rock_factor,
    )


def get_backbreak_defaults():
    """Return the configured back-break default parameters."""
    return BACKBREAK
