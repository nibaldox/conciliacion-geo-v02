import numpy as np
import pytest
import trimesh

ezdxf = pytest.importorskip("ezdxf")

from core import SectionLine, cut_mesh_with_section, import_dxf_surface, inspect_dxf_surface, load_mesh


def _write_face(path, *, units=0, layer="terrain", offset=0.0):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = units
    doc.modelspace().add_3dface(
        [(offset, 0, 0), (offset + 10, 0, 0), (offset + 10, 10, 5), (offset, 10, 5)],
        dxfattribs={"layer": layer},
    )
    doc.saveas(path)
    return path


def test_inspect_dxf_reports_surface_layers_counts_and_bounds(tmp_path):
    path = _write_face(tmp_path / "terrain.dxf", offset=1_000_000)
    report = inspect_dxf_surface(path)
    assert report["declared_units"] == 0
    assert report["layers"][0]["name"] == "terrain"
    assert report["layers"][0]["n_faces"] == 2
    assert report["layers"][0]["bounds"]["xmin"] == 1_000_000
    assert report["entity_counts"]["3DFACE"] == 1


def test_import_preserves_raw_double_coordinates_and_load_mesh_contract(tmp_path):
    path = _write_face(tmp_path / "terrain.dxf", offset=1_000_000)
    mesh, report = import_dxf_surface(path)
    assert isinstance(mesh, trimesh.Trimesh)
    assert mesh.vertices.dtype == np.float64
    assert mesh.bounds[0, 0] == 1_000_000
    assert len(mesh.faces) == 2
    assert report["scale_factor"] == 1.0
    assert np.array_equal(load_mesh(path).vertices, mesh.vertices)


def test_large_mining_coordinates_keep_submillimeter_precision(tmp_path):
    base = 6_000_000.123456
    path = _write_face(tmp_path / "precision.dxf", offset=base)
    mesh, _ = import_dxf_surface(path)
    assert mesh.vertices[:, 0].min() == pytest.approx(base, abs=1e-9)
    assert mesh.vertices.dtype == np.float64


