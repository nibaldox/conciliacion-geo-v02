"""Guided PROPOSAL in the Streamlit UI (wave 10): processing + presentation.

``ui.step3_analysis`` must compare via ``compare_design_vs_asbuilt_guided``
keeping every official field identical; the profiles view and the dashboard
show the proposal next to the official values; sessions processed before
the guided measurement ask to reprocess instead of showing 0.
"""
import math
from types import SimpleNamespace

import numpy as np
import plotly.graph_objects as go
import pytest

from core import compare_design_vs_asbuilt, compare_design_vs_asbuilt_guided
from core.profile_extract import BenchParams

TOLERANCES = {
    "bench_height": {"neg": 2.0, "pos": 2.0},
    "face_angle": {"neg": 5.0, "pos": 5.0},
    "berm_width": {"min": 7.0},
    "crest_toe_deviation": {"neg": 1.0, "pos": 1.0},
    "floor_vertical": {"max": 0.5},
}


def _bench(num, cd, ce, td, te, **kw):
    height = abs(ce - te)
    dx = abs(td - cd)
    angle = math.degrees(math.atan2(height, dx)) if dx > 1e-9 else 90.0
    return BenchParams(
        bench_number=num, crest_elevation=ce, crest_distance=cd,
        toe_elevation=te, toe_distance=td, bench_height=height,
        face_angle=angle, berm_width=kw.get("berm_width", 0.0),
        spill_width=kw.get("spill_width", 0.0),
        effective_berm_width=kw.get("effective_berm_width", 0.0),
    )


def _params(benches, name="S-01", sector="SEC"):
    return SimpleNamespace(section_name=name, sector=sector, benches=benches)


def _prof(pts, res=0.1):
    pts = np.asarray(pts, dtype=float)
    d_out, e_out = [], []
    for i in range(len(pts) - 1):
        d0, e0 = pts[i]
        d1, e1 = pts[i + 1]
        span = d1 - d0
        steps = max(1, int(np.ceil(abs(span) / res)))
        if i == 0:
            d_out.append(d0)
            e_out.append(e0)
        for s in range(1, steps + 1):
            f = s / steps
            d_out.append(d0 + f * span)
            e_out.append(e0 + f * (e1 - e0))
    return np.array(d_out), np.array(e_out)


def _split_fixture():
    design = [_bench(1, cd=0.0, ce=115.0, td=15.0, te=100.0)]
    frag_a = _bench(1, cd=0.2, ce=115.0, td=12.6, te=103.0)
    frag_b = _bench(2, cd=12.6, ce=103.0, td=15.5, te=100.2)
    d, e = _prof([
        (-5, 115), (0.2, 115), (12.6, 103.0), (13.5, 102.2),
        (15.5, 100.2), (22, 100.2),
    ])
    return _params(design), _params([frag_a, frag_b]), d, e


def _not_excavated_fixture():
    design = [
        _bench(1, cd=0.0, ce=100.0, td=10.0, te=85.0),
        _bench(2, cd=18.0, ce=85.0, td=28.0, te=70.0),
    ]
    topo = [_bench(1, cd=0.4, ce=100.0, td=10.4, te=85.0)]
    d, e = _prof([(-5, 100), (0.4, 100), (10.4, 85), (35, 85.0)])
    return _params(design), _params(topo), d, e


def _legacy_rows(rows):
    drop = ('proposed_', 'guided_')
    keys = ('split_bench', 'split_of', 'design_bench_state',
            'floor_offset_m', 'floor_status',
            'excavation_debt_thickness_mean_m', 'excavation_debt_thickness_max_m',
            'excavation_debt_area_m2')
    out = []
    for r in rows:
        new = {k: v for k, v in r.items()
               if not k.startswith(drop) and k not in keys}
        out.append(new)
    return out


class _FakeColumn:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def markdown(self, body, **kwargs):
        self._sink.append(str(body))

    def metric(self, label, value, **kwargs):
        self._sink.append(f"{label}: {value}")

    def info(self, body, **kwargs):
        self._sink.append(str(body))


class _FakeSt:
    def __init__(self):
        self.texts = []

    def subheader(self, body, **kwargs):
        self.texts.append(str(body))

    def caption(self, body, **kwargs):
        self.texts.append(str(body))

    def markdown(self, body, **kwargs):
        self.texts.append(str(body))

    def info(self, body, **kwargs):
        self.texts.append(str(body))

    def warning(self, body, **kwargs):
        self.texts.append(str(body))

    def metric(self, label, value, **kwargs):
        self.texts.append(f"{label}: {value}")

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_FakeColumn(self.texts) for _ in range(count)]

    def dump(self):
        return "\n".join(self.texts)


