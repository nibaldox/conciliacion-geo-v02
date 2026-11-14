"""Tests for core.web_images_report — filtered section images ZIP."""
import io
import zipfile
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

import core.web_images_report as images_report
from core import SectionLine
from core.report_data import ReportFilters, build_report_data
from core.web_images_report import build_images_zip
from tests.conftest import create_pit_surface

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TOLERANCES = {
    "bench_height": {"neg": 1.0, "pos": 1.5},
    "face_angle": {"neg": 5.0, "pos": 5.0},
    "berm_width": {"min": 6.0},
}
STATUS_TEXT = {"CUMPLE": "CUMPLE", "NO_CUMPLE": "NO CUMPLE"}


def _row(section: str, sector: str, bench: int, level: float, status: str = "CUMPLE") -> Dict[str, Any]:
    text = STATUS_TEXT[status]
    return {
        "section": section, "sector": sector, "bench_num": bench, "bench_num_topo": bench,
        "type": "MATCH", "level": f"{level:.0f}",
        "height_design": 15.0, "height_real": 15.0, "height_dev": 0.0, "height_status": "CUMPLE",
        "angle_design": 70.0, "angle_real": 70.0, "angle_dev": 0.0, "angle_status": "CUMPLE",
        "berm_design": 9.0, "berm_real": 9.0, "berm_dev": 0.0, "berm_min": 6.0,
        "berm_status": text,
    }


def _bench(number: int, crest_d: float, crest_z: float, toe_d: float, toe_z: float):
    return SimpleNamespace(
        bench_number=number, crest_distance=crest_d, crest_elevation=crest_z,
        toe_distance=toe_d, toe_elevation=toe_z, bench_height=crest_z - toe_z,
        face_angle=70.0, berm_width=9.0,
    )


def _entry(name: str, sector: str = "Norte", view_window=None, empty: bool = False) -> Dict[str, Any]:
    design_d = np.array([-30.0, -15.0, -10.0, 0.0, 5.0, 15.0, 20.0, 30.0])
    design_z = np.array([140.0, 140.0, 125.0, 125.0, 110.0, 110.0, 95.0, 95.0])
    topo_d = np.linspace(-30.0, 30.0, 121)
    topo_z = np.interp(topo_d, design_d, design_z) + 2.0 * np.sin(topo_d / 4.0)
    if empty:
        design_d = design_z = topo_d = topo_z = np.array([])
    return {
        "section_name": name, "sector": sector, "view_window": view_window, "warnings": [],
        "params_design": SimpleNamespace(benches=[_bench(2, 0.0, 125.0, 5.0, 110.0)]),
        "params_topo": SimpleNamespace(benches=[_bench(2, 0.5, 124.0, 5.5, 110.5)]),
        "profile_d": (design_d, design_z), "profile_t": (topo_d, topo_z),
    }


def _sections(names: List[str], sectors: Optional[Dict[str, str]] = None) -> List[SectionLine]:
    sectors = sectors or {}
    return [
        SectionLine(
            name=name, origin=np.array([150.0 + 20.0 * index, 250.0]), azimuth=0.0,
            length=80.0, sector=sectors.get(name, "Norte"),
        )
        for index, name in enumerate(names)
    ]


def _data(
    names=("S-01", "S-02", "S-03"),
    *,
    geometry_names=None,
    empty=(),
    statuses: Optional[Dict[str, str]] = None,
    sectors: Optional[Dict[str, str]] = None,
    filters: Optional[ReportFilters] = None,
    mesh: Any = None,
    view_window=None,
    with_plan: bool = True,
):
    statuses = statuses or {}
    sectors = sectors or {}
    rows: List[Dict[str, Any]] = []
    for name in names:
        sector = sectors.get(name, "Norte")
        rows.append(_row(name, sector, 1, 125.0, statuses.get(name, "CUMPLE")))
        rows.append(_row(name, sector, 2, 110.0))
    geometry = [
        _entry(name, sectors.get(name, "Norte"), view_window=view_window, empty=name in empty)
        for name in (geometry_names if geometry_names is not None else names)
    ]
    plan_inputs = (
        {"comparisons": rows, "sections": _sections(list(names), sectors), "mesh_topo": mesh,
         "grid_ref": 0.0}
        if with_plan else None
    )
    meta = {"project": "Proyecto Demo", "generated_at": "2026-11-14T10:20:30"}
    return build_report_data(
        rows, {"tolerances": TOLERANCES}, filters or ReportFilters(), meta,
        section_geometry=geometry, plan_inputs=plan_inputs,
    )


