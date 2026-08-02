"""Versioned geometric configuration contract — single source of truth.

Remediación final 3.1 / 4.1: backend, API and UI MUST serialize exactly the
same geometric configuration. This module is the canonical contract; every
layer consumes it and never invents defaults.

The contract is enforced at boundary entry: when ``geometry_user_confirmed``
is not exactly ``True`` (i.e. ``False``, ``None`` or absent), or when the
required inclination/azimuth/unit fields are missing, the configuration is
incomplete and the dependent geometry (toe, influence area, PF) is BLOCKED.
Legacy / unconfirmed events are surfaced as the explicit state
``LEGACY_UNCONFIRMED`` so the operator can see WHY the geometry is blocked
instead of getting silent defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

GEOMETRY_CONFIGURATION_VERSION = "2.0"

_VALID_INCL_CONVENTIONS = ("FROM_VERTICAL", "DIP_FROM_HORIZONTAL")
_VALID_INCL_SIGN = (
    "ABSOLUTE_VALUE",
    "NEGATIVE_IS_DOWNWARD_DIP",
    "SOURCE_DEFINED",
)
_VALID_INCL_UNIT = ("DEGREES", "RADIANS")
_VALID_AZ_CONVENTIONS = (
    "CLOCKWISE_FROM_NORTH",
    "COUNTERCLOCKWISE_FROM_NORTH",
    "CLOCKWISE_FROM_EAST",
    "COUNTERCLOCKWISE_FROM_EAST",
)
_VALID_AZ_UNIT = ("DEGREES", "RADIANS")


class GeometryConfigurationError(ValueError):
    """Raised when the geometric configuration is incomplete or invalid.

    Carries a structured ``details`` dict so callers (API/UI) can surface
    the exact missing/invalid field instead of an opaque message.
    """

    def __init__(self, message: str, *, error_code: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


@dataclass(frozen=True)
class GeometryConfiguration:
    """Immutable, versioned geometric configuration (spec §4.1).

    All defaults are ``None`` / empty strings: the absence of a value is
    surfaced explicitly. No silent defaults are applied anywhere in the
    pipeline.
    """

    geometry_configuration_version: str = GEOMETRY_CONFIGURATION_VERSION
    geometry_user_confirmed: bool | None = None

    inclination_source_column: str = ""
    inclination_convention: str | None = None
    inclination_sign_convention: str | None = None
    inclination_unit: str | None = None
    inclination_source_rule: str = ""

    azimuth_source_column: str = ""
    azimuth_convention: str | None = None
    azimuth_unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_legacy_unconfirmed(self) -> bool:
        """A legacy event carries no confirmation and no convention column."""
        return (
            self.geometry_user_confirmed is None
            and not self.inclination_convention
            and not self.azimuth_convention
        )

    def validate(self) -> "GeometryConfiguration":
        """Validate the configuration; raise on any incompleteness.

        Rules (auditoría §3.1, §4.1):
          * Only ``geometry_user_confirmed is True`` enables geometry.
          * ``False``, ``None`` and absent confirmation BLOCK the geometry.
          * Legacy / unconfirmed events are surfaced as
            ``LEGACY_UNCONFIRMED`` (still blocked — never silently
            computed).
          * Inclination convention / sign / unit and azimuth convention /
            unit are MANDATORY when the geometry is enabled.
          * ``SOURCE_DEFINED`` requires a non-empty ``inclination_source_rule``.
          * No angular defaults are invented — the caller MUST declare units.
        """
        details: dict[str, Any] = {}

        if self.geometry_user_confirmed is None:
            raise GeometryConfigurationError(
                "Configuración geométrica no confirmada (geometry_user_confirmed=None): "
                "el cálculo de toe y geometría dependiente está bloqueado.",
                error_code="GEOMETRY_NOT_CONFIRMED",
                details={"state": "LEGACY_UNCONFIRMED"},
            )
        if self.geometry_user_confirmed is False:
            raise GeometryConfigurationError(
                "Configuración geométrica rechazada (geometry_user_confirmed=False): "
                "el cálculo de toe y geometría dependiente está bloqueado.",
                error_code="GEOMETRY_REJECTED",
                details={"state": "REJECTED"},
            )

        if self.inclination_convention not in _VALID_INCL_CONVENTIONS:
            details["inclination_convention"] = self.inclination_convention
        if self.inclination_sign_convention not in _VALID_INCL_SIGN:
            details["inclination_sign_convention"] = self.inclination_sign_convention
        if self.inclination_unit not in _VALID_INCL_UNIT:
            details["inclination_unit"] = self.inclination_unit
        if self.azimuth_convention not in _VALID_AZ_CONVENTIONS:
            details["azimuth_convention"] = self.azimuth_convention
        if self.azimuth_unit not in _VALID_AZ_UNIT:
            details["azimuth_unit"] = self.azimuth_unit

        if (
            self.inclination_sign_convention == "SOURCE_DEFINED"
            and not self.inclination_source_rule
        ):
            details["inclination_source_rule"] = (
                "required when inclination_sign_convention=SOURCE_DEFINED"
            )

        if details:
            raise GeometryConfigurationError(
                "Configuración geométrica incompleta: faltan campos obligatorios "
                "o tienen valores inválidos. La geometría está bloqueada.",
                error_code="GEOMETRY_INCOMPLETE",
                details={"missing_or_invalid": details},
            )

        return self

    def angle_unit_canonical(self) -> str:
        """Return the canonical lowercase angle unit for downstream math.

        Only callable after ``validate()`` has passed (both inclination and
        azimuth units are mandatory and must be equal in this version).
        """
        if self.inclination_unit == "DEGREES":
            return "degrees"
        return "radians"
