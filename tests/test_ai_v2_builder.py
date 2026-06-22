"""Tests for core.ai_v2 builder."""
from __future__ import annotations

import pytest

from core.ai_v2.builder import (
    _compute_verdict,
    _coerce_bench_params,
    _render_action_plan,
    _render_blast_recommendations,
    _render_compliance_table,
    _render_safety_flags,
    _render_stability_summary,
    _render_top5_desviations,
    build_analysis_prompt,
)
from core.param_extractor import BenchParams


def test_compute_verdict_empty():
    assert "Sin datos" in _compute_verdict([])


def test_compute_verdict_buena():
    results = [{"type": "MATCH"}] * 10
    assert "BUENA" in _compute_verdict(results)


def test_compute_verdict_regular():
    results = [{"type": "MATCH"}] * 8 + [{"type": "EXTRA"}] * 2
    assert "REGULAR" in _compute_verdict(results)


def test_compute_verdict_mala():
    results = [{"type": "MATCH"}] * 5 + [{"type": "EXTRA"}] * 5
    assert "MALA" in _compute_verdict(results)


def test_render_compliance_table_empty():
    out = _render_compliance_table([])
    assert "Sin datos" in out


def test_render_compliance_table_counts():
    results = [
        {"height_status": "CUMPLE", "angle_status": "FUERA DE TOLERANCIA",
         "berm_status": "NO CUMPLE"},
    ]
    out = _render_compliance_table(results)
    assert "HEIGHT" in out
    assert "ANGLE" in out
    assert "BERM" in out
    assert "1" in out


def test_render_top5_desviations_empty():
    assert "Sin datos" in _render_top5_desviations([])


def test_render_top5_desviations_sorts_by_abs():
    results = [
        {"bench_num": 1, "height_dev": 0.1, "angle_dev": 1.0},
        {"bench_num": 2, "height_dev": 1.5, "angle_dev": 5.0},
        {"bench_num": 3, "height_dev": 0.8, "angle_dev": 2.0},
    ]
    out = _render_top5_desviations(results)
    assert "2" in out
    assert "+1.50" in out


def test_render_stability_summary_empty():
    out = _render_stability_summary([])
    assert "Sin datos" in out


def test_render_stability_summary_with_data():
    # No bench_real with overhang metadata → must fall back to "Sin datos."
    # (Idea 1 from brainstorm: no hardcoded FS string).
    out = _render_stability_summary([{"x": 1}])
    assert "Sin datos" in out


def test_render_stability_summary_with_overhang_data():
    out = _render_stability_summary(
        [{"bench_real": {"overhang_m": 1.8}}, {"bench_real": {"overhang_m": 0.2}}]
    )
    assert "overhang" in out.lower()
    assert "CRITICAL" in out


def test_render_blast_recommendations_no_data():
    out = _render_blast_recommendations(None)
    assert "No hay datos" in out


def test_render_blast_recommendations_with_data():
    trend = {
        "pf_promedio": 0.45,
        "pf_desviacion": 0.05,
        "n_pozos_total": 30,
        "trend_slope_pf_per_month": -0.02,
        "trend_direction": "estable",
        "ratios": "{'a': 1}",
        "outliers": "[]",
    }
    out = _render_blast_recommendations(trend)
    assert "0.45" in out
    assert "estable" in out


def test_render_action_plan_empty():
    out = _render_action_plan([], None)
    assert "Sin datos" in out


def test_render_action_plan_with_data():
    # Without critical signals (no NO_CUMPLE rows, no deltas),
    # the new action plan falls back to a "monitor" stub (Idea 1).
    out = _render_action_plan([{"x": 1}], None)
    assert "Sin hallazgos críticos" in out


def test_render_action_plan_with_critical_signals():
    # With a NO_CUMPLE berm row, the plan surfaces a bullet for the LLM
    # to elaborate on.
    out = _render_action_plan(
        [
            {
                "type": "MATCH",
                "bench_num": 4,
                "berm_status": "NO CUMPLE",
                "height_status": "CUMPLE",
                "angle_status": "CUMPLE",
            }
        ],
        None,
    )
    assert "berma fuera de norma" in out
    assert "banco 4" in out


