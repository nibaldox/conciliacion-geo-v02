"""
core/pdf_report.py — Unified executive PDF report for geotechnical reconciliation.

Public API
----------
generate_pdf_report(comparisons, all_data, output_path,
                    project_info=None, df_pozos=None, sections=None)

Produces an A4-portrait PDF with five sections:

    1. Portada (cover): title, project, author, date.
    2. Resumen Ejecutivo: global compliance score + per-parameter compliance
       breakdown (CUMPLE / NO CUMPLE) and % de Logro. FUERA DE TOLERANCIA
       from upstream comparison data is merged into NO CUMPLE so the
       report surface is strictly binary.
    3. Profundidad del Rajo: cota piso global, cota cresta global and
       profundidad total, computed from ``bench_real.floor_elevation`` and
       ``bench_real.crest_elevation`` across all MATCH comparisons.
    4. Top 5 Desviaciones: table with the five largest height deviations.
    5. Gráfico de Torta Embebido: compliance donut charts rendered with
       matplotlib → PNG → ``ImageReader`` → embedded in the PDF.

Design notes
------------
* A4 portrait, 2 cm margins. The doc is built with ``SimpleDocTemplate`` and
  the Platypus ``flowables`` pipeline (``Paragraph``, ``Spacer``,
  ``Table``, ``Image``, ``PageBreak``) so it gracefully paginates when
  the project has many sections.
* Chart embedding is rendered locally via ``_binary_compliance_donuts``
  (matplotlib → PNG → ``ImageReader`` → embedded in the PDF) so the
  binary CUMPLE / NO CUMPLE view used by the rest of the report is
  preserved in the chart. matplotlib is forced to the headless ``Agg``
  backend before any pyplot call.
* Defensive: the function tolerates missing fields (``None``, empty
  ``comparisons``, ``df_pozos=None``, no MATCH comps) and substitutes
  safe placeholders instead of raising. This matters because the same
  helper is invoked from the API endpoint where any of these can be empty.

Spanish-only output: every user-facing string is in Spanish, matching the
Word report generator.
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")  # headless backend — required in the API server.
import matplotlib.pyplot as plt  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm, mm  # noqa: E402
from reportlab.lib.utils import ImageReader  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.compliance_status import (
    STATUS_CUMPLE,
    STATUS_NO_CUMPLE,
)


# ---------------------------------------------------------------------------
# Styles & constants
# ---------------------------------------------------------------------------

PAGE_MARGIN = 2 * cm

# Compliance category colours match the donut chart palette so the pie
# embedded in the PDF and the per-row status badge are visually aligned.
# NOTE: Binary compliance (CUMPLE / NO CUMPLE). FUERA DE TOLERANCIA is
# merged into NO CUMPLE for all user-facing surfaces in this report.
COLOR_CUMPLE = colors.HexColor("#7FBF7F")  # soft green
COLOR_NO_CUMPLE = colors.HexColor("#F08C8C")  # soft red
COLOR_HEADER_BG = colors.HexColor("#1F3A5F")  # deep navy
COLOR_ALT_ROW = colors.HexColor("#F2F4F8")  # very light grey

STATUS_COLOR_MAP = {
    STATUS_CUMPLE: COLOR_CUMPLE,
    STATUS_NO_CUMPLE: COLOR_NO_CUMPLE,
}


def _build_styles() -> Dict[str, ParagraphStyle]:
    """Return a small dict of paragraph styles reused across the report."""
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=COLOR_HEADER_BG,
            alignment=1,  # TA_CENTER
            spaceAfter=14,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=15,
            alignment=1,
            spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=COLOR_HEADER_BG,
            spaceBefore=10,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=COLOR_HEADER_BG,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.grey,
        ),
        "cell": ParagraphStyle(
            "Cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=10.5,
        ),
        "cell_bold": ParagraphStyle(
            "CellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10.5,
        ),
        "cell_center": ParagraphStyle(
            "CellCenter",
            parent=base["Normal"],
            alignment=1,
        ),
    }
    return styles


# ---------------------------------------------------------------------------
# Helpers — data shaping
# ---------------------------------------------------------------------------


def _compute_global_score(comparisons: List[Dict[str, Any]]) -> tuple[float, str]:
    """Return ``(score_0_100, status_label)`` for the executive summary.

    Uses ``section_score`` from the first MATCH comparison when available
    (this is the same field the Word report reads). Falls back to a manual
    computation across MATCH comparisons when the field is missing.
    """
    match_comps = [c for c in comparisons if c.get("type") == "MATCH"]
    if not match_comps:
        return 0.0, "SIN DATOS"

    first = match_comps[0]
    if "section_score" in first and first["section_score"] is not None:
        score = float(first["section_score"])
        status = first.get("section_status", STATUS_NO_CUMPLE)
        return score, status

    # Fallback: ratio of CUMPLE statuses across all three parameters.
    keys = ("height_status", "angle_status", "berm_status")
    total = 0
    ok = 0
    for c in match_comps:
        for k in keys:
            if c.get(k) == STATUS_CUMPLE:
                ok += 1
            total += 1
    score = (ok / total * 100) if total else 0.0
    if score >= 90:
        status = STATUS_CUMPLE
    else:
        status = STATUS_NO_CUMPLE
    return score, status


def _compute_depth_metrics(comparisons: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Compute global crest / floor / depth metrics from MATCH comparisons.

    Only ``bench_real`` rows contribute (the as-built side). The floor
    elevation is ignored when non-positive (sentinels from the extractor
    use 0 / -1 when no floor was detected).
    """
    floors: List[float] = []
    crests: List[float] = []
    for c in comparisons:
        br = c.get("bench_real")
        if br is None:
            continue
        fe = getattr(br, "floor_elevation", None)
        ce = getattr(br, "crest_elevation", None)
        if fe is not None and fe > 0:
            floors.append(float(fe))
        if ce is not None:
            crests.append(float(ce))
    if not floors or not crests:
        return {
            "cota_piso": None,
            "cota_cresta": None,
            "profundidad": None,
            "n_floors": len(floors),
            "n_crests": len(crests),
        }
    cota_piso = min(floors)
    cota_cresta = max(crests)
    return {
        "cota_piso": cota_piso,
        "cota_cresta": cota_cresta,
        "profundidad": cota_cresta - cota_piso,
        "n_floors": len(floors),
        "n_crests": len(crests),
    }


