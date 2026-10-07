"""
Mesh router — upload, info, vertices, delete.

All endpoints operate under the session identified by ``request.state.session_id``
(which is set by the session middleware in ``api/main.py``).

Performance: every handler is ``async def`` and off-loads DB round-trips
(``api.database`` is synchronous SQLite) to the default executor via
:func:`api._async_db.run_db`. The cached heavy helpers (``_get_decimated_*``,
``_get_contours_*``, ``_get_breaklines_*``) stay synchronous so tests can still
call ``.cache_clear()`` on them, but the handler awaits them through
``run_db`` so trimesh decimation / sectioning / breakline extraction never
blocks the event loop.
"""

import asyncio
import os
import tempfile
import functools
import json
import math
from pathlib import Path
from typing import Optional

import numpy as np
import trimesh
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

import api.database as db
import api.dxf_uploads as dxf_uploads
from api.schemas import DxfImportConfirmation
from api._async_db import run_db
from core import (
    HorizontalFaceGeometry,
    SectionLine,
    classify_horizontal_deviation,
    cut_mesh_with_section,
    cut_mesh_with_section_diagnostics,
    extract_parameters,
    get_mesh_bounds,
    load_mesh,
    measure_horizontal_deviation_at_elevation,
    profile_intersections_at_elevation,
)
from core.config import DEFAULTS, DETECTION, HORIZONTAL_DEVIATION

router = APIRouter(prefix="/meshes", tags=["meshes"])

# ---------------------------------------------------------------------------
# Session dependency
# ---------------------------------------------------------------------------


def get_session_id(request: Request) -> str:
    """Extract session_id set by the session middleware."""
    return request.state.session_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_mesh_from_blob(mesh_data: bytes, filename: str) -> trimesh.Trimesh:
    """Load a trimesh from database BLOB via a temporary file."""
    suffix = Path(filename).suffix or ".stl"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(mesh_data)
        return load_mesh(tmp)
    finally:
        os.unlink(tmp)


