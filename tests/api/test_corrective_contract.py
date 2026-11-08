import io
import json

import api.database as db
from api.routers.process import _safe_float
from core.blast_correlation import PF_DEFINITIONS


def test_safe_float_preserves_missing_and_zero():
    assert _safe_float(None) is None
    assert _safe_float(float('nan')) is None
    assert _safe_float(float('inf')) is None
    assert _safe_float(0) == 0


def test_definitions_are_exposed(client):
    response = client.get('/api/v1/blast/definitions')
    assert response.status_code == 200
    definitions = response.json()
    assert all(definitions[key] == value for key, value in PF_DEFINITIONS.items())
    assert definitions["pf_voronoi_bench_g_per_ton"]["unit"] == "g/t"
    assert definitions["pf_voronoi_bench_g_per_ton"]["denominator"] == "footprint_voronoi_area*bench_height*density"


def test_upload_report_persists_and_primary_pf_is_nullable(client):
    sid = db.create_session()
    csv = ('Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real,Kilos_Cargados_real,Taco_m,id_pozo,Nombre_Malla_Original,Tipo_Explosivo,fecha_tronadura\n'
           '1,2,100,0,0,10,19,2,H1,M1,ANFO,2026-01-01\n'
           '1,2,100,0,0,10,19,2,H1,M1,ANFO,2026-01-01\n')
    form = {'session_id': sid, 'geometry_user_confirmed': 'true', 'incl_convention': 'from_vertical',
            'incl_sign_convention': 'ABSOLUTE_VALUE', 'az_convention': 'CLOCKWISE_FROM_NORTH',
            'angle_unit': 'degrees', 'bench_height_m': '15', 'incl_source_column': 'Inclinacion_real',
            'az_source_column': 'Azimuth_real'}
    response = client.post('/api/v1/blast/upload', files={'file': ('p.csv', io.BytesIO(csv.encode()), 'text/csv')}, data=form, headers={'X-Session-ID': sid})
    assert response.status_code == 200, response.text
    body = response.json()
    report = body['consolidation_report']
    assert report["rows_in"] == 2
    assert report["exact_copies_removed"] == 1
    assert report["copies_by_malla"] == {"M1": 1}
    assert body["n_holes"] == 1
    assert report == db.get_settings(sid)['blast_upload_meta']['consolidation_report']
    summary = client.get(f'/api/v1/blast/{sid}/summary', headers={'X-Session-ID': sid}).json()
    assert summary['consolidation_report'] == report
    assert body['accepted_rows'][0]['pf_voronoi_bench_g_per_ton'] is None
    assert body['accepted_rows'][0]['pf_voronoi_bench_status'] == 'MISSING_FOOTPRINT'
    first = client.get('/api/v1/blast/holes/3d', headers={'X-Session-ID': sid}).json()
    second = client.get('/api/v1/blast/holes/3d', headers={'X-Session-ID': sid}).json()
    assert first['data_revision'] == second['data_revision']
    attrs = first['holes'][0]['attributes']
    assert attrs['pf_voronoi_bench_g_per_ton'] is None
    assert attrs['pf_voronoi_bench_status'] == 'MISSING_FOOTPRINT'
    assert {'kg_per_meter_loaded_column', 'n_decks', 'explosive_mixed', 'burden_spacing_source'} <= attrs.keys()
    json.dumps(db.get_settings(sid), allow_nan=False)


def test_damage_model_drops_missing_not_measured_zero(monkeypatch):
    from types import SimpleNamespace
    from api.routers import process

    rows = [SimpleNamespace(section_name="missing", pf_g_per_ton_avg=None, avg_over_break=0.2),
            SimpleNamespace(section_name="unknown", pf_g_per_ton_avg=100, avg_over_break=float("nan")),
            SimpleNamespace(section_name="measured", pf_g_per_ton_avg=100, avg_over_break=0.0)]
    monkeypatch.setattr(process, "_resolve_blast_correlation_rows", lambda *args: (rows, [], 1, {}, ([], [])))
    result = process._build_damage_model_sync("isolated", None)
    assert [point.section_name for point in result.points] == ["measured"]
    assert result.points[0].over_break == 0.0