def _top5_height_deviations(comparisons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the 5 comparisons with the largest absolute height deviation.

    ``delta`` is ``height_real - height_design``. Comparisons without
    both height fields, or where both are ``None``, are skipped.
    """
    rows: List[Dict[str, Any]] = []
    for c in comparisons:
        hd = c.get("height_design")
        hr = c.get("height_real")
        if hd is None or hr is None:
            continue
        try:
            hd_f = float(hd)
            hr_f = float(hr)
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "section": c.get("section", "N/A"),
                "bench_num": c.get("bench_num", "N/A"),
                "level": c.get("level", "N/A"),
                "height_design": hd_f,
                "height_real": hr_f,
                "delta": hr_f - hd_f,
                "abs_delta": abs(hr_f - hd_f),
                "height_status": c.get("height_status", "N/A"),
            }
        )
    rows.sort(key=lambda r: r["abs_delta"], reverse=True)
    return rows[:5]


def _compliance_breakdown(comparisons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-parameter CUMPLE / NO CUMPLE breakdown over MATCH comps.

    Binary compliance: FUERA DE TOLERANCIA counts roll up into NO CUMPLE
    so the user-facing report only shows two categories.
    """
    match_comps = [c for c in comparisons if c.get("type") == "MATCH"]
    specs = [
        ("height_status", "Altura de Banco", "height_real", "m"),
        ("angle_status", "Ángulo de Cara", "angle_real", "°"),
        ("berm_status", "Ancho de Berma", "berm_real", "m"),
    ]
    out: List[Dict[str, Any]] = []
    for key, label, real_field, unit in specs:
        n_ok = sum(
            1 for c in match_comps if c.get(key) == STATUS_CUMPLE
        )
        # Merge FUERA DE TOLERANCIA into NO CUMPLE for the binary view.
        n_no = sum(
            1 for c in match_comps
            if c.get(key) in (STATUS_NO_CUMPLE, "FUERA DE TOLERANCIA")
        )
        total = n_ok + n_no
        pct = (n_ok / total * 100) if total else 0.0

        real_values = [
            float(c[real_field])
            for c in match_comps
            if c.get(real_field) is not None
        ]
        if real_values:
            avg_val = sum(real_values) / len(real_values)
            avg_str = f"{avg_val:.2f} {unit}"
        else:
            avg_str = "N/A"

        out.append(
            {
                "label": label,
                "ok": n_ok,
                "no_cumple": n_no,
                "total": total,
                "pct": pct,
                "avg_str": avg_str,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Helpers — platypus flowables
# ---------------------------------------------------------------------------


def _header_table(rows: List[List[Any]], col_widths: List[float]) -> Table:
    """Two-column key/value table styled with the brand navy header."""
    table = Table(rows, colWidths=col_widths, hAlign="CENTER")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, COLOR_HEADER_BG),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _depth_table(rows: List[List[Any]], col_widths: List[float]) -> Table:
    """Three-row depth metrics table (métrica / valor)."""
    table = Table(rows, colWidths=col_widths, hAlign="CENTER")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_ALT_ROW]),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_HEADER_BG),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _compliance_table(
    breakdown: List[Dict[str, Any]],
    col_widths: List[float],
    styles: Dict[str, ParagraphStyle],
) -> Table:
    """Per-parameter compliance breakdown table (5 cols, binary)."""
    data: List[List[Any]] = [
        [
            Paragraph("Parámetro", styles["cell_bold"]),
            Paragraph(STATUS_CUMPLE, styles["cell_center"]),
            Paragraph(STATUS_NO_CUMPLE, styles["cell_center"]),
            Paragraph("% Logro", styles["cell_center"]),
            Paragraph("Valor Prom. (Real)", styles["cell_center"]),
        ]
    ]
    for row in breakdown:
        data.append(
            [
                Paragraph(row["label"], styles["cell"]),
                Paragraph(str(row["ok"]), styles["cell_center"]),
                Paragraph(str(row["no_cumple"]), styles["cell_center"]),
                Paragraph(f"{row['pct']:.1f}%", styles["cell_center"]),
                Paragraph(row["avg_str"], styles["cell_center"]),
            ]
        )
    table = Table(data, colWidths=col_widths, hAlign="CENTER")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_ALT_ROW]),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_HEADER_BG),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                # Colour the count columns by category
                ("TEXTCOLOR", (1, 1), (1, -1), COLOR_CUMPLE),
                ("TEXTCOLOR", (2, 1), (2, -1), COLOR_NO_CUMPLE),
            ]
        )
    )
    return table