@pytest.fixture
def fake_st(monkeypatch):
    import ui.tabs.dashboard as dash

    fake = _FakeSt()
    monkeypatch.setattr(dash, "st", fake)
    return fake


class TestStep3GuidedComparison:
    def test_official_rows_identical_with_proposal_flag(self):
        import ui.step3_analysis as step3

        p_d, p_t, d, e = _split_fixture()
        profile = SimpleNamespace(distances=d, elevations=e)
        official = compare_design_vs_asbuilt(p_d, p_t, TOLERANCES)
        rows, ok = step3._compare_with_proposal(p_d, p_t, TOLERANCES, profile)
        assert ok is True
        assert len(rows) == len(official)
        for off, row in zip(official, rows):
            for key, value in off.items():
                assert row[key] == value
        assert all("proposed_bench_score" in r for r in rows)

    def test_guided_exception_keeps_official_rows(self, monkeypatch):
        import ui.step3_analysis as step3

        p_d, p_t, d, e = _split_fixture()
        profile = SimpleNamespace(distances=d, elevations=e)
        official = compare_design_vs_asbuilt(p_d, p_t, TOLERANCES)

        def _boom(*args, **kwargs):
            raise RuntimeError("guided failure")

        monkeypatch.setattr(step3, "compare_design_vs_asbuilt_guided", _boom)
        rows, ok = step3._compare_with_proposal(p_d, p_t, TOLERANCES, profile)
        assert ok is False
        assert rows == official
        assert not any("proposed_source" in r for r in rows)

    def test_no_benches_returns_empty_without_guided_call(self, monkeypatch):
        import ui.step3_analysis as step3

        def _boom(*args, **kwargs):
            raise AssertionError("guided must not run without benches")

        monkeypatch.setattr(step3, "compare_design_vs_asbuilt_guided", _boom)
        empty = SimpleNamespace(benches=[])
        profile = SimpleNamespace(distances=np.array([]), elevations=np.array([]))
        rows, ok = step3._compare_with_proposal(empty, empty, TOLERANCES, profile)
        assert rows == []
        assert ok is True


class TestHasProposal:
    def test_detects_guided_rows(self):
        from ui.tabs.profiles.proposal import has_proposal

        p_d, p_t, d, e = _split_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        assert has_proposal(rows) is True

    def test_legacy_rows_have_no_proposal(self):
        from ui.tabs.profiles.proposal import has_proposal

        p_d, p_t, d, e = _split_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        assert has_proposal(_legacy_rows(rows)) is False


