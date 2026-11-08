from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from core.blast_correlation import compute_powder_factor, aggregate_powder_factor_by_group, compute_blast_geotech_correlation
from core.blast_metrics import enrich_blast_dataframe


def holes():
    return pd.DataFrame({'X': [0., 10., 0., 10.], 'Y': [0., 0., 10., 10.], 'Nombre_Malla_Original': ['A'] * 4, 'Kilos_Cargados_real': [100.] * 4, 'longitud_real': [12.] * 4, 'Inclinacion_real': [0.] * 4, 'Z_collar': [100.] * 4, 'Z_toe': [88.] * 4, 'Tipo_Explosivo': ['ANFO'] * 4, 'Burden': [5.] * 4, 'Esp': [10.] * 4, 'Taco_m': [2.] * 4})


def test_recomputes_all_density_dependent_factors_using_frozen_areas():
    polygon = {'A': {'polygon': [(-5,-5),(15,-5),(15,15),(-5,15)], 'source': 'user'}}
    frame = compute_powder_factor(holes(), bench_height_m=10, rock_density_tm3=2, boundary_polygons=polygon)
    frame['section'] = 'S'
    old = aggregate_powder_factor_by_group(frame, 'section', 'S', frame, rock_density_tm3=2)
    new = aggregate_powder_factor_by_group(frame, 'section', 'S', frame, rock_density_tm3=4)
    for key in ['pf_g_per_ton_avg', 'pf_g_per_ton_net_avg', 'pf_voronoi_bench_g_per_ton_section']:
        assert new[key] == pytest.approx(old[key] / 2)
    sec = SimpleNamespace(name='S', origin=np.array([0., 0.]), azimuth=90., length=100., sector='A')
    row = compute_blast_geotech_correlation(frame, [sec], [], tolerance=50, rock_density_tm3=2, sector_density={'A': 4})[0]
    assert row.rock_density_used == 4
    assert row.pf_g_per_ton_avg == pytest.approx(old['pf_g_per_ton_avg'] / 2)


def test_unknown_masses_and_partial_energy_are_not_totals():
    df = holes()
    df['decks'] = [[{'kg': 40., 'explosive': 'ANFO'}, {'kg': None, 'explosive': 'ANFO'}]] * 4
    df['Kilos_Cargados_real'] = [100., np.nan, np.nan, np.nan]
    df = compute_powder_factor(df, bench_height_m=10, rock_density_tm3=2)
    df['section'] = 'S'
    agg = aggregate_powder_factor_by_group(df, 'section', 'S', df)
    assert np.isnan(agg['kg_total'])
    assert agg['n_kg_known'] == 1 and agg['n_kg_missing'] == 3
    assert np.isnan(agg['energy_total_mj'])
    assert agg['energy_known_mj'] == pytest.approx(4 * 40 * 3.72)
    assert np.isnan(agg['energy_coverage_kg_fraction'])
    sec = SimpleNamespace(name='S', origin=np.array([0., 0.]), azimuth=90., length=100., sector='')
    row = compute_blast_geotech_correlation(df, [sec], [], tolerance=50)[0]
    assert np.isnan(row.total_kg)
    assert row.n_kg_known == 1 and row.n_kg_missing == 3
    assert row.energy_known_mj == pytest.approx(4 * 40 * 3.72)


def test_partial_energy_with_known_mass_is_not_total():
    df = holes()
    df['decks'] = [[{'kg': 40., 'explosive': 'ANFO'}, {'kg': 60., 'explosive': 'unknown'}]] * 4
    frame = compute_powder_factor(df, bench_height_m=10)
    frame['section'] = 'S'
    agg = aggregate_powder_factor_by_group(frame, 'section', 'S', frame)
    assert np.isnan(agg['energy_total_mj'])
    assert agg['energy_known_mj'] == pytest.approx(4 * 40 * 3.72)
    assert agg['energy_coverage_kg_fraction'] == pytest.approx(.4)


def test_decks_with_inconsistent_stemming_block_loaded_column():
    df = holes()
    df['decks'] = [[{'taco_m': 2.}, {'taco_m': 4.}], [{'taco_m': 2.}, {'taco_m': 2.}], [{'taco_m': None}, {'taco_m': 2.}], [{'taco_m': 2.}, {'taco_m': 2.}]]
    df.loc[3, 'Taco_m'] = 13.
    df.at[3, 'decks'] = [{'taco_m': 13.}]
    result = enrich_blast_dataframe(df)
    assert np.isnan(result.loc[0, 'kg_per_meter_loaded_column'])
    assert result.loc[0, 'kg_per_meter_loaded_column_warning'] == 'inconsistent_deck_stemming'
    assert result.loc[1, 'kg_per_meter_loaded_column'] == pytest.approx(10)
    assert result.loc[2, 'kg_per_meter_loaded_column'] == pytest.approx(10)
    assert np.isnan(result.loc[3, 'altura_carga_m'])
    assert result.loc[3, 'altura_carga_warning'] == 'stemming_exceeds_length'


def test_burden_and_spacing_sources_are_independent():
    df = holes().drop(columns=['Esp'])
    result = compute_powder_factor(df, bench_height_m=10)
    assert result.loc[0, 'burden_source'] == 'design_column'
    assert result.loc[0, 'spacing_source'] == 'knn_proxy'
    assert result.loc[0, 'burden_spacing_source'] == 'mixed'


def test_net_status_explains_spatial_and_nonpositive_height():
    df = holes()
    df.loc[0, ['X', 'Y']] = [99., 99.]
    df.loc[1, 'Z_toe'] = 70.
    polygon = {'A': {'polygon': [(-5,-5),(15,-5),(15,15),(-5,15)], 'source': 'user'}}
    result = compute_powder_factor(df, bench_height_m=10, rock_density_tm3=2, boundary_polygons=polygon)
    assert result.loc[0, 'pf_g_per_ton_net_status'] == 'OUTSIDE_FOOTPRINT'
    assert result.loc[1, 'pf_g_per_ton_net_status'] == 'INVALID_NET_HEIGHT'
    assert not ((result['pf_g_per_ton_net_status'] == 'VALID') & result['pf_g_per_ton_net'].isna()).any()
