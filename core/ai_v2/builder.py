"""Build the analysis prompt that will be sent to the LLM."""
from __future__ import annotations

from core.ai_v2.prompts import load_prompt_template, render_prompt
from core.config import STABILITY
from core.param_extractor import BenchParams
from core.stability_analysis import (
    assess_bench_stability,
    compute_section_health_score,
)


_VERDICT_THRESHOLDS: tuple[int, int] = (90, 70)

# Default face angle used when coercing a partial dict (e.g. legacy test
# fixtures that only carry ``overhang_m``) into a full ``BenchParams``.
# 60° is a typical open-pit bench face angle and keeps the Hoek-Bray
# infinite-slope proxy in a physically meaningful regime.
_DEFAULT_FACE_ANGLE_DEG: float = 60.0


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


def _coerce_bench_params(value) -> BenchParams | None:
    """Normalise a ``bench_real`` field into a ``BenchParams`` instance.

    Comparisons produced by :func:`core.profile_compliance.compare_design_vs_asbuilt`
    store a real ``BenchParams`` under ``bench_real``, but tests and some
    legacy fixtures pass plain dicts. This helper accepts either and returns
    ``None`` for missing data so callers can short-circuit cleanly.
    """
    if value is None:
        return None
    if isinstance(value, BenchParams):
        return value
    if isinstance(value, dict):
        def _f(key, default=0.0):
            v = value.get(key, default)
            try:
                return float(v) if v is not None else float(default)
            except (TypeError, ValueError):
                return float(default)
        return BenchParams(
            bench_number=int(value.get("bench_number", 0) or 0),
            crest_elevation=_f("crest_elevation"),
            crest_distance=_f("crest_distance"),
            toe_elevation=_f("toe_elevation"),
            toe_distance=_f("toe_distance"),
            bench_height=_f("bench_height", _f("height_real")),
            face_angle=_f("face_angle", _f("angle_real", _DEFAULT_FACE_ANGLE_DEG))
            or _DEFAULT_FACE_ANGLE_DEG,
            berm_width=_f("berm_width", _f("berm_real")),
            is_ramp=bool(value.get("is_ramp", False)),
            spill_width=_f("spill_width"),
            effective_berm_width=_f("effective_berm_width", _f("effective_berm")),
            overhang_m=_f("overhang_m"),
            rock_bridge_thickness_m=_f("rock_bridge_thickness_m"),
            rock_bridge_height_m=_f("rock_bridge_height_m"),
            catch_bench_adequate=bool(value.get("catch_bench_adequate", False)),
            catch_bench_ratio=_f("catch_bench_ratio"),
            wedge_risk=bool(value.get("wedge_risk", False)),
            toppling_risk=bool(value.get("toppling_risk", False)),
            face_angle_inconsistent=bool(value.get("face_angle_inconsistent", False)),
            anisotropy_dispersion_deg=_f("anisotropy_dispersion_deg"),
        )
    return None


def _section_label(r: dict) -> str:
    return str(r.get("section") or "global")


def _action_for_overhang(severity: str) -> str:
    if severity == "CRITICAL":
        return "Detener trabajo; pre-corte y berma de captura ampliada"
    if severity == "WARNING":
        return "Restringir acceso; monitorear y reevaluar"
    return "Mantener plan estándar"


def _render_stability_summary(results: list[dict]) -> str:
    """Section 4 — Stability table driven by real stability helpers (Idea 10).

    Calls :func:`compute_section_health_score` per section to surface the
    aggregate 0-100 score plus its components, and uses
    :func:`assess_bench_stability` per bench to flag every meaningful
    overhang / wedge / toppling / face-angle / catch-bench signal.
    """
    if not results:
        return "_Sin datos._"

    by_section: dict[str, list[BenchParams]] = {}
    for r in results:
        bp = _coerce_bench_params(r.get("bench_real"))
        if bp is None:
            continue
        by_section.setdefault(_section_label(r), []).append(bp)

    if not by_section:
        return "_Sin datos._"

    rows = [
        "| Sección | Banco | Métrica | Valor | Severidad | Acción |",
        "|---|---|---|---|---|---|",
    ]
    for section, benches in by_section.items():
        # Section-level health score (one summary row per section).
        try:
            health = compute_section_health_score(section, benches)
            rows.append(
                f"| {section} | (sección) | Health Score | "
                f"{health.health_score:.0f}/100 ({health.health_category}) | "
                f"{health.health_category} | {health.recommended_action} |"
            )
            if health.critical_bench_numbers:
                crit = ", ".join(str(b) for b in health.critical_bench_numbers)
                rows.append(
                    f"| {section} | {crit} | Bancos críticos (overhang) | "
                    f"{len(health.critical_bench_numbers)} banco(s) | CRITICAL | "
                    f"{_action_for_overhang('CRITICAL')} |"
                )
        except (ValueError, ZeroDivisionError, ArithmeticError):
            # Section scoring needs valid face angles; degrade gracefully.
            pass

        # Per-bench flags (only when there is something to flag).
        for b in benches:
            assessment = assess_bench_stability(b)
            if assessment.overhang_severity != "OK":
                rows.append(
                    f"| {section} | {assessment.bench_number} | Overhang | "
                    f"{assessment.overhang_m:.2f} m | {assessment.overhang_severity} | "
                    f"{_action_for_overhang(assessment.overhang_severity)} |"
                )
            if assessment.wedge_risk:
                rows.append(
                    f"| {section} | {assessment.bench_number} | Wedge risk | "
                    f" detectado | WARNING | Mapear discontinuidades y reanalizar |"
                )
            if assessment.toppling_risk:
                rows.append(
                    f"| {section} | {assessment.bench_number} | Toppling risk | "
                    f"detectado | WARNING | Evaluar anclajes / geomembrana |"
                )
            if assessment.face_angle_inconsistent:
                rows.append(
                    f"| {section} | {assessment.bench_number} | "
                    f"Ángulo de cara inconsistente | detectado | WARNING | "
                    f"Re-medir cara de banco |"
                )
            if not assessment.catch_bench_adequate and assessment.catch_bench_ratio > 0:
                rows.append(
                    f"| {section} | {assessment.bench_number} | Catch bench | "
                    f"ratio={assessment.catch_bench_ratio:.2f} | WARNING | "
                    f"Ampliar berma de captura |"
                )
    return "\n".join(rows)