def _finite_float(value, fallback: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if math.isfinite(result) else fallback


def _section_from_payload(payload: dict) -> SectionLine:
    origin = np.asarray(payload["origin"], dtype=float)
    if origin.shape not in ((2,), (3,)) or not np.isfinite(origin).all():
        raise ValueError("Section origins must contain two or three finite coordinates")
    azimuth = _finite_float(payload.get("azimuth"), math.nan)
    length = _finite_float(payload.get("length"), math.nan)
    if not math.isfinite(azimuth) or not math.isfinite(length) or length <= 0:
        raise ValueError("Sections need a finite azimuth and positive length")
    length_up = payload.get("length_up")
    length_down = payload.get("length_down")
    if length_up is not None and length_down is not None:
        length_up = _finite_float(length_up, math.nan)
        length_down = _finite_float(length_down, math.nan)
        if not math.isfinite(length_up) or not math.isfinite(length_down):
            raise ValueError("Section lengths must be finite")
    else:
        length_up = None
        length_down = None
    return SectionLine(
        name=str(payload.get("name", "")),
        origin=origin[:2],
        azimuth=azimuth % 360.0,
        length=length,
        sector=str(payload.get("sector", "")),
        length_up=length_up,
        length_down=length_down,
    )


def _section_at_fraction(
    left: SectionLine,
    right: SectionLine,
    fraction: float,
    station_m: float,
) -> SectionLine:
    azimuth_delta = (right.azimuth - left.azimuth + 180.0) % 360.0 - 180.0
    up = None
    down = None
    if left.length_up is not None and right.length_up is not None:
        up = left.length_up + fraction * (right.length_up - left.length_up)
    if left.length_down is not None and right.length_down is not None:
        down = left.length_down + fraction * (right.length_down - left.length_down)
    length = left.length + fraction * (right.length - left.length)
    return SectionLine(
        name=f"{left.name}:{right.name}:{station_m:.3f}",
        origin=left.origin + fraction * (right.origin - left.origin),
        azimuth=(left.azimuth + fraction * azimuth_delta) % 360.0,
        length=length,
        sector=left.sector,
        length_up=up,
        length_down=down,
    )


def _profile_data(mesh: trimesh.Trimesh, section: SectionLine) -> tuple[np.ndarray, np.ndarray] | None:
    profile = cut_mesh_with_section(mesh, section)
    if profile is None or len(profile.distances) < 2:
        return None
    return (
        np.asarray(profile.distances, dtype=float),
        np.asarray(profile.elevations, dtype=float),
    )


def _profile_data_with_diagnostics(
    mesh: trimesh.Trimesh,
    section: SectionLine,
) -> tuple[tuple[np.ndarray, np.ndarray] | None, tuple[str, ...]]:
    cut = cut_mesh_with_section_diagnostics(mesh, section)
    profile = cut.profile
    if profile is None or len(profile.distances) < 2:
        return None, cut.warnings
    return (
        (
            np.asarray(profile.distances, dtype=float),
            np.asarray(profile.elevations, dtype=float),
        ),
        cut.warnings,
    )


def _missing_profile_status(profile, warnings: tuple[str, ...]) -> str:
    if profile is not None:
        return "missing"
    if any(
        code in warnings
        for code in ("disconnected_profile_components", "ambiguous_profile_geometry")
    ):
        return "ambiguous"
    return "missing"


def _crop_mesh_to_sections(
    mesh: trimesh.Trimesh,
    sections: list[SectionLine],
) -> trimesh.Trimesh:
    origins = np.asarray([section.origin for section in sections], dtype=float)
    radius = max(
        max(
            section.length / 2.0,
            float(section.length_up or 0.0),
            float(section.length_down or 0.0),
        )
        for section in sections
    )
    lower = origins.min(axis=0) - radius
    upper = origins.max(axis=0) + radius
    selected_faces: list[np.ndarray] = []
    vertices = np.asarray(mesh.vertices)
    source_faces = np.asarray(mesh.faces)
    chunk_size = 250000
    for start in range(0, len(source_faces), chunk_size):
        chunk = source_faces[start:start + chunk_size]
        triangles = vertices[chunk]
        keep = (
            (triangles[:, :, 0].max(axis=1) >= lower[0])
            & (triangles[:, :, 0].min(axis=1) <= upper[0])
            & (triangles[:, :, 1].max(axis=1) >= lower[1])
            & (triangles[:, :, 1].min(axis=1) <= upper[1])
        )
        if np.any(keep):
            selected_faces.append(chunk[keep])
    if not selected_faces:
        return trimesh.Trimesh(
            vertices=np.empty((0, 3), dtype=float),
            faces=np.empty((0, 3), dtype=np.int64),
            process=False,
        )
    faces = np.concatenate(selected_faces, axis=0)
    used_vertices, inverse = np.unique(faces, return_inverse=True)
    return trimesh.Trimesh(
        vertices=vertices[used_vertices],
        faces=inverse.reshape((-1, 3)),
        process=False,
    )


def _extract_faces(
    profile: tuple[np.ndarray, np.ndarray] | None,
    section: SectionLine,
    detection_options: dict,
) -> dict[int, HorizontalFaceGeometry]:
    if profile is None:
        return {}
    extraction = extract_parameters(
        profile[0],
        profile[1],
        section.name,
        section.sector,
        resolution=float(detection_options["profile_resolution"]),
        face_threshold=float(detection_options["face_threshold"]),
        berm_threshold=float(detection_options["berm_threshold"]),
        max_berm_width=float(detection_options["max_berm_width"]),
        max_single_bench_width=float(detection_options["max_single_bench_width"]),
    )
    faces: dict[int, HorizontalFaceGeometry] = {}
    for bench in extraction.benches:
        if bool(getattr(bench, "is_ramp", False)):
            continue
        crest_distance = _finite_float(getattr(bench, "crest_distance", math.nan), math.nan)
        toe_distance = _finite_float(getattr(bench, "toe_distance", math.nan), math.nan)
        crest_elevation = _finite_float(getattr(bench, "crest_elevation", math.nan), math.nan)
        toe_elevation = _finite_float(getattr(bench, "toe_elevation", math.nan), math.nan)
        bench_height = _finite_float(getattr(bench, "bench_height", math.nan), math.nan)
        if not all(math.isfinite(v) for v in (
            crest_distance, toe_distance, crest_elevation, toe_elevation, bench_height,
        )):
            continue
        if abs(crest_elevation - toe_elevation) <= HORIZONTAL_DEVIATION.intersection_epsilon_m:
            continue
        number = int(bench.bench_number)
        faces[number] = HorizontalFaceGeometry(
            bench_number=number,
            crest_distance=crest_distance,
            crest_elevation=crest_elevation,
            toe_distance=toe_distance,
            toe_elevation=toe_elevation,
            bench_height=bench_height,
        )
    return faces


def _grid_levels(max_height: float, step: float) -> list[float]:
    if max_height <= 0:
        return []
    levels = [float(v) for v in np.arange(0.0, max_height, step)]
    if not levels or levels[0] != 0.0:
        levels.insert(0, 0.0)
    if max_height - levels[-1] > 1.0e-8:
        levels.append(float(max_height))
    else:
        levels[-1] = float(max_height)
    return levels


def _height_elevation(face: HorizontalFaceGeometry, height: float) -> float | None:
    face_height = abs(float(face.crest_elevation) - float(face.toe_elevation))
    if height < -HORIZONTAL_DEVIATION.intersection_epsilon_m or height > face_height + HORIZONTAL_DEVIATION.intersection_epsilon_m:
        return None
    direction = 1.0 if face.crest_elevation >= face.toe_elevation else -1.0
    return float(face.toe_elevation + direction * min(max(height, 0.0), face_height))


def _same_design_face_across_stations(faces: list[HorizontalFaceGeometry | None]) -> bool:
    if any(face is None for face in faces):
        return False
    complete = [face for face in faces if face is not None]
    if not complete:
        return False
    intervals = [
        (
            min(face.crest_elevation, face.toe_elevation),
            max(face.crest_elevation, face.toe_elevation),
        )
        for face in complete
    ]
    shared_low = max(interval[0] for interval in intervals)
    shared_high = min(interval[1] for interval in intervals)
    minimum_height = min(high - low for low, high in intervals)
    directions = [
        1 if face.crest_distance > face.toe_distance else -1
        for face in complete
    ]
    elevation_directions = [
        1 if face.crest_elevation > face.toe_elevation else -1
        for face in complete
    ]
    return (
        len(set(directions)) == 1
        and len(set(elevation_directions)) == 1
        and shared_high - shared_low >= 0.5 * minimum_height
    )


def _intersection_distance(
    profile: tuple[np.ndarray, np.ndarray] | None,
    face: HorizontalFaceGeometry | None,
    elevation: float | None,
) -> tuple[float | None, str]:
    if profile is None or elevation is None:
        return None, "missing"
    bounds = {}
    if face is not None:
        bounds = {
            "min_distance": min(face.crest_distance, face.toe_distance),
            "max_distance": max(face.crest_distance, face.toe_distance),
        }
    hit = profile_intersections_at_elevation(profile[0], profile[1], elevation, **bounds)
    return hit.distance_m, hit.status


def _point_at_distance(section: SectionLine, distance: float, elevation: float) -> tuple[float, float, float]:
    azimuth = math.radians(section.azimuth)
    return (
        float(section.origin[0] + math.sin(azimuth) * distance),
        float(section.origin[1] + math.cos(azimuth) * distance),
        float(elevation),
    )


def _build_horizontal_deviation_payload(
    topo_id: str,
    design_mesh_id: str,
    sections: list[dict],
    sector: str,
    bench_num: int | None,
    longitudinal_step: float,
    vertical_step: float,
    detection_options: dict,
) -> dict:
    indexed_sections = [
        (index, _section_from_payload(raw))
        for index, raw in enumerate(sections)
        if str(raw.get("sector", "")) == sector
    ]
    if len(indexed_sections) < 2:
        raise ValueError("insufficient_sections: at least two configured sections in the selected sector are required for a 3D patch")

    section_refs: list[SectionLine] = []
    section_ref_indices: set[int] = set()
    for pair_index in range(len(indexed_sections) - 1):
        left_index, left = indexed_sections[pair_index]
        right_index, right = indexed_sections[pair_index + 1]
        gap = float(np.linalg.norm(right.origin - left.origin))
        azimuth_delta = abs((right.azimuth - left.azimuth + 180.0) % 360.0 - 180.0)
        if (
            1.0e-6 < gap <= HORIZONTAL_DEVIATION.heatmap_max_section_gap_m
            and azimuth_delta <= HORIZONTAL_DEVIATION.heatmap_max_azimuth_delta_deg
        ):
            for index, section in ((left_index, left), (right_index, right)):
                if index not in section_ref_indices:
                    section_refs.append(section)
                    section_ref_indices.add(index)
    if not section_refs:
        raise ValueError("no_compatible_section_pairs: no same-sector section pair has coherent spacing and direction")
    topo_mesh = _crop_mesh_to_sections(db.get_trimesh_by_id(topo_id), section_refs)
    design_mesh = _crop_mesh_to_sections(db.get_trimesh_by_id(design_mesh_id), section_refs)

    warnings: list[str] = []
    vertices = {"x": [], "y": [], "z": []}
    faces: list[list[int]] = []
    cell_index_by_face: list[int] = []
    cells: list[dict] = []
    station_offset = 0.0
    cut_count = 0
    total_cells = 0
    effective_longitudinal_steps: list[float] = []
    effective_vertical_steps: list[float] = []

    for pair_index in range(len(indexed_sections) - 1):
        left_index, left = indexed_sections[pair_index]
        right_index, right = indexed_sections[pair_index + 1]
        section_gap = float(np.linalg.norm(right.origin - left.origin))
        azimuth_delta = abs((right.azimuth - left.azimuth + 180.0) % 360.0 - 180.0)
        if section_gap <= 1.0e-6:
            warnings.append("section_pair_zero_spacing")
            continue
        if section_gap > HORIZONTAL_DEVIATION.heatmap_max_section_gap_m:
            warnings.append("section_pair_gap_too_large")
            station_offset += section_gap
            continue
        if azimuth_delta > HORIZONTAL_DEVIATION.heatmap_max_azimuth_delta_deg:
            warnings.append("section_pair_azimuth_change_too_large")
            station_offset += section_gap
            continue

        interval_edges = [float(v) for v in np.arange(0.0, section_gap, longitudinal_step)]
        if not interval_edges or interval_edges[0] != 0.0:
            interval_edges.insert(0, 0.0)
        if section_gap - interval_edges[-1] > 1.0e-8:
            interval_edges.append(section_gap)
        else:
            interval_edges[-1] = section_gap
        if len(interval_edges) < 2:
            warnings.append(f"section_pair_has_no_cells:{left.name}:{right.name}")
            station_offset += section_gap
            continue

        fractions = sorted(set(
            [distance / section_gap for distance in interval_edges]
            + [
                (interval_edges[index] + interval_edges[index + 1]) / (2.0 * section_gap)
                for index in range(len(interval_edges) - 1)
            ]
        ))
        cut_count += len(fractions)
        if cut_count > HORIZONTAL_DEVIATION.heatmap_max_cuts:
            raise OverflowError(
                f"Requested grid needs more than {HORIZONTAL_DEVIATION.heatmap_max_cuts} source-mesh section cuts; increase longitudinal_step"
            )

        station_data: dict[float, dict] = {}
        for fraction in fractions:
            local_station_m = fraction * section_gap
            section = _section_at_fraction(
                left, right, fraction, station_offset + local_station_m
            )
            design_profile, design_profile_warnings = _profile_data_with_diagnostics(
                design_mesh, section
            )
            topo_profile, topo_profile_warnings = _profile_data_with_diagnostics(
                topo_mesh, section
            )
            station_data[fraction] = {
                "section": section,
                "station_m": station_offset + local_station_m,
                "design_profile": design_profile,
                "topo_profile": topo_profile,
                "design_profile_warnings": design_profile_warnings,
                "topo_profile_warnings": topo_profile_warnings,
                "design_faces": _extract_faces(design_profile, section, detection_options),
            }

        edge_fractions = [distance / section_gap for distance in interval_edges]
        for interval_index in range(len(edge_fractions) - 1):
            left_fraction = edge_fractions[interval_index]
            right_fraction = edge_fractions[interval_index + 1]
            center_fraction = (
                interval_edges[interval_index] + interval_edges[interval_index + 1]
            ) / (2.0 * section_gap)
            left_data = station_data[left_fraction]
            right_data = station_data[right_fraction]
            center_data = station_data[center_fraction]
            effective_longitudinal_steps.append(
                (right_fraction - left_fraction) * section_gap
            )
            bank_numbers = sorted(set(left_data["design_faces"]) | set(right_data["design_faces"]) | set(center_data["design_faces"]))
            if bench_num is not None:
                bank_numbers = [number for number in bank_numbers if number == bench_num]
            for bank_number in bank_numbers:
                center_face = center_data["design_faces"].get(bank_number)
                if center_face is None:
                    continue
                bank_faces = [
                    data["design_faces"].get(bank_number)
                    for data in (left_data, right_data, center_data)
                ]
                face_is_consistent = _same_design_face_across_stations(bank_faces)
                center_face_height = abs(
                    center_face.crest_elevation - center_face.toe_elevation
                )
                height_levels = _grid_levels(center_face_height, vertical_step)
                if len(height_levels) < 2:
                    continue
                effective_vertical_steps.extend(
                    height_levels[index + 1] - height_levels[index]
                    for index in range(len(height_levels) - 1)
                )
                if total_cells + (len(height_levels) - 1) > HORIZONTAL_DEVIATION.heatmap_max_cells:
                    raise OverflowError(
                        f"Requested grid exceeds {HORIZONTAL_DEVIATION.heatmap_max_cells} cells; increase longitudinal_step or vertical_step"
                    )
                for height_index in range(len(height_levels) - 1):
                    h_low = height_levels[height_index]
                    h_high = height_levels[height_index + 1]
                    h_center = (h_low + h_high) / 2.0
                    center_elevation = _height_elevation(center_face, h_center)
                    if center_elevation is None:
                        continue
                    total_cells += 1
                    center_topo_hit, center_topo_status = _intersection_distance(
                        center_data["topo_profile"], None, center_elevation
                    )
                    if center_topo_hit is None and center_data["topo_profile"] is None:
                        center_topo_status = _missing_profile_status(
                            center_data["topo_profile"], center_data["topo_profile_warnings"]
                        )
                    center_design_hit, center_design_status = _intersection_distance(
                        center_data["design_profile"], center_face, center_elevation
                    )
                    if center_design_hit is None and center_data["design_profile"] is None:
                        center_design_status = _missing_profile_status(
                            center_data["design_profile"], center_data["design_profile_warnings"]
                        )
                    measurement = None
                    if not face_is_consistent:
                        cell_status = "inconsistent_design_face_across_stations"
                    elif center_design_hit is None:
                        cell_status = f"design_{center_design_status}"
                    elif center_topo_hit is None:
                        cell_status = f"topo_{center_topo_status}"
                    else:
                        measurement = measure_horizontal_deviation_at_elevation(
                            center_data["design_profile"][0],
                            center_data["design_profile"][1],
                            center_elevation,
                            center_topo_hit,
                            center_face,
                            source="original_mesh_section_profile",
                        )
                        cell_status = measurement.status

                    corner_points: list[tuple[float, float, float]] = []
                    corner_ok = True
                    corner_status = ""
                    for data, face in (
                        (left_data, bank_faces[0]),
                        (right_data, bank_faces[1]),
                        (right_data, bank_faces[1]),
                        (left_data, bank_faces[0]),
                    ):
                        h = h_low if len(corner_points) < 2 else h_high
                        corner_elevation = _height_elevation(face, h) if face is not None else None
                        if corner_elevation is None:
                            corner_ok = False
                            corner_status = "design_corner_outside_face"
                            break
                        design_distance, design_status = _intersection_distance(
                            data["design_profile"], face, corner_elevation
                        )
                        if design_distance is None:
                            corner_ok = False
                            corner_status = f"design_corner_{design_status}"
                            break
                        distance, corner_topo_status = _intersection_distance(
                            data["topo_profile"], None, corner_elevation
                        )
                        if distance is None and data["topo_profile"] is None:
                            corner_topo_status = _missing_profile_status(
                                data["topo_profile"], data["topo_profile_warnings"]
                            )
                        if distance is None:
                            corner_ok = False
                            corner_status = f"topo_corner_{corner_topo_status}"
                            break
                        corner_points.append(_point_at_distance(data["section"], distance, corner_elevation))

                    is_measured = (
                        face_is_consistent
                        and measurement is not None
                        and measurement.deviation_m is not None
                    )
                    if not corner_ok:
                        is_measured = False
                        cell_status = corner_status or "missing_or_ambiguous_corner"
                    deviation = float(measurement.deviation_m) if is_measured else None
                    cell_warnings = list(measurement.warnings) if measurement is not None else []
                    if not is_measured:
                        cell_warnings.append(cell_status or "unmeasured")
                    category = (
                        classify_horizontal_deviation(deviation)
                        if deviation is not None else "unmeasured"
                    )
                    cells.append({
                        "deviation_m": deviation,
                        "value": deviation,
                        "unit": "m",
                        "category": category,
                        "status": cell_status if is_measured else (cell_status or "unmeasured"),
                        "station_m": float(center_data["station_m"]),
                        "elevation_m": float(center_elevation),
                        "bench_num": int(bank_number),
                        "design_distance_m": (
                            float(measurement.design_distance_m)
                            if measurement is not None and measurement.design_distance_m is not None
                            else center_design_hit
                        ),
                        "topo_distance_m": (
                            float(measurement.topo_distance_m)
                            if measurement is not None and measurement.topo_distance_m is not None
                            else center_topo_hit
                        ),
                        "source": (
                            measurement.source
                            if measurement is not None else "original_mesh_section_profile"
                        ),
                        "assumptions": (
                            list(measurement.assumptions)
                            if measurement is not None
                            else [
                                "piecewise_linear_profile_intersections",
                                "unique_topographic_crossing_at_equal_elevation",
                                "no_extrapolation",
                            ]
                        ),
                        "warnings": list(dict.fromkeys(cell_warnings)),
                    })

                    if is_measured:
                        base_index = len(vertices["x"])
                        ordered_points = (
                            corner_points[0], corner_points[1], corner_points[2],
                            corner_points[3],
                        )
                        for point_index in (0, 1, 2, 0, 2, 3):
                            point = ordered_points[point_index]
                            vertices["x"].append(point[0])
                            vertices["y"].append(point[1])
                            vertices["z"].append(point[2])
                        faces.append([base_index, base_index + 1, base_index + 2])
                        faces.append([base_index + 3, base_index + 4, base_index + 5])
                        cell_idx = len(cells) - 1
                        cell_index_by_face.extend([cell_idx, cell_idx])

        station_offset += section_gap

    measured_values = [cell["deviation_m"] for cell in cells if cell["deviation_m"] is not None]
    within_count = sum(
        abs(value) <= HORIZONTAL_DEVIATION.within_tolerance_m
        for value in measured_values
    )
    if not cells:
        warnings.append("no_design_faces_intersected_the_selected_sector")

    effective = {
        "longitudinal_step_min": min(effective_longitudinal_steps) if effective_longitudinal_steps else None,
        "longitudinal_step_max": max(effective_longitudinal_steps) if effective_longitudinal_steps else None,
        "vertical_step_min": min(effective_vertical_steps) if effective_vertical_steps else None,
        "vertical_step_max": max(effective_vertical_steps) if effective_vertical_steps else None,
    }
    return {
        "vertices": vertices,
        "faces": faces,
        "cell_index_by_face": cell_index_by_face,
        "cells": cells,
        "unit": "m",
        "method": "horizontal_at_equal_elevation",
        "direction": "positive_overbreak_negative_underbreak",
        "thresholds": {
            "within": HORIZONTAL_DEVIATION.within_tolerance_m,
            "moderate": HORIZONTAL_DEVIATION.moderate_tolerance_m,
            "severe": HORIZONTAL_DEVIATION.severe_tolerance_m,
        },
        "resolution": {
            "longitudinal_step": longitudinal_step,
            "vertical_step": vertical_step,
        },
        "effective_resolution": effective,
        "summary": {
            "measured": len(measured_values),
            "total": len(cells),
            "within_percent": (
                100.0 * within_count / len(measured_values)
                if measured_values else None
            ),
            "max_abs_deviation": (
                max(abs(value) for value in measured_values)
                if measured_values else None
            ),
        },
        "warnings": list(dict.fromkeys(warnings)),
        "assumptions": [
            "cross_sections_cut_from_original_design_and_topo_meshes",
            "patch_triangles_interpolated_between_original_mesh_section_intersections",
            "no_extrapolation_outside_configured_sections_or_detected_faces",
            "topographic_profile_crossing_must_be_unique_at_each_sample",
        ],
        "sector": sector,
        "bench_num": bench_num,
    }


@functools.lru_cache(maxsize=2)
def _build_horizontal_deviation_cached(
    topo_id: str,
    design_mesh_id: str,
    sections_payload: str,
    sector: str,
    bench_num: int | None,
    longitudinal_step: float,
    vertical_step: float,
    config_payload: str,
) -> dict:
    config = json.loads(config_payload)
    return _build_horizontal_deviation_payload(
        topo_id,
        design_mesh_id,
        json.loads(sections_payload),
        sector,
        bench_num,
        longitudinal_step,
        vertical_step,
        config["detection"],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_mesh(
    request: Request,
    file: UploadFile = File(...),
    type: str = Form(...),  # "design" | "topo"
):
    """
    Upload a mesh file (STL / OBJ / PLY / DXF).

    Saves raw bytes to the database and returns summary info.
    """
    if type not in ("design", "topo"):
        raise HTTPException(400, "type must be 'design' or 'topo'")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    filename = file.filename or "mesh.stl"

    # Load mesh to validate and extract metadata
    suffix = Path(filename).suffix or ".stl"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        mesh = load_mesh(tmp)
    except Exception as exc:
        raise HTTPException(400, f"Error loading mesh: {exc}")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    raw_bounds = get_mesh_bounds(mesh)
    clean_bounds = {
        "xmin": raw_bounds["xmin"],
        "xmax": raw_bounds["xmax"],
        "ymin": raw_bounds["ymin"],
        "ymax": raw_bounds["ymax"],
        "zmin": raw_bounds["zmin"],
        "zmax": raw_bounds["zmax"],
    }

    session_id = await run_db(db.get_or_create_session, get_session_id(request))
    mesh_id = await run_db(
        db.save_mesh,
        session_id=session_id,
        mesh_type=type,
        filename=filename,
        data=content,
        n_vertices=len(mesh.vertices),
        n_faces=len(mesh.faces),
        bounds=clean_bounds,
    )

    return {
        "mesh_id": mesh_id,
        "n_vertices": len(mesh.vertices),
        "n_faces": len(mesh.faces),
        "bounds": clean_bounds,
    }


@router.post("/dxf/inspect")
async def inspect_dxf(
    request: Request,
    file: UploadFile = File(...),
    type: str = Form(...),
):
    if type not in ("design", "topo"):
        raise HTTPException(400, "type must be 'design' or 'topo'")
    filename = file.filename or "surface.dxf"
    if Path(filename).suffix.lower() != ".dxf":
        raise HTTPException(400, "A .dxf file is required")
    fd, tmp = dxf_uploads.create_temp_file()
    size = 0
    try:
        with os.fdopen(fd, "wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > DEFAULTS.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, f"Upload exceeds the {DEFAULTS.max_upload_mb} MiB request limit")
                target.write(chunk)
        if size == 0:
            raise HTTPException(400, "Empty file")
        from core import inspect_dxf_surface
        inspection = await asyncio.to_thread(dxf_uploads.parse_dxf, inspect_dxf_surface, tmp)
        session_id = await run_db(db.get_or_create_session, get_session_id(request))
        try:
            upload = dxf_uploads.store(tmp, session_id, filename, type, size)
        except ValueError as exc:
            raise HTTPException(429, str(exc)) from exc
        tmp = ""
        return {**inspection, **upload}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, str(exc))
    finally:
        await file.close()
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


@router.post("/dxf/confirm")
async def confirm_dxf(request: Request, body: DxfImportConfirmation):
    session_id = request.state.session_id
    pending = dxf_uploads.claim(body.upload_id, session_id)
    if pending is None:
        raise HTTPException(404, "DXF upload not found or expired")
    try:
        from core import get_mesh_bounds, import_dxf_surface
        mesh, report = await asyncio.to_thread(
            dxf_uploads.parse_dxf,
            import_dxf_surface,
            pending["path"],
            layers=body.layers,
            units=body.units,
        )
        raw_bounds = get_mesh_bounds(mesh)
        clean_bounds = {key: raw_bounds[key] for key in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")}
        other_type = "topo" if pending["type"] == "design" else "design"
        other_mesh = await run_db(db.get_mesh, session_id, other_type)
        if other_mesh is not None:
            other_bounds = other_mesh["bounds"]
            overlaps_xy = not (
                clean_bounds["xmax"] < other_bounds["xmin"]
                or other_bounds["xmax"] < clean_bounds["xmin"]
                or clean_bounds["ymax"] < other_bounds["ymin"]
                or other_bounds["ymax"] < clean_bounds["ymin"]
            )
            if not overlaps_xy:
                report["warnings"] = sorted(set(report.get("warnings", [])) | {"SURFACES_NO_XY_OVERLAP"})
        with open(pending["path"], "rb") as source:
            content = source.read()
        mesh_id = await run_db(
            db.save_mesh,
            session_id=session_id,
            mesh_type=pending["type"],
            filename=pending["filename"],
            data=content,
            n_vertices=len(mesh.vertices),
            n_faces=len(mesh.faces),
            bounds=clean_bounds,
            import_options={"layers": body.layers, "units": body.units},
            import_report=report,
        )
        consumed = dxf_uploads.take(body.upload_id, session_id)
        if consumed:
            os.unlink(consumed["path"])
        return {
            "mesh_id": mesh_id,
            "n_vertices": len(mesh.vertices),
            "n_faces": len(mesh.faces),
            "bounds": clean_bounds,
            "import_report": report,
        }
    except HTTPException:
        dxf_uploads.release(body.upload_id, session_id)
        raise
    except Exception as exc:
        dxf_uploads.release(body.upload_id, session_id)
        raise HTTPException(422, str(exc))


@router.delete("/dxf/{upload_id}")
async def cancel_dxf(request: Request, upload_id: str):
    if not dxf_uploads.cancel(upload_id, request.state.session_id):
        raise HTTPException(404, "DXF upload not found or expired")
    return {"success": True}


@router.get("/{mesh_id}/info")
async def mesh_info(request: Request, mesh_id: str):
    """Return summary information for a stored mesh."""
    session_id = get_session_id(request)
    mesh = await run_db(db.get_mesh_by_id, mesh_id)
    if mesh is None:
        raise HTTPException(404, "Mesh not found")
    return {
        "id": mesh["id"],
        "type": mesh["type"],
        "filename": mesh["filename"],
        "n_vertices": mesh["n_vertices"],
        "n_faces": mesh["n_faces"],
        "bounds": mesh["bounds"],
        "uploaded_at": mesh["uploaded_at"],
        "import_report": mesh.get("import_report"),
    }


@functools.lru_cache(maxsize=16)
def _get_decimated_vertices_cached(mesh_id: str, step: int) -> dict:
    tmesh = db.get_trimesh_by_id(mesh_id)

    from core.mesh_handler import decimate_mesh
    if len(tmesh.faces) > 0:
        dec = decimate_mesh(tmesh, step)
        verts = dec.vertices
        faces = dec.faces
    else:
        verts = tmesh.vertices
        stride = max(1, len(verts) // step)
        verts = verts[::stride]
        faces = []

    return {
        "x": verts[:, 0].tolist(),
        "y": verts[:, 1].tolist(),
        "z": verts[:, 2].tolist(),
        "faces": faces.tolist() if len(faces) > 0 else [],
    }


def _vertices_payload(mesh: trimesh.Trimesh) -> dict:
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)
    return {
        "x": vertices[:, 0].tolist(),
        "y": vertices[:, 1].tolist(),
        "z": vertices[:, 2].tolist(),
        "faces": faces.tolist() if len(faces) else [],
    }


def _crop_mesh_to_xy_bounds(
    mesh: trimesh.Trimesh,
    bounds: tuple[float, float, float, float],
) -> trimesh.Trimesh:
    xmin, ymin, xmax, ymax = bounds
    vertices = np.asarray(mesh.vertices)
    source_faces = np.asarray(mesh.faces)
    selected_faces: list[np.ndarray] = []
    chunk_size = 250000
    for start in range(0, len(source_faces), chunk_size):
        chunk = source_faces[start:start + chunk_size]
        triangles = vertices[chunk]
        keep = (
            (triangles[:, :, 0].max(axis=1) >= xmin)
            & (triangles[:, :, 0].min(axis=1) <= xmax)
            & (triangles[:, :, 1].max(axis=1) >= ymin)
            & (triangles[:, :, 1].min(axis=1) <= ymax)
        )
        if np.any(keep):
            selected_faces.append(chunk[keep])
    if not selected_faces:
        return trimesh.Trimesh(
            vertices=np.empty((0, 3), dtype=vertices.dtype),
            faces=np.empty((0, 3), dtype=source_faces.dtype),
            process=False,
        )
    faces = np.concatenate(selected_faces, axis=0)
    used_vertices, inverse = np.unique(faces, return_inverse=True)
    return trimesh.Trimesh(
        vertices=vertices[used_vertices],
        faces=inverse.reshape((-1, 3)),
        process=False,
    )


@functools.lru_cache(maxsize=2)
def _get_roi_vertices_cached(
    session_id: str,
    mesh_id: str,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    step: int,
) -> dict:
    mesh = db.get_trimesh_by_id(mesh_id)
    mesh_extents = np.asarray(mesh.bounds[1] - mesh.bounds[0], dtype=float)
    max_width = max(4.0 * float(mesh_extents[0]), 1.0)
    max_height = max(4.0 * float(mesh_extents[1]), 1.0)
    if xmax - xmin > max_width or ymax - ymin > max_height:
        raise ValueError("ROI bounds are too large for the mesh extent")
    cropped = _crop_mesh_to_xy_bounds(mesh, (xmin, ymin, xmax, ymax))
    if len(cropped.faces) > step:
        from core.mesh_handler import decimate_mesh
        cropped = decimate_mesh(cropped, step)
    return _vertices_payload(cropped)


@functools.lru_cache(maxsize=16)
def _get_contours_cached(mesh_id: str, interval: float, grid_size: int) -> dict:
    tmesh = db.get_trimesh_by_id(mesh_id)
    z_min, z_max = tmesh.bounds[0][2], tmesh.bounds[1][2]

    # Round to nearest interval
    levels = np.arange(
        np.floor(z_min / interval) * interval, z_max + interval, interval
    )

    contour_lines: list[dict] = []

    # We use exact trimesh sectioning instead of griddata interpolation!
    # This prevents staircases and produces geometrically perfect contours.
    for z in levels:
        slice_path = tmesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if slice_path is not None:
            segs = []
            # slice_path.discrete gives ordered polylines (requires networkx)
            for poly in slice_path.discrete:
                if len(poly) < 2:
                    continue
                poly_2d = [[float(v[0]), float(v[1])] for v in poly]
                segs.append(poly_2d)

            if segs:
                contour_lines.append({
                    "elevation": float(z),
                    "segments": segs
                })

    bounds = {
        "xmin": float(tmesh.bounds[0][0]),
        "xmax": float(tmesh.bounds[1][0]),
        "ymin": float(tmesh.bounds[0][1]),
        "ymax": float(tmesh.bounds[1][1]),
        "zmin": float(tmesh.bounds[0][2]),
        "zmax": float(tmesh.bounds[1][2]),
    }

    return {
        "bounds": bounds,
        "elevation_min": z_min,
        "elevation_max": z_max,
        "interval": interval,
        "lines": contour_lines,
    }


@router.get("/{mesh_id}/vertices")
async def mesh_vertices(request: Request, mesh_id: str, step: int = 8000):
    """
    Return decimated mesh vertices and faces for 3D visualization.

    ``step`` is the *maximum number of faces/points* to return (default 8000).
    """
    try:
        return await run_db(_get_decimated_vertices_cached, mesh_id, step)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/{mesh_id}/vertices/roi")
async def mesh_vertices_roi(
    request: Request,
    mesh_id: str,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    step: int = 60000,
):
    if not all(math.isfinite(value) for value in (xmin, ymin, xmax, ymax)):
        raise HTTPException(422, "ROI bounds must be finite")
    if xmin >= xmax or ymin >= ymax:
        raise HTTPException(422, "ROI minimum bounds must be below maximum bounds")
    if not 1000 <= step <= 75000:
        raise HTTPException(422, "step must be between 1000 and 75000 faces")
    session_id = get_session_id(request)
    session_meshes = await run_db(db.get_all_meshes, session_id)
    if not any(mesh["id"] == mesh_id for mesh in session_meshes):
        raise HTTPException(404, "Mesh not found")
    cache_bounds = tuple(round(value, 2) for value in (xmin, ymin, xmax, ymax))
    try:
        return await run_db(
            _get_roi_vertices_cached,
            session_id,
            mesh_id,
            *cache_bounds,
            step,
        )
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(404, "Mesh not found") from exc
        raise HTTPException(422, str(exc)) from exc


@router.get("/{topo_id}/horizontal-deviation")
async def mesh_horizontal_deviation(
    request: Request,
    topo_id: str,
    design_mesh_id: str,
    sector: Optional[str] = None,
    bench_num: Optional[int] = None,
    longitudinal_step: float = 2.0,
    vertical_step: float = 1.0,
):
    """Return a signed equal-elevation horizontal-deviation patch."""
    if bench_num is not None and bench_num < 1:
        raise HTTPException(422, "bench_num must be a positive design bench number")
    if not 0.5 <= longitudinal_step <= 20.0:
        raise HTTPException(422, "longitudinal_step must be between 0.5 and 20 metres")
    if not 0.25 <= vertical_step <= 5.0:
        raise HTTPException(422, "vertical_step must be between 0.25 and 5 metres")

    session_id = request.state.session_id
    mesh_rows = await run_db(db.get_all_meshes, session_id)
    mesh_by_id = {row["id"]: row for row in mesh_rows}
    topo_info = mesh_by_id.get(topo_id)
    design_info = mesh_by_id.get(design_mesh_id)
    if topo_info is None or design_info is None:
        raise HTTPException(404, "Mesh not found in this session")
    if topo_info.get("type") != "topo" or design_info.get("type") != "design":
        raise HTTPException(404, "Mesh not found in this session")

    sections = await run_db(db.get_sections, session_id)
    if not sections:
        raise HTTPException(422, "insufficient_sections: configure at least two sections in one sector before requesting the 3D comparison")
    sector_names = list(dict.fromkeys(str(row.get("sector", "")) for row in sections))
    if sector is None:
        if len(sector_names) == 1:
            sector = sector_names[0]
        else:
            raise HTTPException(422, "sector_required: select a sector to build the 3D comparison")
    sector = str(sector).strip()
    sector_sections = [row for row in sections if str(row.get("sector", "")) == sector]
    if len(sector_sections) < 2:
        raise HTTPException(422, f"insufficient_sections: sector '{sector}' needs at least two configured sections for the 3D comparison")

    stored_settings = await run_db(db.get_settings, session_id)
    process_settings = (stored_settings or {}).get("process", {})
    detection_options = vars(DETECTION).copy()
    setting_map = {
        "resolution": "profile_resolution",
        "face_threshold": "face_threshold",
        "berm_threshold": "berm_threshold",
        "max_berm_width": "max_berm_width",
        "max_single_bench_width": "max_single_bench_width",
    }
    for setting_key, option_key in setting_map.items():
        if setting_key in process_settings:
            value = _finite_float(process_settings[setting_key], math.nan)
            if not math.isfinite(value) or value <= 0:
                raise HTTPException(422, f"invalid_detection_setting: {setting_key}")
            detection_options[option_key] = value

    config_payload = json.dumps({
        "detection": detection_options,
        "horizontal_deviation": vars(HORIZONTAL_DEVIATION),
    }, sort_keys=True, separators=(",", ":"))
    try:
        return await run_db(
            _build_horizontal_deviation_cached,
            topo_id,
            design_mesh_id,
            json.dumps(sections, sort_keys=True, separators=(",", ":")),
            sector,
            bench_num,
            float(longitudinal_step),
            float(vertical_step),
            config_payload,
        )
    except OverflowError as exc:
        raise HTTPException(413, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Unable to calculate horizontal deviation: {exc}")


@router.delete("/{mesh_id}")
async def delete_mesh(request: Request, mesh_id: str):
    """Delete a stored mesh."""
    deleted = await run_db(db.delete_mesh, mesh_id)
    if not deleted:
        raise HTTPException(404, "Mesh not found")
    return {"message": "Mesh deleted"}


@router.get("/{mesh_id}/contours")
async def mesh_contours(
    request: Request,
    mesh_id: str,
    interval: float = 15.0,
    grid_size: int = 1500,
):
    """
    Return contour/isoline data for a mesh.

    ``interval`` is the elevation step between contour lines (default 15 m).
    ``grid_size`` controls the interpolation resolution (default 400×400).

    Returns contour line segments grouped by elevation level, suitable for
    rendering with Chart.js or any line chart library.
    """
    try:
        return await run_db(_get_contours_cached, mesh_id, interval, grid_size)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@functools.lru_cache(maxsize=16)
def _get_breaklines_cached(mesh_id: str, angle_threshold: float) -> dict:
    from core.breaklines import extract_breaklines
    tmesh = db.get_trimesh_by_id(mesh_id)

    # Extract breaklines
    result = extract_breaklines(tmesh, angle_threshold_deg=angle_threshold)

    contour_lines = []
    if result["crests"]:
        contour_lines.append({
            "elevation": 1.0,
            "type": "crest",
            "segments": result["crests"]
        })
    if result["toes"]:
        contour_lines.append({
            "elevation": -1.0,
            "type": "toe",
            "segments": result["toes"]
        })

    bounds = {
        "xmin": float(tmesh.bounds[0][0]),
        "xmax": float(tmesh.bounds[1][0]),
        "ymin": float(tmesh.bounds[0][1]),
        "ymax": float(tmesh.bounds[1][1]),
        "zmin": float(tmesh.bounds[0][2]),
        "zmax": float(tmesh.bounds[1][2]),
    }

    return {
        "bounds": bounds,
        "elevation_min": bounds["zmin"],
        "elevation_max": bounds["zmax"],
        "interval": 0,
        "lines": contour_lines,
    }


@router.get("/{mesh_id}/breaklines")
async def mesh_breaklines(
    request: Request,
    mesh_id: str,
    angle_threshold: float = 20.0,
):
    """
    Return analytic structural breaklines (crests, toes) extracted from the mesh dihedral angles.
    """
    try:
        return await run_db(_get_breaklines_cached, mesh_id, angle_threshold)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