def _zip(buffer: io.BytesIO) -> zipfile.ZipFile:
    assert isinstance(buffer, io.BytesIO)
    assert buffer.tell() == 0
    return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))


def _readme(archive: zipfile.ZipFile) -> str:
    return archive.read("LEEME.txt").decode("utf-8")


class TestMembers:
    def test_members_and_order(self):
        archive = _zip(build_images_zip(_data()))
        assert archive.namelist() == [
            "LEEME.txt", "plano.png", "matriz.png",
            "01_S-01.png", "02_S-02.png", "03_S-03.png",
        ]
        assert archive.testzip() is None

    def test_every_png_member_has_png_signature_and_is_deflated(self):
        archive = _zip(build_images_zip(_data()))
        pngs = [info for info in archive.infolist() if info.filename.endswith(".png")]
        assert len(pngs) == 5
        for info in archive.infolist():
            assert info.compress_type == zipfile.ZIP_DEFLATED
        for info in pngs:
            assert archive.read(info.filename).startswith(PNG_SIGNATURE), info.filename

    def test_only_filtered_sections_are_exported_in_defined_order(self):
        data = _data(geometry_names=("S-03", "S-01"))
        names = _zip(build_images_zip(data)).namelist()
        assert [name for name in names if name[:2].isdigit()] == ["01_S-03.png", "02_S-01.png"]
        assert not any("S-02" in name for name in names)

    def test_position_is_zero_padded_to_the_section_count(self):
        names = [f"S-{index:03d}" for index in range(1, 101)]
        calls: List[str] = []

        def fake_profile(entry, **kwargs):
            calls.append(entry["section_name"])
            return PNG_SIGNATURE + b"x"

        original = images_report.cropped_profile_png
        images_report.cropped_profile_png = fake_profile
        try:
            members = _zip(build_images_zip(_data(tuple(names)))).namelist()
        finally:
            images_report.cropped_profile_png = original
        assert "001_S-001.png" in members
        assert "100_S-100.png" in members
        assert calls == names

    def test_build_is_deterministic(self):
        first = build_images_zip(_data()).getvalue()
        second = build_images_zip(_data()).getvalue()
        assert first == second

    def test_empty_report_still_returns_a_zip_with_readme(self):
        data = build_report_data([], {}, ReportFilters(), {})
        archive = _zip(build_images_zip(data))
        assert archive.namelist() == ["LEEME.txt"]


