import itertools
from types import SimpleNamespace

import pytest

from core.blast_achievement import compute_design_achievement_score
from core.design_achievement import build_design_achievement_summary, build_sector_achievement_summary
from core.profile_compliance import _build_match_row


@pytest.mark.parametrize('present', list(itertools.product([False, True], repeat=3)))
def test_component_presence_matrix(present):
    names = ['crest', 'toe', 'berm']
    weights = [0.4, 0.3, 0.3]
    row = {'delta_crest': 0.0 if present[0] else None,
           'delta_toe': 0.0 if present[1] else None,
           'berm_status': 'CUMPLE' if present[2] else 'MISSING'}
    result = compute_design_achievement_score([row])
    details = result['rows'][0]
    assert details['score'] == (100 if any(present) else None)
    assert details['components_available'] == [n for n, p in zip(names, present) if p]
    assert details['components_missing'] == [n for n, p in zip(names, present) if not p]
    assert details['weight_available'] == pytest.approx(sum(w for w, p in zip(weights, present) if p))


def test_partial_credit_asymmetric_tolerances():
    rows = [{'delta_crest': -1.2}, {'delta_crest': 0.6}]
    result = compute_design_achievement_score(rows, crest_tolerance_neg_m=1.5, crest_tolerance_pos_m=0.5)
    assert [r['score'] for r in result['rows']] == [100, 50]
    assert result['global'] == 75


def test_coverage_global_sector_malla_and_structural_rows():
    rows = [
        {'type': 'MATCH', 'section': 'S1', 'sector': 'A', 'delta_crest': 0},
        {'type': 'MATCH', 'section': 'S1', 'sector': 'A', 'delta_crest': 2, 'delta_toe': 0, 'berm_status': 'CUMPLE'},
        {'type': 'MATCH', 'section': 'S1', 'sector': 'A'},
        {'type': 'EXTRA', 'section': 'S1', 'sector': 'A', 'delta_crest': 0, 'berm_status': 'CUMPLE'},
        {'type': 'MISSING', 'section': 'S1', 'sector': 'A', 'delta_toe': 0},
    ]
    result = compute_design_achievement_score(rows, {'M': ['S1']})
    coverage = result['coverage']
    assert result['global'] == 80
    assert coverage['n_rows'] == 5
    assert coverage['n_evaluable'] == 2
    assert coverage['n_complete'] == 1
    assert coverage['weight_available_mean'] == pytest.approx(1.4 / 5)
    assert coverage['n_available'] == {'crest': 2, 'toe': 1, 'berm': 1}
    assert result['breakdown'] == {'crest': 50, 'toe': 100, 'berm': 100}
    assert result['per_malla']['M'] == 80
    assert result['per_malla_coverage']['M'] == coverage
    assert build_design_achievement_summary(rows, None)['coverage'] == coverage
    assert build_sector_achievement_summary(rows, None)[0]['coverage'] == coverage


def make_bench(berm, effective):
    return SimpleNamespace(bench_height=10.0, face_angle=70.0, berm_width=berm,
                           spill_width=1.0, effective_berm_width=effective,
                           bench_number=1, toe_elevation=100.0,
                           crest_distance=10.0, toe_distance=0.0)


@pytest.mark.parametrize('design,real,expected', [(8.123, 9.456, 1.33), (float('nan'), 8, None), (8, float('nan'), None), (None, 8, None), (8, None, None)])
def test_match_berm_deviation(design, real, expected):
    tol = {'bench_height': {'neg': 1, 'pos': 1}, 'face_angle': {'neg': 5, 'pos': 5}, 'berm_width': {'min': 7}}
    row = _build_match_row(make_bench(design, 8), make_bench(real, 8), SimpleNamespace(sector='', section_name='S'), tol)
    assert row['berm_dev'] == expected


@pytest.mark.parametrize('effective,expected', [(8, 'CUMPLE'), (7, 'CUMPLE'), (6.999, 'CUMPLE'), (1, 'NO CUMPLE'), (float('nan'), None), (None, None)])
def test_effective_berm_indicator_does_not_change_score(effective, expected):
    tol = {'bench_height': {'neg': 1, 'pos': 1}, 'face_angle': {'neg': 5, 'pos': 5}, 'berm_width': {'min': 7}}
    row = _build_match_row(make_bench(8, 8), make_bench(8, effective), SimpleNamespace(sector='', section_name='S'), tol)
    assert row['effective_berm_status'] == expected
    assert row['berm_status'] == 'CUMPLE'
    assert row['bench_score'] == 100
