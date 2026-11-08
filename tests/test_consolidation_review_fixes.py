from types import SimpleNamespace

import pandas as pd
import pytest

from core.blast_hole_consolidation import consolidate_blast_holes
from core.calculo_tronadura import procesar_pozos
from core.profile_compliance import _build_match_row


def row(**changes):
    result = dict(uniqid='event', id_pozo='H1', Nombre_Malla_Original='A', Blast='B',
                  X=1., Y=2., Z_collar=100., Len=10., Incl=0., Az=0.,
                  Kilos_Cargados_real=100., Tipo_Explosivo='ANFO', Taco_m=2.,
                  fecha_tronadura='2026-01-01')
    result.update(changes)
    return result


@pytest.mark.parametrize('changes', [dict(Taco_m=4.), dict(Taco_m=4., Kilos_Cargados_real=50.)])
def test_incompatible_stemming_is_conflict(changes):
    output, report = consolidate_blast_holes(pd.DataFrame([row(), row(**changes)]))
    assert len(output) == 2
    assert report['conflicts'][0]['reason'] == 'non_charge_attribute_mismatch'
    assert output.Kilos_Cargados_real.tolist() == [100., changes.get('Kilos_Cargados_real', 100.)]


@pytest.mark.parametrize('changes', [dict(Nombre_Malla_Original='C'), dict(Blast='C')])
def test_inconsistent_event_identity_is_conflict(changes):
    output, report = consolidate_blast_holes(pd.DataFrame([row(), row(Kilos_Cargados_real=50., **changes)]))
    assert len(output) == 2
    assert report['conflicts'][0]['reason'] == 'event_identity_mismatch'


def input_frame(rows, index=None):
    return pd.DataFrame(rows, index=index).rename(columns={'Z_collar': 'Cota_Collar', 'Incl': 'Inclinacion_real', 'Az': 'Azimuth_real', 'Len': 'longitud_real'})


def test_position_is_authoritative_even_with_spoof_and_rejected_rows():
    data = input_frame([row(source_row_index=991), row(source_row_index=992, Len=None),
                        row(source_row_index=993, Kilos_Cargados_real=50.)], index=[21, 22, 23])
    result = procesar_pozos(data, geometry_user_confirmed=True, incl_convention='from_vertical',
                            z_collar_semantic='collar_elevation', return_result=True)
    accepted = result.accepted_rows[0]
    assert accepted['source_row_index'] == 0
    assert accepted['source_row_indices'] == [0, 2]
    assert [deck['source_row_index'] for deck in accepted['decks']] == [0, 2]
    assert accepted['source_row_index_user'] == 991
    assert result.rejected_rows[0]['source_row_index'] == 1


def test_algorithm_version_on_accepted_rows():
    from core import blast_hole_consolidation as module
    result = procesar_pozos(input_frame([row()]), geometry_user_confirmed=True,
                            incl_convention='from_vertical', z_collar_semantic='collar_elevation',
                            return_result=True)
    assert getattr(module, 'BLAST_ALGORITHM_VERSION', None) == 'blast-auditable.v1'
    assert result.accepted_rows[0].get('blast_algorithm_version') == 'blast-auditable.v1'


def test_missing_berm_is_not_an_evaluated_failure():
    bench = dict(bench_height=15., face_angle=70., berm_width=8., bench_number=1,
                 toe_elevation=100., crest_distance=1., toe_distance=2., spill_width=0.,
                 effective_berm_width=8.)
    design = SimpleNamespace(**bench)
    topo = SimpleNamespace(**{**bench, 'berm_width': None})
    result = _build_match_row(design, topo, SimpleNamespace(sector='s', section_name='x'),
                              {'bench_height': {'neg': 1., 'pos': 1.},
                               'face_angle': {'neg': 1., 'pos': 1.}, 'berm_width': {'min': 7.}})
    assert result['berm_status'] == '-'
    assert result['berm_score'] is None
    assert result['bench_score'] is None
