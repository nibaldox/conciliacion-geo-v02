import numpy as np
import pandas as pd
import pytest

from core.blast_advisor import (
    recommend_pf_adjustment,
    recommend_charge_change_pct,
    validate_recommendation,
    format_recommendation_text,
    FEASIBILITY_APPLICABLE,
    FEASIBILITY_CAUTION,
    FEASIBILITY_INSUFFICIENT,
)


def _model(beta1=1.4, n=20, p=0.01, conf='HIGH'):
    return {
        'beta0': -0.2,
        'beta1': beta1,
        'r_squared': 0.6,
        'p_value': p,
        'n': n,
        'std_err_beta1': 0.2,
        'ci_beta1_low': beta1 - 0.4,
        'ci_beta1_high': beta1 + 0.4,
        'mean_pf': 0.45,
        'confidence': conf,
        'is_significant': p < 0.05,
    }


class TestValidateRecommendation:
    def test_within_limits_passes(self):
        rec = recommend_pf_adjustment(_model(), current_pf=0.50, target_overbreak_m=0.5)
        res = validate_recommendation(rec)
        assert res['valid'] is True
        assert res['warnings'] == []
        assert res['adjusted_feasibility'] == rec['feasibility']

    def test_exceeds_max_pct_warns_and_degrades(self):
        rec = {
            'target_pf': 0.20,
            'current_pf': 0.80,
            'delta_pf': -0.60,
            'delta_pf_pct': -75.0,
            'predicted_current_damage': 0.8,
            'predicted_target_damage': 0.5,
            'feasibility': FEASIBILITY_APPLICABLE,
            'message': '',
            'confidence': 'HIGH',
        }
        res = validate_recommendation(rec)
        assert res['valid'] is False
        assert any('excede' in w for w in res['warnings'])
        assert res['adjusted_feasibility'] == FEASIBILITY_CAUTION

    def test_target_pf_below_min_warns(self):
        rec = {
            'target_pf': 0.05,
            'current_pf': 0.50,
            'delta_pf': -0.45,
            'delta_pf_pct': -90.0,
            'predicted_current_damage': 0.0,
            'predicted_target_damage': 0.0,
            'feasibility': FEASIBILITY_CAUTION,
            'message': '',
            'confidence': 'LOW',
        }
        res = validate_recommendation(rec)
        assert any('minimo' in w for w in res['warnings'])

    def test_invalid_rec_returns_failure(self):
        res = validate_recommendation('not a dict')
        assert res['valid'] is False
        assert any('invalida' in w.lower() for w in res['warnings'])

    def test_custom_constraints(self):
        rec = recommend_pf_adjustment(_model(), current_pf=0.45, target_overbreak_m=0.2)
        res_strict = validate_recommendation(rec, constraints={'max_recommendation_pct': 1.0})
        res_loose = validate_recommendation(rec, constraints={'max_recommendation_pct': 200.0})
        assert res_strict['valid'] is False
        assert res_loose['valid'] is True


class TestBuildAnalysisPrompt:
    def test_basic_prompt_includes_results(self):
        results = [
            {'height_status': 'CUMPLE', 'angle_status': 'CUMPLE', 'berm_status': 'CUMPLE',
             'type': 'MATCH', 'section': 'S1', 'height_dev': 0.2, 'angle_dev': 1.5,
             'bench_num': 1},
        ]
        from core.ai_v2.builder import build_analysis_prompt
        system, user = build_analysis_prompt(results, [], {'tolerances': {}}, seccion='S1')
        assert '1/1 bancos comparados' in user
        assert 'S1' in user
        assert system != ''

    def test_blast_trend_block_included(self):
        results = [{'height_status': 'CUMPLE', 'type': 'MATCH', 'section': 'S1',
                    'height_dev': 0.1, 'angle_dev': 0.0, 'bench_num': 1}]
        trend = {
            'pf_promedio': 0.42,
            'pf_desviacion': 0.08,
            'n_pozos_total': 25,
            'trend_slope_pf_per_month': -0.015,
            'trend_direction': 'bajando',
            'ratios': {'stemming_ratio': 0.85, 'subdrilling_ratio': 0.3},
            'outliers': [{'label_pozo': 'P-007', 'pf_vol_kgm3': 0.92}],
        }
        from core.ai_v2.builder import build_analysis_prompt
        system, user = build_analysis_prompt(results, [], {}, blast_trend=trend)
        assert '0.42 kg/m³' in user
        assert 'bajando' in user
        assert 'P-007' in user

    def test_blast_trend_optional(self):
        results = [{'height_status': 'CUMPLE', 'type': 'MATCH', 'section': 'S1',
                    'height_dev': 0.1, 'angle_dev': 0.0, 'bench_num': 1}]
        from core.ai_v2.builder import build_analysis_prompt
        _, user_no_trend = build_analysis_prompt(results, [], {})
        _, user_with_none = build_analysis_prompt(results, [], {}, blast_trend=None)
        assert user_no_trend == user_with_none