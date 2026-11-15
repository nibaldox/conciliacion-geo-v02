"""Section images ZIP for the web export, built from the shared ``ReportData``.

One cropped profile per filtered section in the defined order, the plan view,
the status matrix and a ``LEEME.txt`` stating the scope of the export.
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from core.report_charts import STATUS_LABELS_ES
from core.report_data import ReportData
from core.report_figures_analysis import status_matrix_png
from core.report_figures_plan import dashboard_plan_png
from core.report_figures_profile import cropped_profile_png
from core.report_surface import plan_surface_from_mesh, sections_bounds, shaded_relief

logger = logging.getLogger(__name__)

PROFILE_WIDTH_IN = 8.0
PROFILE_HEIGHT_IN = 5.0
PROFILE_DPI = 150
README_NAME = "LEEME.txt"
PLAN_NAME = "plano.png"
MATRIX_NAME = "matriz.png"
FALLBACK_SECTION_NAME = "seccion"
MAX_NAME_LENGTH = 80

_UNSAFE_CHARS = re.compile(r"[^\w.\-]+", re.UNICODE)
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_NOT_RENDERED = "no generado"

OFFICIAL_VALUES_LINE = (
    "Solo valores oficiales: los estados y las desviaciones provienen de la conciliación "
    "oficial; la medición guiada o propuesta no se incluye."
)
NOMINAL_LEVEL_LINE = (
    "Cota nominal: las cotas de pata cercanas se agrupan por sector en una cota nominal; "
    "los grupos se separan donde el salto entre cotas consecutivas es ≥ ⅓ de la altura de "
    "banco de diseño (mediana del sector) y dos bancos de una misma sección nunca comparten "
    "cota nominal."
)
CROP_LINE = (
    "Con filtro de cota, cada perfil se recorta a los bancos seleccionados: ±10 m en "
    "distancia y ± media altura de banco de diseño en cota, a escala 1:1."
)


def _safe_name(value: Any) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", str(value if value is not None else "")).strip("._")
    return cleaned[:MAX_NAME_LENGTH].strip("._") or FALLBACK_SECTION_NAME


def _zip_date(meta: Mapping[str, Any]) -> tuple[int, int, int, int, int, int]:
    try:
        stamp = datetime.fromisoformat(str(meta.get("generated_at")))
    except (TypeError, ValueError):
        return _ZIP_EPOCH
    if not 1980 <= stamp.year <= 2107:
        return _ZIP_EPOCH
    return (stamp.year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)


def _entry_field(entry: Any, name: str) -> Any:
    return entry.get(name) if isinstance(entry, Mapping) else None


def _profile_statuses(data: ReportData) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    by_identity: dict[tuple[str, str], str] = {}
    by_name: dict[str, str] = {}
    for profile in data.profiles:
        by_identity.setdefault((profile.section, profile.sector or ""), profile.worst_status)
        by_name.setdefault(profile.section, profile.worst_status)
    return by_identity, by_name


def _plan_backdrop(plan_inputs: Mapping[str, Any], sections: Sequence[Any]):
    mesh = plan_inputs.get("mesh_topo")
    if mesh is None:
        return None, None
    try:
        surface = plan_surface_from_mesh(mesh, bounds=sections_bounds(sections))
        shade = shaded_relief(surface) if surface is not None else None
    except Exception:
        logger.exception("Plan surface backdrop failed; rendering the plan without relief")
        return None, None
    if surface is None:
        return None, None
    return surface, shade


def _plan_png(data: ReportData) -> Optional[bytes]:
    plan_inputs = data.plan_inputs
    if not isinstance(plan_inputs, Mapping):
        return None
    from core.web_pdf_report import _plan_sections, _plan_statuses
    sections = _plan_sections(data)
    if not sections:
        return None
    surface, shade = _plan_backdrop(plan_inputs, sections)
    statuses = _plan_statuses(sections)
    try:
        return dashboard_plan_png(sections, statuses, shade=shade, surface=surface)
    except Exception:
        logger.exception("Plan view render failed")
        return None


def _matrix_png(data: ReportData) -> Optional[bytes]:
    try:
        return status_matrix_png(data.matrix)
    except Exception:
        logger.exception("Status matrix render failed")
        return None


def _sector_label(sector: Any) -> str:
    name = str(sector).strip() if sector is not None else ""
    return f"Sector {name}" if name else "Secciones sin sector"


def _levels_text(levels: Sequence[Any]) -> str:
    labels = [str(level) for level in levels]
    if not labels:
        return "todas las cotas"
    return ("cota " if len(labels) == 1 else "cotas ") + ", ".join(labels)


def _filter_lines(data: ReportData) -> list[str]:
    filters = data.filters
    if filters.is_empty():
        lines = ["Sin filtros: se exportan todas las secciones con resultados."]
    else:
        parts = []
        if filters.sectors:
            parts.append("Sectores: " + ", ".join(str(item) for item in filters.sectors))
        if filters.sections:
            parts.append("Secciones: " + ", ".join(str(item) for item in filters.sections))
        if filters.levels:
            parts.append("Cotas: " + ", ".join(str(item) for item in filters.levels))
        if filters.benches:
            parts.append("Bancos: " + ", ".join(str(item) for item in filters.benches))
        lines = ["Filtros aplicados. " + "; ".join(parts) if parts else "Filtros aplicados."]
    for summary in data.sector_summaries:
        lines.append(
            f"{_sector_label(summary.get('sector'))}: {_levels_text(summary.get('levels') or ())}"
        )
    return lines


def _readme_text(
    data: ReportData,
    members: Sequence[tuple[str, str]],
    without_profile: Sequence[str],
    extras: Mapping[str, bool],
) -> str:
    meta = data.meta or {}
    lines = ["Conciliación geotécnica: imágenes de secciones"]
    for label, key in (
        ("Proyecto", "project"), ("Operación", "operation"), ("Fase", "phase"),
        ("Autor", "author"), ("Generado", "generated_at"),
    ):
        value = str(meta.get(key) or "").strip()
        if value:
            if key == "generated_at":
                try:
                    value = datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
                except ValueError:
                    pass
            lines.append(f"{label}: {value}")

    lines += ["", "Alcance"]
    scope = [OFFICIAL_VALUES_LINE, *_filter_lines(data), NOMINAL_LEVEL_LINE]
    if any(_entry_field(entry, "view_window") is not None for entry in data.section_geometry):
        scope.append(CROP_LINE)
    scope.extend(str(warning) for warning in data.level_warnings)
    for entry in data.section_geometry:
        scope.extend(str(warning) for warning in _entry_field(entry, "warnings") or ())
    lines += [f"- {line}" for line in scope]

    lines += ["", "Contenido"]
    descriptions = {
        PLAN_NAME: "vista en planta con las secciones en color de estado",
        MATRIX_NAME: "matriz de estado por sección y cota nominal",
    }
    for name, description in descriptions.items():
        lines.append(f"- {name}: {description if extras.get(name) else _NOT_RENDERED}")
    lines += [f"- {name}: {description}" for name, description in members]
    lines.append(f"- Perfiles exportados: {len(members)} de {len(data.section_geometry)}")

    if without_profile:
        lines += ["", "Secciones sin perfil"]
        lines += [f"- {label}: sin perfil" for label in without_profile]
    return "\n".join(lines) + "\n"


def _section_label(name: str, sector: str) -> str:
    return f"Sección {name} · {_sector_label(sector)}" if sector else f"Sección {name}"


def build_images_zip(data: ReportData) -> io.BytesIO:
    """Build the images ZIP of the filtered report.

    Members, in order: ``LEEME.txt``, ``plano.png`` and ``matriz.png`` when
    they render, then ``<NN>_<section>.png`` for every entry of
    ``data.section_geometry`` in its defined order (NN is the entry position).
    Sections whose profile cannot be drawn are listed in ``LEEME.txt``.
    """
    by_identity, by_name = _profile_statuses(data)
    total = len(data.section_geometry)
    digits = max(2, len(str(total)))

    profiles: list[tuple[str, bytes]] = []
    described: list[tuple[str, str]] = []
    without_profile: list[str] = []
    for position, entry in enumerate(data.section_geometry, start=1):
        name = str(_entry_field(entry, "section_name") or "")
        sector = str(_entry_field(entry, "sector") or "")
        status = by_identity.get((name, sector)) or by_name.get(name)
        try:
            png = cropped_profile_png(
                entry, status=status, width_in=PROFILE_WIDTH_IN,
                height_in=PROFILE_HEIGHT_IN, dpi=PROFILE_DPI,
            )
        except Exception:
            logger.exception("Profile render failed for section %r", name)
            png = None
        label = _section_label(name, sector)
        if not png:
            without_profile.append(label)
            continue
        member = f"{position:0{digits}d}_{_safe_name(name)}.png"
        profiles.append((member, png))
        status_text = STATUS_LABELS_ES.get(status or "", "") if status else ""
        described.append((member, f"{label} · {status_text}" if status_text else label))

    extras = {PLAN_NAME: _plan_png(data), MATRIX_NAME: _matrix_png(data)}
    readme = _readme_text(
        data, described, without_profile, {name: bool(png) for name, png in extras.items()}
    )

    date_time = _zip_date(data.meta or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        def write(name: str, payload: bytes) -> None:
            info = zipfile.ZipInfo(name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, payload)

        write(README_NAME, readme.encode("utf-8"))
        for name, png in extras.items():
            if png:
                write(name, png)
        for name, png in profiles:
            write(name, png)
    buffer.seek(0)
    return buffer


__all__ = ["build_images_zip"]