def test_units_selection_and_conversion_to_meters(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    msp.add_3dface([(0, 0, 0), (1000, 0, 0), (1000, 1000, 0), (0, 1000, 0)], dxfattribs={"layer": "surface"})
    msp.add_line((0, 0, 0), (1, 1, 0), dxfattribs={"layer": "notes"})
    path = tmp_path / "units.dxf"
    doc.saveas(path)
    mesh, report = import_dxf_surface(path, layers=["surface"], units=4)
    assert report["declared_units"] == 4
    assert report["confirmed_units"] == 4
    assert report["scale_factor"] == 0.001
    assert mesh.bounds[1, 0] == pytest.approx(1.0)
    with pytest.raises(ValueError, match="DXF_LAYER_EMPTY"):
        import_dxf_surface(path, layers=["notes"])


def test_survey_foot_units_convert_using_dxf_definition(tmp_path):
    path = _write_face(tmp_path / "survey_feet.dxf", units=21)
    mesh, report = import_dxf_surface(path, units=21)
    assert report["scale_factor"] == pytest.approx(1200 / 3937)
    assert mesh.bounds[1, 0] == pytest.approx(10 * 1200 / 3937)


def test_polyface_imports_indexed_faces(tmp_path):
    doc = ezdxf.new("R2010")
    polyface = doc.modelspace().add_polyface(dxfattribs={"layer": "polyface"})
    polyface.append_face([(0, 0, 0), (2, 0, 0), (2, 2, 1), (0, 2, 1)])
    path = tmp_path / "polyface.dxf"
    doc.saveas(path)
    mesh, report = import_dxf_surface(path)
    assert len(mesh.faces) == 2
    assert report["entity_counts"]["POLYLINE"] == 1


def test_nested_insert_applies_translation_rotation_and_layer_inheritance(tmp_path):
    doc = ezdxf.new("R2010")
    block = doc.blocks.new("SURFACE")
    block.add_3dface([(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)], dxfattribs={"layer": "0"})
    nested = doc.blocks.new("NESTED")
    nested.add_blockref("SURFACE", (0, 0, 0), dxfattribs={"layer": "0"})
    doc.modelspace().add_blockref("NESTED", (100, 200, 0), dxfattribs={"layer": "chosen", "rotation": 90})
    path = tmp_path / "insert.dxf"
    doc.saveas(path)
    summary = inspect_dxf_surface(path)
    assert [layer["name"] for layer in summary["layers"]] == ["chosen"]
    mesh, _ = import_dxf_surface(path)
    assert mesh.bounds[:, 0] == pytest.approx([99.0, 100.0])
    assert mesh.bounds[:, 1] == pytest.approx([200.0, 202.0])


def test_minsert_expands_instances_with_bounded_count(tmp_path):
    doc = ezdxf.new("R2010")
    block = doc.blocks.new("FACE")
    block.add_3dface([(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)], dxfattribs={"layer": "0"})
    doc.modelspace().add_blockref("FACE", (0, 0, 0), dxfattribs={"layer": "surface", "column_count": 2, "column_spacing": 3})
    path = tmp_path / "array.dxf"
    doc.saveas(path)
    mesh, report = import_dxf_surface(path)
    assert mesh.bounds[:, 0] == pytest.approx([0, 5])
    assert report["entity_counts"]["3DFACE"] == 2


def test_minsert_array_is_rejected_before_expansion_limit(tmp_path, monkeypatch):
    doc = ezdxf.new("R2010")
    block = doc.blocks.new("FACE")
    block.add_3dface([(0, 0, 0), (1, 0, 0), (1, 1, 0)])
    doc.modelspace().add_blockref("FACE", (0, 0, 0), dxfattribs={"column_count": 100, "column_spacing": 2})
    path = tmp_path / "oversized_array.dxf"
    doc.saveas(path)
    import core.dxf_import as dxf_import

    monkeypatch.setattr(dxf_import, "MAX_EXPANDED_ENTITIES", 8)
    with pytest.raises(ValueError, match="DXF_ENTITY_LIMIT_EXCEEDED"):
        inspect_dxf_surface(path)


def test_cyclic_block_reference_is_rejected(tmp_path):
    doc = ezdxf.new("R2010")
    block = doc.blocks.new("LOOP")
    block.add_blockref("LOOP", (0, 0, 0))
    doc.modelspace().add_blockref("LOOP", (0, 0, 0))
    path = tmp_path / "cycle.dxf"
    doc.saveas(path)
    with pytest.raises(ValueError, match="DXF_BLOCK_CYCLE"):
        inspect_dxf_surface(path)


def test_missing_block_definition_is_rejected(tmp_path):
    doc = ezdxf.new("R2010")
    doc.blocks.new("EXISTS")
    insert = doc.modelspace().add_blockref("EXISTS", (0, 0, 0))
    insert.dxf.name = "MISSING"
    path = tmp_path / "missing_block.dxf"
    doc.saveas(path)
    with pytest.raises(ValueError, match="DXF_MISSING_BLOCK"):
        inspect_dxf_surface(path)


def test_xclip_insert_is_rejected(tmp_path):
    from ezdxf.xclip import XClip

    doc = ezdxf.new("R2010")
    block = doc.blocks.new("FACE")
    block.add_3dface([(0, 0, 0), (2, 0, 0), (2, 2, 0)])
    insert = doc.modelspace().add_blockref("FACE", (0, 0, 0))
    XClip(insert).set_block_clipping_path([(0, 0), (1, 0), (1, 1), (0, 1)])
    XClip(insert).enable_clipping()
    path = tmp_path / "xclip.dxf"
    doc.saveas(path)
    with pytest.raises(ValueError, match="DXF_XCLIP_UNSUPPORTED"):
        inspect_dxf_surface(path)


def test_skipped_surface_from_virtual_insert_is_reported(tmp_path, monkeypatch):
    from ezdxf.entities import Insert

    doc = ezdxf.new("R2010")
    block = doc.blocks.new("FACE")
    face = block.add_3dface([(0, 0, 0), (1, 0, 0), (1, 1, 0)])
    doc.modelspace().add_blockref("FACE", (0, 0, 0))
    path = tmp_path / "skipped.dxf"
    doc.saveas(path)

    def skipped(self, *, skipped_entity_callback=None, redraw_order=False):
        if skipped_entity_callback:
            skipped_entity_callback(face, "test transform rejection")
        return iter(())

    monkeypatch.setattr(Insert, "virtual_entities", skipped)
    with pytest.raises(ValueError, match="DXF_TRANSFORM_UNSUPPORTED"):
        inspect_dxf_surface(path)


def test_concave_face_triangulates_without_filling_notch(tmp_path):
    doc = ezdxf.new("R2010")
    mesh_entity = doc.modelspace().add_mesh(dxfattribs={"layer": "concave"})
    mesh_entity.vertices = [(0, 0, 0), (3, 0, 0), (3, 3, 0), (1, 1, 0), (0, 3, 0)]
    mesh_entity.faces.set_data([[0, 1, 2, 3, 4]])
    path = tmp_path / "concave.dxf"
    doc.saveas(path)
    mesh, _ = import_dxf_surface(path)
    assert len(mesh.faces) == 3
    assert mesh.area == pytest.approx(6.0)


def test_nonplanar_ngon_is_rejected(tmp_path):
    doc = ezdxf.new("R2010")
    mesh_entity = doc.modelspace().add_mesh()
    mesh_entity.vertices = [(0, 0, 0), (2, 0, 0), (2, 2, 1), (0, 2, 0)]
    mesh_entity.faces.set_data([[0, 1, 2, 3]])
    path = tmp_path / "nonplanar.dxf"
    doc.saveas(path)
    with pytest.raises(ValueError, match="DXF_NONPLANAR_POLYGON"):
        import_dxf_surface(path)


def test_self_intersecting_bowtie_is_rejected(tmp_path):
    doc = ezdxf.new("R2010")
    mesh_entity = doc.modelspace().add_mesh()
    mesh_entity.vertices = [(0, 0, 0), (2, 2, 0), (0, 2, 0), (2, 0, 0)]
    mesh_entity.faces.set_data([[0, 1, 2, 3]])
    path = tmp_path / "bowtie.dxf"
    doc.saveas(path)
    with pytest.raises(ValueError, match="DXF_AMBIGUOUS_POLYGON"):
        import_dxf_surface(path)


def test_closed_polyline_is_not_inferred_as_surface(tmp_path):
    doc = ezdxf.new("R2010")
    polyline = doc.modelspace().add_polyline3d([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
    polyline.close(True)
    path = tmp_path / "outline.dxf"
    doc.saveas(path)
    assert inspect_dxf_surface(path)["layers"] == []
    with pytest.raises(ValueError, match="DXF_NO_SURFACE"):
        import_dxf_surface(path)


def test_polygon_mesh_polyline_is_reported_as_unsupported(tmp_path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_polymesh((2, 2))
    path = tmp_path / "polymesh.dxf"
    doc.saveas(path)
    report = inspect_dxf_surface(path)
    assert "UNSUPPORTED_POLYMESH" in report["warnings"]
    with pytest.raises(ValueError, match="DXF_NO_SURFACE"):
        import_dxf_surface(path)


def test_mesh_with_subdivision_is_rejected_instead_of_importing_control_cage(tmp_path):
    doc = ezdxf.new("R2010")
    mesh_entity = doc.modelspace().add_mesh()
    mesh_entity.dxf.subdivision_levels = 1
    mesh_entity.vertices = [(0, 0, 0), (1, 0, 0), (1, 1, 0)]
    mesh_entity.faces.set_data([[0, 1, 2]])
    path = tmp_path / "subdivided.dxf"
    doc.saveas(path)
    assert "UNSUPPORTED_MESH_SUBDIVISION" in inspect_dxf_surface(path)["warnings"]
    with pytest.raises(ValueError, match="DXF_MESH_SUBDIVISION_UNSUPPORTED"):
        import_dxf_surface(path)


def test_face_expansion_limit_is_enforced(tmp_path, monkeypatch):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for offset in (0, 2):
        msp.add_3dface([(offset, 0, 0), (offset + 1, 0, 0), (offset + 1, 1, 0), (offset, 1, 0)])
    path = tmp_path / "many_faces.dxf"
    doc.saveas(path)
    import core.dxf_import as dxf_import

    monkeypatch.setattr(dxf_import, "MAX_SURFACE_FACES", 1)
    with pytest.raises(ValueError, match="DXF_FACE_LIMIT_EXCEEDED"):
        inspect_dxf_surface(path)


def test_discarded_degenerate_and_duplicate_faces_are_reported(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    face = [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]
    msp.add_3dface(face)
    msp.add_3dface(face)
    msp.add_3dface([(0, 0, 0), (1, 0, 0), (2, 0, 0)])
    path = tmp_path / "cleanup.dxf"
    doc.saveas(path)
    mesh, report = import_dxf_surface(path)
    assert len(mesh.faces) == 2
    assert report["discarded_faces"] == 3
    assert "DISCARDED_FACES" in report["warnings"]


def test_identical_dxf_and_stl_faces_have_identical_profiles(tmp_path):
    path = _write_face(tmp_path / "same.dxf")
    dxf_mesh, _ = import_dxf_surface(path)
    stl_path = tmp_path / "same.stl"
    trimesh.Trimesh(vertices=dxf_mesh.vertices.copy(), faces=dxf_mesh.faces.copy(), process=False).export(stl_path)
    stl_mesh = trimesh.load(stl_path, force="mesh")
    assert np.allclose(np.sort(dxf_mesh.bounds, axis=0), np.sort(stl_mesh.bounds, axis=0), atol=1e-6)
    assert np.allclose(np.sort(dxf_mesh.area_faces), np.sort(stl_mesh.area_faces), atol=1e-6)
    section = SectionLine(name="check", origin=np.array([5.0, 0.0]), azimuth=0.0, length=20.0)
    dxf_profile = cut_mesh_with_section(dxf_mesh, section)
    stl_profile = cut_mesh_with_section(stl_mesh, section)
    assert dxf_profile is not None and stl_profile is not None
    assert np.allclose(dxf_profile.distances, stl_profile.distances, atol=1e-6)
    assert np.allclose(dxf_profile.elevations, stl_profile.elevations, atol=1e-6)
