"""Pure classification functions for drilling analytics.

Parity-critical surface ported from dureza_relativa/classification.py.
Must not import pandas, numpy, streamlit, plotly, or logging.
"""

from __future__ import annotations

import math
from typing import Literal, TypedDict


class MetricThresholds(TypedDict):
    soft: float
    medium: float
    hard: float


class Thresholds(TypedDict):
    duration: MetricThresholds
    rate: MetricThresholds


Metric = Literal["duration", "penetration_rate", "rig_normalized_penetration"]


DEFAULT_DURATION_THRESHOLDS: MetricThresholds = {
    "soft": 16.0,
    "medium": 24.0,
    "hard": 40.0,
}
DEFAULT_RATE_THRESHOLDS: MetricThresholds = {
    "soft": 1.0,
    "medium": 0.7,
    "hard": 0.4,
}
DEFAULT_THRESHOLDS: Thresholds = {
    "duration": DEFAULT_DURATION_THRESHOLDS,
    "rate": DEFAULT_RATE_THRESHOLDS,
}

DURATION_INDEX_UPPER_SATURATION: float = 60.0
RATE_INDEX_UPPER_SATURATION: float = 2.0
STD_EPSILON: float = 1e-9


def classify_duracion(minutos):
    if minutos < 16:
        return "roca suave"
    elif minutos < 24:
        return "roca media"
    elif minutos < 40:
        return "roca dura"
    return "roca muy dura"


def hardness_index(T):
    if T < 0:
        return 0.0
    elif T <= 16:
        return 25.0 * (T / 16.0)
    elif T <= 24:
        return 25.0 + 25.0 * ((T - 16.0) / 8.0)
    elif T <= 40:
        return 50.0 + 25.0 * ((T - 24.0) / 16.0)
    elif T <= 60:
        return 75.0 + 25.0 * ((T - 40.0) / 20.0)
    return 100.0


def penetration_rate(depth_m, duration_min):
    if depth_m is None or duration_min is None:
        return None
    if not math.isfinite(depth_m) or not math.isfinite(duration_min):
        return None
    if duration_min <= 0:
        return None
    return depth_m / duration_min


def classify_with_metric(value, thresholds, metric):
    if value is None:
        return None
    if metric == "duration":
        soft = thresholds["duration"]["soft"]
        medium = thresholds["duration"]["medium"]
        hard = thresholds["duration"]["hard"]
        if value < soft:
            return "roca suave"
        if value < medium:
            return "roca media"
        if value < hard:
            return "roca dura"
        return "roca muy dura"
    if metric in ("penetration_rate", "rig_normalized_penetration"):
        soft = thresholds["rate"]["soft"]
        medium = thresholds["rate"]["medium"]
        hard = thresholds["rate"]["hard"]
        if value > soft:
            return "roca suave"
        if value > medium:
            return "roca media"
        if value > hard:
            return "roca dura"
        return "roca muy dura"
    raise ValueError(
        f"Unknown metric {metric!r}; expected one of "
        "'duration', 'penetration_rate', 'rig_normalized_penetration'."
    )


def hardness_index_with_metric(value, thresholds, metric):
    if value is None:
        return None
    if metric == "duration":
        soft = thresholds["duration"]["soft"]
        medium = thresholds["duration"]["medium"]
        hard = thresholds["duration"]["hard"]
        if value <= 0:
            return 0.0
        if value <= soft:
            return 25.0 * (value / soft)
        if value <= medium:
            return 25.0 + 25.0 * ((value - soft) / (medium - soft))
        if value <= hard:
            return 50.0 + 25.0 * ((value - medium) / (hard - medium))
        if value <= DURATION_INDEX_UPPER_SATURATION:
            return 75.0 + 25.0 * (
                (value - hard)
                / (DURATION_INDEX_UPPER_SATURATION - hard)
            )
        return 100.0
    if metric in ("penetration_rate", "rig_normalized_penetration"):
        soft = thresholds["rate"]["soft"]
        medium = thresholds["rate"]["medium"]
        hard = thresholds["rate"]["hard"]
        upper = RATE_INDEX_UPPER_SATURATION
        if value > upper:
            return 0.0
        if value > soft:
            return 25.0 * (upper - value) / (upper - soft)
        if value > medium:
            return 25.0 + 25.0 * (soft - value) / (soft - medium)
        if value > hard:
            return 50.0 + 25.0 * (medium - value) / (medium - hard)
        return 75.0 + 25.0 * (hard - value) / hard
    raise ValueError(
        f"Unknown metric {metric!r}; expected one of "
        "'duration', 'penetration_rate', 'rig_normalized_penetration'."
    )


def rig_mean_penetration(rates):
    if not rates:
        return None
    total = 0.0
    count = 0
    for rate in rates:
        if rate is None:
            continue
        if not math.isfinite(rate):
            continue
        total += rate
        count += 1
    if count == 0:
        return None
    return total / count


def rig_normalized_penetration(rate, rig_avg, rig_std):
    if rate is None:
        return 0.0
    if not math.isfinite(rate):
        return 0.0
    if rig_std is None or rig_std <= STD_EPSILON:
        return 0.0
    if not math.isfinite(rig_avg) or not math.isfinite(rig_std):
        return 0.0
    return (rate - rig_avg) / rig_std
