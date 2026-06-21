"""Build the analysis prompt that will be sent to the LLM."""
from __future__ import annotations

from core.ai_v2.prompts import load_prompt_template, render_prompt


_VERDICT_THRESHOLDS: tuple[int, int] = (90, 70)


def _compute_verdict(results: list[dict]) -> str:
    """Compute a high-level verdict using both MATCH ratio and weighted bench_score.

    MATCH-only ratio is misleading: a 95% MATCH count can hide a section full
    of NO_CUMPLE angle rows. We surface both signals.
    """
    if not results:
        return "**Sin datos suficientes** para emitir un veredicto."

    n_total = len(results)
    n_match = sum(1 for r in results if r.get("type") == "MATCH")
    pct_match = 100 * n_match / n_total

    match_only = results and pct_match >= _VERDICT_THRESHOLDS[0]

    scores: list[float] = []
    for r in results:
        s = r.get("bench_score")
        if isinstance(s, (int, float)):
            scores.append(float(s))
    avg_score = sum(scores) / len(scores) if scores else None

    n_no_cumple_total = sum(
        1 for r in results
        for k in ("height_status", "angle_status", "berm_status")
        if r.get(k) == "NO CUMPLE"
    )

    if match_only and (avg_score is None or avg_score >= 70) and n_no_cumple_total == 0:
        verdict = "BUENA"
    elif pct_match >= _VERDICT_THRESHOLDS[1] and (avg_score is None or avg_score >= 50):
        verdict = "REGULAR"
    else:
        verdict = "MALA"

    pieces: list[str] = [
        f"{n_match}/{n_total} bancos comparados (umbral BUENA≥{_VERDICT_THRESHOLDS[0]}%)"
    ]
    if avg_score is not None:
        pieces.append(f"score promedio {avg_score:.1f}/100")
    if n_no_cumple_total:
        pieces.append(f"{n_no_cumple_total} alertas NO CUMPLE")

    return f"Adherencia al diseño: **{verdict}** ({'; '.join(pieces)})."


def _render_tolerances(settings: dict | None) -> str:
    """Render the tolerance block (Idea 2).

    The LLM classifies CUMPLE/FUERA/NO_CUMPLE but without the actual
    tolerances it cannot judge *why* a bank is out. This block exposes the
    threshold values used by the engine.
    """
    if not settings:
        return "_No hay criterios de tolerancia definidos._"

    candidates: list[tuple[str, str, str]] = [
        ("bench_height", "Altura de banco", "m"),
        ("face_angle", "Ángulo de cara", "°"),
        ("berm_width", "Ancho de berma", "m"),
        ("inter_ramp_angle", "Ángulo inter-rampa", "°"),
    ]
    rows: list[str] = [
        "| Parámetro | Tolerancia |",
        "|---|---|",
    ]
    any_row = False
    for key, label, unit in candidates:
        val = settings.get(key)
        if val is None:
            continue
        if isinstance(val, dict):
            neg = val.get("negative")
            pos = val.get("positive")
            if neg is not None and pos is not None:
                tol = f"{neg:+.2f} / {pos:+.2f} {unit}"
            else:
                tol = str(val)
        elif isinstance(val, (int, float)):
            tol = f"±{val:.2f} {unit}"
        else:
            tol = f"{val} {unit}"
        rows.append(f"| {label} | {tol} |")
        any_row = True
    if not any_row:
        return "_No hay criterios de tolerancia definidos._"
    return "\n".join(rows)


def _render_compliance_table(results: list[dict]) -> str:
    if not results:
        return "_Sin datos._"
    rows = ["| Parámetro | CUMPLE | FUERA | NO CUMPLE |", "|---|---|---|---|"]
    for param in ("height", "angle", "berm"):
        status_key = f"{param}_status"
        cumple = sum(1 for r in results if r.get(status_key) == "CUMPLE")
        fuera = sum(1 for r in results if r.get(status_key) == "FUERA DE TOLERANCIA")
        no_cumple = sum(
            1 for r in results if r.get(status_key) == "NO CUMPLE"
        )
        rows.append(f"| {param.upper()} | {cumple} | {fuera} | {no_cumple} |")
    return "\n".join(rows)


def _format_bench(r: dict) -> str:
    """Render bench_num with a human-readable type tag (Idea from brainstorm)."""
    btype = r.get("type")
    num = r.get("bench_num")
    if btype == "EXTRA":
        return "EXTRA (sin diseño)"
    if btype == "MISSING":
        return f"FALTA (cota {r.get('level', '?')})"
    return str(num) if num is not None else "?"


