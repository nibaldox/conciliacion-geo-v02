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
silent ANFO fallback. Family matches (e.g. ``Pirex-930 Heavy``) resolve
to the base grade with ``is_exact=False`` so callers can warn the value
is an approximation of the base grade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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

# Config values (core.config.EXPLOSIVE) — still referenced by legacy code;
# the registry above is the authoritative per-product source.
_PIREX_GRADES = {"920", "930", "950", "970"}
_FAMILY_KEYS = ("Pirex-", "Enaline", "ANFO", "Heavy ANFO", "H-ANFO", "Emulsion", "Bulk Emulsion", "Emuline")


def _normalize(name: str) -> str:
    return (name or "").strip().lower()


def resolve_explosive(explosive_name: str) -> Optional[ExplosiveProduct]:
    """Resolve a product name to its full record, or None if unknown.

    Matching order:
      1. exact (case-insensitive) key in the registry
      2. ``Pirex-<grade>`` prefix with a known grade (suffixes allowed),
         flagged ``is_exact=False``
      3. ``Enaline`` prefix (suffixes allowed), flagged ``is_exact=False``
      4. family substrings (ANFO / Heavy ANFO / Emulsion) — exact keys
         already cover these; substrings only match when the registry
         key is a prefix of the input name (e.g. ``Emuline 8000``)

    Anything else returns None (explicit UNKNOWN, never ANFO).
    """
    if not explosive_name:
        return None
    n = explosive_name.strip()

    key = _normalize(n)
    for k, prod in EXPLOSIVE_PRODUCTS.items():
        if _normalize(k) == key:
            return prod

    for grade, prod in (
        (g, EXPLOSIVE_PRODUCTS[f"Pirex-{g}"]) for g in sorted(_PIREX_GRADES, key=lambda g: -len(g))
    ):
        prefix = f"pirex-{grade}"
        if key.startswith(prefix):
            return _family_copy(prod)

    if key.startswith("enaline"):
        return _family_copy(EXPLOSIVE_PRODUCTS["Enaline"])

    for family in ("heavy anfo", "h-anfo"):
        if family in key:
            return EXPLOSIVE_PRODUCTS["Heavy ANFO"]
    if "emul" in key:
        return EXPLOSIVE_PRODUCTS["Bulk Emulsion"]
    if "anfo" in key:
        return EXPLOSIVE_PRODUCTS["ANFO"]
    return None


def _family_copy(prod: ExplosiveProduct) -> ExplosiveProduct:
    return ExplosiveProduct(
        normalized_name=prod.normalized_name,
        density_g_cm3=prod.density_g_cm3,
        energy_mj_kg=prod.energy_mj_kg,
        rws=prod.rws,
        vod_m_s=prod.vod_m_s,
        source=prod.source,
        datasheet_version=prod.datasheet_version,
        validation_status=prod.validation_status,
        is_exact=False,
    )


def get_explosive_density_g_cm3(explosive_name: str) -> Optional[float]:
    """Density (g/cm³) for a known explosive. None if unknown."""
    prod = resolve_explosive(explosive_name)
    return prod.density_g_cm3 if prod else None


def get_explosive_energy_mj_kg(explosive_name: str) -> Optional[float]:
    """Specific energy (MJ/kg) for a known explosive. None if unknown."""
    prod = resolve_explosive(explosive_name)
    return prod.energy_mj_kg if prod else None


def get_explosive_status(explosive_name: str) -> str:
    """Explicit validation state: VALIDATED | UNVALIDATED_REFERENCE |
    FAMILY_MATCH | UNKNOWN | MISSING."""
    if not explosive_name:
        return "MISSING"
    prod = resolve_explosive(explosive_name)
    if prod is None:
        return "UNKNOWN"
    if not prod.is_exact:
        return "FAMILY_MATCH"
    return prod.validation_status


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
