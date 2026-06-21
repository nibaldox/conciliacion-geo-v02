"""Tests for core.ai_v2 builder."""
from __future__ import annotations

import pytest

from core.ai_v2.builder import (
    _compute_verdict,
    _render_action_plan,
    _render_blast_recommendations,
    _render_compliance_table,
    _render_stability_summary,
    _render_top5_desviations,
    build_analysis_prompt,
)


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