class TestProposedRowsTable:
    def test_pairs_official_and_proposed_per_bench(self):
        from ui.tabs.profiles.proposal import build_proposed_rows

        p_d, p_t, d, e = _split_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        table = build_proposed_rows(rows)
        assert table
        match = next(r for r in rows if r["type"] == "MATCH")
        entry = next(t for t in table if t["Banco"] == f"B{match['bench_num']}")
        for col in ("Altura", "Ángulo", "Δ Cresta", "Δ Pata", "Berma", "Puntaje"):
            assert "→" in entry[col]
        assert match["proposed_source"] == "mixed"
        assert match["proposed_height_source"] == "guided"
        assert match["proposed_berm_source"] == "current"
        assert entry["Origen"] == "Mixta"
        assert entry["Altura"].endswith("(g)")
        assert entry["Berma"].endswith("(o)")
        assert entry["Estado banco"] == "Banco partido"

    def test_guided_source_labelled_and_per_magnitude_suffix(self):
        from ui.tabs.profiles.proposal import build_proposed_rows

        rows = [{
            "section": "S-01", "type": "MATCH", "bench_num": 1,
            "height_real": 14.2, "angle_real": 70.0, "delta_crest": -0.3,
            "delta_toe": 1.1, "berm_real": 8.2, "bench_score": 100,
            "proposed_source": "guided", "proposed_height": 15.0,
            "proposed_angle": 71.0, "proposed_delta_crest": None,
            "proposed_delta_toe": 0.4, "proposed_berm": 8.0,
            "proposed_height_source": "guided", "proposed_angle_source": "guided",
            "proposed_crest_source": None, "proposed_toe_source": "guided",
            "proposed_berm_source": "current",
            "proposed_bench_score": 90.0, "proposed_evaluable": True,
            "design_bench_state": "excavated",
        }]
        entry = build_proposed_rows(rows)[0]
        assert entry["Origen"] == "Guiada"
        assert entry["Altura"].endswith("(g)")
        assert entry["Ángulo"].endswith("(g)")
        assert entry["Δ Cresta"] == "-0.3 → —"
        assert entry["Δ Pata"].endswith("(g)")
        assert entry["Berma"].endswith("(o)")
        assert not entry["Puntaje"].endswith(("(g)", "(o)"))

    def test_current_source_labelled(self):
        from ui.tabs.profiles.proposal import build_proposed_rows

        rows = [{
            "section": "S-01", "type": "MATCH", "bench_num": 1,
            "height_real": 14.2, "proposed_height": 14.2,
            "proposed_source": "current", "proposed_height_source": "current",
            "design_bench_state": "excavated",
        }]
        entry = build_proposed_rows(rows)[0]
        assert entry["Origen"] == "Actual"

    def test_split_fragment_labelled(self):
        from ui.tabs.profiles.proposal import build_proposed_rows

        p_d, p_t, d, e = _split_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        table = build_proposed_rows(rows)
        frag = next(t for t in table if "fragmento" in t["Estado banco"].lower())
        assert frag["Origen"] == "—"

    def test_not_excavated_shows_debt_and_never_zero(self):
        from ui.tabs.profiles.proposal import build_proposed_rows

        p_d, p_t, d, e = _not_excavated_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        table = build_proposed_rows(rows)
        ne = next(t for t in table if "no excavado" in t["Estado banco"].lower())
        assert "m²" in ne["Estado banco"]
        assert "—" in ne["Puntaje"]
        assert "None" not in ne["Puntaje"]

    def test_missing_magnitudes_render_dash_not_none(self):
        from ui.tabs.profiles.proposal import build_proposed_rows

        rows = [{
            "section": "S-01", "type": "MISSING", "bench_num": 3,
            "height_real": None, "angle_real": None, "delta_crest": None,
            "delta_toe": None, "berm_real": None, "bench_score": 0,
            "proposed_source": None, "proposed_height": None,
            "proposed_angle": None, "proposed_delta_crest": None,
            "proposed_delta_toe": None, "proposed_berm": None,
            "proposed_bench_score": None, "proposed_exclusion_reason": "unmeasured",
            "floor_offset_m": None, "floor_status": "-",
            "excavation_debt_area_m2": None, "design_bench_state": "unmeasured",
        }]
        entry = build_proposed_rows(rows)[0]
        assert entry["Altura"] == "— → —"
        assert entry["Puntaje"] == "0 → —"
        assert entry["Estado banco"] == "Sin medir"
        assert entry["Piso (±0,5 m)"] == "—"

    def test_include_section_adds_column(self):
        from ui.tabs.profiles.proposal import build_proposed_rows

        p_d, p_t, d, e = _split_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        table = build_proposed_rows(rows, include_section=True)
        assert all(t["Sección"] == "S-01" for t in table)


class TestProposalFigureTraces:
    def test_adds_guided_toe_and_local_floor_traces(self):
        from ui.tabs.profiles.proposal import add_proposal_traces

        p_d, p_t, d, e = _split_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        fig = go.Figure()
        add_proposal_traces(fig, rows, p_d.benches)
        names = [t.name for t in fig.data]
        assert "Pata sólida guiada" in names
        assert "Piso local (propuesta)" in names

    def test_empty_inputs_add_nothing(self):
        from ui.tabs.profiles.proposal import add_proposal_traces

        fig = go.Figure()
        add_proposal_traces(fig, [], [])
        assert len(fig.data) == 0

    def test_legacy_rows_add_nothing(self):
        from ui.tabs.profiles.proposal import add_proposal_traces

        p_d, p_t, d, e = _split_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        fig = go.Figure()
        add_proposal_traces(fig, _legacy_rows(rows), p_d.benches)
        assert len(fig.data) == 0