def _render_safety_flags(results: list[dict]) -> str:
    """Section 6 — Safety flags table for WARNING/CRITICAL banks (Idea 12).

    Uses :func:`assess_bench_stability` and the configured warning/critical
    thresholds (:data:`core.config.STABILITY`). The table is sorted with
    CRITICAL rows first so the LLM reads the most urgent items at the top.
    """
    if not results:
        return "_Sin datos._"

    flagged: list[tuple[int, str, str, str, str, str]] = []
    for r in results:
        bp = _coerce_bench_params(r.get("bench_real"))
        if bp is None:
            continue
        section = _section_label(r)
        bench_id = _format_bench(r)
        assessment = assess_bench_stability(bp)

        if assessment.overhang_severity == "CRITICAL":
            flagged.append((0, section, bench_id, "Overhang",
                            f"{assessment.overhang_m:.2f} m", "CRITICAL"))
        elif assessment.overhang_severity == "WARNING":
            flagged.append((1, section, bench_id, "Overhang",
                            f"{assessment.overhang_m:.2f} m", "WARNING"))
        if assessment.wedge_risk:
            flagged.append((1, section, bench_id, "Wedge",
                            "detectado", "WARNING"))
        if assessment.toppling_risk:
            flagged.append((1, section, bench_id, "Toppling",
                            "detectado", "WARNING"))
        if assessment.face_angle_inconsistent:
            flagged.append((1, section, bench_id, "Ángulo inconsistente",
                            "detectado", "WARNING"))
        # Face angle far steeper than the critical overhang angle indicates
        # an incipient failure plane — surface it even without explicit flags.
        if (bp.face_angle >= 80.0
                and assessment.overhang_severity == "OK"
                and not (assessment.wedge_risk or assessment.toppling_risk)):
            flagged.append((1, section, bench_id, "Cara muy steep",
                            f"{bp.face_angle:.1f}°", "WARNING"))

    if not flagged:
        return "_Sin bancos con flags de seguridad. Operación normal._"

    flagged.sort(key=lambda x: x[0])
    rows = [
        "| Sección | Banco | Flag | Valor | Severidad |",
        "|---|---|---|---|---|",
    ]
    for _, section, bench_id, metric, value, severity in flagged:
        rows.append(f"| {section} | {bench_id} | {metric} | {value} | {severity} |")
    return "\n".join(rows)


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


# Severity ranks used by ``_render_action_plan``. Lower number = higher
# urgency. Bullets are emitted in this order so the LLM reads critical
# items first and translates them into 3-5 prioritised actions.
_SEV_CRITICAL: int = 0
_SEV_HIGH: int = 1
_SEV_MEDIUM: int = 2


