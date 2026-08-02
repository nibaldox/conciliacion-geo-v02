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
    """Accepted input conventions for azimuth (auditoría §3.3).

    All inputs are normalized to the canonical convention: degrees
    clockwise from North (N=0, E=90, S=180, W=270).
    """

    CLOCKWISE_FROM_NORTH = "CLOCKWISE_FROM_NORTH"            # canonical
    COUNTERCLOCKWISE_FROM_NORTH = "COUNTERCLOCKWISE_FROM_NORTH"
    CLOCKWISE_FROM_EAST = "CLOCKWISE_FROM_EAST"
    COUNTERCLOCKWISE_FROM_EAST = "COUNTERCLOCKWISE_FROM_EAST"

    # Legacy alias (pre-auditoría) → canonical
    FROM_NORTH_CW = "CLOCKWISE_FROM_NORTH"


class SignConvention(str, Enum):
    """Inclination sign handling policies (auditoría §3.3).

    The sign is processed BEFORE the convention conversion.
    """

    ABSOLUTE_VALUE = "ABSOLUTE_VALUE"
    NEGATIVE_IS_DOWNWARD_DIP = "NEGATIVE_IS_DOWNWARD_DIP"
    SOURCE_DEFINED = "SOURCE_DEFINED"


# Legacy sign strings → canonical policies (migration layer)
_SIGN_ALIASES = {
    "abs": SignConvention.ABSOLUTE_VALUE,
    "negative_dip_descending": SignConvention.NEGATIVE_IS_DOWNWARD_DIP,
    "source_defined": SignConvention.SOURCE_DEFINED,
}

# Accepted explicit rules for SOURCE_DEFINED
_SOURCE_RULES = ("negative_is_downward_dip", "positive_only", "absolute_value")


INCL_VALID_RANGE_DEG = (0.0, 90.0)
AZ_VALID_RANGE_DEG = (0.0, 360.0)


def normalize_inclination(
    values: pd.Series,
    convention: InclinationConvention | str = InclinationConvention.FROM_VERTICAL,
    sign_convention: SignConvention | str = SignConvention.ABSOLUTE_VALUE,
    sign_source_rule: str | None = None,
) -> tuple[pd.Series, dict]:
    """Convert inclination to the canonical from-vertical convention.

    Parameters
    ----------
    values : pd.Series
        Inclination in degrees (or radians — the caller converts units
        before calling; units are the caller's contract, recorded in the
        returned metadata via ``unit`` when provided through the meta).
    convention : InclinationConvention
        ``from_vertical`` (0 = vertical, canonical) or
        ``dip_from_horizontal`` (converts with ``90 - magnitude``).
    sign_convention : SignConvention (auditoría §3.3)
        Applied BEFORE the convention conversion:
        - ABSOLUTE_VALUE: explicit magnitude |v| (recorded).
        - NEGATIVE_IS_DOWNWARD_DIP: negative values carry downward-dip
          semantics; only compatible with DIP_FROM_HORIZONTAL (raises
          otherwise); magnitude |v| converted, sign recorded.
        - SOURCE_DEFINED: requires an explicit ``sign_source_rule``;
          without one the geometry is BLOCKED (raises). Accepted rules:
          ``negative_is_downward_dip``, ``positive_only`` (negatives are
          rejected with a diagnostic), ``absolute_value``.
    sign_source_rule : str | None
        Explicit transformation rule for SOURCE_DEFINED.

    Returns
    -------
    (normalized, metadata) with convention, sign_convention, sign_applied,
    conversion, per-value orientation_sign, counts of wrapped/rejected
    values. Invalid sign/rule combinations raise ValueError instead of
    silently falling back.
    """
    out = pd.to_numeric(values, errors="coerce").astype(float)
    conv = InclinationConvention(convention)
    sign_conv = _resolve_sign_convention(sign_convention)
    meta: dict = {
        "convention": conv.value,
        "sign_convention": sign_conv.value,
        "conversion": "none",
        "sign_applied": "none",
    }

    if sign_conv is SignConvention.NEGATIVE_IS_DOWNWARD_DIP and             conv is InclinationConvention.FROM_VERTICAL:
        raise ValueError(
            "NEGATIVE_IS_DOWNWARD_DIP es incompatible con FROM_VERTICAL: la "
            "semántica de 'dip descendente' solo aplica a DIP_FROM_HORIZONTAL."
        )

    rejected_negative = 0
    if sign_conv is SignConvention.SOURCE_DEFINED:
        if not sign_source_rule:
            raise ValueError(
                "SOURCE_DEFINED requiere una transformación explícita "
                "(sign_source_rule = 'negative_is_downward_dip' | 'positive_only' "
                "| 'absolute_value'); sin regla la geometría se bloquea."
            )
        if sign_source_rule not in _SOURCE_RULES:
            raise ValueError(
                f"sign_source_rule inválido: {sign_source_rule!r}. Use "
                f"{_SOURCE_RULES}."
            )
        if sign_source_rule == "positive_only":
            neg = (out < 0) & out.notna()
            rejected_negative = int(neg.sum())
            out = out.where(~neg)
            meta["sign_applied"] = "positive_only"
            if rejected_negative:
                meta["rejected_negative"] = rejected_negative
        elif sign_source_rule == "negative_is_downward_dip":
            meta["sign_applied"] = "negative_dip_downward"
        else:
            meta["sign_applied"] = "abs"
    elif sign_conv is SignConvention.NEGATIVE_IS_DOWNWARD_DIP:
        meta["sign_applied"] = "negative_dip_downward"
    else:
        meta["sign_applied"] = "abs"

    # 1) Magnitude/orientation separation BEFORE conversion (H-04/§3.3).
    orientation = np.sign(out.values)
    magnitude = out.abs()

    # 2) Convert the sign-agnostic magnitude to the canonical convention.
    if conv is InclinationConvention.DIP_FROM_HORIZONTAL:
        magnitude = 90.0 - magnitude
        meta["conversion"] = "dip->90-dip"

    negative = (out < 0) & out.notna()
    n_neg = int(negative.sum())
    if n_neg and meta["sign_applied"] == "abs":
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


