"""DXF surface inspection and import."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import trimesh


IMPORTER_VERSION = "1.0.0"
MAX_INSERT_DEPTH = 16
MAX_EXPANDED_ENTITIES = 2_000_000
_SUPPORTED_UNITS = set(range(1, 25))
MAX_SURFACE_FACES = 2_000_000


def _read_document(filepath: str):
    try:
        import ezdxf
    except ImportError as exc:
        raise ImportError("ezdxf is required for loading DXF files. Install it with `pip install ezdxf`.") from exc
    try:
        return ezdxf.readfile(filepath)
    except Exception as exc:
        raise ValueError(f"No se pudo leer el archivo DXF: {exc}") from exc


def _entity_layer(entity: Any, inherited: str | None = None) -> str:
    layer = str(entity.dxf.get("layer", "0"))
    return inherited if layer.casefold() == "0" and inherited else layer


def _has_clip(insert: Any) -> bool:
    try:
        from ezdxf.xclip import XClip

        if XClip(insert).has_clipping_path:
            return True
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    try:
        return insert.has_extension_dict and insert.get_extension_dict().get("ACAD_FILTER") is not None
    except (AttributeError, TypeError):
        return False


def _surface_faces(doc: Any, *, max_depth: int = MAX_INSERT_DEPTH):
    counts: Counter[str] = Counter()
    layer_data: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    expanded = 0
    surface_face_count = 0

    def record_skipped(entity: Any, reason: str) -> None:
        kind = entity.dxftype()
        warnings.append(f"INSERT_ENTITY_SKIPPED_{kind}")
        if kind in {"3DFACE", "MESH", "ACAD_PROXY_ENTITY"} or (kind == "POLYLINE" and (entity.is_poly_face_mesh or entity.is_polygon_mesh)):
            raise ValueError(f"DXF_TRANSFORM_UNSUPPORTED: no se pudo transformar una entidad de superficie {kind}: {reason}")

    def add_polygon(layer: str, coords: Any, entity_type: str) -> None:
        nonlocal surface_face_count
        if surface_face_count >= MAX_SURFACE_FACES:
            raise ValueError("DXF_FACE_LIMIT_EXCEEDED: el archivo excede el límite de caras de superficie.")
        points = np.asarray(coords, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3:
            warnings.append("INVALID_FACE")
            return
        if not np.isfinite(points).all():
            warnings.append("NONFINITE_COORDINATES")
            return
        layer_data.setdefault(layer, {"polygons": [], "vertices": [], "counts": Counter()})
        layer_data[layer]["polygons"].append(points)
        layer_data[layer]["vertices"].extend(points)
        layer_data[layer]["counts"][entity_type] += 1
        surface_face_count += 1

    def visit(entities: Any, inherited: str | None, stack: tuple[str, ...], depth: int) -> None:
        nonlocal expanded
        if depth > max_depth:
            raise ValueError("DXF_INSERT_DEPTH_EXCEEDED: bloques anidados exceden el límite permitido.")
        for entity in entities:
            expanded += 1
            if expanded > MAX_EXPANDED_ENTITIES:
                raise ValueError("DXF_ENTITY_LIMIT_EXCEEDED: expansión de entidades excede el límite permitido.")
            kind = entity.dxftype()
            layer = _entity_layer(entity, inherited)
            counts[kind] += 1
            if kind == "INSERT":
                if _has_clip(entity):
                    raise ValueError("DXF_XCLIP_UNSUPPORTED: no se puede resolver el recorte XCLIP del bloque.")
                name = entity.dxf.name
                key = name.casefold()
                if key in stack:
                    raise ValueError("DXF_BLOCK_CYCLE: se detectó una referencia cíclica entre bloques.")
                block = doc.blocks.get(name)
                if block is None:
                    raise ValueError(f"DXF_MISSING_BLOCK: no se encontró la definición del bloque '{name}'.")
                try:
                    rows = int(entity.dxf.get("row_count", 1))
                    columns = int(entity.dxf.get("column_count", 1))
                    if rows < 1 or columns < 1 or rows * columns > MAX_EXPANDED_ENTITIES - expanded:
                        raise ValueError("DXF_ENTITY_LIMIT_EXCEEDED: matriz INSERT excede el límite de expansión.")
                    instances = entity.multi_insert() if rows > 1 or columns > 1 else iter((entity,))
                    def virtual_entities():
                        for instance in instances:
                            yield from instance.virtual_entities(skipped_entity_callback=record_skipped)
                except Exception as exc:
                    if str(exc).startswith("DXF_ENTITY_LIMIT_EXCEEDED"):
                        raise
                    raise ValueError(f"DXF_TRANSFORM_UNSUPPORTED: no se pudo transformar el bloque '{name}': {exc}") from exc
                visit(virtual_entities(), layer, stack + (key,), depth + 1)
                continue
            if kind == "3DFACE":
                raw = [np.asarray(entity.dxf.get(f"vtx{i}"), dtype=np.float64) for i in range(4)]
                points = raw[:3] if np.array_equal(raw[2], raw[3]) else raw
                add_polygon(layer, points, kind)
            elif kind == "POLYLINE" and entity.is_poly_face_mesh:
                try:
                    for face in entity.virtual_entities():
                        if face.dxftype() == "3DFACE":
                            raw = [np.asarray(face.dxf.get(f"vtx{i}"), dtype=np.float64) for i in range(4)]
                            points = raw[:3] if np.array_equal(raw[2], raw[3]) else raw
                            add_polygon(layer, points, kind)
                except Exception as exc:
                    raise ValueError(f"DXF_INVALID_POLYFACE: no se pudo interpretar POLYFACE: {exc}") from exc
            elif kind == "MESH":
                try:
                    if int(entity.dxf.get("subdivision_levels", 0)) > 0:
                        warnings.append("UNSUPPORTED_MESH_SUBDIVISION")
                        continue
                    vertices = np.asarray(entity.vertices, dtype=np.float64)
                    faces = entity.faces
                    if len(faces) > MAX_SURFACE_FACES:
                        raise ValueError("DXF_FACE_LIMIT_EXCEEDED: la malla excede el límite de caras.")
                    for face in faces:
                        if len(face) >= 3 and min(face) >= 0 and max(face) < len(vertices):
                            add_polygon(layer, vertices[list(face)], kind)
                        else:
                            warnings.append("INVALID_MESH_INDEX")
                except Exception as exc:
                    if str(exc).startswith("DXF_FACE_LIMIT_EXCEEDED"):
                        raise
                    raise ValueError(f"DXF_INVALID_MESH: no se pudo interpretar una entidad MESH: {exc}") from exc
            elif kind == "POLYLINE" and entity.is_polygon_mesh:
                warnings.append("UNSUPPORTED_POLYMESH")
            elif kind in {"POLYMESH", "SOLID", "BODY", "3DSOLID", "SURFACE", "REGION", "ACAD_PROXY_ENTITY"}:
                warnings.append(f"UNSUPPORTED_{kind}")
    visit(doc.modelspace(), None, (), 0)
    return layer_data, counts, warnings


def _layer_summary(data: dict[str, Any]) -> dict[str, Any]:
    points = np.asarray(data["vertices"], dtype=np.float64)
    bounds = np.column_stack((points.min(axis=0), points.max(axis=0)))
    polygons = data["polygons"]
    return {
        "name": "", "n_faces": sum(max(len(p) - 2, 1) for p in polygons),
        "n_vertices": len(np.unique(points, axis=0)),
        "bounds": {key: float(bounds[i, j]) for i, axis in enumerate("xyz") for j, key in enumerate((f"{axis}min", f"{axis}max"))},
        "entity_counts": dict(data["counts"]),
    }


def inspect_dxf_surface(filepath: str) -> dict[str, Any]:
    doc = _read_document(filepath)
    layers, counts, warnings = _surface_faces(doc)
    summaries = []
    for name, data in sorted(layers.items(), key=lambda item: item[0].casefold()):
        summary = _layer_summary(data)
        summary["name"] = name
        summaries.append(summary)
    declared_units = int(doc.header.get("$INSUNITS", 0) or 0)
    if declared_units not in _SUPPORTED_UNITS:
        warnings.append("UNITS_UNKNOWN" if declared_units == 0 else "UNITS_UNSUPPORTED")
    return {"declared_units": declared_units, "layers": summaries, "entity_counts": dict(counts),
            "warnings": sorted(set(warnings)), "importer_version": IMPORTER_VERSION}


def _triangulate_polygon(points: np.ndarray) -> list[list[int]]:
    points = np.asarray(points, dtype=np.float64)
    if len(points) > 1 and np.array_equal(points[0], points[-1]):
        points = points[:-1]
    if len(points) < 3:
        return []
    keep = [0]
    for i in range(1, len(points)):
        if not np.array_equal(points[i], points[keep[-1]]):
            keep.append(i)
    points = points[keep]
    if len(points) < 3:
        return []
    scale = max(float(np.linalg.norm(np.ptp(points, axis=0))), 1.0)
    if len(points) == 3:
        if not np.isfinite(points).all():
            return []
        area_vector = np.cross(points[1] - points[0], points[2] - points[0])
        return [[keep[0], keep[1], keep[2]]] if np.linalg.norm(area_vector) > scale * scale * 1e-14 else []
    centered = points - points[0]
    _, singular, vh = np.linalg.svd(centered, full_matrices=False)
    if len(singular) < 2 or singular[1] <= scale * 1e-12:
        return []
    normal = vh[-1]
    if np.max(np.abs(centered @ normal)) > scale * 1e-8:
        raise ValueError("DXF_NONPLANAR_POLYGON: polígono no plano; exporte la superficie triangulada.")
    axis = int(np.argmax(np.abs(normal)))
    projected = np.delete(points, axis, axis=1)
    projected = projected - projected[0]
    eps = scale * scale * 1e-14
    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    def intersects(a, b, c, d):
        ab_c = cross(a, b, c)
        ab_d = cross(a, b, d)
        cd_a = cross(c, d, a)
        cd_b = cross(c, d, b)
        return ab_c * ab_d < -eps and cd_a * cd_b < -eps
    for i in range(len(projected)):
        for j in range(i + 1, len(projected)):
            if j in (i, (i + 1) % len(projected)) or (j + 1) % len(projected) in (i, (i + 1) % len(projected)):
                continue
            if intersects(projected[i], projected[(i + 1) % len(projected)], projected[j], projected[(j + 1) % len(projected)]):
                raise ValueError("DXF_AMBIGUOUS_POLYGON: polígono autointersectado; exporte la superficie triangulada.")
    area = sum(projected[i, 0] * projected[(i + 1) % len(points), 1] - projected[(i + 1) % len(points), 0] * projected[i, 1] for i in range(len(points)))
    if abs(area) <= scale * scale * 1e-14:
        return []
    sign = 1.0 if area > 0 else -1.0
    remaining = list(range(len(points)))
    result = []
    while len(remaining) > 3:
        ear = None
        for pos, current in enumerate(remaining):
            prev, nxt = remaining[pos - 1], remaining[(pos + 1) % len(remaining)]
            if sign * cross(projected[prev], projected[current], projected[nxt]) <= eps:
                continue
            inside = False
            for idx in remaining:
                if idx in (prev, current, nxt):
                    continue
                c1 = sign * cross(projected[prev], projected[current], projected[idx])
                c2 = sign * cross(projected[current], projected[nxt], projected[idx])
                c3 = sign * cross(projected[nxt], projected[prev], projected[idx])
                if min(c1, c2, c3) >= -eps:
                    inside = True
                    break
            if not inside:
                ear = (pos, [prev, current, nxt])
                break
        if ear is None:
            raise ValueError("DXF_AMBIGUOUS_POLYGON: no se pudo triangular el polígono sin alterar su forma.")
        result.append([keep[i] for i in ear[1]])
        remaining.pop(ear[0])
    result.append([keep[i] for i in remaining])
    return result


def import_dxf_surface(filepath: str, *, layers: list[str] | None = None, units: int | None = None) -> tuple[trimesh.Trimesh, dict[str, Any]]:
    doc = _read_document(filepath)
    layer_data, counts, warnings = _surface_faces(doc)
    if "UNSUPPORTED_MESH_SUBDIVISION" in warnings:
        raise ValueError("DXF_MESH_SUBDIVISION_UNSUPPORTED: se requiere la superficie MESH subdividida, no su jaula de control.")
    selected = list(layer_data) if layers is None else list(layers)
    missing = [name for name in selected if name not in layer_data]
    if missing:
        raise ValueError(f"DXF_LAYER_EMPTY: las capas seleccionadas no contienen caras: {', '.join(missing)}")
    if not selected:
        raise ValueError("DXF_NO_SURFACE: no se encontraron caras de superficie compatibles en el DXF.")
    declared = int(doc.header.get("$INSUNITS", 0) or 0)
    if units is not None and units not in _SUPPORTED_UNITS:
        raise ValueError(f"DXF_UNITS_UNSUPPORTED: código de unidades no compatible: {units}")
    if units is None:
        factor = 1.0
    elif units in {21, 22, 23, 24}:
        survey_foot = 1200 / 3937
        factor = {21: survey_foot, 22: survey_foot / 12, 23: survey_foot * 3, 24: survey_foot * 5280}[units]
    else:
        from ezdxf.units import conversion_factor

        factor = float(conversion_factor(units, 6))
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    discarded = sum(warnings.count(code) for code in (
        "INVALID_FACE", "NONFINITE_COORDINATES", "INVALID_POLYFACE_INDEX", "INVALID_MESH_INDEX"
    ))
    for name in selected:
        for polygon in layer_data[name]["polygons"]:
            triangles = _triangulate_polygon(polygon)
            if not triangles:
                discarded += 1
                continue
            offset = len(vertices)
            vertices.extend(polygon.tolist())
            faces.extend([[offset + i for i in tri] for tri in triangles])
    if not faces:
        raise ValueError("DXF_NO_VALID_FACES: no quedaron caras válidas después de validar la geometría.")
    vertices_array = np.asarray(vertices, dtype=np.float64) * factor
    faces_array = np.asarray(faces, dtype=np.int64)
    unique_vertices, inverse = np.unique(vertices_array, axis=0, return_inverse=True)
    faces_array = inverse[faces_array]
    valid = ((faces_array[:, 0] != faces_array[:, 1]) &
             (faces_array[:, 1] != faces_array[:, 2]) &
             (faces_array[:, 2] != faces_array[:, 0]))
    discarded += int(len(faces_array) - np.count_nonzero(valid))
    faces_array = faces_array[valid]
    sorted_faces = np.sort(faces_array, axis=1)
    _, unique_indices = np.unique(sorted_faces, axis=0, return_index=True)
    discarded += int(len(faces_array) - len(unique_indices))
    faces_array = faces_array[np.sort(unique_indices)]
    if discarded:
        warnings.append("DISCARDED_FACES")
    if not len(faces_array):
        raise ValueError("DXF_NO_VALID_FACES: no quedaron caras válidas después de validar la geometría.")
    used = np.unique(faces_array)
    remap = np.full(len(unique_vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    mesh = trimesh.Trimesh(vertices=unique_vertices[used], faces=remap[faces_array], process=False)
    report = {"selected_layers": selected, "declared_units": declared, "confirmed_units": units,
              "scale_factor": factor, "importer_version": IMPORTER_VERSION,
              "entity_counts": dict(counts), "warnings": sorted(set(warnings)), "discarded_faces": discarded}
    return mesh, report