def test_achievement_assumptions_describe_renormalization(client):
    body = client.get('/api/v1/process/design-achievement').json()
    assert any('renormal' in assumption for assumption in body['metadata']['assumptions'])


def test_profile_missing_burden_and_spacing_are_null():
    import pandas as pd
    from api.routers.process import _projected_to_holes

    frame = pd.DataFrame([{"X": 1, "Y": 2, "Z_collar": 100, "dist_along": 1,
                           "dist_perp": 0, "Burden": float("inf"), "Esp": float("nan")}])
    hole = _projected_to_holes(frame, 2, "test")[0]
    assert hole.burden is None
    assert hole.spacing is None


def test_damage_model_does_not_round_away_valid_small_samples(monkeypatch):
    from types import SimpleNamespace
    from api.routers import process

    rows = [SimpleNamespace(section_name="small", pf_g_per_ton_avg=1e-14, avg_over_break=0)]
    monkeypatch.setattr(process, "_resolve_blast_correlation_rows", lambda *args: (rows, [], 1, {}, ([], [])))
    assert len(process._build_damage_model_sync("isolated", None).points) == 1


def test_legacy_records_missing_metrics_remain_null():
    import pandas as pd
    from api.routers.blast import _df_to_hole_records

    row = _df_to_hole_records(pd.DataFrame([{"X": 1}]))[0]
    assert row["carga"] is None
    assert row["descarga"] is None


def test_linear_charge_definitions(client):
    definitions = client.get("/api/v1/blast/definitions").json()
    assert definitions["kg_per_meter"] == {"formula": "Q/L", "unit": "kg/m"}
    assert definitions["kg_per_meter_loaded_column"] == {"formula": "Q/(L-T)", "unit": "kg/m"}


