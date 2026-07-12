from dataclasses import replace

import pandas as pd
import pytest

from core.config import DRILL_COMPLIANCE
from core.drill_compliance import compute_drill_compliance


def hole(label="H-1", x=100.0, y=200.0, z=1015.0, incl=10.0, az=179.0, length=16.0, kg=100.0, malla="M-1"):
    return {
        "Pozo": label,
        "X": x,
        "Y": y,
        "Z_collar": z,
        "Incl": incl,
        "Az": az,
        "Len": length,
        "Kilos": kg,
        "malla": malla,
    }


def test_label_match_has_seven_deviations():
    result = compute_drill_compliance(pd.DataFrame([hole()]), pd.DataFrame([hole(x=100.2)]))
    row = result["per_hole"].iloc[0]
    assert row["match_method"] == "label"
    assert row["delta_x"] == pytest.approx(0.2)
    assert set(["delta_x", "delta_y", "delta_z_collar", "delta_incl", "delta_az", "delta_len", "delta_kg_pct"]) <= set(result["per_hole"].columns)


def test_unmatched_label_is_reported():
    result = compute_drill_compliance(pd.DataFrame([hole()]), pd.DataFrame([hole("H-2")]))
    assert result["per_hole"].empty
    assert result["unmatched"] == {"design": ["H-1"], "actual": ["H-2"]}


def test_nearest_match_respects_radius():
    design = pd.DataFrame([hole(x=101.0, y=199.0)])
    actual = pd.DataFrame([hole("A", x=100.0, y=200.0), hole("B", x=110.0, y=210.0)])
    result = compute_drill_compliance(design, actual, match_by="nearest")
    assert result["per_hole"]["match_method"].tolist() == ["nearest"]
    assert result["unmatched"]["actual"] == ["B"]


def test_label_auto_falls_back_to_nearest():
    design = pd.DataFrame([{key: value for key, value in hole().items() if key != "Pozo"}])
    with pytest.warns(UserWarning, match="falling back"):
        result = compute_drill_compliance(design, pd.DataFrame([hole()]))
    assert result["per_hole"].iloc[0]["match_method"] == "nearest"


def test_azimuth_wrap_is_circular():
    result = compute_drill_compliance(pd.DataFrame([hole(az=179.0)]), pd.DataFrame([hole(az=181.0)]))
    assert result["per_hole"].iloc[0]["delta_az"] == pytest.approx(2.0)


@pytest.mark.parametrize("design,actual,message", [
    (None, pd.DataFrame([hole()]), "No design"),
    (pd.DataFrame([hole()]), pd.DataFrame(), "No actual"),
    (pd.DataFrame([{"Pozo": "H-1"}]), pd.DataFrame([hole()]), "spatial matching impossible"),
])
def test_empty_and_missing_spatial_inputs_are_graceful(design, actual, message):
    with pytest.warns(UserWarning, match=message):
        result = compute_drill_compliance(design, actual)
    assert result["per_hole"].empty
    assert result["compliance_score"] is None
    assert result["warnings"]


def test_all_dimensions_score_and_tolerance_override():
    design = pd.DataFrame([hole(), hole("H-2")])
    actual = pd.DataFrame([hole(x=101.0), hole("H-2")])
    assert compute_drill_compliance(design, actual)["compliance_score"] == pytest.approx(0.5)
    custom = replace(DRILL_COMPLIANCE, delta_x_m=1.0)
    assert compute_drill_compliance(design, actual, tolerances=custom)["compliance_score"] == 1.0


def test_per_group_malla_contains_dimension_metrics():
    design = pd.DataFrame([hole(f"H-{i}", malla="M-1" if i < 15 else "M-2") for i in range(30)])
    actual = design.copy()
    result = compute_drill_compliance(design, actual, group_by="malla")
    assert len(result["per_group"]) == 2
    assert set(result["per_group"]["n"]) == {15}
    assert len([column for column in result["per_group"] if column.startswith("mean_abs_")]) == 7
    assert len([column for column in result["per_group"] if column.startswith("within_tol_pct_")]) == 7