def _resolve_sign_convention(sign_convention: SignConvention | str) -> SignConvention:
    """Map legacy sign strings to canonical policies (migration)."""
    if isinstance(sign_convention, SignConvention):
        return sign_convention
    key = str(sign_convention)
    if key in _SIGN_ALIASES:
        return _SIGN_ALIASES[key]
    return SignConvention(key)


def normalize_azimuth(
    values: pd.Series,
    convention: AzimuthConvention | str = AzimuthConvention.CLOCKWISE_FROM_NORTH,
) -> tuple[pd.Series, dict]:
    """Convert azimuth to the canonical clockwise-from-North convention.

    Supported input conventions (auditoría §3.3), all normalized to
    [0°, 360°) clockwise from North:
    - CLOCKWISE_FROM_NORTH (canonical): identity.
    - COUNTERCLOCKWISE_FROM_NORTH:  az = (360 - v) % 360
    - CLOCKWISE_FROM_EAST:           az = (90 + v) % 360
    - COUNTERCLOCKWISE_FROM_EAST:    az = (90 - v) % 360

    Returns ``(normalized, metadata)`` with the input convention and the
    conversion applied.
    """
    out = pd.to_numeric(values, errors="coerce").astype(float)
    conv = AzimuthConvention(convention)
    meta: dict = {"convention": conv.value, "conversion": "mod-360"}
    if conv is AzimuthConvention.COUNTERCLOCKWISE_FROM_NORTH:
        out = (360.0 - out).mod(360.0)
        meta["conversion"] = "ccw_from_north->cw_from_north"
    elif conv is AzimuthConvention.CLOCKWISE_FROM_EAST:
        out = (90.0 + out).mod(360.0)
        meta["conversion"] = "cw_from_east->cw_from_north"
    elif conv is AzimuthConvention.COUNTERCLOCKWISE_FROM_EAST:
        out = (90.0 - out).mod(360.0)
        meta["conversion"] = "ccw_from_east->cw_from_north"
    else:
        out = out.mod(360.0)
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