def test_correlation_status_counts_and_histogram(client):
    sid = db.create_session()
    headers = {"X-Session-ID": sid}
    db.save_sections(sid, [{"name": "A", "origin": [0, 0], "azimuth": 0, "length": 100},
                           {"name": "B", "origin": [1000, 0], "azimuth": 0, "length": 100}])
    holes = [
        {"X": 0, "Y": 5, "Z_collar": 100, "Z_toe": 90, "Len": 10, "Kilos_Cargados_real": 20, "Taco_m": 2, "kg_per_meter": 2, "kg_per_meter_loaded_column": 2.5, "pf_voronoi_bench_status": "MISSING_FOOTPRINT", "area_influence_m2": None},
        {"X": 0, "Y": 6, "Z_collar": 100, "Z_toe": 90, "Len": 10, "Kilos_Cargados_real": 0, "Taco_m": 2, "kg_per_meter": 0, "kg_per_meter_loaded_column": None, "pf_voronoi_bench_status": "MISSING_HEIGHT", "area_influence_m2": None},
        {"X": 1000, "Y": 5, "Z_collar": 100, "Z_toe": 90, "Len": 10, "Kilos_Cargados_real": 10, "Taco_m": 2, "kg_per_meter": 1, "kg_per_meter_loaded_column": 1.25, "pf_voronoi_bench_status": "MISSING_FOOTPRINT", "area_influence_m2": None},
    ]
    db.save_settings(sid, {"blast_holes": holes})
    db.save_results(sid, [{"section": "A", "delta_crest": 0.3}])
    response = client.get("/api/v1/process/blast-correlation", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    rows = {row["section_name"]: row for row in body["rows"]}
    assert rows["A"]["pf_voronoi_bench_status_counts"] == {"MISSING_FOOTPRINT": 1, "MISSING_HEIGHT": 1}
    assert rows["B"]["pf_voronoi_bench_status_counts"] == {"MISSING_FOOTPRINT": 1}
    assert rows["A"]["pf_voronoi_bench_g_per_ton_section"] is None
    assert body["kg_per_meter"] == [2.0, 0.0, 1.0]
    assert body["kg_per_meter_loaded_column"] == [2.5, 1.25]
    assert body["carga"] == body["kg_per_meter"]


def test_histogram_excludes_nonfinite_values():
    import pandas as pd
    from api.routers.process import _blast_histogram_values

    values = _blast_histogram_values(pd.DataFrame({"kg_per_meter": [0, float("nan"), float("inf")],
                                                   "kg_per_meter_loaded_column": [0, float("nan"), float("-inf")]}))
    assert values[0] == [0.0]
    assert values[2] == [0.0]


def test_correlation_computes_missing_footprint_status_with_core(client):
    sid = db.create_session()
    headers = {"X-Session-ID": sid}
    db.save_sections(sid, [{"name": "A", "origin": [0, 0], "azimuth": 0, "length": 100}])
    db.save_settings(sid, {"blast_holes": [{"X": 0, "Y": 5, "Z_collar": 100, "Z_toe": 90,
                                             "Len": 10, "Kilos_Cargados_real": 20, "Taco_m": 2}]})
    db.save_results(sid, [{"section": "A", "delta_crest": 0.3}])
    response = client.get("/api/v1/process/blast-correlation", headers=headers)
    assert response.status_code == 200, response.text
    row = response.json()["rows"][0]
    assert row["num_wells"] == 1
    assert row["pf_voronoi_bench_status_counts"] == {"MISSING_FOOTPRINT": 1}
    assert row["pf_voronoi_bench_g_per_ton_section"] is None


def test_correlation_reports_unknown_legacy_status(client):
    sid = db.create_session()
    headers = {"X-Session-ID": sid}
    db.save_sections(sid, [{"name": "A", "origin": [0, 0], "azimuth": 0, "length": 100}])
    db.save_settings(sid, {"blast_holes": [{"X": 0, "Y": 5, "Z_collar": 100, "Z_toe": 90,
                                             "Len": 10, "Kilos_Cargados_real": 20, "area_influence_m2": 4}]})
    db.save_results(sid, [{"section": "A", "delta_crest": 0.3}])
    response = client.get("/api/v1/process/blast-correlation", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["rows"][0]["pf_voronoi_bench_status_counts"] == {"UNKNOWN": 1}


RESULTS_RETURNED_KEYS = frozenset({
    "angle_design", "angle_dev", "angle_real", "angle_score",
    "angle_status", "bench_num", "bench_num_topo", "bench_score",
    "berm_design", "berm_dev", "berm_min", "berm_real",
    "berm_remnant_area_m2", "berm_remnant_max_m", "berm_score", "berm_status",
    "delta_crest", "delta_toe", "design_bench_state", "effective_berm",
    "effective_berm_status", "excavation_debt_area_m2",
    "excavation_debt_thickness_max_m", "excavation_debt_thickness_mean_m",
    "floor_offset_m", "floor_status", "guided_angle", "guided_angle_status",
    "guided_berm", "guided_berm_remnant_area_m2", "guided_berm_remnant_max_m",
    "guided_berm_status", "guided_delta_crest", "guided_delta_crest_status",
    "guided_delta_toe", "guided_delta_toe_status",
    "guided_excavation_debt_area_m2", "guided_floor_offset_m",
    "guided_floor_offset_status", "guided_height", "guided_height_status",
    "guided_remaining_thickness_max_m", "guided_remaining_thickness_mean_m",
    "guided_warnings", "height_design", "height_dev", "height_real",
    "height_score", "height_status", "level", "proposal_status",
    "proposed_angle", "proposed_angle_source", "proposed_angle_status",
    "proposed_bench_score", "proposed_berm", "proposed_berm_source",
    "proposed_berm_status", "proposed_crest_source", "proposed_crest_status",
    "proposed_delta_crest", "proposed_delta_toe", "proposed_evaluable",
    "proposed_exclusion_reason", "proposed_height", "proposed_height_source",
    "proposed_height_status", "proposed_source", "proposed_toe_source",
    "proposed_toe_status", "section", "section_score", "section_status",
    "sector", "spill_width", "split_bench", "split_of", "type",
})

NEW_RESULT_KEYS = frozenset({
    "angle_score", "bench_score", "berm_dev", "berm_remnant_area_m2",
    "berm_remnant_max_m", "berm_score", "effective_berm",
    "effective_berm_status", "floor_tolerance_used",
    "guided_berm_remnant_area_m2", "guided_berm_remnant_max_m",
    "guided_warnings", "height_score", "section_score", "section_status",
    "spill_width",
})

NEW_NUMERIC_RESULT_KEYS = frozenset({
    "angle_score", "bench_score", "berm_dev", "berm_remnant_area_m2",
    "berm_remnant_max_m", "berm_score", "effective_berm",
    "guided_berm_remnant_area_m2", "guided_berm_remnant_max_m",
    "height_score", "section_score", "spill_width",
})


def _comparison_schema_fields():
    import api.schemas as schemas

    return set(schemas.ComparisonResult.model_fields)


def _comparison_types_ts_fields():
    import re
    from pathlib import Path

    types_path = Path(__file__).resolve().parents[2] / "web" / "src" / "api" / "types.ts"
    match = re.search(
        r"export interface ComparisonResult \{(.*?)\n\}",
        types_path.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert match is not None, "ComparisonResult interface missing in types.ts"
    return set(re.findall(r"^\s{2}([A-Za-z_][A-Za-z0-9_]*)\??:", match.group(1), re.MULTILINE))


def test_process_results_keys_are_declared_in_schema():
    undeclared = sorted(RESULTS_RETURNED_KEYS - _comparison_schema_fields())
    assert undeclared == []


def test_new_result_keys_are_optional_and_nullable():
    import api.schemas as schemas

    for key in sorted(NEW_RESULT_KEYS):
        field = schemas.ComparisonResult.model_fields[key]
        assert field.is_required() is False, key


def test_schema_contract_matches_web_types():
    schema_fields = _comparison_schema_fields()
    assert schema_fields == _comparison_types_ts_fields(), {
        "schema_only": sorted(schema_fields - _comparison_types_ts_fields()),
        "types_only": sorted(_comparison_types_ts_fields() - schema_fields),
    }


def test_proposed_row_keys_are_declared_in_schema():
    from api.routers.process import PROPOSED_ROW_KEYS

    assert PROPOSED_ROW_KEYS <= _comparison_schema_fields()


def test_new_numeric_keys_survive_strict_json():
    from api.routers import process
    from api.schemas import ComparisonResult

    row = {
        "section": "S-16", "sector": "A", "bench_num": 1, "bench_num_topo": 1,
        "type": "MATCH", "level": "85",
        "height_status": "CUMPLE", "angle_status": "CUMPLE", "berm_status": "CUMPLE",
        "guided_warnings": ["incline_berm"],
    }
    for index, key in enumerate(sorted(NEW_NUMERIC_RESULT_KEYS)):
        row[key] = float("nan") if index % 2 == 0 else float("inf")
    finalized = process._finalize_proposal_rows([row], True, None, {"max": 0.5})
    clean = finalized[0]
    assert clean["floor_tolerance_used"] == {"max": 0.5}
    for key in sorted(NEW_NUMERIC_RESULT_KEYS):
        assert clean[key] is None, key
    assert clean["guided_warnings"] == ["incline_berm"]
    assert clean["proposal_status"] == "current"
    json.dumps(finalized, allow_nan=False)
    validated = ComparisonResult(**clean)
    assert validated.floor_tolerance_used == {"max": 0.5}