def test_build_analysis_prompt_returns_tuple():
    system, user = build_analysis_prompt([], [], {}, project_name="X")
    assert isinstance(system, str) and system
    assert isinstance(user, str) and user
    assert "X" in user


def test_build_analysis_prompt_includes_seccion():
    _, user = build_analysis_prompt([], [], {}, seccion="S-42")
    assert "S-42" in user


def test_build_analysis_prompt_includes_banco():
    _, user = build_analysis_prompt([], [], {}, banco="B-7")
    assert "B-7" in user


def test_build_analysis_prompt_with_blast_trend():
    trend = {
        "pf_promedio": 0.5, "pf_desviacion": 0.1, "n_pozos_total": 20,
        "trend_slope_pf_per_month": 0.0, "trend_direction": "estable",
        "ratios": "{}", "outliers": "[]",
    }
    _, user = build_analysis_prompt([], [], {}, blast_trend=trend)
    assert "0.5" in user
    assert "estable" in user


# ---------------------------------------------------------------------------
# New tests for ideas #10, #12, #14 (real stability, safety flags, dynamic plan)
# ---------------------------------------------------------------------------

def _bench(
    bench_number: int = 1,
    face_angle: float = 60.0,
    bench_height: float = 15.0,
    overhang_m: float = 0.0,
    wedge_risk: bool = False,
    toppling_risk: bool = False,
    face_angle_inconsistent: bool = False,
    berm_width: float = 8.0,
    catch_bench_adequate: bool = True,
    catch_bench_ratio: float = 1.0,
    **extra,
) -> BenchParams:
    """Minimal BenchParams factory for stability tests."""
    base = dict(
        bench_number=bench_number,
        crest_elevation=1000.0,
        crest_distance=0.0,
        toe_elevation=1000.0 - bench_height,
        toe_distance=10.0,
        bench_height=bench_height,
        face_angle=face_angle,
        berm_width=berm_width,
        overhang_m=overhang_m,
        wedge_risk=wedge_risk,
        toppling_risk=toppling_risk,
        face_angle_inconsistent=face_angle_inconsistent,
        catch_bench_adequate=catch_bench_adequate,
        catch_bench_ratio=catch_bench_ratio,
    )
    base.update(extra)
    return BenchParams(**base)


def test_coerce_bench_params_handles_dict_and_object():
    bp = _bench(overhang_m=1.8)
    assert _coerce_bench_params(bp) is bp
    coerced = _coerce_bench_params({"overhang_m": 1.8, "face_angle": 60.0})
    assert isinstance(coerced, BenchParams)
    assert coerced.overhang_m == 1.8
    assert coerced.face_angle == 60.0
    assert _coerce_bench_params(None) is None
    assert _coerce_bench_params("foo") is None


def test_render_stability_summary_with_real_benchparams():
    # Real BenchParams with a CRITICAL overhang drives the new table-based
    # stability summary (Idea #10). Should include the health score row,
    # the critical-bank row and the per-bench overhang row.
    results = [
        {
            "section": "S-1",
            "bench_num": 4,
            "type": "MATCH",
            "bench_real": _bench(bench_number=4, overhang_m=1.8),
        },
        {
            "section": "S-1",
            "bench_num": 5,
            "type": "MATCH",
            "bench_real": _bench(bench_number=5, overhang_m=0.2),
        },
    ]
    out = _render_stability_summary(results)
    assert "Health Score" in out
    assert "Overhang" in out
    assert "CRITICAL" in out
    assert "S-1" in out


def test_render_stability_summary_falls_back_when_no_bench_real():
    # Comparisons without bench_real still degrade gracefully.
    assert "Sin datos" in _render_stability_summary([{"x": 1}])