class TestProfiles:
    def test_profile_is_rendered_with_the_contract_arguments(self, monkeypatch):
        calls: List[Dict[str, Any]] = []

        def fake_profile(entry, **kwargs):
            calls.append({"name": entry["section_name"], **kwargs})
            return PNG_SIGNATURE + entry["section_name"].encode()

        monkeypatch.setattr(images_report, "cropped_profile_png", fake_profile)
        data = _data(statuses={"S-02": "NO_CUMPLE"})
        archive = _zip(build_images_zip(data))

        assert calls == [
            {"name": "S-01", "status": "CUMPLE", "width_in": 8.0, "height_in": 5.0, "dpi": 150},
            {"name": "S-02", "status": "NO_CUMPLE", "width_in": 8.0, "height_in": 5.0, "dpi": 150},
            {"name": "S-03", "status": "CUMPLE", "width_in": 8.0, "height_in": 5.0, "dpi": 150},
        ]
        assert archive.read("02_S-02.png") == PNG_SIGNATURE + b"S-02"

    def test_section_without_rows_has_no_status(self, monkeypatch):
        statuses: Dict[str, Any] = {}
        monkeypatch.setattr(
            images_report, "cropped_profile_png",
            lambda entry, **kwargs: statuses.__setitem__(entry["section_name"], kwargs["status"]),
        )
        data = _data(("S-01",), geometry_names=("S-01", "S-99"))
        build_images_zip(data)
        assert statuses == {"S-01": "CUMPLE", "S-99": None}

    def test_none_figure_is_listed_as_sin_perfil_and_keeps_positions(self):
        data = _data(empty=("S-02",))
        archive = _zip(build_images_zip(data))
        assert [name for name in archive.namelist() if name[:2].isdigit()] == [
            "01_S-01.png", "03_S-03.png",
        ]
        lines = [line for line in _readme(archive).splitlines() if line.endswith(": sin perfil")]
        assert lines == ["- Sección S-02 · Sector Norte: sin perfil"]
        assert "S-02" in lines[0]
        assert "S-01" not in lines[0]

    def test_cropped_profile_differs_from_full_profile(self):
        full = _zip(build_images_zip(_data(("S-01",)))).read("01_S-01.png")
        cropped = _zip(
            build_images_zip(_data(("S-01",), view_window=(-10.0, 15.0, 102.5, 132.5)))
        ).read("01_S-01.png")
        assert full != cropped

    @pytest.mark.parametrize(
        "section,expected",
        [
            ("Sec 1/á:b", "01_Sec_1_á_b.png"),
            ("..\\..\\evil", "01_evil.png"),
            ("  ", "01_seccion.png"),
            ("a*b?c<d>e|f\"g", "01_a_b_c_d_e_f_g.png"),
        ],
    )
    def test_member_names_are_sanitised(self, monkeypatch, section, expected):
        monkeypatch.setattr(
            images_report, "cropped_profile_png", lambda entry, **kwargs: PNG_SIGNATURE,
        )
        data = _data((section,))
        names = _zip(build_images_zip(data)).namelist()
        assert expected in names
        for name in names:
            assert not set(name) & set('/\\:*?"<>| ')

    def test_duplicate_sanitised_names_stay_unique_by_position(self, monkeypatch):
        monkeypatch.setattr(
            images_report, "cropped_profile_png", lambda entry, **kwargs: PNG_SIGNATURE,
        )
        names = _zip(build_images_zip(_data(("S/1", "S:1")))).namelist()
        assert "01_S_1.png" in names and "02_S_1.png" in names


