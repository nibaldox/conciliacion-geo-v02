"""Canonical geometric conventions for drill & blast holes (spec §4.1).

Every angle entering the pipeline is normalized to a single canonical
convention before any trigonometry:

- Inclination: deviation from vertical, positive degrees, 0 = vertical
  (90 = horizontal). Dip-from-horizontal inputs are converted with
  ``incl = 90 - dip``.
- Azimuth: degrees clockwise from North (N=0, E=90, S=180, W=270).

The normalization functions are pure: they return the normalized values
plus a metadata dict describing the conversion applied (so callers can
persist provenance instead of losing the original meaning).
"""
from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd


class InclinationConvention(str, Enum):
    """Accepted input conventions for inclination."""

    FROM_VERTICAL = "from_vertical"            # canonical: 0 = vertical
    DIP_FROM_HORIZONTAL = "dip_from_horizontal"  # 0 = horizontal, 90 = vertical


class AzimuthConvention(str, Enum):
    """Accepted input conventions for azimuth."""

    FROM_NORTH_CW = "from_north_cw"  # canonical: N=0, E=90


INCL_VALID_RANGE_DEG = (0.0, 90.0)
AZ_VALID_RANGE_DEG = (0.0, 360.0)


def normalize_inclination(
    values: pd.Series,
    convention: InclinationConvention | str = InclinationConvention.FROM_VERTICAL,
) -> tuple[pd.Series, dict]:
    """Convert inclination to the canonical from-vertical convention.

    Parameters
    ----------
    values : pd.Series
        Inclination in degrees.
    convention : InclinationConvention
        The convention the input values use. ``dip_from_horizontal``
        converts with ``90 - magnitude``.

    Magnitude/orientation separation (audit H-04): the sign of the input
    is treated as an orientation hint, NOT part of the magnitude. The
    magnitude is absolutized BEFORE any convention conversion, so a
    -65° dip converts to 25° from vertical (never 155°); the orientation
    sign is preserved in ``meta["orientation_sign"]`` (array of -1/0/+1)
    for callers to persist.

    Returns
    -------
    (normalized, metadata) where metadata records the input convention,
    the conversion applied, the per-value orientation sign (0 for NaN),
    the number of negative values absolutized and the number of values
    rejected as out of range [0, 90]° (returned as NaN).
    """
    out = pd.to_numeric(values, errors="coerce").astype(float)
    conv = InclinationConvention(convention)
    meta: dict = {"convention": conv.value, "conversion": "none"}

    # 1) Separate orientation sign from magnitude BEFORE conversion (H-04).
    orientation = np.sign(out.values)
    magnitude = out.abs()

    # 2) Convert the (sign-agnostic) magnitude to the canonical convention.
    if conv is InclinationConvention.DIP_FROM_HORIZONTAL:
        magnitude = 90.0 - magnitude
        meta["conversion"] = "dip->90-dip"

    negative = (out < 0) & out.notna()
    n_neg = int(negative.sum())
    if n_neg:
        meta["negative_wrapped"] = n_neg
        meta["conversion"] = (
            meta["conversion"] + "+abs" if meta["conversion"] != "none" else "abs"
        )
    meta["orientation_sign"] = orientation.tolist()
    meta["orientation_field"] = "incl_orientation"

    out_of_range = (magnitude > INCL_VALID_RANGE_DEG[1]) & magnitude.notna()
    n_rejected = int(out_of_range.sum())
    if n_rejected:
        magnitude = magnitude.where(~out_of_range)
        meta["rejected_out_of_range"] = n_rejected

    return magnitude, meta


def normalize_azimuth(
    values: pd.Series,
    convention: AzimuthConvention | str = AzimuthConvention.FROM_NORTH_CW,
) -> tuple[pd.Series, dict]:
    """Convert azimuth to the canonical from-north-clockwise convention.

    Values are wrapped into [0, 360) degrees. Returns ``(normalized,
    metadata)`` with the input convention recorded.
    """
    out = pd.to_numeric(values, errors="coerce").astype(float)
    conv = AzimuthConvention(convention)
    out = out.mod(360.0)
    meta: dict = {"convention": conv.value, "conversion": "mod-360"}
    return out, meta


def normalize_vector_components(
    incl_from_vertical: pd.Series,
    az_from_north: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Unit vector along the hole axis, from collar to toe (downwards).

    The input Series must already be in canonical convention (outputs of
    :func:`normalize_inclination` / :func:`normalize_azimuth`). A hole
    with incl=0 (vertical) points Down (-Z); az=0 (North) with incl=90
    points +Y (North).

    Returns
    -------
    (vx, vy, vz) — components along East, North and Down, each a Series
    with NaN where either input is NaN.
    """
    incl = pd.to_numeric(incl_from_vertical, errors="coerce").astype(float)
    az = pd.to_numeric(az_from_north, errors="coerce").astype(float)
    incl_r = np.radians(incl)
    az_r = np.radians(az)
    sin_i = np.sin(incl_r)
    vx = sin_i * np.sin(az_r)
    vy = sin_i * np.cos(az_r)
    vz = -np.cos(incl_r)
    return vx, vy, vz
