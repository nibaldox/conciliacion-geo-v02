"""Build the analysis prompt that will be sent to the LLM."""
from __future__ import annotations

from core.ai_v2.prompts import load_prompt_template, render_prompt


def _compute_verdict(results: list[dict]) -> str:
    if not results:
        return "**Sin datos suficientes** para emitir un veredicto."
    n_total = len(results)
    n_match = sum(1 for r in results if r.get("type") == "MATCH")
    pct_match = 100 * n_match / n_total
    if pct_match >= 90:
        verdict = "BUENA"
    elif pct_match >= 70:
        verdict = "REGULAR"
    else:
        verdict = "MALA"
    return f"Adherencia al diseño: **{verdict}** ({n_match}/{n_total} bancos comparados)."


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


def _render_top5_desviations(results: list[dict]) -> str:
    if not results:
        return "_Sin datos._"
    sorted_h = sorted(
        results, key=lambda r: abs(r.get("height_dev", 0) or 0), reverse=True
    )[:5]
    rows = ["| Banco | Δh (m) | Δangle (°) |", "|---|---|---|"]
    for r in sorted_h:
        rows.append(
            f"| {r.get('bench_num', '?')} | "
            f"{r.get('height_dev', 0):+.2f} | "
            f"{r.get('angle_dev', 0):+.1f} |"
        )
    return "\n".join(rows)


def _render_stability_summary(results: list[dict]) -> str:
    if not results:
        return "_Sin datos._"
    return "Análisis de FS planar y alertas se incluye en el reporte técnico adjunto."


def _render_blast_recommendations(blast_trend: dict | None) -> str:
    if not blast_trend:
        return "_No hay datos de tronadura disponibles._"
    template = load_prompt_template("blast_enrichment.md")
    return render_prompt(
        template,
        pf_promedio=blast_trend.get("pf_promedio", "N/A"),
        pf_desviacion=blast_trend.get("pf_desviacion", "N/A"),
        n_pozos=blast_trend.get("n_pozos_total", "N/A"),
        trend_slope=blast_trend.get("trend_slope_pf_per_month", "N/A"),
        trend_direction=blast_trend.get("trend_direction", "estable"),
        ratios=blast_trend.get("ratios", "{}"),
        outliers=blast_trend.get("outliers", "[]"),
    )


def _render_action_plan(results: list[dict], blast_trend: dict | None) -> str:
    if not results:
        return "_Sin datos._"
    return (
        "1. Validar desviaciones críticas con el equipo de tronadura.\n"
        "2. Ajustar parámetros de perforación si sobre-excavación > 0.5 m.\n"
        "3. Monitorear bancos con alerta FUERA DE TOLERANCIA."
    )


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
        tabla_cumplimiento=_render_compliance_table(results),
        top5_desviaciones=_render_top5_desviations(results),
        fs_y_alertas=_render_stability_summary(results),
        recomendaciones_blast=_render_blast_recommendations(blast_trend),
        plan_accion_priorizado=_render_action_plan(results, blast_trend),
    )
    return system, user