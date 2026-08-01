"""Tests for the per-hole powder-factor heat halo (3D).

Confirms each hole emits its own halo whose value peaks on the hole axis
and decays with distance, the trace uses the cold-to-warm Turbo scale
capped at 200 g/ton, and missing inputs degrade gracefully.
"""
import numpy as np
import pandas as pd
import pytest

from ui.modulo_tronadura.figures import (
    build_pf_halo_rings_3d_trace,
    build_pf_halo_rings_trace,
)


def _two_holes_df():
    return pd.DataFrame({
        "X": [0.0, 30.0],
        "Y": [0.0, 0.0],
        "Z_collar": [15.0, 15.0],
        "X_toe": [0.0, 30.0],
        "Y_toe": [0.0, 0.0],
        "Z_toe": [0.0, 0.0],
        "pf_g_per_ton_inf": [100.0, 200.0],
    })


class TestBuildPfHaloRings3D:
    def test_rings_3d_peaks_at_axis_and_decays(self):
        df = _two_holes_df()
        trace = build_pf_halo_rings_3d_trace(df, "pf_g_per_ton_inf",
                                             search_radius=10.0, levels=2,
                                             ring_points=16)
        colors = np.asarray(trace.line.color, dtype=float)
        assert trace.mode == "lines"
        # Per hole: 2 levels x 3 rings x 16 points (closed circle).
        assert len(trace.x) == 2 * 2 * 3 * 16
        # Inner ring (σ/4) carries PF×exp(-(2.5²)/200); outer (σ) PF×exp(-100/200).
        w_inner = float(np.exp(-(2.5 ** 2) / 200.0))
        w_outer = float(np.exp(-(10.0 ** 2) / 200.0))
        n = 16
        assert np.allclose(colors[:n], 100.0 * w_inner)  # hole 1, level 0, inner
        assert np.allclose(colors[2 * n:3 * n], 100.0 * w_outer)  # hole 1, level 0, outer
        assert np.allclose(colors[6 * n:7 * n], 200.0 * w_inner)  # hole 2, level 0, inner
        assert max(colors) <= 200.0 * w_inner

    def test_rings_at_collar_and_toe_levels(self):
        df = _two_holes_df()
        trace = build_pf_halo_rings_3d_trace(df, "pf_g_per_ton_inf",
                                             search_radius=10.0, levels=2,
                                             ring_points=16)
        zs = np.asarray(trace.z, dtype=float)
        n = 16
        # Level 0 at collar Z (15), level 1 at toe Z (0).
        assert np.allclose(zs[:3 * n], 15.0)
        assert np.allclose(zs[3 * n:6 * n], 0.0)

    def test_scale_and_labels(self):
        trace = build_pf_halo_rings_3d_trace(_two_holes_df(), "pf_g_per_ton_inf",
                                             search_radius=10.0)
        cs = trace.line.colorscale
        assert cs[0][0] == 0.0 and cs[-1][0] == 1.0  # Turbo (cold->warm)
        assert trace.line.cmin == 0.0
        assert trace.line.cmax == 200.0  # capped
        assert trace.name == "Halos Espaciales de Factor de Carga por Pozo (g/ton)"
        assert "g/ton" in trace.line.colorbar.title.text

    def test_missing_column_or_empty_returns_none(self):
        df = _two_holes_df().drop(columns=["pf_g_per_ton_inf"])
        assert build_pf_halo_rings_3d_trace(df, "pf_g_per_ton_inf", search_radius=10.0) is None
        assert build_pf_halo_rings_3d_trace(_two_holes_df().iloc[:0],
                                            "pf_g_per_ton_inf", search_radius=10.0) is None

    def test_max_holes_sampling(self):
        df = pd.concat([_two_holes_df()] * 2500, ignore_index=True)  # 5000 rows
        trace = build_pf_halo_rings_3d_trace(df, "pf_g_per_ton_inf",
                                             search_radius=10.0, levels=2,
                                             ring_points=16, max_holes=1000)
        assert len(trace.x) == 1000 * 2 * 3 * 16


class TestBuildPfHaloRings:
    def _df(self):
        return pd.DataFrame({
            "X": [0.0, 30.0],
            "Y": [0.0, 0.0],
            "Z_collar": [15.0, 15.0],
            "X_toe": [0.0, 30.0],
            "Y_toe": [0.0, 0.0],
            "Z_toe": [0.0, 0.0],
            "pf_g_per_ton_inf": [100.0, 200.0],
        })

    def test_one_ring_set_per_hole(self):
        """Each hole draws its own 3 rings — halos never merge."""
        trace = build_pf_halo_rings_trace(self._df(), "pf_g_per_ton_inf",
                                          search_radius=10.0, ring_points=16)
        assert trace.mode == "markers"
        # 2 holes x 3 rings x 16 points
        assert len(trace.x) == 2 * 3 * 16

    def test_rings_centered_on_each_hole(self):
        """Ring x coords must be centred on the hole's own X (0 and 30)."""
        trace = build_pf_halo_rings_trace(self._df(), "pf_g_per_ton_inf",
                                          search_radius=10.0, ring_points=16)
        xs = np.asarray(trace.x)
        n_ring = 16
        # First ring of hole 1 spans cx ± r1; hole 2 rings are at 30 ± r.
        assert xs[:n_ring].min() <= 0.0 and xs[:n_ring].max() > 0.0
        hole2 = xs[3 * n_ring:]
        assert hole2.min() < 30.0 and hole2.max() > 30.0

    def test_ring_colors_decay_with_radius(self):
        """Inner ring = PF×exp(-(σ/4)²/2σ²); outer = PF×exp(-σ²/2σ²)."""
        trace = build_pf_halo_rings_trace(self._df(), "pf_g_per_ton_inf",
                                          search_radius=10.0, ring_points=16)
        colors = np.asarray(trace.marker.color, dtype=float)
        n_ring = 16
        w_inner = float(np.exp(-(2.5 ** 2) / 200.0))
        w_outer = float(np.exp(-(10.0 ** 2) / 200.0))
        assert np.allclose(colors[:n_ring], 100.0 * w_inner)  # hole 1 inner
        assert np.allclose(colors[2 * n_ring:3 * n_ring], 100.0 * w_outer)  # hole 1 outer
        assert np.allclose(colors[3 * n_ring:4 * n_ring], 200.0 * w_inner)  # hole 2 inner

    def test_scale_and_labels(self):
        trace = build_pf_halo_rings_trace(self._df(), "pf_g_per_ton_inf",
                                          search_radius=10.0)
        cs = trace.marker.colorscale
        assert cs[0][0] == 0.0 and cs[-1][0] == 1.0  # Turbo (cold->warm)
        assert trace.marker.cmin == 0.0
        assert trace.marker.cmax == 200.0  # capped
        assert "g/ton" in trace.marker.colorbar.title.text

    def test_missing_column_or_empty_returns_none(self):
        df = self._df().drop(columns=["pf_g_per_ton_inf"])
        assert build_pf_halo_rings_trace(df, "pf_g_per_ton_inf", search_radius=10.0) is None
        assert build_pf_halo_rings_trace(self._df().iloc[:0], "pf_g_per_ton_inf",
                                         search_radius=10.0) is None

    def test_max_holes_sampling(self):
        df = pd.concat([self._df()] * 2500, ignore_index=True)  # 5000 rows
        trace = build_pf_halo_rings_trace(df, "pf_g_per_ton_inf",
                                          search_radius=10.0, ring_points=16,
                                          max_holes=1000)
        assert len(trace.x) == 1000 * 3 * 16
