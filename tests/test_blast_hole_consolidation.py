import json

import pandas as pd
import pytest

from core.calculo_tronadura import procesar_pozos


def consolidate(rows):
    from core.blast_hole_consolidation import consolidate_blast_holes
    return consolidate_blast_holes(pd.DataFrame(rows))


def row(**changes):
    result = dict(uniqid='event', id_pozo='001', Nombre_Malla_Original='mesh',
                  X=1., Y=2., Z_collar=100., Len=10., Incl=0., Az=0.,
                  Kilos_Cargados_real=19., Tipo_Explosivo='A', Taco_m=2.,
                  fecha_tronadura='2026-01-01')
    result.update(changes)
    return result


def test_exact_copies_and_report():
    result, report = consolidate([row(), row(), row()])
    assert len(result) == 1
    assert result.iloc[0].hole_key == 'event|001'
    assert result.iloc[0].duplicate_rows_removed == 2
    assert result.iloc[0].source_row_indices == [0, 1, 2]
    assert report['exact_copies_removed'] == 2
    assert report['copies_by_malla'] == {'mesh': 2}
    assert report['rows_in'] == 3 and report['holes_out'] == 1
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('product', ['A', 'B'])
def test_decks_and_mix(product):
    result, report = consolidate([row(), row(Kilos_Cargados_real=20., Tipo_Explosivo=product)])
    hole = result.iloc[0]
    assert hole.Kilos_Cargados_real == 39.
    assert hole.n_decks == 2
    assert hole.explosive_mix == ({'A': 39.} if product == 'A' else {'A': 19., 'B': 20.})
    assert bool(hole.explosive_mixed) == (product == 'B')
    assert report['holes_with_decks'] == 1 and report['deck_rows_merged'] == 1


def test_repeated_decks_are_deduplicated_first():
    result, report = consolidate([row()] * 3 + [row(Kilos_Cargados_real=20.)] * 3)
    assert result.iloc[0].n_decks == 2
    assert result.iloc[0].Kilos_Cargados_real == 39.
    assert report['exact_copies_removed'] == 4
    assert report['deck_rows_merged'] == 1


@pytest.mark.parametrize('other', [row(uniqid='other'), row(id_pozo='002')])
def test_identity_not_coordinates(other):
    result, _ = consolidate([row(), other])
    assert len(result) == 2


def test_missing_compared_value_does_not_prove_copy():
    result, report = consolidate([row(Taco_m=None), row(Taco_m=None)])
    assert report['exact_copies_removed'] == 0
    assert len(result) == 2


def test_missing_comparison_does_not_block_proven_duplicates():
    result, report = consolidate([row(), row(), row(Taco_m=None)])
    assert len(result) == 2
    assert report['exact_copies_removed'] == 1
    assert result.iloc[0].source_row_indices == [0, 1]


def test_geometry_conflict_preserves_rows():
    result, report = consolidate([row(), row(X=3.)])
    assert len(result) == 2
    assert report['conflicts'][0]['source_row_indices'] == [0, 1]


def test_conflict_with_other_missing_geometry():
    result, report = consolidate([row(X=1., Y=None), row(X=3., Y=None)])
    assert len(result) == 2
    assert len(report['conflicts']) == 1


def test_missing_identity_and_fallback():
    result, report = consolidate([row(uniqid=None), row(uniqid=None), row(id_pozo=None)])
    assert len(result) == 2
    assert result.iloc[0].hole_key == 'mesh|001'
    assert report['unmerged_missing_identity'] == 1


def test_idempotence():
    first, _ = consolidate([row()] * 3 + [row(Kilos_Cargados_real=20.)] * 3)
    from core.blast_hole_consolidation import consolidate_blast_holes
    second, _ = consolidate_blast_holes(first)
    pd.testing.assert_frame_equal(first, second)


def test_charge_alias_and_missing_mass():
    first = row(Tipo_Explosivo='A')
    second = row(Tipo_Explosivo='B', Kilos_Cargados_real=None)
    for entry in (first, second):
        entry['Carga_kg'] = entry.pop('Kilos_Cargados_real')
    result, _ = consolidate([first, second])
    assert len(result) == 1
    assert pd.isna(result.iloc[0].Kilos_Cargados_real)
    assert result.iloc[0].decks[0]['kg'] == 19.
    assert result.iloc[0].decks[1]['kg'] is None


def test_processing_paths_share_consolidation():
    data = pd.DataFrame([row(), row(), row(Kilos_Cargados_real=20.)]).rename(columns={'Z_collar': 'Cota_Collar', 'Incl': 'Inclinacion_real', 'Az': 'Azimuth_real', 'Len': 'longitud_real'})
    kwargs = dict(geometry_user_confirmed=True, incl_convention='from_vertical', z_collar_semantic='collar_elevation')
    legacy = procesar_pozos(data, **kwargs)
    result = procesar_pozos(data, return_result=True, **kwargs)
    assert len(legacy) == 4
    assert len(legacy[0]) == len(result.accepted_dataframe) == 1
    assert result.rows_received == 3
    assert result.consolidation_report['exact_copies_removed'] == 1
    assert result.to_dict()['consolidation_report'] == result.consolidation_report
    assert result.accepted_rows[0]['n_decks'] == 2