def _top5_table(
    rows: List[Dict[str, Any]],
    col_widths: List[float],
    styles: Dict[str, ParagraphStyle],
) -> Table:
    """Top-N deviations table."""
    data: List[List[Any]] = [
        [
            Paragraph("#", styles["cell_bold"]),
            Paragraph("Sección", styles["cell_bold"]),
            Paragraph("Banco", styles["cell_bold"]),
            Paragraph("H. Diseño (m)", styles["cell_bold"]),
            Paragraph("H. Real (m)", styles["cell_bold"]),
            Paragraph("Δ (m)", styles["cell_bold"]),
            Paragraph("Estado", styles["cell_bold"]),
        ]
    ]
    if not rows:
        data.append(
            [
                Paragraph("—", styles["cell_center"]),
                Paragraph("Sin datos suficientes", styles["cell"]),
                "",
                "",
                "",
                "",
                "",
            ]
        )
    for idx, r in enumerate(rows, start=1):
        data.append(
            [
                Paragraph(str(idx), styles["cell_center"]),
                Paragraph(str(r["section"]), styles["cell"]),
                Paragraph(f"B{r['bench_num']}", styles["cell_center"]),
                Paragraph(f"{r['height_design']:.2f}", styles["cell_center"]),
                Paragraph(f"{r['height_real']:.2f}", styles["cell_center"]),
                Paragraph(
                    f"{r['delta']:+.2f}",
                    ParagraphStyle(
                        "DeltaCell",
                        parent=styles["cell_center"],
                        textColor=(
                            COLOR_NO_CUMPLE
                            if abs(r["delta"]) >= 1.0
                            else COLOR_CUMPLE
                        ),
                    ),
                ),
                Paragraph(
                    str(r["height_status"]),
                    ParagraphStyle(
                        "StatusCell",
                        parent=styles["cell_center"],
                        textColor=STATUS_COLOR_MAP.get(
                            r["height_status"], colors.black
                        ),
                    ),
                ),
            ]
        )
    table = Table(data, colWidths=col_widths, hAlign="CENTER", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_ALT_ROW]),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_HEADER_BG),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


