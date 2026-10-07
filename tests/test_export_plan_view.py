import json
import io

import pytest

import api.routers.export as export_router
from tests.test_export_with_filters import isolated_db, client, session_id, headers, _seed_results


@pytest.mark.parametrize("format_name", ["word", "pdf"])
def test_reports_receive_actual_topography_sections_and_filtered_results(format_name, client, headers, monkeypatch):
    _seed_results(client, headers, headers["x-session-id"])
    captured = {}

    def writer(results, all_data, path, *args, **kwargs):
        captured.update(kwargs)
        captured["results"] = results
        with open(path, "wb") as output:
            output.write(b"report")

    if format_name == "word":
        monkeypatch.setattr(export_router, "generate_word_report", writer)
    else:
        monkeypatch.setattr(export_router, "_import_pdf_report", lambda: writer)
    response = client.get(
        f"/api/v1/export/{format_name}", headers=headers,
        params={"filters": json.dumps({"selectedBenchNumbers": [2]})},
    )
    assert response.status_code == 200, response.text
    assert [row["bench_num"] for row in captured["results"]] == [2]
    assert [section.name for section in captured["sections"]] == ["S-01"]
    assert len(captured["mesh_topo"].vertices) > 0
    assert json.loads(response.headers["X-Export-Filters-Applied"])["selected_bench_numbers"] == [2]


def test_pdf_embeds_plan_as_an_image_instead_of_an_error_placeholder(monkeypatch):
    from PIL import Image as PillowImage
    from reportlab.platypus import Image, Paragraph
    from core.pdf_report import _build_plan_section, _build_styles
    import core.report_generator as generator

    def plan(*args, **kwargs):
        output = io.BytesIO()
        PillowImage.new("RGB", (100, 80), "gray").save(output, format="PNG")
        output.seek(0)
        return output

    monkeypatch.setattr(generator, "create_plan_view_image", plan)
    story = []
    _build_plan_section(story, [], [object()], _build_styles())
    assert any(isinstance(item, Image) for item in story)
    assert not any(isinstance(item, Paragraph) and "Error al" in item.text for item in story)


def test_selected_benches_recalculate_report_plan_scores_without_mutating_session():
    from api.schemas import ExportFilters
    from core.reconciliation_summary import compute_section_scores

    rows = [
        {"section": "S-01", "type": "MATCH", "bench_num": 1, "bench_score": 100, "section_score": 50},
        {"section": "S-01", "type": "MATCH", "bench_num": 2, "bench_score": 0, "section_score": 50},
    ]
    selected = export_router._filter_comparisons(rows, ExportFilters(selected_bench_numbers=[1]))
    assert compute_section_scores(selected, prefer_canonical=True) == {"S-01": 100}
    assert selected[0]["section_score"] == 100
    assert rows[0]["section_score"] == 50
    assert export_router._filter_comparisons(rows, ExportFilters()) == rows