class TestPlanAndMatrix:
    def test_plan_uses_the_shared_backdrop_recipe(self, monkeypatch):
        captured: Dict[str, Any] = {}

        def fake_plan(sections, statuses, **kwargs):
            captured.update(sections=sections, statuses=dict(statuses), **kwargs)
            return PNG_SIGNATURE + b"plan"

        monkeypatch.setattr(images_report, "dashboard_plan_png", fake_plan)
        mesh = create_pit_surface(nx=30, ny=30)
        data = _data(statuses={"S-02": "NO_CUMPLE"}, mesh=mesh)
        archive = _zip(build_images_zip(data))

        assert archive.read("plano.png") == PNG_SIGNATURE + b"plan"
        assert captured["sections"] is data.plan_inputs["sections"]
        assert captured["statuses"] == {"S-01": "CUMPLE", "S-02": "NO_CUMPLE", "S-03": "CUMPLE"}
        assert captured["surface"] is not None
        shade, extent = captured["shade"]
        assert shade.shape == captured["surface"].z.shape
        assert len(extent) == 4

    def test_plan_renders_without_relief_when_the_mesh_is_missing(self, monkeypatch):
        captured: Dict[str, Any] = {}

        def fake_plan(sections, statuses, **kwargs):
            captured.update(kwargs)
            return PNG_SIGNATURE

        monkeypatch.setattr(images_report, "dashboard_plan_png", fake_plan)
        archive = _zip(build_images_zip(_data(mesh=None)))
        assert "plano.png" in archive.namelist()
        assert captured["shade"] is None and captured["surface"] is None

    def test_plan_survives_a_failing_surface(self, monkeypatch):
        captured: Dict[str, Any] = {}

        def broken_surface(*args, **kwargs):
            raise RuntimeError("boom")

        def fake_plan(sections, statuses, **kwargs):
            captured.update(kwargs)
            return PNG_SIGNATURE

        monkeypatch.setattr(images_report, "plan_surface_from_mesh", broken_surface)
        monkeypatch.setattr(images_report, "dashboard_plan_png", fake_plan)
        archive = _zip(build_images_zip(_data(mesh=object())))
        assert "plano.png" in archive.namelist()
        assert captured["shade"] is None and captured["surface"] is None

    def test_real_plan_with_relief_is_a_png(self):
        mesh = create_pit_surface(nx=30, ny=30)
        archive = _zip(build_images_zip(_data(mesh=mesh)))
        assert archive.read("plano.png").startswith(PNG_SIGNATURE)

    def test_matrix_receives_the_report_matrix(self, monkeypatch):
        captured: Dict[str, Any] = {}

        def fake_matrix(matrix, **kwargs):
            captured["matrix"] = matrix
            return PNG_SIGNATURE + b"matrix"

        monkeypatch.setattr(images_report, "status_matrix_png", fake_matrix)
        data = _data()
        archive = _zip(build_images_zip(data))
        assert captured["matrix"] is data.matrix
        assert archive.read("matriz.png") == PNG_SIGNATURE + b"matrix"

    def test_plan_and_matrix_are_omitted_when_they_do_not_render(self, monkeypatch):
        monkeypatch.setattr(images_report, "dashboard_plan_png", lambda *a, **k: None)
        monkeypatch.setattr(images_report, "status_matrix_png", lambda *a, **k: None)
        archive = _zip(build_images_zip(_data()))
        assert archive.namelist() == ["LEEME.txt", "01_S-01.png", "02_S-02.png", "03_S-03.png"]
        readme = _readme(archive)
        assert "plano.png: no generado" in readme
        assert "matriz.png: no generado" in readme

    def test_without_plan_inputs_there_is_no_plan(self):
        archive = _zip(build_images_zip(_data(with_plan=False)))
        assert "plano.png" not in archive.namelist()
        assert "matriz.png" in archive.namelist()

    def test_a_failing_figure_does_not_break_the_zip(self, monkeypatch):
        def broken(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(images_report, "dashboard_plan_png", broken)
        monkeypatch.setattr(images_report, "status_matrix_png", broken)
        archive = _zip(build_images_zip(_data()))
        assert archive.namelist() == ["LEEME.txt", "01_S-01.png", "02_S-02.png", "03_S-03.png"]


class TestReadme:
    def test_scope_lines_without_filters(self):
        readme = _readme(_zip(build_images_zip(_data())))
        assert "Proyecto Demo" in readme
        assert "2026-11-14T10:20:30" in readme
        assert "Solo valores oficiales" in readme
        assert "Sin filtros" in readme
        assert "Cota nominal" in readme
        assert "⅓" in readme
        assert "01_S-01.png" in readme
        assert "Cumple" in readme

    def test_scope_lists_the_level_selection_of_each_sector(self):
        filters = ReportFilters(
            sectors=("Norte", "Sur"),
            levels_by_sector=(("Norte", ("110",)),),
            benches=(1, 2),
        )
        data = _data(
            ("S-01", "S-02"), sectors={"S-02": "Sur"}, filters=filters,
            view_window=(-10.0, 15.0, 102.5, 132.5),
        )
        readme = _readme(_zip(build_images_zip(data)))
        assert "Sectores: Norte, Sur" in readme
        assert "Bancos: 1, 2" in readme
        assert "Sector Norte: cota 110" in readme
        assert "Sector Sur: todas las cotas" in readme
        assert "recorta" in readme

    def test_scope_lists_global_levels_and_sections(self):
        filters = ReportFilters(sections=("S-01",), levels=("125",))
        data = _data(("S-01", "S-02"), geometry_names=("S-01",), filters=filters)
        readme = _readme(_zip(build_images_zip(data)))
        assert "Secciones: S-01" in readme
        assert "Cotas: 125" in readme
        assert "Sector Norte: cota 125" in readme

    def test_scope_names_the_sections_without_sector(self):
        filters = ReportFilters(levels=("110",))
        data = _data(("S-01",), sectors={"S-01": ""}, filters=filters)
        readme = _readme(_zip(build_images_zip(data)))
        assert "Filtros aplicados. Cotas: 110" in readme
        assert "Secciones sin sector: cota 110" in readme

    def test_level_warnings_and_window_warnings_are_listed(self):
        data = _data(("S-01",))
        data.section_geometry[0]["warnings"].append("Sección S-01: sin altura de banco válida.")
        object.__setattr__(data, "level_warnings", ("Cota no numérica en S-09.",))
        readme = _readme(_zip(build_images_zip(data)))
        assert "Cota no numérica en S-09." in readme
        assert "Sección S-01: sin altura de banco válida." in readme

    def test_readme_uses_crlf_free_utf8_text(self):
        raw = _zip(build_images_zip(_data())).read("LEEME.txt")
        assert b"\r" not in raw
        assert raw.decode("utf-8").endswith("\n")
