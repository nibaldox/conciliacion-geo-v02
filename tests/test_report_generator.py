"""Tests for core.report_generator — plots, pie charts, image zip."""
import io
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest

from core.report_generator import (
    create_section_plot,
    create_compliance_pie_charts,
    generate_section_images_zip,
)


class TestCreateSectionPlot:
    def test_basic_section_plot(self):
        distances = np.linspace(0, 50, 20)
        elevations = 100 - distances * 0.5
        buf = create_section_plot(
            params_design=None,
            params_topo=None,
            distances_d=distances,
            elevations_d=elevations,
            distances_t=distances,
            elevations_t=elevations - 0.5,
        )
        assert isinstance(buf, io.BytesIO)
        assert buf.getbuffer().nbytes > 0
        buf.seek(0)
        assert buf.read(8).startswith(b"\x89PNG\r\n\x1a\n")

    def test_section_plot_with_bench_params(self):
        from core.param_extractor import BenchParams, ExtractionResult
        distances = np.array([0, 10, 20, 30, 40])
        elevations = np.array([100, 95, 90, 85, 80])
        bench = BenchParams(
            bench_number=1,
            crest_elevation=100.0,
            crest_distance=0.0,
            toe_elevation=85.0,
            toe_distance=40.0,
            bench_height=15.0,
            face_angle=70.0,
            berm_width=8.0,
        )
        params = ExtractionResult(
            section_name="BENCH", sector="TEST",
            benches=[bench], inter_ramp_angle=65.0, overall_angle=55.0,
        )
        buf = create_section_plot(
            params_design=params,
            params_topo=params,
            distances_d=distances,
            elevations_d=elevations,
            distances_t=distances,
            elevations_t=elevations,
        )
        assert isinstance(buf, io.BytesIO)
        assert buf.getbuffer().nbytes > 0

    def test_section_plot_empty(self):
        buf = create_section_plot(
            params_design=None,
            params_topo=None,
            distances_d=np.array([]),
            elevations_d=np.array([]),
            distances_t=np.array([]),
            elevations_t=np.array([]),
        )
        assert isinstance(buf, io.BytesIO)


class TestCompliancePieCharts:
    def test_pie_chart_returns_figures(self):
        comparisons = [
            {"height_status": "CUMPLE"},
            {"height_status": "CUMPLE"},
            {"height_status": "FUERA DE TOLERANCIA"},
            {"height_status": "NO CUMPLE"},
        ]
        result = create_compliance_pie_charts(comparisons)
        assert result is not None

    def test_empty_comparisons(self):
        result = create_compliance_pie_charts([])
        assert result is not None

    def test_all_cumple(self):
        comparisons = [{"height_status": "CUMPLE"}] * 5
        result = create_compliance_pie_charts(comparisons)
        assert result is not None

    def test_mixed_statuses_with_berm(self):
        comparisons = [
            {"height_status": "CUMPLE", "angle_status": "FUERA DE TOLERANCIA", "berm_status": "NO CUMPLE"},
            {"height_status": "FUERA DE TOLERANCIA", "angle_status": "CUMPLE", "berm_status": "CUMPLE"},
        ]
        result = create_compliance_pie_charts(comparisons)
        assert result is not None


class TestGenerateSectionImagesZip:
    def test_zip_creation_with_minimal_data(self):
        all_data = [
            {
                "section_name": "SEC_A",
                "params_design": None,
                "params_topo": None,
                "profile_d": (np.linspace(0, 30, 10), 100 - np.linspace(0, 30, 10)),
                "profile_t": (np.linspace(0, 30, 10), 99 - np.linspace(0, 30, 10)),
                "comparisons": [],
            }
        ]
        result = generate_section_images_zip(all_data)
        assert result is not None
        assert hasattr(result, "read") or isinstance(result, (bytes, io.BytesIO))

    def test_zip_creation_with_sections_list(self):
        from core.section_cutter import SectionLine
        sec = SectionLine(
            name="SEC_X",
            origin=np.array([0.0, 0.0]),
            azimuth=0.0,
            length=50.0,
        )
        all_data = [
            {
                "section_name": "SEC_X",
                "params_design": None,
                "params_topo": None,
                "profile_d": ([0.0, 25.0, 50.0], [100.0, 95.0, 90.0]),
                "profile_t": ([0.0, 25.0, 50.0], [99.0, 94.5, 89.5]),
                "comparisons": [],
            }
        ]
        result = generate_section_images_zip(all_data, sections=[sec])
        assert result is not None

    def test_zip_with_multiple_sections(self):
        all_data = []
        for i in range(3):
            all_data.append({
                "section_name": f"SEC_{i}",
                "params_design": None,
                "params_topo": None,
                "profile_d": ([0.0, 10.0], [100.0, 90.0]),
                "profile_t": ([0.0, 10.0], [99.0, 89.0]),
                "comparisons": [],
            })
        result = generate_section_images_zip(all_data)
        assert result is not None

    def test_zip_with_plot_options(self):
        all_data = [
            {
                "section_name": "SEC_Y",
                "params_design": None,
                "params_topo": None,
                "profile_d": ([0.0, 50.0], [100.0, 90.0]),
                "profile_t": ([0.0, 50.0], [99.0, 89.0]),
                "comparisons": [],
            }
        ]
        result = generate_section_images_zip(
            all_data, plot_options={"show_areas": False, "show_reconciled": False},
        )
        assert result is not None