# ---------------------------------------------------------------------------
# Pie-chart rendering (matplotlib → PNG bytes)
# ---------------------------------------------------------------------------


def _pie_chart_image_bytes(comparisons: List[Dict[str, Any]]) -> Optional[io.BytesIO]:
    """Return the PNG bytes of the compliance donut chart, or ``None``.

    Renders a binary (CUMPLE / NO CUMPLE) donut row — one chart per
    parameter — so the PDF is consistent with the binary compliance view.
    ``FUERA DE TOLERANCIA`` counts are merged into NO CUMPLE inside the
    chart so only two colours appear (green / red). Any exception during
    rendering is swallowed and reported as ``None`` — better a working
    PDF without chart than a 500 from the API.
    """
    return _binary_compliance_donuts(comparisons)


def _binary_compliance_donuts(
    comparisons: List[Dict[str, Any]],
) -> Optional[io.BytesIO]:
    """Render the per-parameter binary compliance donut chart to PNG."""
    try:
        keys = ("height_status", "angle_status", "berm_status")
        titles = ("Altura de Banco", "Ángulo de Cara", "Ancho de Berma")
        category_colors = {
            STATUS_CUMPLE: "#7FBF7F",      # soft green
            STATUS_NO_CUMPLE: "#F08C8C",   # soft red
        }
        category_order = [STATUS_CUMPLE, STATUS_NO_CUMPLE]

        match_comps = [c for c in comparisons if c.get("type") == "MATCH"]
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        for idx, (key, title) in enumerate(zip(keys, titles)):
            ax = axes[idx]
            n_ok = sum(1 for c in match_comps if c.get(key) == STATUS_CUMPLE)
            # Merge FUERA DE TOLERANCIA into NO CUMPLE for the binary view.
            n_no = sum(
                1 for c in match_comps
                if c.get(key) in (STATUS_NO_CUMPLE, "FUERA DE TOLERANCIA")
            )
            counts = {cat: n_ok if cat == STATUS_CUMPLE else n_no
                      for cat in category_order}

            labels_to_show: List[str] = []
            sizes: List[int] = []
            colors_to_show: List[str] = []
            for cat in category_order:
                val = counts[cat]
                if val > 0:
                    labels_to_show.append(f"{cat}\n({val})")
                    sizes.append(val)
                    colors_to_show.append(category_colors[cat])

            if sum(sizes) > 0:
                wedges, _texts, autotexts = ax.pie(
                    sizes,
                    labels=labels_to_show,
                    autopct="%1.1f%%",
                    startangle=90,
                    colors=colors_to_show,
                    wedgeprops={"width": 0.38, "edgecolor": "white",
                                "linewidth": 1.5},
                    textprops={"fontsize": 9, "weight": "bold"},
                )
                for at in autotexts:
                    at.set_color("black")
                    at.set_fontsize(8)

                total = sum(sizes)
                pct = (counts[STATUS_CUMPLE] / total * 100) if total > 0 else 0
                ax.text(
                    0, 0, f"{pct:.0f}%\nLogro",
                    ha="center", va="center",
                    fontsize=10, weight="bold",
                )
                ax.set_title(title, fontsize=11, weight="bold", pad=10)
            else:
                ax.text(0.5, 0.5, "Sin Datos", ha="center", va="center")
                ax.axis("off")

        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        plt.close("all")
        return _fallback_pie_bytes(comparisons)


