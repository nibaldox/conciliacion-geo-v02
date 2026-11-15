import time
from datetime import datetime, timezone

import pytest

from core import config
from core.web_pdf_report import _fmt_date
from core.web_word_report import _date_text


@pytest.mark.parametrize('value, expected', [('0', 30), ('-5', 30), ('abc', 30), ('45', 45)])
def test_session_ttl_parsing(monkeypatch, value, expected):
    monkeypatch.setenv('CONCILIACION_SESSION_TTL_DAYS', value)
    assert config.DeployDefaults().session_ttl_days == expected


def test_timezone_and_list_configuration(monkeypatch, caplog):
    monkeypatch.setenv('CONCILIACION_TIMEZONE', 'Bad/Zone')
    monkeypatch.setenv('CONCILIACION_SESSION_LIST_ENABLED', 'yes')
    settings = config.DeployDefaults()
    assert settings.report_timezone == 'America/Santiago'
    assert settings.session_list_enabled is True
    assert 'Bad/Zone' in caplog.text
    monkeypatch.setenv('CONCILIACION_TIMEZONE', 'Europe/London')
    assert config.DeployDefaults().report_timezone == 'Europe/London'


def test_fixed_instant_local_wall_time_under_utc(monkeypatch):
    monkeypatch.setenv('TZ', 'UTC')
    time.tzset()
    try:
        instant = datetime(2026, 11, 14, 19, 12, tzinfo=timezone.utc)
        stamp = instant.astimezone(config.report_tz()).isoformat()
        assert _fmt_date(stamp) == '14/11/2026 16:12'
        assert _date_text(stamp) == '14/11/2026 16:12'
    finally:
        monkeypatch.undo()
        time.tzset()


def test_fixed_local_stamp_survives_all_export_builders(monkeypatch):
    import dataclasses
    import io
    import zipfile
    from docx import Document
    from openpyxl import load_workbook
    from pypdf import PdfReader
    from core.web_pdf_report import build_pdf_report
    from core.web_word_report import build_word_report
    from core.web_excel_report import build_excel_report
    from core.web_images_report import build_images_zip
    from tests.test_web_excel_report import _data

    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    try:
        stamp = datetime(2026, 11, 14, 19, 12, tzinfo=timezone.utc).astimezone(config.report_tz()).isoformat()
        data = dataclasses.replace(_data(), meta={"project": "Prueba", "generated_at": stamp})
        pdf = PdfReader(build_pdf_report(data))
        assert "14/11/2026 16:12" in " ".join(page.extract_text() for page in pdf.pages)
        doc = Document(build_word_report(data))
        xml = doc.element.xml
        assert "14/11/2026 16:12" in xml
        book = load_workbook(build_excel_report(data))
        assert any("14/11/2026 16:12" in str(c.value) for ws in book for row in ws for c in row)
        with zipfile.ZipFile(build_images_zip(data)) as archive:
            assert "14/11/2026 16:12" in archive.read("LEEME.txt").decode()
    finally:
        monkeypatch.undo()
        time.tzset()
