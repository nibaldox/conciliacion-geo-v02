"""Tests for pure generators in ui.tabs.export."""
import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ui.tabs.export import dxf, excel, png, word


class FakeProfile:
    def __init__(self, distances, elevations):
        self.distances = np.array(distances)
        self.elevations = np.array(elevations)


class FakeSection:
    def __init__(self, name='S1', origin=(0.0, 0.0), azimuth=0.0):
        self.name = name
        self.origin = origin
        self.azimuth = azimuth


class FakeParams:
    def __init__(self, benches=None):
        self.benches = benches or []


class TestBuildWorkbook:
    def test_returns_bytes_from_export_results(self, monkeypatch, tmp_path):
        def fake_export(*args, **kwargs):
            path = args[4]
            with open(path, 'wb') as f:
                f.write(b'XLSX')

        monkeypatch.setattr(excel, 'export_results', fake_export)
        monkeypatch.setattr(excel.tempfile, 'gettempdir', lambda: str(tmp_path))
        result = excel.build_workbook([], [], [], {}, {})
        assert result == b'XLSX'


class TestBuildDocument:
    def test_returns_bytes_from_generate_word_report(self, monkeypatch, tmp_path):
        def fake_generate(*args, **kwargs):
            path = args[2]
            with open(path, 'wb') as f:
                f.write(b'DOCX')

        monkeypatch.setattr(word, 'generate_word_report', fake_generate)
        monkeypatch.setattr(word.tempfile, 'gettempdir', lambda: str(tmp_path))
        pd_prof = FakeProfile([0, 1], [10, 11])
        pt_prof = FakeProfile([0, 1], [10, 11])
        profile_pairs = {'S1': (pd_prof, pt_prof)}
        design_map = {'S1': FakeParams()}
        topo_map = {'S1': FakeParams()}
        result = word.build_document(
            [], [FakeSection()], profile_pairs, design_map, topo_map, {}
        )
        assert result == b'DOCX'

    def test_skips_sections_without_profile_pair(self, monkeypatch, tmp_path):
        calls = []

        def fake_generate(filtered_comps, all_data, path, **kwargs):
            calls.append(all_data)
            with open(path, 'wb') as f:
                f.write(b'DOCX')

        monkeypatch.setattr(word, 'generate_word_report', fake_generate)
        monkeypatch.setattr(word.tempfile, 'gettempdir', lambda: str(tmp_path))
        result = word.build_document(
            [], [FakeSection()], {}, {}, {}, {}
        )
        assert result == b'DOCX'
        assert calls[0] == []


class TestBuildPngZip:
    def test_returns_zip_bytes(self, monkeypatch):
        def fake_generate(*args, **kwargs):
            buf = io.BytesIO(b'ZIP')
            return buf

        monkeypatch.setattr(png, 'generate_section_images_zip', fake_generate)
        pd_prof = FakeProfile([0, 1], [10, 11])
        pt_prof = FakeProfile([0, 1], [10, 11])
        result = png.build_png_zip(
            [FakeSection()], {'S1': (pd_prof, pt_prof)}, {}, {}, {}
        )
        assert result == b'ZIP'

    def test_skips_sections_without_profile_pair(self, monkeypatch):
        calls = []

        def fake_generate(all_data, **kwargs):
            calls.append(all_data)
            buf = io.BytesIO(b'ZIP')
            return buf

        monkeypatch.setattr(png, 'generate_section_images_zip', fake_generate)
        result = png.build_png_zip([FakeSection()], {}, {}, {}, {})
        assert result == b'ZIP'
        assert calls[0] == []


class TestBuildDxf:
    @patch('ui.tabs.export.dxf.ezdxf')
    def test_returns_bytes_and_count(self, mock_ezdxf, monkeypatch, tmp_path):
        doc = MagicMock()
        msp = MagicMock()
        doc.modelspace.return_value = msp
        doc.layers = MagicMock()
        mock_ezdxf.new.return_value = doc

        def fake_saveas(path):
            with open(path, 'wb') as f:
                f.write(b'DXF')

        doc.saveas.side_effect = fake_saveas

        monkeypatch.setattr(dxf, '_write_section_to_dxf', lambda *args, **kwargs: None)
        monkeypatch.setattr(dxf, '_create_dxf_layers', lambda doc: None)

        pd_prof = FakeProfile([0, 1], [10, 11])
        pt_prof = FakeProfile([0, 1], [10, 11])
        result_bytes, n = dxf.build_dxf(
            [FakeSection()], {'S1': (pd_prof, pt_prof)}, {}, {}, []
        )
        assert n == 1
        assert result_bytes == b'DXF'
        mock_ezdxf.new.assert_called_once_with('R2010')

    @patch('ui.tabs.export.dxf.ezdxf')
    @patch('ui.tabs.export.dxf.azimuth_to_direction')
    @patch('ui.tabs.export.dxf.build_reconciled_profile')
    def test_writes_section_with_reconciled_profiles(
        self, mock_build_reconciled, mock_azimuth, mock_ezdxf, monkeypatch, tmp_path
    ):
        doc = MagicMock()
        msp = MagicMock()
        doc.modelspace.return_value = msp
        doc.layers = MagicMock()
        mock_ezdxf.new.return_value = doc

        def fake_saveas(path):
            with open(path, 'wb') as f:
                f.write(b'DXF')

        doc.saveas.side_effect = fake_saveas
        mock_azimuth.return_value = (1.0, 0.0)
        mock_build_reconciled.return_value = ([0.0, 1.0], [10.0, 11.0])

        class FakeParamsWithBenches:
            benches = [object()]

        pd_prof = FakeProfile([0, 1], [10, 11])
        pt_prof = FakeProfile([0, 1], [10, 11])
        result_bytes, n = dxf.build_dxf(
            [FakeSection()],
            {'S1': (pd_prof, pt_prof)},
            {'S1': FakeParamsWithBenches()},
            {'S1': FakeParamsWithBenches()},
            [],
        )
        assert n == 1
        assert result_bytes == b'DXF'
        assert msp.add_polyline3d.called
        assert msp.add_text.called
        assert mock_build_reconciled.call_count == 2