def _fallback_pie_bytes(comparisons: List[Dict[str, Any]]) -> Optional[io.BytesIO]:
    """Last-resort single-pie chart with binary height-status counts."""
    try:
        match_comps = [c for c in comparisons if c.get("type") == "MATCH"]
        n_ok = sum(
            1 for c in match_comps if c.get("height_status") == STATUS_CUMPLE
        )
        # Merge FUERA DE TOLERANCIA into NO CUMPLE for the binary view.
        n_no = sum(
            1 for c in match_comps
            if c.get("height_status") in (STATUS_NO_CUMPLE, "FUERA DE TOLERANCIA")
        )
        counts = {STATUS_CUMPLE: n_ok, STATUS_NO_CUMPLE: n_no}
        labels = [k for k, v in counts.items() if v > 0]
        sizes = [counts[k] for k in labels]
        colors_map = {
            STATUS_CUMPLE: "#7FBF7F",
            STATUS_NO_CUMPLE: "#F08C8C",
        }
        pie_colors = [colors_map[k] for k in labels]

        fig, ax = plt.subplots(figsize=(8, 4.5))
        if sum(sizes) > 0:
            ax.pie(
                sizes,
                labels=[f"{l}\n({v})" for l, v in zip(labels, sizes)],
                autopct="%1.1f%%",
                colors=pie_colors,
                startangle=90,
            )
        else:
            ax.text(0.5, 0.5, "Sin Datos", ha="center", va="center")
            ax.axis("off")
        ax.set_title("Cumplimiento Global — Altura de Banco", fontsize=11)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        plt.close("all")
        return None


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_cover(
    story: List[Any],
    project_info: Dict[str, Any],
    styles: Dict[str, ParagraphStyle],
) -> None:
    """Append the cover-page flowables to ``story``."""
    # Vertical spacer to push the title roughly into the upper third.
    story.append(Spacer(1, 4 * cm))

    story.append(
        Paragraph("Informe de Conciliación Geotécnica", styles["title"])
    )
    story.append(
        Paragraph(
            "Resultados ejecutivos de cumplimiento entre el diseño y el<br/>"
            "estado as-built de la excavación",
            styles["subtitle"],
        )
    )

    project = project_info.get("project") or "Proyecto no especificado"
    author = project_info.get("author") or "Autor no especificado"
    operation = project_info.get("operation") or "N/A"
    phase = project_info.get("phase") or "N/A"
    date_str = (
        project_info.get("date")
        or datetime.now().strftime("%d/%m/%Y")
    )

    header_rows = [
        ["Proyecto", "Operación", "Fase", "Fecha"],
        [project, operation, phase, date_str],
    ]
    # Slightly wider first column to accommodate long project names.
    story.append(Spacer(1, 1.5 * cm))
    story.append(
        _header_table(
            header_rows,
            col_widths=[5.2 * cm, 4.0 * cm, 4.0 * cm, 3.6 * cm],
        )
    )

    story.append(Spacer(1, 3.0 * cm))
    story.append(
        Paragraph(f"<b>Elaborado por:</b> {author}", styles["body"])
    )
    story.append(
        Paragraph(
            "<i>Documento generado automáticamente por el módulo de "
            "conciliación geotécnica.</i>",
            styles["small"],
        )
    )
    story.append(PageBreak())