class TestProposalFloorGeometryS46:
    DESIGN = [
        _bench(1, cd=-18.15, ce=3095.0, td=-12.69, te=3080.0, berm_width=6.66),
        _bench(2, cd=0.0, ce=3080.0, td=4.04, te=3065.0, berm_width=12.69),
    ]
    RANGE = (-18.15, 10.0)
    ROWS = [
        {"type": "MATCH", "bench_num": 1, "guided_delta_toe": 3.49,
         "floor_offset_m": 0.9, "berm_design": 6.66},
        {"type": "MATCH", "bench_num": 2, "guided_delta_toe": -1.63,
         "floor_offset_m": -0.21, "berm_design": 12.69},
    ]

    def _figure(self, rows=None, benches=None, profile_range="default"):
        from ui.tabs.profiles.proposal import add_proposal_traces

        fig = go.Figure()
        add_proposal_traces(fig, rows if rows is not None else self.ROWS,
                            benches if benches is not None else self.DESIGN,
                            self.RANGE if profile_range == "default" else profile_range)
        return fig

    def _floor_traces(self, fig):
        return [t for t in fig.data if t.legendgroup == "propuesta piso"]

    def test_floor_runs_from_guided_toe_to_lower_crest(self):
        floors = self._floor_traces(self._figure())
        assert len(floors) == 2
        b1, b2 = floors
        assert b1.x[0] == pytest.approx(-16.18, abs=1e-6)
        assert b1.x[1] == pytest.approx(0.0, abs=1e-6)
        assert b1.y[0] == pytest.approx(3080.9, abs=1e-6)
        assert b1.y[0] == pytest.approx(b1.y[1], abs=1e-9)
        assert b2.x[0] == pytest.approx(5.67, abs=1e-6)
        assert b2.x[1] == pytest.approx(10.0, abs=1e-6)
        assert b2.y[0] == pytest.approx(3064.79, abs=1e-6)
        assert b2.y[0] == pytest.approx(b2.y[1], abs=1e-9)

    def test_floor_never_crosses_another_bench(self):
        b1, b2 = self._floor_traces(self._figure())
        assert max(b1.x) <= 0.0
        assert min(b1.x) > -18.15
        assert max(b2.x) <= 10.0

    def test_guided_toe_markers_positions(self):
        fig = self._figure()
        markers = [t for t in fig.data if t.name == "Pata sólida guiada"]
        assert len(markers) == 1
        assert list(markers[0].x) == pytest.approx([-16.18, 5.67], abs=1e-6)
        assert list(markers[0].y) == pytest.approx([3080.9, 3064.79], abs=1e-6)

    def test_prefers_guided_lower_crest(self):
        rows = [self.ROWS[0], dict(self.ROWS[1], guided_delta_crest=-1.0)]
        b1 = self._floor_traces(self._figure(rows=rows))[0]
        assert b1.x[1] == pytest.approx(1.0, abs=1e-6)

    def test_lower_crest_beyond_profile_clamps_to_range(self):
        benches = self.DESIGN + [
            _bench(3, cd=15.0, ce=3065.0, td=19.7, te=3050.0, berm_width=8.0)]
        b2 = self._floor_traces(
            self._figure(rows=[self.ROWS[1]], benches=benches))[0]
        assert b2.x[1] == pytest.approx(10.0, abs=1e-6)

    def test_no_range_no_lower_bench_falls_back_to_berm_width(self):
        b2 = self._floor_traces(
            self._figure(rows=[self.ROWS[1]], profile_range=None))[0]
        assert b2.x[1] == pytest.approx(18.36, abs=1e-6)

    def test_range_derived_from_existing_figure_traces(self):
        from ui.tabs.profiles.proposal import add_proposal_traces

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[-18.15, -12.69, 0, 4.04, 10], y=[3095, 3080, 3080, 3065, 3065],
            mode="lines", name="Topografía Real"))
        add_proposal_traces(fig, [self.ROWS[1]], self.DESIGN, None)
        b2 = [t for t in fig.data if t.legendgroup == "propuesta piso"][0]
        assert b2.x[1] == pytest.approx(10.0, abs=1e-6)

    def test_floor_without_guided_delta_starts_at_design_toe(self):
        rows = [{k: v for k, v in self.ROWS[0].items() if k != "guided_delta_toe"}]
        b1 = self._floor_traces(self._figure(rows=rows))[0]
        assert b1.x[0] == pytest.approx(-12.69, abs=1e-6)
        assert b1.x[1] == pytest.approx(0.0, abs=1e-6)


class TestDashboardProposalKpi:
    def test_shows_score_coverage_split_debt_and_floor(self, fake_st):
        import ui.tabs.dashboard as dash

        p_d, p_t, d, e = _split_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        dash._render_proposal_kpi(rows)
        out = fake_st.dump()
        assert "Propuesta (en validación)" in out
        assert "bancos de diseño evaluables" in out
        assert "Bancos partidos" in out
        assert "m²" in out
        assert "Piso" in out

    def test_legacy_rows_ask_to_reprocess_never_zero(self, fake_st):
        import ui.tabs.dashboard as dash

        p_d, p_t, d, e = _split_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        dash._render_proposal_kpi(_legacy_rows(rows))
        out = fake_st.dump()
        assert "Reprocese" in out
        assert "0.0" not in out

    def test_no_evaluable_rows_score_is_sin_dato(self, fake_st):
        import ui.tabs.dashboard as dash

        p_d, p_t, d, e = _not_excavated_fixture()
        rows = compare_design_vs_asbuilt_guided(p_d, p_t, TOLERANCES, d, e)
        rows = [r for r in rows if r.get("proposed_exclusion_reason") == "not_excavated"]
        assert rows
        dash._render_proposal_kpi(rows)
        out = fake_st.dump()
        assert "sin dato" in out
