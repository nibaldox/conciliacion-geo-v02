from core.report_figures_plan import _build_plan_figure


def test_excluded_sections_have_separate_legend_and_context_lines():
    sections = [{'name': str(i), 'origin': [i * 20, 0, 0], 'azimuth': 0, 'length': 30} for i in range(7)]
    statuses = {'0': 'CUMPLE', '1': 'NO_CUMPLE', '2': 'UNKNOWN', '3': 'CUMPLE'}
    fig, ax = _build_plan_figure(sections, statuses, excluded={'4', '5', '6'})
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert 'Sin evaluar (1)' in labels
    assert 'Fuera del filtro (3)' in labels
    assert len([line for line in ax.lines if line.get_gid() == 'plan-section-excluded']) == 3
    fig.clear()


def test_no_exclusions_omit_filter_legend():
    sections = [{'name': 'A', 'origin': [0, 0, 0], 'azimuth': 0, 'length': 30}]
    fig, ax = _build_plan_figure(sections, {'A': 'CUMPLE'})
    assert not any('Fuera del filtro' in t.get_text() for t in ax.get_legend().get_texts())
    fig.clear()


def test_pdf_word_and_zip_use_same_filtered_plan(monkeypatch):
    from core.report_data import ReportFilters
    from core import web_pdf_report, web_word_report, web_images_report
    from tests.test_web_images_report import _data

    data = _data(filters=ReportFilters(sections=("S-01",)))
    sections = web_pdf_report._plan_sections(data)
    assert [item["included"] for item in sections] == [True, False, False]
    assert web_word_report._plan_sections(data) == sections
    captured = {}
    def fake(sections, statuses, **kwargs):
        captured["sections"] = sections
        return b"png"
    monkeypatch.setattr(web_images_report, "dashboard_plan_png", fake)
    assert web_images_report._plan_png(data) == b"png"
    assert captured["sections"] == sections


def test_same_name_different_sector_keeps_included_official_status():
    sections = [
        {"name": "S", "origin": [0, 0, 0], "azimuth": 0, "length": 30, "included": True, "worst_status": "CUMPLE"},
        {"name": "S", "origin": [20, 0, 0], "azimuth": 0, "length": 30, "included": False, "worst_status": "UNKNOWN"},
    ]
    fig, ax = _build_plan_figure(sections, {})
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert "Cumple (1)" in labels
    assert not any(t.startswith("Sin evaluar") for t in labels)
    assert "Fuera del filtro (1)" in labels
    fig.clear()