def _build_executive_summary(
    story: List[Any],
    comparisons: List[Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
) -> None:
    """Append section 2 (Resumen Ejecutivo)."""
    story.append(Paragraph("2. Resumen Ejecutivo", styles["h1"]))

    if not comparisons:
        story.append(
            Paragraph(
                "No se encontraron comparaciones para reportar.",
                styles["body"],
            )
        )
        return

    match_comps = [c for c in comparisons if c.get("type") == "MATCH"]
    score, status = _compute_global_score(comparisons)

    # Score headline
    headline = (
        f"<b>Cumplimiento General (Ponderado):</b> {score:.0f} / 100 — "
        f'<font color="{STATUS_COLOR_MAP.get(status, colors.black).hexval()}">'
        f"<b>{status}</b></font>"
    )
    story.append(Paragraph(headline, styles["body"]))
    story.append(
        Paragraph(
            f"Se evaluaron <b>{len(match_comps)}</b> bancos emparejados "
            f"sobre un total de <b>{len(comparisons)}</b> comparaciones.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Cumplimiento por parámetro", styles["h2"]))
    breakdown = _compliance_breakdown(comparisons)
    story.append(
        _compliance_table(
            breakdown,
            col_widths=[
                4.5 * cm,
                2.6 * cm,
                3.0 * cm,
                2.4 * cm,
                3.5 * cm,
            ],
            styles=styles,
        )
    )


def _build_depth_section(
    story: List[Any],
    comparisons: List[Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
) -> None:
    """Append section 3 (Profundidad del Rajo)."""
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("3. Profundidad del Rajo", styles["h1"]))

    metrics = _compute_depth_metrics(comparisons)
    if metrics["profundidad"] is None:
        story.append(
            Paragraph(
                "No hay datos suficientes de bancos para calcular la "
                "profundidad total de la excavación.",
                styles["body"],
            )
        )
        return

    rows = [
        ["Métrica", "Valor"],
        ["Cota Piso Global", f"{metrics['cota_piso']:.2f} m"],
        ["Cota Cresta Global", f"{metrics['cota_cresta']:.2f} m"],
        ["Profundidad Total", f"{metrics['profundidad']:.2f} m"],
    ]
    story.append(
        _depth_table(rows, col_widths=[6.5 * cm, 5.0 * cm])
    )
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            f"<i>Calculado a partir de {metrics['n_floors']} cotas de piso y "
            f"{metrics['n_crests']} cotas de cresta de bancos as-built "
            f"(<code>bench_real</code>).</i>",
            styles["small"],
        )
    )


def _build_top5_section(
    story: List[Any],
    comparisons: List[Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
) -> None:
    """Append section 4 (Top 5 desviaciones)."""
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("4. Top 5 Desviaciones de Altura", styles["h1"]))
    story.append(
        Paragraph(
            "Las cinco mayores desviaciones absolutas entre altura de "
            "banco de diseño y altura de banco as-built (en valor absoluto).",
            styles["body"],
        )
    )

    top5 = _top5_height_deviations(comparisons)
    story.append(
        _top5_table(
            top5,
            col_widths=[
                0.8 * cm,
                3.6 * cm,
                1.6 * cm,
                2.6 * cm,
                2.6 * cm,
                2.0 * cm,
                3.6 * cm,
            ],
            styles=styles,
        )
    )


