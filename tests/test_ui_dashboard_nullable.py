"""Nullable contract on the dashboard screens (bench_score / berma faltantes).

Dato faltante = ``None`` y se muestra «sin dato»; un 0 medido se muestra 0.
Nunca se convierte un faltante en 0.
"""
import pytest


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


def _row(section="S1", bench_score=80.0, row_type="MATCH", **extra):
    row = {
        "section": section,
        "type": row_type,
        "bench_score": bench_score,
        "delta_crest": 0.2,
        "delta_toe": 0.2,
        "berm_status": "CUMPLE",
        "sector": "Norte",
        "height_status": "CUMPLE",
        "angle_status": "CUMPLE",
        "height_dev": 0.1,
        "angle_dev": 1.0,
        "height_real": 15.0,
        "angle_real": 70.0,
        "berm_real": 6.0,
    }
    row.update(extra)
    return row


@pytest.fixture
def fake_st(monkeypatch):
    import ui.tabs.dashboard as dash

    fake = _FakeSt()
    monkeypatch.setattr(dash, "st", fake)
    return fake


class TestGlobalKpiNullable:
    def test_finite_bench_scores_only(self, fake_st):
        import ui.tabs.dashboard as dash

        rows = [
            _row("S1", 80.0),
            _row("S1", None),
            _row("S2", 40.0),
        ]
        dash._render_global_kpi(rows)
        out = fake_st.dump()
        assert "60.0" in out
        assert "2 de 3 bancos evaluables" in out

    def test_all_missing_shows_sin_dato(self, fake_st):
        import ui.tabs.dashboard as dash

        dash._render_global_kpi([_row("S1", None), _row("S2", None)])
        out = fake_st.dump()
        assert "sin dato" in out
        assert "Score Global" in out

    def test_nonfinite_scores_excluded(self, fake_st):
        import ui.tabs.dashboard as dash

        rows = [
            _row("S1", float("nan")),
            _row("S2", 50.0),
            _row("S3", float("inf")),
        ]
        dash._render_global_kpi(rows)
        out = fake_st.dump()
        assert "50.0" in out
        assert "1 de 3 bancos evaluables" in out

    def test_measured_zero_stays_zero(self, fake_st):
        import ui.tabs.dashboard as dash

        dash._render_global_kpi([_row("S1", 0.0)])
        out = fake_st.dump()
        assert "0.0" in out
        assert "1 de 1 bancos evaluables" in out

    def test_non_match_rows_not_counted(self, fake_st):
        import ui.tabs.dashboard as dash

        rows = [_row("S1", 90.0), _row("S2", 10.0, row_type="MISSING")]
        dash._render_global_kpi(rows)
        out = fake_st.dump()
        assert "90.0" in out
        assert "1 de 1 bancos evaluables" in out


class TestAchievementKpiCoverage:
    def test_partial_weights_show_coverage(self, fake_st):
        import ui.tabs.dashboard as dash

        rows = [_row("S1", 80.0, delta_crest=None, delta_toe=None, berm_status="CUMPLE")]
        dash._render_achievement_kpi(rows, {"neg": 1.0, "pos": 0.5})
        out = fake_st.dump()
        assert "100%" in out
        assert "Cobertura logro diseño" in out
        assert "1 de 1 bancos evaluables" in out
        assert "con dato: berma" in out
        assert "sin dato: cresta, pata" in out

    def test_full_coverage_lists_all_components(self, fake_st):
        import ui.tabs.dashboard as dash

        dash._render_achievement_kpi([_row("S1", 80.0)], {"neg": 1.0, "pos": 0.5})
        out = fake_st.dump()
        assert "con dato: cresta, pata, berma" in out
        assert "sin dato:" not in out


class TestSummaryCoverage:
    def test_summary_exposes_coverage(self):
        from ui.tabs.dashboard_achievement import build_achievement_summary

        rows = [_row("S1", 80.0, delta_crest=None, delta_toe=None, berm_status="CUMPLE")]
        summary = build_achievement_summary(rows, {"neg": 1.0, "pos": 0.5})
        coverage = summary["coverage"]
        assert coverage["n_rows"] == 1
        assert coverage["n_evaluable"] == 1
        assert coverage["n_available"] == {"crest": 0, "toe": 0, "berm": 1}
        assert coverage["weight_available_mean"] == pytest.approx(0.3)

    def test_signed_mean_empty_is_none(self):
        from ui.tabs.dashboard_achievement import _signed_mean

        assert _signed_mean([]) is None
        assert _signed_mean([1.0, -0.5]) == pytest.approx(0.25)


class TestParameterRowsNullable:
    def test_missing_berm_average_is_sin_dato(self):
        from ui.tabs.dashboard_achievement import build_parameter_breakdown_rows

        rows = [
            _row("S1", 80.0, berm_status="CUMPLE", berm_real=None),
            _row("S2", 80.0, berm_status="CUMPLE", berm_real=float("nan")),
            _row("S3", 80.0, berm_status="CUMPLE", berm_real=6.0),
        ]
        out = build_parameter_breakdown_rows(rows, {"neg": 1.0, "pos": 0.5})
        berm = next(r for r in out if r["Parámetro"] == "Ancho de Berma")
        assert berm["Total Evaluado"] == 3
        assert berm["Promedio Real"] == "6.0 m"
        assert "nan" not in berm["Promedio Real"].lower()

    def test_all_berm_missing_average_is_sin_dato(self):
        from ui.tabs.dashboard_achievement import build_parameter_breakdown_rows

        rows = [_row("S1", 80.0, berm_status="CUMPLE", berm_real=float("nan"))]
        out = build_parameter_breakdown_rows(rows, {"neg": 1.0, "pos": 0.5})
        berm = next(r for r in out if r["Parámetro"] == "Ancho de Berma")
        assert berm["Promedio Real"] == "sin dato"
        assert berm["% Cumplimiento"] == "100%"

    def test_measured_zero_average_stays_zero(self):
        from ui.tabs.dashboard_achievement import build_parameter_breakdown_rows

        rows = [_row("S1", 80.0, berm_status="CUMPLE", berm_real=0.0)]
        out = build_parameter_breakdown_rows(rows, {"neg": 1.0, "pos": 0.5})
        berm = next(r for r in out if r["Parámetro"] == "Ancho de Berma")
        assert berm["Promedio Real"] == "0.0 m"

    def test_empty_denominator_pct_is_sin_dato(self):
        from ui.tabs.dashboard_achievement import build_parameter_breakdown_rows

        out = build_parameter_breakdown_rows([], {"neg": 1.0, "pos": 0.5})
        assert [r["% Cumplimiento"] for r in out] == ["sin dato"] * 5
        assert [r["Promedio Real"] for r in out] == ["sin dato"] * 5
