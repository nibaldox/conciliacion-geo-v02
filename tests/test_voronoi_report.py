"""Tests for compute_influence_area_report — Voronoi influence with provenance.

Spec §4.8: per-hole influence areas must (a) distinguish real cells from
heuristic estimates, (b) handle duplicate collars, (c) optionally clip to
the real blast polygon, (d) verify the area sum against the domain, and
(e) report invalid cells.
"""
import numpy as np
import pandas as pd
import pytest

from core.blast_metrics import compute_influence_area_report


def _grid_df(n_side=5, spacing=6.0, x0=100.0, y0=200.0):
    """n_side×n_side regular grid of collars (interior + edge holes)."""
    rows = []
    for ix in range(n_side):
        for iy in range(n_side):
            rows.append({"X": x0 + ix * spacing, "Y": y0 + iy * spacing, "label": f"H-{ix}-{iy}"})
    return pd.DataFrame(rows)


class TestAreaReport:
    def test_columns_present(self):
        out = compute_influence_area_report(_grid_df())
        assert {"area_m2", "area_status", "label"}.issubset(out.columns)

    def test_interior_holes_real_cells(self):
        out = compute_influence_area_report(_grid_df(n_side=5))
        # True interior = rows/cols 1..3 (the outer ring touches the domain box)
        interior = out.loc[
            ~out["label"].str.match(r"H-[04]-|H-[0-4]-[04]")
        ]
        assert (interior["area_status"] == "voronoi_cell").all()
        assert np.allclose(interior["area_m2"].to_numpy(), 36.0, rtol=1e-6)

    def test_sum_areas_matches_domain(self):
        out = compute_influence_area_report(_grid_df(n_side=5))
        domain = (4 * 6.0) ** 2  # 24×24 m box
        assert out["area_m2"].sum() == pytest.approx(domain, rel=1e-6)

    def test_duplicate_collars_share_cell(self):
        """H-03: duplicate collars SPLIT the shared cell area (never duplicated)."""
        df = _grid_df(n_side=3)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)  # duplicate collar
        out = compute_influence_area_report(df)
        dup = out.tail(1)
        assert dup["area_status"].iloc[0] == "duplicate_shared"
        assert dup["area_m2"].iloc[0] == pytest.approx(out.iloc[0]["area_m2"], rel=1e-6)
        # The shared cell is counted ONCE: original + duplicate = same cell
        # area as the non-duplicated corner cell (H-2-2).
        corner = out.loc[out["label"] == "H-2-2"]
        assert out.iloc[0]["area_m2"] + dup["area_m2"].iloc[0] == pytest.approx(
            corner["area_m2"].iloc[0], rel=1e-6
        )

    def test_duplicates_area_conservation(self):
        """H-03: sum of assigned areas equals the domain even with duplicates."""
        df = _grid_df(n_side=5)
        df = pd.concat([df, df.iloc[[0]], df.iloc[[1]]], ignore_index=True)
        out = compute_influence_area_report(df)
        domain = (4 * 6.0) ** 2
        assert out["area_m2"].sum() == pytest.approx(domain, rel=1e-6)

    def test_duplicates_share_cell_series_api(self):
        """H-03: the bare-Series API splits the area the same way."""
        from core.blast_metrics import compute_influence_area_m2
        df = _grid_df(n_side=3)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        out = compute_influence_area_m2(df)
        assert out.iloc[-1] == pytest.approx(out.iloc[0], rel=1e-6)
        # original + duplicate = same as the non-duplicated corner cell
        corner = out.iloc[8]  # H-2-2 corner, not duplicated
        assert out.iloc[0] + out.iloc[-1] == pytest.approx(corner, rel=1e-6)

    def test_invalid_cells_reported(self):
        df = _grid_df(n_side=3)
        df.loc[0, "X"] = np.nan
        out = compute_influence_area_report(df)
        invalid_mask = out["area_status"] == "invalid_coordinates"
        assert invalid_mask.sum() == 1
        assert out.loc[invalid_mask, "area_m2"].iloc[0] == 0.0

    def test_too_few_holes_all_invalid(self):
        df = _grid_df(n_side=2).head(3)
        out = compute_influence_area_report(df)
        assert (out["area_status"] == "invalid").sum() == 3

    def test_edge_holes_not_flagged_as_real(self):
        """Edge (convex hull) cells use heuristic closure -> not 'voronoi_cell'."""
        out = compute_influence_area_report(_grid_df(n_side=5))
        edges = out.loc[out["label"].isin(["H-0-0", "H-4-4", "H-0-4", "H-4-0"])]
        assert not (edges["area_status"] == "voronoi_cell").all()

    def test_clip_to_blast_polygon(self):
        """Clipping to the real blast polygon must keep the sum <= polygon area."""
        shapely = pytest.importorskip("shapely")
        df = _grid_df(n_side=7)  # 36×36 m grid
        polygon = [(100.0, 200.0), (130.0, 200.0), (130.0, 230.0), (100.0, 230.0)]  # 30×30 m
        out = compute_influence_area_report(df, boundary_polygon=polygon)
        assert (out["area_status"] == "clipped_to_blast_polygon").any()
        poly = shapely.geometry.Polygon(polygon)
        assert out["area_m2"].sum() <= poly.area + 1e-6
        assert out["area_m2"].sum() > 0


class TestOperationalIntegration:
    """H-02: compute_powder_factor must consume the validated Voronoi areas."""

    def test_operational_and_report_areas_identical(self):
        from core.blast_correlation import compute_powder_factor

        df = _grid_df(n_side=4)
        df["Kilos_Cargados_real"] = 300.0
        df["Nombre_Banco"] = 4000.0
        df["Inclinacion_real"] = 0.0
        df["Azimuth_real"] = 0.0
        df["longitud_real"] = 12.0
        out = compute_powder_factor(df)
        rep = compute_influence_area_report(df.rename(columns={"X": "X", "Y": "Y"}))
        assert out["area_influence_m2"].to_numpy() == pytest.approx(
            rep["area_m2"].to_numpy(), rel=1e-9
        )

    def test_status_propagated_to_operational_frame(self):
        from core.blast_correlation import compute_powder_factor

        df = _grid_df(n_side=4)
        df["Kilos_Cargados_real"] = 300.0
        df["Nombre_Banco"] = 4000.0
        df["Inclinacion_real"] = 0.0
        df["Azimuth_real"] = 0.0
        df["longitud_real"] = 12.0
        out = compute_powder_factor(df)
        assert "area_status" in out.columns
        assert "domain_area_m2" in out.columns
        assert set(out["area_status"].unique()) <= {
            "voronoi_cell", "edge_clipped", "duplicate_shared",
        }

    def test_powder_factor_with_duplicates_uses_split_areas(self):
        from core.blast_correlation import compute_powder_factor

        df = _grid_df(n_side=3)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        df["Kilos_Cargados_real"] = 300.0
        df["Nombre_Banco"] = 4000.0
        df["Inclinacion_real"] = 0.0
        df["Azimuth_real"] = 0.0
        df["longitud_real"] = 12.0
        out = compute_powder_factor(df)
        dup_area = out["area_influence_m2"].iloc[-1]
        orig_area = out["area_influence_m2"].iloc[0]
        assert dup_area == pytest.approx(orig_area, rel=1e-9)
        # pf uses the split area -> both rows share the same pf
        assert out["pf_g_per_ton_inf"].iloc[0] == pytest.approx(
            out["pf_g_per_ton_inf"].iloc[-1], rel=1e-9
        )
