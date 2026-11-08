import numpy as np
import pandas as pd
import pytest

from core import blast_correlation as bc
from core.blast_metrics import enrich_blast_dataframe


def holes():
    return pd.DataFrame({"X": [0., 10., 0., 10.], "Y": [0., 0., 10., 10.],
                         "Nombre_Malla_Original": ["A"] * 4,
                         "Kilos_Cargados_real": [100.] * 4,
                         "longitud_real": [12.] * 4, "Inclinacion_real": [0.] * 4,
                         "Z_collar": [100.] * 4, "Z_toe": [88.] * 4,
                         "Tipo_Explosivo": ["ANFO"] * 4})


def test_unique_sites_and_partial_design():
    df = pd.concat([holes(), holes().iloc[[0]]], ignore_index=True)
    df['Burden'] = [5., np.nan, np.nan, np.nan, np.nan]
    result = bc.compute_powder_factor(df, bench_height_m=10)
    assert result.loc[0, 'burden_est_m'] == 5
    assert result.loc[1, 'burden_est_m'] > 0
    assert result.loc[0, 'burden_spacing_source'] == 'mixed'
    assert result.loc[1, 'burden_spacing_source'] == 'knn_proxy'
    assert result.loc[0, 'esp_est_m'] == pytest.approx(result.loc[4, 'esp_est_m'])


def test_primary_footprint_and_section_ratio():
    df = holes()
    polygons = {'A': {'polygon': [(-5,-5),(15,-5),(15,15),(-5,15)], 'source': 'user_polygon'}}
    result = bc.compute_powder_factor(df, bench_height_m=10, rock_density_tm3=2, boundary_polygons=polygons)
    assert result['pf_voronoi_bench_status'].eq('VALID').all()
    assert result['pf_voronoi_bench_g_per_ton'].iloc[0] == pytest.approx(50)
    assert result['pf_voronoi_bench_source'].iloc[0] == 'footprint:user_polygon'
    subset = result.iloc[:2].copy()
    subset['section'] = 'S'
    aggregate = bc.aggregate_powder_factor_by_group(result, 'section', 'S', subset)
    assert aggregate['pf_voronoi_bench_g_per_ton_section'] == pytest.approx(50)
    assert aggregate['n_pf_voronoi_bench_valid'] == 2


def test_missing_footprint_and_formula_definitions():
    result = bc.compute_powder_factor(holes(), bench_height_m=10)
    assert result['pf_voronoi_bench_status'].eq('MISSING_FOOTPRINT').all()
    assert result['pf_voronoi_bench_g_per_ton'].isna().all()
    assert bc.PF_DEFINITIONS['pf_g_per_ton']['height_source'] == 'vertical_hole_length'


def test_estimated_footprint_and_degenerate():
    df = holes()
    df.loc[0, 'Nombre_Malla_Original'] = 'B'
    footprints = bc.estimate_malla_footprints(df, 'Nombre_Malla_Original')
    assert footprints['A']['source'] == 'estimated_hull'
    assert footprints['B']['polygon'] is None
    assert footprints['B']['reason']


def test_net_invalid_subdrill_is_blocked():
    df = holes()
    df.loc[0, 'Z_toe'] = np.nan
    df.loc[1, 'Z_toe'] = 91.
    result = bc.compute_powder_factor(df, bench_height_m=10)
    assert result['pf_g_per_ton_net'].iloc[:2].isna().all()
    assert result.loc[1, 'pf_g_per_ton_net_status'] == 'INVALID_SUBDRILL'


def test_deck_energy_and_coverage():
    df = holes()
    df['decks'] = [[{'kg': 40., 'explosive': 'ANFO'}, {'kg': 60., 'explosive': 'mystery'}]] * 4
    result = bc.compute_powder_factor(df, bench_height_m=10)
    assert result['energy_mj'].isna().all()
    assert result['energy_coverage_kg_fraction'].iloc[0] == pytest.approx(.4)
    assert result['energy_warnings'].iloc[0]
    result['section'] = 'S'
    agg = bc.aggregate_powder_factor_by_group(result, 'section', 'S', result)
    assert np.isnan(agg['energy_total_mj'])
    assert agg['energy_known_mj'] == pytest.approx(4 * 40 * 3.72)
    assert agg['energy_coverage_kg_fraction'] == pytest.approx(.4)


def test_missing_signed_deltas_and_toe_label():
    r = bc.compute_signed_deviations([{'section': 'S', 'angle_dev': 5}], 'S')
    assert np.isnan(r['avg_over']) and np.isnan(r['avg_under'])
    r = bc.compute_signed_deviations([{'section': 'S', 'delta_toe': -2}], 'S')
    assert r['source'] == 'delta_toe'


def test_loaded_column_metric():
    df = holes()
    df['Taco_m'] = [2., 12., np.nan, -1.]
    result = enrich_blast_dataframe(df)
    assert result['kg_per_meter'].iloc[0] == pytest.approx(100/12)
    assert result['kg_per_meter_loaded_column'].iloc[0] == pytest.approx(10)
    assert result['kg_per_meter_loaded_column'].iloc[1:].isna().all()