def test_render_safety_flags_empty():
    assert "Sin datos" in _render_safety_flags([])


def test_render_safety_flags_no_issues():
    # All-clean benches → no flags.
    results = [
        {"section": "S-1", "bench_num": 4, "type": "MATCH",
         "bench_real": _bench(bench_number=4)},
    ]
    out = _render_safety_flags(results)
    assert "Operación normal" in out


def test_render_safety_flags_with_critical_overhang():
    results = [
        {"section": "S-1", "bench_num": 4, "type": "MATCH",
         "bench_real": _bench(bench_number=4, overhang_m=1.8)},
        {"section": "S-1", "bench_num": 5, "type": "MATCH",
         "bench_real": _bench(bench_number=5, overhang_m=0.6)},
        {"section": "S-1", "bench_num": 6, "type": "MATCH",
         "bench_real": _bench(bench_number=6, wedge_risk=True)},
    ]
    out = _render_safety_flags(results)
    assert "CRITICAL" in out
    assert "WARNING" in out
    assert "Overhang" in out
    assert "Wedge" in out
    # CRITICAL row should appear before WARNING rows.
    assert out.index("CRITICAL") < out.index("WARNING")


def test_render_action_plan_with_delta_toe_signal():
    # delta_toe > 0.3 m should trigger a bullet (Idea #14 expansion).
    results = [
        {"section": "S-1", "bench_num": 4, "type": "MATCH",
         "delta_toe": 0.55, "bench_real": _bench(bench_number=4)},
    ]
    out = _render_action_plan(results, None)
    assert "Δtoe=" in out
    assert "banco 4" in out


def test_render_action_plan_with_berm_min_below_effective():
    # berm_min > effective_berm should trigger a bullet.
    results = [
        {"section": "S-1", "bench_num": 4, "type": "MATCH",
         "berm_min": 8.0, "effective_berm": 6.5,
         "bench_real": _bench(bench_number=4)},
    ]
    out = _render_action_plan(results, None)
    assert "berma efectiva" in out
    assert "6.50" in out
    assert "8.00" in out


def test_render_action_plan_with_critical_overhang_sorts_first():
    # Mix a CRITICAL overhang with a NO_CUMPLE berm and verify CRITICAL
    # bullet comes first (severity-rank ordering).
    results = [
        {"section": "S-1", "bench_num": 7, "type": "MATCH",
         "berm_status": "NO CUMPLE",
         "bench_real": _bench(bench_number=7, overhang_m=1.8)},
    ]
    out = _render_action_plan(results, None)
    critical_pos = out.find("DETENER trabajo")
    berm_pos = out.find("berma fuera de norma")
    assert critical_pos >= 0
    assert berm_pos >= 0
    assert critical_pos < berm_pos


def test_render_action_plan_pf_overbreak_correlation():
    # When PF is high AND there is overbreak, a correlated recommendation
    # bullet should appear (Idea #14 cross-signal).
    results = [
        {"section": "S-1", "bench_num": 4, "type": "MATCH",
         "delta_crest": 0.8, "bench_real": _bench(bench_number=4)},
    ]
    trend = {"pf_promedio": 0.75, "pf_desviacion": 0.1, "n_pozos_total": 20,
             "trend_slope_pf_per_month": 0.0, "trend_direction": "estable",
             "ratios": {}, "outliers": []}
    out = _render_action_plan(results, trend)
    assert "Reducir burden" in out


def test_build_analysis_prompt_includes_flags_seguridad_section():
    # The new section 6 must appear in the rendered prompt with the right
    # placeholder filled in.
    results = [
        {"section": "S-1", "bench_num": 4, "type": "MATCH",
         "bench_real": _bench(bench_number=4, overhang_m=1.8)},
    ]
    _, user = build_analysis_prompt(results, [], {})
    assert "## 6. Flags de Seguridad" in user
    assert "## 7. Plan de Acción" in user
    assert "CRITICAL" in user