def _render_top5_desviations(results: list[dict]) -> str:
    """Top-5 with signed deltas + delta_crest/delta_toe (Idea 8)."""
    if not results:
        return "_Sin datos._"
    sorted_h = sorted(
        results, key=lambda r: abs(r.get("height_dev", 0) or 0), reverse=True
    )[:5]
    rows = [
        "| Banco | H diseño→real (m) | Δh (m) | Δangle (°) | Δcrest (m) | Δtoe (m) |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted_h:
        h_d = r.get("height_design")
        h_r = r.get("height_real")
        h_text = f"{h_d:.2f}→{h_r:.2f}" if (h_d is not None and h_r is not None) else "-"
        delta_crest = r.get("delta_crest")
        delta_toe = r.get("delta_toe")
        crest_text = f"{delta_crest:+.2f}" if isinstance(delta_crest, (int, float)) else "-"
        toe_text = f"{delta_toe:+.2f}" if isinstance(delta_toe, (int, float)) else "-"
        rows.append(
            f"| {_format_bench(r)} | "
            f"{h_text} | "
            f"{r.get('height_dev', 0):+.2f} | "
            f"{r.get('angle_dev', 0):+.1f} | "
            f"{crest_text} | "
            f"{toe_text} |"
        )
    return "\n".join(rows)


def _render_stability_summary(results: list[dict]) -> str:
    """Section 4 — Stability. Static string removed (Idea 1).

    The LLM is instructed to analyse the data itself. We pass a lightweight
    prompt stub that asks it to cite which banks (if any) have critical
    overhang/wedge flags. If we have no stability metadata, the LLM writes
    'Sin datos.' per the format rules.
    """
    if not results:
        return "_Sin datos._"
    has_overhang = any(
        isinstance((r.get("bench_real") or {}).get("overhang_m"), (int, float))
        for r in results
    )
    if has_overhang:
        return (
            "Identifica bancos con `overhang_m ≥ 1.5 m` (CRITICAL) o "
            "≥ 0.5 m (WARNING). Para cada uno, indica sección, banco, "
            "valor exacto y acción recomendada (pre-corte, berma de "
            "captura ampliada, monitoreo)."
        )
    return "_Sin datos._"


def _render_blast_recommendations(blast_trend: dict | None) -> str:
    if not blast_trend:
        return "_No hay datos de tronadura disponibles._"
    template = load_prompt_template("blast_enrichment.md")
    ratios = blast_trend.get("ratios") or {}
    outliers = blast_trend.get("outliers") or []
    return render_prompt(
        template,
        pf_promedio=blast_trend.get("pf_promedio", "N/A"),
        pf_desviacion=blast_trend.get("pf_desviacion", "N/A"),
        n_pozos=blast_trend.get("n_pozos_total", "N/A"),
        trend_slope=blast_trend.get("trend_slope_pf_per_month", "N/A"),
        trend_direction=blast_trend.get("trend_direction", "estable"),
        ratios=ratios if isinstance(ratios, str) else ", ".join(f"{k}={v}" for k, v in ratios.items()),
        outliers=outliers if isinstance(outliers, str) else ", ".join(str(o) for o in outliers),
    )


def _render_action_plan(results: list[dict], blast_trend: dict | None) -> str:
    """Section 6 — Action plan. Static text removed (Idea 1).

    The LLM is instructed in the system prompt to generate specific,
    parameter-anchored actions (rule #4). We give it a list of the
    most actionable signals so it can pick 3-5 actions.
    """
    if not results:
        return "_Sin datos._"
    signals: list[str] = []
    for r in results:
        if r.get("berm_status") == "NO CUMPLE":
            signals.append(f"berma fuera de norma en banco {_format_bench(r)}")
        if r.get("angle_status") == "NO CUMPLE":
            signals.append(f"ángulo excedido en banco {_format_bench(r)}")
        if isinstance(r.get("delta_crest"), (int, float)) and abs(r["delta_crest"]) > 0.5:
            signals.append(f"sobre/deuda de crest en banco {_format_bench(r)} (Δcrest={r['delta_crest']:+.2f} m)")
        if isinstance(r.get("spill_width"), (int, float)) and r["spill_width"] > 0.5:
            signals.append(f"derrame significativo en banco {_format_bench(r)} (spill={r['spill_width']:.2f} m)")
    if not signals:
        return "_Sin hallazgos críticos; mantener plan de monitoreo estándar._"
    bullets = "\n".join(f"- {s}" for s in signals[:10])
    return f"Con base en los hallazgos siguientes, redacta 3-5 acciones específicas con valores concretos:\n{bullets}"


def build_analysis_prompt(
    results: list[dict],
    sections: list[dict] | None = None,
    settings: dict | None = None,
    blast_trend: dict | None = None,
    *,
    project_name: str = "Sin nombre",
    fecha_informe: str = "N/A",
    seccion: str = "global",
    banco: str = "N/A",
) -> tuple[str, str]:
    """Build the (system_prompt, user_prompt) tuple from raw data."""
    system = load_prompt_template("system_role.md")
    user_template = load_prompt_template("executive_summary.md")

    user = render_prompt(
        user_template,
        project_name=project_name,
        fecha_informe=fecha_informe,
        seccion=seccion,
        banco=banco,
        verdict_global=_compute_verdict(results),
        criterios_tolerancia=_render_tolerances(settings),
        tabla_cumplimiento=_render_compliance_table(results),
        top5_desviaciones=_render_top5_desviations(results),
        fs_y_alertas=_render_stability_summary(results),
        recomendaciones_blast=_render_blast_recommendations(blast_trend),
        plan_accion_priorizado=_render_action_plan(results, blast_trend),
    )
    return system, user