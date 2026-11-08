import json

import pandas as pd
import pytest

from core.calculo_tronadura import procesar_pozos

GRID = [(0, 0), (10, 0), (20, 0), (0, 10), (10, 10), (20, 10)]


def _raw(with_density_column=False):
    rows = []
    for i, (x, y) in enumerate(GRID):
        rows.append({
            "id_pozo": f"H{i}",
            "Nombre_Malla_Original": "A",
            "X": float(x),
            "Y": float(y),
            "Cota_Collar": 100.0,
            "Inclinacion_real": 0.0,
            "Azimuth_real": 0.0,
            "longitud_real": 12.0,
            "Kilos_Cargados_real": 100.0,
            "Tipo_Explosivo": "ANFO",
        })
    rows.append({
        "id_pozo": "B0",
        "Nombre_Malla_Original": "B",
        "X": 100.0,
        "Y": 100.0,
        "Cota_Collar": 100.0,
        "Inclinacion_real": 0.0,
        "Azimuth_real": 0.0,
        "longitud_real": 12.0,
        "Kilos_Cargados_real": 100.0,
        "Tipo_Explosivo": "ANFO",
    })
    return pd.DataFrame(rows)


def _result(df=None, **kwargs):
    return procesar_pozos(
        _raw() if df is None else df,
        geometry_user_confirmed=True,
        incl_convention="from_vertical",
        bench_height_m=10.0,
        return_result=True,
        **kwargs,
    )


def test_default_estimates_footprint_and_labels_source():
    result = _result(rock_density_tm3=2.0)
    df = result.accepted_dataframe
    malla_a = df[df["Nombre_Malla_Original"] == "A"]
    assert malla_a["pf_voronoi_bench_source"].eq("footprint:estimated_hull").all()
    assert malla_a["pf_voronoi_bench_status"].eq("VALID").all()
    assert malla_a["pf_voronoi_bench_g_per_ton"].notna().all()


def test_report_counts_and_method_are_auditable():
    result = _result(rock_density_tm3=2.0)
    report = result.footprint_report
    assert report["mode"] == "estimated_hull"
    assert report["buffer_factor"] == 0.5
    assert report["method"] == (
        "convex hull of unique collar sites buffered by 0.5×median "
        "nearest-neighbour spacing"
    )
    assert report["n_mallas"] == 2
    assert report["n_estimated"] == 1
    assert report["n_user"] == 0
    assert report["n_missing"] == 1
    assert report["missing_reasons"]["B"] == "insufficient_noncollinear_sites"
    json.dumps(report, allow_nan=False)


def test_estimated_area_is_conserved_inside_footprint():
    result = _result(rock_density_tm3=2.0)
    df = result.accepted_dataframe
    malla_a = df[df["Nombre_Malla_Original"] == "A"]
    domain = float(malla_a["pf_voronoi_bench_domain_area_m2"].iloc[0])
    assigned = float(malla_a["pf_voronoi_bench_assigned_area_m2"].iloc[0])
    assert domain > 0
    assert assigned <= domain


def test_insufficient_sites_stays_missing_with_reason():
    result = _result(rock_density_tm3=2.0)
    df = result.accepted_dataframe
    malla_b = df[df["Nombre_Malla_Original"] == "B"]
    assert malla_b["pf_voronoi_bench_status"].eq("MISSING_FOOTPRINT").all()
    assert malla_b["pf_voronoi_bench_g_per_ton"].isna().all()


def test_user_polygons_override_estimated_per_malla():
    polygons = {
        "A": {
            "polygon": [(-5.0, -5.0), (25.0, -5.0), (25.0, 15.0), (-5.0, 15.0)],
            "source": "user_polygon",
        }
    }
    result = _result(rock_density_tm3=2.0, boundary_polygons=polygons)
    df = result.accepted_dataframe
    malla_a = df[df["Nombre_Malla_Original"] == "A"]
    assert malla_a["pf_voronoi_bench_source"].eq("footprint:user_polygon").all()
    report = result.footprint_report
    assert report["n_user"] == 1
    assert report["n_estimated"] == 0
    assert report["n_missing"] == 1


def test_mode_none_keeps_missing_footprint():
    result = _result(footprint_mode="none", rock_density_tm3=2.0)
    df = result.accepted_dataframe
    assert df["pf_voronoi_bench_status"].eq("MISSING_FOOTPRINT").all()
    assert df["pf_voronoi_bench_source"].eq("").all()
    report = result.footprint_report
    assert report["mode"] == "none"
    assert report["n_mallas"] == 2
    assert report["n_estimated"] == 0
    assert report["n_user"] == 0
    assert report["n_missing"] == 2


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        _result(footprint_mode="bbox")


def test_density_remains_an_explicit_prerequisite():
    result = _result()
    df = result.accepted_dataframe
    malla_a = df[df["Nombre_Malla_Original"] == "A"]
    assert malla_a["pf_voronoi_bench_status"].eq("MISSING_DENSITY").all()
    assert df["pf_voronoi_bench_g_per_ton"].isna().all()


def test_legacy_tuple_signature_is_preserved():
    out = procesar_pozos(
        _raw(),
        geometry_user_confirmed=True,
        incl_convention="from_vertical",
        bench_height_m=10.0,
    )
    assert isinstance(out, tuple) and len(out) == 4
    assert not out[0].empty


def test_processing_result_dict_carries_footprint_report():
    payload = _result(rock_density_tm3=2.0).to_dict()
    assert payload["footprint_report"]["mode"] == "estimated_hull"
    assert payload["footprint_report"]["n_estimated"] == 1


def test_schema_typed_footprint_report():
    from api.schemas import BlastFootprintReport, BlastSessionSummary

    report = BlastFootprintReport(
        mode="estimated_hull",
        n_mallas=2,
        n_estimated=1,
        n_user=0,
        n_missing=1,
        buffer_factor=0.5,
        method="convex hull of unique collar sites buffered by 0.5×median nearest-neighbour spacing",
    )
    summary = BlastSessionSummary(n_holes=1, footprint_report=report)
    assert summary.footprint_report.mode == "estimated_hull"