def _build_pie_section(
    story: List[Any],
    comparisons: List[Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
) -> None:
    """Append section 5 (Gráfico de torta embebido)."""
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("5. Gráfico de Cumplimiento", styles["h1"]))
    story.append(
        Paragraph(
            "Distribución porcentual del estado de cumplimiento para los "
            "tres parámetros evaluados: Altura de Banco, Ángulo de Cara y "
            "Ancho de Berma.",
            styles["body"],
        )
    )

    pie_buf = _pie_chart_image_bytes(comparisons)
    if pie_buf is None:
        story.append(
            Paragraph(
                "<i>(No se pudo renderizar el gráfico de torta.)</i>",
                styles["body"],
            )
        )
        return

    # ``ImageReader`` accepts a BytesIO directly. Scale to the printable
    # area width minus margins (A4 21 cm − 2 × 2 cm = 17 cm).
    try:
        reader = ImageReader(pie_buf)
        iw, ih = reader.getSize()
        max_w = 16.5 * cm
        ratio = max_w / float(iw)
        display_h = float(ih) * ratio
        story.append(
            Image(
                reader,
                width=max_w,
                height=display_h,
                hAlign="CENTER",
            )
        )
    except Exception:
        story.append(
            Paragraph(
                "<i>(Error al insertar el gráfico en el PDF.)</i>",
                styles["body"],
            )
        )
    finally:
        try:
            pie_buf.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_pdf_report(
    comparisons: List[Dict[str, Any]],
    all_data: List[Dict[str, Any]],
    output_path: str,
    project_info: Optional[Dict[str, Any]] = None,
    df_pozos: Optional[Any] = None,  # pandas.DataFrame — unused in this stub
    sections: Optional[List[Any]] = None,  # unused in this stub
) -> str:
    """Build the unified executive PDF report at ``output_path``.

    Parameters
    ----------
    comparisons:
        List of comparison dicts produced by
        :func:`core.param_extractor.compare_design_vs_asbuilt`. Each dict
        carries the ``*_status``, ``*_real`` and ``*_design`` fields plus
        a ``bench_real`` object.
    all_data:
        Per-section dicts with the ``section_name`` and
        ``params_design`` / ``params_topo`` keys. Currently accepted for
        API parity with ``generate_word_report`` but not required for
        the executive report (the top-level sections reuse ``comparisons``).
    output_path:
        Destination filesystem path for the resulting ``.pdf``.
    project_info:
        Optional dict with ``project``, ``author``, ``operation``,
        ``phase``, ``date`` keys. Missing fields fall back to safe
        placeholders.
    df_pozos:
        Optional blast-hole DataFrame. Reserved for future use; the
        executive report doesn't currently include a drilling section.
    sections:
        Optional list of ``SectionLine`` objects. Reserved for future
        use.

    Returns
    -------
    str
        ``output_path`` (so callers can chain the call).

    Notes
    -----
    The function never raises on missing data — it produces a valid PDF
    with placeholders so the API endpoint can always serve a download.
    """
    if project_info is None:
        project_info = {}

    # Make sure the destination directory exists.
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # Close any matplotlib state left over from previous builds.
    plt.close("all")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title="Informe de Conciliación Geotécnica",
        author=project_info.get("author", "Conciliación Geo v02"),
        subject="Conciliación Geotécnica — Reporte Ejecutivo",
    )

    styles = _build_styles()
    story: List[Any] = []

    # 1. Portada
    _build_cover(story, project_info, styles)

    # 2. Resumen Ejecutivo (score + breakdown)
    _build_executive_summary(story, comparisons, styles)

    # 3. Profundidad del Rajo
    _build_depth_section(story, comparisons, styles)

    # 4. Top 5 Desviaciones
    _build_top5_section(story, comparisons, styles)

    # 5. Gráfico de torta embebido
    _build_pie_section(story, comparisons, styles)

    # Footer line
    story.append(Spacer(1, 0.6 * cm))
    story.append(
        Paragraph(
            f"<i>Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — "
            "Conciliación Geotécnica v02</i>",
            styles["small"],
        )
    )

    doc.build(story)

    # Cleanup any lingering matplotlib figures to avoid memory growth
    # when many exports run sequentially.
    plt.close("all")

    return output_path


__all__ = ["generate_pdf_report"]