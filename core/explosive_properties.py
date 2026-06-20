"""Reference properties for ENAEX explosives seen in production reports.

Used by compute_altura_carga() and the 3D viewer to enrich well tooltips.
Values from ENAEX product catalog (Pirex emulsions + Enaline cartridges).

The per-grade Pirex energy/density tables are sourced from
:data:`core.config.EXPLOSIVE` (single source of truth) instead of being
duplicated here.
"""
from __future__ import annotations

from typing import Optional

from core.config import EXPLOSIVE


PIREX_ENERGY_MJ_KG = dict(EXPLOSIVE.pirex_energy_by_grade)
PIREX_DENSITY_G_CM3 = dict(EXPLOSIVE.pirex_density_by_grade)
ENALINE_DENSITY_G_CM3 = 1.10
ENALINE_ENERGY_MJ_KG = 2.85


def get_explosive_density_g_cm3(explosive_name: str) -> Optional[float]:
    """Density (g/cm³) for a given explosive type. None if unknown."""
    if not explosive_name:
        return None
    n = explosive_name.strip()
    if n in PIREX_DENSITY_G_CM3:
        return PIREX_DENSITY_G_CM3[n]
    if 'Pirex' in n:
        return PIREX_DENSITY_G_CM3.get('Pirex-930')
    if 'Enaline' in n:
        return ENALINE_DENSITY_G_CM3
    return None


def get_explosive_energy_mj_kg(explosive_name: str) -> Optional[float]:
    """Specific energy (MJ/kg) for a given explosive type. None if unknown."""
    if not explosive_name:
        return None
    n = explosive_name.strip()
    if n in PIREX_ENERGY_MJ_KG:
        return PIREX_ENERGY_MJ_KG[n]
    if 'Pirex' in n:
        return PIREX_ENERGY_MJ_KG.get('Pirex-930')
    if 'Enaline' in n:
        return ENALINE_ENERGY_MJ_KG
    return None


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
