"""Versioned geometric configuration contract — single source of truth.

Remediación integración 3.3/3.4/3.5: backend, API and UI MUST serialize
exactly the same geometric configuration. This module is the canonical
contract; every layer consumes it and never invents defaults.

The contract is enforced at boundary entry: when ``geometry_user_confirmed``
is not exactly ``True`` (i.e. ``False``, ``None`` or absent), or when the
required inclination/azimuth/unit/source-column fields are missing, the
configuration is incomplete and the dependent geometry (toe, influence
area, PF) is BLOCKED. Legacy / unconfirmed events are surfaced as the
explicit state ``LEGACY_UNCONFIRMED`` so the operator can see WHY the
geometry is blocked instead of getting silent defaults.

Single source of truth for the contract version:
    GEOMETRY_CONFIGURATION_VERSION
Every accepted/rejected row, persistence record, API response, export
sheet and UI label references THIS constant — never a divergent literal.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
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


def _unit_to_canonical(unit: str | None) -> str:
    """Map a canonical unit to the lowercase keyword the math expects."""
    if unit == "DEGREES":
        return "degrees"
    if unit == "RADIANS":
        return "radians"
    raise GeometryConfigurationError(
        f"Unidad angular inválida: {unit!r} (use 'DEGREES' o 'RADIANS')",
        error_code="GEOMETRY_INCOMPLETE",
        details={"invalid_unit": unit},
    )


@dataclass(frozen=True)
class GeometryConfiguration:
    """Immutable, versioned geometric configuration (spec §4.1).

    All defaults are ``None`` / empty strings: the absence of a value is
    surfaced explicitly. No silent defaults are applied anywhere in the
    pipeline.

    Source columns (``inclination_source_column`` / ``azimuth_source_column``)
    are MANDATORY in any confirmed configuration: the operator MUST
    declare which dataset column holds each angle, and the processor MUST
    use exactly that column (no autodetection after confirmation).

    Inclination and azimuth units are INDEPENDENT: ``inclination_unit``
    applies only to the inclination column, ``azimuth_unit`` only to the
    azimuth column. The legacy ``angle_unit`` keyword is accepted ONLY as
    an explicit legacy migration and never overrides v2 units.
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

        Rules (auditoría §3.1, §4.1, integración §3.3/3.4/3.5):
          * Only ``geometry_user_confirmed is True`` enables geometry.
          * ``False``, ``None`` and absent confirmation BLOCK the geometry.
          * Legacy / unconfirmed events are surfaced as
            ``LEGACY_UNCONFIRMED`` (still blocked — never silently
            computed).
          * Inclination convention / sign / unit and azimuth convention /
            unit are MANDATORY when the geometry is enabled.
          * ``SOURCE_DEFINED`` requires a non-empty ``inclination_source_rule``.
          * Source columns (``inclination_source_column`` /
            ``azimuth_source_column``) are MANDATORY and non-empty: the
            operator MUST declare which dataset column holds each angle.
          * No angular defaults are invented — inclination and azimuth
            units are INDEPENDENT.
          * ``geometry_configuration_version`` MUST equal
            :data:`GEOMETRY_CONFIGURATION_VERSION`.
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

        # Version check — guards against stale literals drifting back.
        if self.geometry_configuration_version != GEOMETRY_CONFIGURATION_VERSION:
            details["geometry_configuration_version"] = (
                f"expected {GEOMETRY_CONFIGURATION_VERSION!r}, "
                f"got {self.geometry_configuration_version!r}"
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

        # Source columns are mandatory when the geometry is enabled.
        if not self.inclination_source_column:
            details["inclination_source_column"] = (
                "required: declare the dataset column that holds the inclination"
            )
        if not self.azimuth_source_column:
            details["azimuth_source_column"] = (
                "required: declare the dataset column that holds the azimuth"
            )

        if details:
            raise GeometryConfigurationError(
                "Configuración geométrica incompleta: faltan campos obligatorios "
                "o tienen valores inválidos. La geometría está bloqueada.",
                error_code="GEOMETRY_INCOMPLETE",
                details={"missing_or_invalid": details},
            )

        return self

    def inclination_unit_canonical(self) -> str:
        """Lowercase math keyword for the INDEPENDENT inclination unit."""
        return _unit_to_canonical(self.inclination_unit)

    def azimuth_unit_canonical(self) -> str:
        """Lowercase math keyword for the INDEPENDENT azimuth unit."""
        return _unit_to_canonical(self.azimuth_unit)

    # Backward-compat shim — DEPRECATED. Returns the inclination unit when
    # both units agree and raises when they don't, so callers that still
    # ask for a single shared unit get an explicit error instead of
    # silently collapsing RADIANS+DEGREES to the wrong value.
    def angle_unit_canonical(self) -> str:
        if self.inclination_unit != self.azimuth_unit:
            raise GeometryConfigurationError(
                "inclination_unit y azimuth_unit difieren; use "
                "inclination_unit_canonical() / azimuth_unit_canonical() "
                "para obtener cada unidad por separado.",
                error_code="UNITS_ARE_INDEPENDENT",
                details={
                    "inclination_unit": self.inclination_unit,
                    "azimuth_unit": self.azimuth_unit,
                },
            )
        return self.inclination_unit_canonical()
