import io
import os
from pathlib import Path

import openpyxl
import pytest
from docx import Document

from core.blast_correlation import PF_DEFINITIONS
from tests.test_excel_writer import _match_comp, _tolerances


def _text(data, kind):
    stream = io.BytesIO(data)
    if kind == "excel":
        wb = openpyxl.load_workbook(stream)
        return "\n".join(str(c.value) for s in wb for row in s for c in row if c.value is not None)
    if kind == "word":
        doc = Document(stream)
        return "\n".join([p.text for p in doc.paragraphs] + [c.text for t in doc.tables for r in t.rows for c in r.cells])
    reader = pytest.importorskip("pypdf").PdfReader
    return "\n".join(page.extract_text() for page in reader(stream).pages)


@pytest.mark.parametrize("kind,legacy", [("excel", False), ("word", False), ("word", True), ("pdf", False), ("pdf", True)])
def test_corrective_exports_real_writers(api_test_client, monkeypatch, kind, legacy):
    import api.database as db
    from api.routers import export

    sid = db.get_or_create_session()
    row = _match_comp(delta_crest=0.0, delta_toe=None, berm_dev=None, effective_berm=1.0, effective_berm_status="NO CUMPLE")
    from tests.conftest import create_pit_surface

    db.save_results(sid, [row])
    db.save_sections(sid, [{"name": "S-01", "origin": [100., 200.], "azimuth": 0., "length": 100., "sector": "Norte"}])
    hole = {"hole_id": "H-1", "label_pozo": "H-1", "X": 100., "Y": 200., "Z_collar": 3870., "X_toe": 100., "Y_toe": 200., "Z_toe": 3855., "Incl": 0., "Az": 0., "Len": 15., "Kilos_Cargados_real": None, "pf_voronoi_bench_g_per_ton": None, "pf_voronoi_bench_status": "MISSING"}
    db.save_settings(sid, {"tolerances": _tolerances(), "blast_holes": [hole], "blast_upload_meta": {"consolidation_report": {"holes_out": 1, "exact_copies_removed": 2, "deck_rows_merged": 0}}})
    mesh = create_pit_surface(nx=12, ny=12)
    monkeypatch.setattr(export, "_load_mesh_from_db", lambda *args: mesh)
    if legacy:
        monkeypatch.setattr(export, "build_word_report" if kind == "word" else "build_pdf_report", None)
    response = api_test_client.get(f"/api/v1/export/{kind}", headers={"X-Session-ID": sid}, params={"filters": '{"showBlastHoles":true}'})
    assert response.status_code == 200, response.text
    text = _text(response.content, kind)
    for expected in ("sin dato", "Cobertura", "componentes faltantes", "copias eliminadas", "1000*Q/(A*H*rho)"):
        assert expected.lower() in text.lower(), (kind, legacy, expected, text)
    for definition in PF_DEFINITIONS.values():
        assert definition["formula"] in text
    assert 'MISSING' in text
    if kind != 'pdf' or legacy:
        assert 'berma efectiva' in text.lower()
    if kind == 'excel':
        sheet = openpyxl.load_workbook(io.BytesIO(response.content))['Bancos']
        header = [cell.value for cell in sheet[1]]
        values = [cell.value for cell in sheet[2]]
        assert values[header.index('Cumpl. B')] == 'CUMPLE'
        assert values[header.index('Estado berma efectiva')] == 'NO CUMPLE'
    artifact_dir = os.environ.get("CORRECTIVE_REPORT_ARTIFACTS")
    if artifact_dir:
        suffix = {"excel": "xlsx", "word": "docx", "pdf": "pdf"}[kind]
        name = f"{kind}-{'legacy' if legacy else 'web'}.{suffix}"
        Path(artifact_dir, name).write_bytes(response.content)
        Path(artifact_dir, name + ".txt").write_text(text, encoding="utf-8")


@pytest.mark.parametrize('kind', ['excel', 'word', 'pdf'])
def test_legacy_export_preserves_literal_hole_ids(api_test_client, monkeypatch, kind):
    import api.database as db
    from api.routers import export

    sid = db.get_or_create_session()
    db.save_results(sid, [_match_comp()])
    holes = [{"id_pozo": name, "hole_id": str(index), "X": 100., "Y": 200., "Z_collar": 100., "X_toe": 100., "Y_toe": 200., "Z_toe": 90., "Len": 10., "Incl": 0., "Az": 0., "decks": [{"kg": 19, "explosive": "ANFO", "source_row_index": 0}], "explosive_mix": {"ANFO": 19}, "source_row_indices": [0]} for index, name in enumerate(['H-OLD', 'H-SECOND'])]
    db.save_settings(sid, {"tolerances": _tolerances(), "blast_holes": holes})
    monkeypatch.setattr(export, '_load_mesh_from_db', lambda *args: None)
    response = api_test_client.get(f'/api/v1/export/{kind}', headers={'X-Session-ID': sid}, params={'filters': '{"showBlastHoles":true}'})
    assert response.status_code == 200, response.text
    text = _text(response.content, kind).lower()
    assert 'h-old' in text and 'h-second' in text
    assert 'datos de pozos importados con una versión anterior: reimportar' in text


@pytest.mark.parametrize('kind', ['excel', 'word'])
def test_writer_accepts_incomplete_hole(api_test_client, monkeypatch, kind):
    import api.database as db
    from api.routers import export

    sid = db.get_or_create_session()
    db.save_results(sid, [_match_comp()])
    db.save_settings(sid, {"tolerances": _tolerances(), "blast_holes": [{"hole_id": "H-incomplete", "X": 100.0, "Y": 200.0}]})
    monkeypatch.setattr(export, '_load_mesh_from_db', lambda *args: None)
    if kind == 'word':
        monkeypatch.setattr(export, 'build_word_report', None)
    response = api_test_client.get(f'/api/v1/export/{kind}', headers={'X-Session-ID': sid}, params={'filters': '{"showBlastHoles":true}'})
    assert response.status_code == 200, response.text
    text = _text(response.content, kind)
    assert 'sin dato' in text.lower()
    assert 'H-incomplete' in text
