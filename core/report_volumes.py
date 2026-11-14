"""Excavation areas per section and estimated volumes for reports (contract C2)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from core.geom_utils import calculate_area_between_profiles

AREA_SOURCE = "calculate_area_between_profiles"
MIN_PROFILE_POINTS = 2

_ASSUMPTION_AREA = (
    "Áreas entre el perfil de diseño y el perfil topográfico, integradas sobre el "
    "tramo de distancia común a ambos: sobreexcavación = topografía por debajo del "
    "diseño; subexcavación = topografía por encima del diseño."
)
_ASSUMPTION_WINDOW = (
    "Ventana aplicada: los perfiles se recortan al rango de distancia indicado y sus "
    "cotas se limitan al rango de cota indicado, por lo que el área situada fuera de "
    "ese rango de cota no se integra."
)
_ASSUMPTION_VOLUME = (
    "Volumen estimado = área de la sección × ancho de influencia (mitad de la "
    "distancia a las secciones vecinas); es una estimación, no una cubicación."
)


@dataclass(frozen=True)
class SectionExcavation:
    section: str
    sector: str
    area_over_m2: Optional[float]
    area_under_m2: Optional[float]
    influence_width_m: Optional[float]
    volume_over_m3: Optional[float]
    volume_under_m3: Optional[float]
    window: Optional[tuple[float, float, float, float]]
    source: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]


def _finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _section_origin(section: Mapping[str, Any]) -> Optional[tuple[float, float]]:
    origin = section.get("origin")
    if origin is None or isinstance(origin, (str, bytes)):
        return None
    try:
        raw_x, raw_y = origin[0], origin[1]
    except (TypeError, IndexError, KeyError):
        return None
    x = _finite_float(raw_x)
    y = _finite_float(raw_y)
    if x is None or y is None:
        return None
    return (x, y)


def _positive_distance(
    a: Optional[tuple[float, float]], b: Optional[tuple[float, float]]
) -> Optional[float]:
    if a is None or b is None:
        return None
    distance = math.hypot(b[0] - a[0], b[1] - a[1])
    return distance if distance > 0.0 else None


def section_influence_widths(
    sections: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], Optional[float]]:
    """Influence width per (sector, section name), in metres.

    Sections are chained per sector in input order. The width is half the
    distance between section origins (distance 0 of the section line, on the
    crest line) to the previous section plus half to the next one; at
    the ends the available half is doubled. A sector with a single section,
    or a section whose distance to an adjacent section cannot be measured
    (missing origin or coincident origins), gets ``None``.
    """
    by_sector: dict[str, list[tuple[str, Optional[tuple[float, float]]]]] = {}
    for section in sections:
        sector = str(section.get("sector") or "")
        name = str(section.get("name") or "")
        by_sector.setdefault(sector, []).append((name, _section_origin(section)))

    widths: dict[tuple[str, str], Optional[float]] = {}
    for sector, entries in by_sector.items():
        count = len(entries)
        for index, (name, origin) in enumerate(entries):
            key = (sector, name)
            if count < 2:
                widths[key] = None
                continue
            gaps = []
            if index > 0:
                gaps.append(_positive_distance(entries[index - 1][1], origin))
            if index < count - 1:
                gaps.append(_positive_distance(origin, entries[index + 1][1]))
            if any(gap is None for gap in gaps):
                widths[key] = None
            elif len(gaps) == 1:
                widths[key] = gaps[0]
            else:
                widths[key] = gaps[0] / 2.0 + gaps[1] / 2.0
    return widths


def _profile_arrays(profile: Any) -> Optional[tuple[np.ndarray, np.ndarray]]:
    if profile is None:
        return None
    if hasattr(profile, "distances") and hasattr(profile, "elevations"):
        raw_d, raw_z = profile.distances, profile.elevations
    else:
        try:
            raw_d, raw_z = profile
        except (TypeError, ValueError):
            return None
    try:
        distances = np.asarray(raw_d, dtype=float).ravel()
        elevations = np.asarray(raw_z, dtype=float).ravel()
    except (TypeError, ValueError):
        return None
    if distances.size != elevations.size:
        return None
    finite = np.isfinite(distances) & np.isfinite(elevations)
    distances, elevations = distances[finite], elevations[finite]
    order = np.argsort(distances, kind="stable")
    return distances[order], elevations[order]


def _clip_distance(
    distances: np.ndarray, elevations: np.ndarray, d_min: float, d_max: float
) -> tuple[np.ndarray, np.ndarray]:
    low = max(d_min, float(distances[0]))
    high = min(d_max, float(distances[-1]))
    if high <= low:
        return np.array([]), np.array([])
    inside = (distances > low) & (distances < high)
    clipped_d = np.concatenate(([low], distances[inside], [high]))
    clipped_z = np.concatenate(
        (
            [np.interp(low, distances, elevations)],
            elevations[inside],
            [np.interp(high, distances, elevations)],
        )
    )
    return clipped_d, clipped_z


def _clamp_elevation(
    distances: np.ndarray, elevations: np.ndarray, z_min: float, z_max: float
) -> tuple[np.ndarray, np.ndarray]:
    out_d = [float(distances[0])]
    out_z = [float(elevations[0])]
    for index in range(1, distances.size):
        d0, z0 = float(distances[index - 1]), float(elevations[index - 1])
        d1, z1 = float(distances[index]), float(elevations[index])
        crossings = []
        for bound in (z_min, z_max):
            if (z0 - bound) * (z1 - bound) < 0.0:
                fraction = (bound - z0) / (z1 - z0)
                crossings.append((fraction, d0 + fraction * (d1 - d0), bound))
        for _, crossing_d, crossing_z in sorted(crossings):
            out_d.append(crossing_d)
            out_z.append(crossing_z)
        out_d.append(d1)
        out_z.append(z1)
    return np.asarray(out_d), np.clip(np.asarray(out_z), z_min, z_max)


def _valid_window(
    window: tuple[float, float, float, float],
) -> Optional[tuple[float, float, float, float]]:
    try:
        values = tuple(_finite_float(value) for value in window)
    except TypeError:
        return None
    if len(values) != 4:
        return None
    d_min, d_max, z_min, z_max = values
    if d_min is None or d_max is None or z_min is None or z_max is None:
        return None
    if d_max <= d_min or z_max <= z_min:
        return None
    return (d_min, d_max, z_min, z_max)


def _measure_areas(
    design_profile: Any,
    topo_profile: Any,
    window: Optional[tuple[float, float, float, float]],
) -> tuple[Optional[tuple[float, float]], Optional[str]]:
    design = _profile_arrays(design_profile)
    topo = _profile_arrays(topo_profile)
    if design is None or design[0].size < MIN_PROFILE_POINTS:
        return None, "Perfil de diseño vacío o con menos de dos puntos válidos: áreas no calculadas."
    if topo is None or topo[0].size < MIN_PROFILE_POINTS:
        return None, "Perfil topográfico vacío o con menos de dos puntos válidos: áreas no calculadas."

    if window is not None:
        d_min, d_max, z_min, z_max = window
        design = _clip_distance(*design, d_min, d_max)
        topo = _clip_distance(*topo, d_min, d_max)
        if design[0].size < MIN_PROFILE_POINTS or topo[0].size < MIN_PROFILE_POINTS:
            return None, "Los perfiles no cubren el rango de distancia de la ventana: áreas no calculadas."
        in_band = [
            float(z.min()) <= z_max and float(z.max()) >= z_min for _, z in (design, topo)
        ]
        if not any(in_band):
            return None, "Ningún perfil cae dentro del rango de cota de la ventana: áreas no calculadas."
        design = _clamp_elevation(*design, z_min, z_max)
        topo = _clamp_elevation(*topo, z_min, z_max)

    overlap_min = max(float(design[0][0]), float(topo[0][0]))
    overlap_max = min(float(design[0][-1]), float(topo[0][-1]))
    if overlap_max <= overlap_min:
        return None, "Los perfiles de diseño y topografía no se traslapan en distancia: áreas no calculadas."

    result = calculate_area_between_profiles(
        SimpleNamespace(distances=design[0], elevations=design[1]),
        SimpleNamespace(distances=topo[0], elevations=topo[1]),
    )
    if len(result) < 5 or np.size(result[2]) == 0:
        return None, "Los perfiles de diseño y topografía no se traslapan en distancia: áreas no calculadas."
    area_over, area_under = float(result[0]), float(result[1])
    if not (math.isfinite(area_over) and math.isfinite(area_under)):
        return None, "La integración entre perfiles no entregó un valor finito: áreas no calculadas."
    return (area_over, area_under), None


def section_excavation(
    section: str,
    sector: str,
    design_profile: Any,
    topo_profile: Any,
    window: Optional[tuple[float, float, float, float]],
    influence_width_m: Optional[float],
) -> SectionExcavation:
    """Over/under-excavation areas of one section and their estimated volumes.

    Profiles are objects with ``distances``/``elevations`` or
    ``(distances, elevations)`` tuples. Missing inputs yield ``None`` values
    and a warning, never 0.
    """
    assumptions = [_ASSUMPTION_AREA]
    warnings: list[str] = []

    used_window: Optional[tuple[float, float, float, float]] = None
    areas: Optional[tuple[float, float]] = None
    if window is not None:
        used_window = _valid_window(window)
        if used_window is None:
            warnings.append(
                "Ventana inválida (se requiere d_min < d_max y z_min < z_max, valores finitos): "
                "áreas no calculadas."
            )
        else:
            assumptions.append(_ASSUMPTION_WINDOW)
    if window is None or used_window is not None:
        areas, area_warning = _measure_areas(design_profile, topo_profile, used_window)
        if area_warning is not None:
            warnings.append(area_warning)

    width: Optional[float] = None
    if influence_width_m is not None:
        width = _finite_float(influence_width_m)
        if width is not None and width <= 0.0:
            width = None
        if width is None:
            warnings.append("Ancho de influencia no válido: volúmenes no estimados.")
    assumptions.append(_ASSUMPTION_VOLUME)

    area_over: Optional[float] = None
    area_under: Optional[float] = None
    volume_over: Optional[float] = None
    volume_under: Optional[float] = None
    if areas is not None:
        area_over, area_under = areas
        if width is not None:
            volume_over = area_over * width
            volume_under = area_under * width
    return SectionExcavation(
        section=section,
        sector=sector,
        area_over_m2=area_over,
        area_under_m2=area_under,
        influence_width_m=width,
        volume_over_m3=volume_over,
        volume_under_m3=volume_under,
        window=used_window,
        source=AREA_SOURCE,
        assumptions=tuple(assumptions),
        warnings=tuple(warnings),
    )
