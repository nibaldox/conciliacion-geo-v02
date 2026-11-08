"""Explosive product registry — single source of truth for product data.

Spec §4.4: every known product stores

- normalized name
- density (g/cm³)
- absolute energy (MJ/kg) when available
- RWS (relative weight strength, ANFO = 1.0) when available
- VOD (m/s) when available
- data source
- datasheet version/date
- validation status

Unknown products resolve to ``None`` / status ``UNKNOWN`` — never a
silent ANFO fallback. Only explicitly listed aliases are recognized.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from numbers import Real
from typing import Optional

from core.config import EXPLOSIVE


# Backward-compat module constants (historical import paths)
PIREX_ENERGY_MJ_KG = dict(EXPLOSIVE.pirex_energy_by_grade)
PIREX_DENSITY_G_CM3 = dict(EXPLOSIVE.pirex_density_by_grade)
ENALINE_DENSITY_G_CM3 = 1.10
ENALINE_ENERGY_MJ_KG = 2.85


@dataclass(frozen=True)
class ExplosiveProduct:
    """Full product record (spec §4.4)."""

    normalized_name: str
    density_g_cm3: float
    energy_mj_kg: float
    rws: Optional[float]
    vod_m_s: Optional[float]
    source: str
    datasheet_version: Optional[str]
    validation_status: str
    is_exact: bool = True


def _product(
    name: str,
    density: float,
    energy: float,
    *,
    rws: Optional[float] = None,
    vod: Optional[float] = None,
    source: str = "Catálogo ENAEX (referencia, sin ficha oficial)",
    version: Optional[str] = None,
    status: str = "UNVALIDATED_REFERENCE",
) -> ExplosiveProduct:
    return ExplosiveProduct(
        normalized_name=name,
        density_g_cm3=density,
        energy_mj_kg=energy,
        rws=rws,
        vod_m_s=vod,
        source=source,
        datasheet_version=version,
        validation_status=status,
    )


EXPLOSIVE_PRODUCTS: dict[str, ExplosiveProduct] = {
    "Pirex-920": _product("Pirex-920", 1.15, 2.95),
    "Pirex-930": _product("Pirex-930", 1.20, 3.05),
    "Pirex-950": _product("Pirex-950", 1.23, 3.15),
    "Pirex-970": _product("Pirex-970", 1.25, 3.25),
    "ANFO": _product(
        "ANFO",
        0.80,
        3.72,
        rws=1.0,
        source="Referencia industrial estándar (ANFO = base 1.0 RWS)",
        status="VALIDATED",
    ),
    "Heavy ANFO": _product("Heavy ANFO", 1.05, 3.40),
    "Bulk Emulsion": _product("Bulk Emulsion", 1.15, 3.05),
    "Enaline": _product("Enaline", 1.10, 2.85),
}

EXPLOSIVE_ALIAS_VERSION = "1"
EXPLOSIVE_ALIASES: dict[str, tuple[str, ...]] = {
    "Pirex-920": ("Pirex-920",),
    "Pirex-930": ("Pirex-930",),
    "Pirex-950": ("Pirex-950",),
    "Pirex-970": ("Pirex-970",),
    "ANFO": ("ANFO",),
    "Heavy ANFO": ("Heavy ANFO", "H-ANFO"),
    "Bulk Emulsion": ("Bulk Emulsion", "Emulsion"),
    "Enaline": ("Enaline", "Enaline 1 1/4 12", "Enaline 1 1/4*12"),
}


def _normalize(name: str) -> str:
    return re.sub(r"[\s_-]+", " ", name.strip().upper())


_ALIAS_LOOKUP = {
    _normalize(alias): product
    for product, aliases in EXPLOSIVE_ALIASES.items()
    for alias in aliases
}


def _missing_name(name: object) -> bool:
    return (
        name is None
        or isinstance(name, str) and not name.strip()
        or isinstance(name, Real) and math.isnan(name)
    )


def resolve_explosive(explosive_name: str) -> Optional[ExplosiveProduct]:
    """Resolve only explicit aliases, preserving the legacy product return type."""
    if not isinstance(explosive_name, str):
        return None
    key = _ALIAS_LOOKUP.get(_normalize(explosive_name))
    return EXPLOSIVE_PRODUCTS.get(key) if key is not None else None


def get_explosive_density_g_cm3(explosive_name: str) -> Optional[float]:
    """Density (g/cm³) for a known explosive. None if unknown."""
    prod = resolve_explosive(explosive_name)
    return prod.density_g_cm3 if prod else None


def get_explosive_energy_mj_kg(explosive_name: str) -> Optional[float]:
    """Specific energy (MJ/kg) for a known explosive. None if unknown."""
    prod = resolve_explosive(explosive_name)
    return prod.energy_mj_kg if prod else None


def get_explosive_status(explosive_name: str) -> str:
    """Return the product validation state or UNKNOWN / MISSING."""
    if _missing_name(explosive_name):
        return "MISSING"
    prod = resolve_explosive(explosive_name)
    return prod.validation_status if prod else "UNKNOWN"


def get_explosive_rws(explosive_name: str) -> Optional[float]:
    """RWS relative to ANFO (1.0) when available; None otherwise."""
    prod = resolve_explosive(explosive_name)
    return prod.rws if prod else None


def get_explosive_vod_m_s(explosive_name: str) -> Optional[float]:
    """Detonation velocity (m/s) when available; None otherwise."""
    prod = resolve_explosive(explosive_name)
    return prod.vod_m_s if prod else None


def parse_diameter_mm(diameter_str) -> Optional[float]:
    """Parse diameter strings like '10 5/8' or '270' to mm.

    Imperial forms (10 5/8", 6 1/2") are converted to mm.
    Metric forms (270, 165) are returned as float.
    """
    if not diameter_str:
        return None
    s = str(diameter_str).strip().replace('"', '').replace("'", '')
    if '/' in s:
        parts = s.split()
        try:
            if len(parts) == 2:
                whole = float(parts[0])
                frac_parts = parts[1].split('/')
                frac = float(frac_parts[0]) / float(frac_parts[1])
                inches = whole + frac
                return inches * 25.4
            elif len(parts) == 1 and '/' in parts[0]:
                frac_parts = parts[0].split('/')
                frac = float(frac_parts[0]) / float(frac_parts[1])
                return frac * 25.4
        except (ValueError, ZeroDivisionError):
            return None
        return None
    try:
        v = float(s)
        if v < 50:
            return v * 25.4
        return v
    except ValueError:
        return None
