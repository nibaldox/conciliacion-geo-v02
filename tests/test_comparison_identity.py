import pytest

from core import compare_design_vs_asbuilt
from core.param_extractor import BenchParams, ExtractionResult


def _bench(bench_number, crest_distance, toe_distance, crest_elevation=3900.0):
    return BenchParams(
        bench_number=bench_number,
        crest_elevation=crest_elevation,
        crest_distance=crest_distance,
        toe_elevation=crest_elevation - 15.0,
        toe_distance=toe_distance,
        bench_height=15.0,
        face_angle=70.0,
        berm_width=9.0,
    )


def _params(benches):
    return ExtractionResult(section_name="S-01", sector="Test", benches=benches)


@pytest.mark.parametrize(
    "crest_distance,toe_distance,direction",
    [(110.0, 100.0, 1.0), (100.0, 110.0, -1.0)],
)
@pytest.mark.parametrize(
    "expected_crest_delta,expected_toe_delta", [(-3.0, 1.0), (3.0, -1.0)]
)
def test_match_preserves_design_and_topo_ids_and_signed_endpoint_deltas(
    sample_tolerances,
    crest_distance,
    toe_distance,
    direction,
    expected_crest_delta,
    expected_toe_delta,
):
    design = _bench(1, crest_distance, toe_distance)
    topo = _bench(
        2,
        crest_distance + direction * expected_crest_delta,
        toe_distance + direction * expected_toe_delta,
    )

    comparisons = compare_design_vs_asbuilt(
        _params([design]), _params([topo]), sample_tolerances
    )

    assert len(comparisons) == 1
    match = comparisons[0]
    assert match["type"] == "MATCH"
    assert match["bench_num"] == 1
    assert match["bench_num_topo"] == 2
    assert match["delta_crest"] == expected_crest_delta
    assert match["delta_toe"] == expected_toe_delta


@pytest.mark.parametrize(
    "crest_distance,toe_distance", [(110.0, 100.0), (100.0, 110.0)]
)
def test_exact_match_has_zero_crest_and_toe_deltas(
    sample_tolerances, crest_distance, toe_distance
):
    design = _bench(1, crest_distance, toe_distance)
    topo = _bench(2, crest_distance, toe_distance)

    comparison = compare_design_vs_asbuilt(
        _params([design]), _params([topo]), sample_tolerances
    )[0]

    assert comparison["type"] == "MATCH"
    assert comparison["bench_num"] == 1
    assert comparison["bench_num_topo"] == 2
    assert comparison["delta_crest"] == 0.0
    assert comparison["delta_toe"] == 0.0


def test_missing_and_extra_rows_keep_identity_without_invented_deltas(sample_tolerances):
    design = _bench(7, 110.0, 100.0, crest_elevation=3900.0)
    topo = _bench(22, 110.0, 100.0, crest_elevation=3860.0)

    comparisons = compare_design_vs_asbuilt(
        _params([design]), _params([topo]), sample_tolerances
    )

    missing = next(row for row in comparisons if row["type"] == "MISSING")
    extra = next(row for row in comparisons if row["type"] == "EXTRA")

    assert missing["bench_num"] == 7
    assert missing["bench_num_topo"] is None
    assert missing["height_real"] is None
    assert missing["height_dev"] is None
    assert missing["angle_real"] is None
    assert missing["angle_dev"] is None
    assert missing["delta_crest"] is None
    assert missing["delta_toe"] is None
    assert extra["bench_num"] == 999
    assert extra["bench_num_topo"] == 22
    assert extra["height_design"] is None
    assert extra["height_dev"] is None
    assert extra["angle_design"] is None
    assert extra["angle_dev"] is None
    assert extra["delta_crest"] is None
    assert extra["delta_toe"] is None