def test_missing_deck_mass_makes_coverage_unknown():
    df = holes()
    df['decks'] = [[{'kg': 40., 'explosive': 'ANFO'}, {'kg': None, 'explosive': 'ANFO'}]] * 4
    result = bc.compute_powder_factor(df, bench_height_m=10)
    assert result['energy_coverage_kg_fraction'].isna().all()


def test_section_mean_deviation_never_uses_angle():
    assert bc._deviation_column([{'section': 'S', 'angle_dev': 5}]) is None


@pytest.mark.parametrize('rho', [None, 0, float('inf'), 'invalid'])
def test_invalid_session_density_blocks_principal(rho):
    polygons = {'A': {'polygon': [(-5,-5),(15,-5),(15,15),(-5,15)], 'source': 'user_polygon'}}
    result = bc.compute_powder_factor(holes(), bench_height_m=10, rock_density_tm3=rho, boundary_polygons=polygons)
    assert result['pf_voronoi_bench_status'].eq('MISSING_DENSITY').all()
    assert result['pf_voronoi_bench_g_per_ton'].isna().all()


def test_section_ratio_uses_rock_mass_not_simple_or_charge_weighted_mean():
    df = pd.DataFrame({'section':['S','S'], 'Kilos_Cargados_real':[100.,200.],
                       'area_influence_m2':[100.,200.],
                       'pf_voronoi_bench_g_per_ton':[100.,400.],
                       'pf_voronoi_bench_status':['VALID','VALID']})
    agg = bc.aggregate_powder_factor_by_group(df,'section','S',df)
    assert agg['pf_voronoi_bench_g_per_ton_section'] == pytest.approx(200.)


def test_principal_unit_and_outside_collar():
    df = pd.concat([holes(), pd.DataFrame([{'X': 99., 'Y': 99., 'Nombre_Malla_Original':'A', 'Kilos_Cargados_real':100., 'longitud_real':12., 'Inclinacion_real':0., 'Z_collar':100., 'Z_toe':88.}])], ignore_index=True)
    polygons = {'A': {'polygon': [(-5,-5),(15,-5),(15,15),(-5,15)], 'source': 'user_polygon'}}
    result = bc.compute_powder_factor(df, bench_height_m=10, rock_density_tm3=2, boundary_polygons=polygons)
    assert result.loc[4, 'pf_voronoi_bench_status'] == 'OUTSIDE_FOOTPRINT'
    assert np.isnan(result.loc[4, 'pf_g_per_ton_net'])
    assert result.loc[0, 'pf_voronoi_bench_unit'] == 'g/t'


def test_principal_shared_site_status():
    df = pd.concat([holes(), holes().iloc[[0]]], ignore_index=True)
    polygons = {'A': {'polygon': [(-5,-5),(15,-5),(15,15),(-5,15)], 'source': 'user_polygon'}}
    result = bc.compute_powder_factor(df, bench_height_m=10, rock_density_tm3=2, boundary_polygons=polygons)
    assert result.loc[0, 'pf_voronoi_bench_area_status'] == 'shared_site'
    assert result.loc[0, 'pf_voronoi_bench_area_m2'] == pytest.approx(result.loc[4, 'pf_voronoi_bench_area_m2'])


def test_section_empty_geometry_keeps_missing_values():
    section = type('Section', (), {'name': 'S', 'origin': np.array([1000., 1000.]), 'azimuth': 90., 'length': 10., 'sector': ''})()
    rows = bc.compute_blast_geotech_correlation(holes(), [section], [{'section':'S', 'angle_dev':5.}])
    assert np.isnan(rows[0].mean_abs_deviation)
    assert np.isnan(rows[0].energy_total_mj)


def test_correlation_row_defaults_do_not_invent_zero_measurements():
    row = bc.BlastCorrelationRow('S', 0, np.nan, np.nan)
    assert np.isnan(row.energy_total_mj)
    assert np.isnan(row.pf_g_per_ton_avg)
    assert np.isnan(row.avg_over_break)


def test_deviation_column_considers_all_rows():
    assert bc._deviation_column([{'section':'S'}, {'section':'S', 'delta_crest':1.}]) == 'delta_crest'


def test_unknown_footprint_status_does_not_mask_geometry_error():
    df = holes()
    polygons = {'A': {'polygon': [(0,0),(1,1)], 'source': 'user_polygon'}}
    result = bc.compute_powder_factor(df, bench_height_m=10, rock_density_tm3=2, boundary_polygons=polygons)
    assert result['pf_voronoi_bench_status'].eq('INVALID_AREA').all()


def test_unconfirmed_event_height_blocks_principal():
    df = holes()
    df['bench_height_m'] = 15.
    df['bench_height_user_confirmed'] = False
    df['bench_height_assumption_flag'] = True
    polygons = {'A': {'polygon': [(-5,-5),(15,-5),(15,15),(-5,15)], 'source': 'user_polygon'}}
    result = bc.compute_powder_factor(df, rock_density_tm3=2, boundary_polygons=polygons)
    assert result['pf_voronoi_bench_status'].eq('MISSING_BENCH_HEIGHT').all()
    assert result['pf_voronoi_bench_g_per_ton'].isna().all()