def _render_action_plan(results: list[dict], blast_trend: dict | None) -> str:
    """Section 7 — Action plan with severity-ranked signals (Idea 14).

    Expands the bullet generator to cover the full signal catalog:
    overhang (CRITICAL/WARNING), wedge, toppling, NO_CUMPLE compliance
    rows, signed crest/toe deviations > 0.3 m, spill_width > 0.5 m and
    berm_min > effective_berm. Bullets are sorted by severity so the
    LLM picks the most urgent 3-5 actions.
    """
    if not results:
        return "_Sin datos._"

    signals: list[tuple[int, str]] = []
    for r in results:
        bench_id = _format_bench(r)
        bp = _coerce_bench_params(r.get("bench_real"))
        if bp is not None:
            assessment = assess_bench_stability(bp)
            if assessment.overhang_severity == "CRITICAL":
                signals.append((
                    _SEV_CRITICAL,
                    f"DETENER trabajo en banco {bench_id} "
                    f"(overhang CRITICAL {assessment.overhang_m:.2f} m, "
                    f"riesgo de desplome inminente)",
                ))
            elif assessment.overhang_severity == "WARNING":
                signals.append((
                    _SEV_MEDIUM,
                    f"Restringir acceso a banco {bench_id} "
                    f"(overhang WARNING {assessment.overhang_m:.2f} m)",
                ))
            if assessment.wedge_risk:
                signals.append((
                    _SEV_MEDIUM,
                    f"Mapear discontinuidades en banco {bench_id} "
                    f"(wedge risk detectado)",
                ))
            if assessment.toppling_risk:
                signals.append((
                    _SEV_MEDIUM,
                    f"Evaluar anclajes en banco {bench_id} "
                    f"(toppling risk detectado)",
                ))

        # Compliance rows.
        if r.get("berm_status") == "NO CUMPLE":
            signals.append((
                _SEV_HIGH,
                f"berma fuera de norma en banco {bench_id}",
            ))
        if r.get("angle_status") == "NO CUMPLE":
            signals.append((
                _SEV_HIGH,
                f"ángulo excedido en banco {bench_id}",
            ))
        if r.get("height_status") == "NO CUMPLE":
            signals.append((
                _SEV_HIGH,
                f"altura fuera de norma en banco {bench_id}",
            ))

        # Signed crest/toe deltas (lowered threshold to 0.3 m per brainstorm).
        if isinstance(r.get("delta_crest"), (int, float)) and abs(r["delta_crest"]) > 0.3:
            direction = "sobre-excavación" if r["delta_crest"] > 0 else "deuda"
            signals.append((
                _SEV_MEDIUM,
                f"Corregir crest en banco {bench_id} "
                f"(Δcrest={r['delta_crest']:+.2f} m → {direction})",
            ))
        if isinstance(r.get("delta_toe"), (int, float)) and abs(r["delta_toe"]) > 0.3:
            direction = "sobre-excavación" if r["delta_toe"] > 0 else "deuda"
            signals.append((
                _SEV_MEDIUM,
                f"Corregir toe en banco {bench_id} "
                f"(Δtoe={r['delta_toe']:+.2f} m → {direction})",
            ))

        # Spill / derrame.
        if isinstance(r.get("spill_width"), (int, float)) and r["spill_width"] > 0.5:
            signals.append((
                _SEV_MEDIUM,
                f"Derrame significativo en banco {bench_id} "
                f"(spill={r['spill_width']:.2f} m)",
            ))

        # Effective berm below minimum.
        berm_min = r.get("berm_min")
        eff_berm = r.get("effective_berm")
        if (isinstance(berm_min, (int, float))
                and isinstance(eff_berm, (int, float))
                and berm_min > eff_berm):
            signals.append((
                _SEV_MEDIUM,
                f"Ampliar berma efectiva en banco {bench_id} "
                f"(actual {eff_berm:.2f} m < mínimo {berm_min:.2f} m)",
            ))

    # Cross-signal: high PF + overbreak correlation (only when we have
    # both pieces of context).
    if blast_trend and isinstance(blast_trend.get("pf_promedio"), (int, float)):
        pf = float(blast_trend["pf_promedio"])
        over_rows = [
            r for r in results
            if isinstance(r.get("delta_crest"), (int, float)) and r["delta_crest"] > 0.3
        ]
        if pf > 0.6 and over_rows:
            sample = over_rows[0]
            signals.append((
                _SEV_HIGH,
                f"Reducir burden en banco {_format_bench(sample)} "
                f"(PF promedio {pf:.2f} kg/m³ correlacionado con "
                f"sobre-excavación Δcrest={sample['delta_crest']:+.2f} m)",
            ))

    if not signals:
        return "_Sin hallazgos críticos; mantener plan de monitoreo estándar._"

    signals.sort(key=lambda x: x[0])
    bullets = "\n".join(f"- {text}" for _, text in signals[:10])
    return (
        "Con base en los hallazgos siguientes (ordenados por severidad, "
        "CRITICAL primero), redacta 3-5 acciones específicas con valores "
        f"concretos:\n{bullets}"
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
        criterios_tolerancia=_render_tolerances(settings),
        tabla_cumplimiento=_render_compliance_table(results),
        top5_desviaciones=_render_top5_desviations(results),
        fs_y_alertas=_render_stability_summary(results),
        recomendaciones_blast=_render_blast_recommendations(blast_trend),
        flags_seguridad=_render_safety_flags(results),
        plan_accion_priorizado=_render_action_plan(results, blast_trend),
    )
    return system, user
