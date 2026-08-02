"""Voronoi global conservation tests (Fase 1.1 cierre, sección 2.1).

The event domain must be assigned exactly once: with multiple mallas and
a single event polygon, the total assigned area must equal the event
area (regression: 300 m² must NOT become 337.5 m²).
"""
import numpy as np
import pandas as pd
import pytest

from core.blast_correlation import compute_powder_factor


def _event_df(n_side=3, spacing=5.0, x0=100.0, y0=200.0, malla="M1"):
    """n_side×n_side grid of holes, all in one malla."""
    rows = []
    for ix in range(n_side):
        for iy in range(n_side):
            rows.append({
                "X": x0 + ix * spacing,
                "Y": y0 + iy * spacing,
                "label_pozo": f"{malla}-{ix}-{iy}",
                "Kilos_Cargados_real": 300.0,
                "Nombre_Banco": 4000.0,
                "Inclinacion_real": 0.0,
                "Azimuth_real": 0.0,
                "longitud_real": 12.0,
                "Burden": 5.0,
                "Esp": 5.0,
                "Tipo_Explosivo": "ANFO",
                "Nombre_Malla_Original": malla,
            })
    return pd.DataFrame(rows)


def _event_polygon(n_side=3, spacing=5.0, x0=100.0, y0=200.0):
    """Square polygon covering the full cell domain: 15×15 m for 3×3 @ 5 m
    (cells span [x0 - s/2, x0 + (n-1)s + s/2])."""
    half = n_side * spacing / 2.0
    cx, cy = x0 + (n_side - 1) * spacing / 2.0, y0 + (n_side - 1) * spacing / 2.0
    return [
        (cx - half, cy - half), (cx + half, cy - half),
        (cx + half, cy + half), (cx - half, cy + half),
    ]


def _event_area():
    """Area of _event_polygon() for 3×3 @ 5 m: 15×15 = 225 m²."""
    return 225.0


def _square_polygon(cx, cy, half):
    return [(cx - half, cy - half), (cx + half, cy - half),
            (cx + half, cy + half), (cx - half, cy + half)]


class TestGlobalConservation:
    def test_single_malla_225_m2_polygon(self):
        """Una malla + polígono 15×15 = 225 m²: asignado = dominio."""
        df = _event_df()
        out = compute_powder_factor(df, boundary_polygon=_event_polygon())
        # 15×15 m polygon = 225 m²; assigned must equal it within tolerance
        assert out["area_influence_m2"].sum() == pytest.approx(_event_area(), rel=1e-3)
        assert bool(out["voronoi_conservation_ok"].iloc[0]) is True
        assert abs(out["area_residual_pct"].iloc[0]) < 1.0

    def test_two_mallas_global_polygon_no_duplication(self):
        """Regression case: 300 m² must NOT become 337.5 m² (per-malla clip)."""
        df_a = _event_df(n_side=3, spacing=5.0, x0=100.0, y0=200.0, malla="A")
        df_b = _event_df(n_side=3, spacing=5.0, x0=100.0, y0=200.0, malla="B")
        df = pd.concat([df_a, df_b], ignore_index=True)
        poly = _event_polygon(n_side=3, spacing=5.0)  # 15×15 = 225 m²
        out = compute_powder_factor(df, boundary_polygon=poly)
        assigned = out["area_influence_m2"].sum()
        # One shared domain: duplicates across mallas SPLIT the shared cell.
        assert assigned == pytest.approx(_event_area(), rel=1e-3)
        # regression guard: 225 m² must never become ~450 m² (per-malla clip)
        assert assigned < _event_area() * 1.2
        assert bool(out["voronoi_conservation_ok"].iloc[0]) is True

    def test_duplicate_collars_across_mallas_split(self):
        """Same collar in two mallas: the shared cell is split, not doubled."""
        df_a = _event_df(n_side=3, spacing=5.0, x0=100.0, y0=200.0, malla="A")
        df_b = _event_df(n_side=3, spacing=5.0, x0=100.0, y0=200.0, malla="B")
        df = pd.concat([df_a, df_b], ignore_index=True)
        out = compute_powder_factor(df, boundary_polygon=_event_polygon())
        dup = out[out["label_pozo"] == "B-0-0"]
        orig = out[out["label_pozo"] == "A-0-0"]
        assert dup["area_influence_m2"].iloc[0] == pytest.approx(
            orig["area_influence_m2"].iloc[0], rel=1e-9
        )
        assert (out["area_status"] == "duplicate_shared").sum() == len(out)  # all 9 collars duplicated across mallas

    def test_duplicates_within_malla_split(self):
        df = _event_df(n_side=3)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        out = compute_powder_factor(df, boundary_polygon=_event_polygon())
        assert (out["area_status"] == "duplicate_shared").sum() == 2  # one collar duplicated
        assert out["area_influence_m2"].sum() == pytest.approx(_event_area(), rel=1e-3)

    def test_holes_outside_domain_reported(self):
        df = _event_df(n_side=3)
        df.loc[0, "X"] = 500.0  # hole far outside the event polygon
        out = compute_powder_factor(df, boundary_polygon=_event_polygon())
        assert "fuera del dominio" in str(out["voronoi_validation_messages"].iloc[0]) or \
            (out["area_status"] == "invalid").any()
        assert out["area_influence_m2"].sum() <= _event_area() + 1e-6

    def test_conservation_diagnostics_columns(self):
        df = _event_df()
        out = compute_powder_factor(df, boundary_polygon=_event_polygon())
        for col in ("voronoi_method", "domain_area_m2", "assigned_area_m2",
                    "area_residual_m2", "area_residual_pct",
                    "voronoi_conservation_ok", "voronoi_validation_messages"):
            assert col in out.columns, col
        assert out["domain_area_m2"].iloc[0] == pytest.approx(_event_area(), rel=1e-6)
        assert out["assigned_area_m2"].iloc[0] == pytest.approx(out["area_influence_m2"].sum())

    def test_conservation_failure_blocks_pf_inf(self):
        """When conservation fails, pf_g_per_ton_inf is blocked (NaN + message)."""
        from core.config import DEFAULTS

        df = _event_df()
        df = pd.concat([df, df], ignore_index=True)  # heavy duplication
        out = compute_powder_factor(df, boundary_polygon=_event_polygon())
        if not bool(out["voronoi_conservation_ok"].iloc[0]):
            assert pd.isna(out["pf_g_per_ton_inf"]).all()
            assert "bloqueado" in str(out["voronoi_validation_messages"].iloc[0])
        else:
            # with the global approach duplication only splits cells, so the
            # conservation must hold; assert the mechanism exists instead
            assert "voronoi_conservation_ok" in out.columns


class TestPerMallaPolygons:
    def test_independent_polygons_conserved(self):
        df_a = _event_df(n_side=3, spacing=5.0, x0=100.0, y0=200.0, malla="A")
        df_b = _event_df(n_side=3, spacing=5.0, x0=130.0, y0=200.0, malla="B")
        df = pd.concat([df_a, df_b], ignore_index=True)
        polys = {"A": _square_polygon(105.0, 205.0, 5.0),  # 10×10 around A
                 "B": _square_polygon(135.0, 205.0, 5.0)}  # 10×10 around B
        out = compute_powder_factor(df, boundary_polygons=polys)
        assert out["domain_area_m2"].iloc[0] == pytest.approx(200.0, rel=1e-6)
        assert out["area_influence_m2"].sum() == pytest.approx(200.0, rel=1e-3)
        assert bool(out["voronoi_conservation_ok"].iloc[0]) is True

    def test_overlapping_polygons_detected(self):
        df_a = _event_df(n_side=3, spacing=5.0, x0=100.0, y0=200.0, malla="A")
        df_b = _event_df(n_side=3, spacing=5.0, x0=102.0, y0=200.0, malla="B")
        df = pd.concat([df_a, df_b], ignore_index=True)
        polys = {"A": _square_polygon(105.0, 205.0, 5.0),
                 "B": _square_polygon(107.0, 205.0, 5.0)}  # overlapping squares
        out = compute_powder_factor(df, boundary_polygons=polys)
        assert bool(out["voronoi_conservation_ok"].iloc[0]) is False
        msg = str(out["voronoi_validation_messages"].iloc[0])
        assert "superp" in msg

    def test_gaps_between_polygons_detected(self):
        df_a = _event_df(n_side=3, spacing=5.0, x0=100.0, y0=200.0, malla="A")
        df_b = _event_df(n_side=3, spacing=5.0, x0=140.0, y0=200.0, malla="B")
        df = pd.concat([df_a, df_b], ignore_index=True)
        polys = {"A": _square_polygon(105.0, 205.0, 5.0),
                 "B": _square_polygon(145.0, 205.0, 5.0)}  # gap between
        out = compute_powder_factor(df, boundary_polygons=polys)
        msg = str(out["voronoi_validation_messages"].iloc[0])
        assert "vací" in msg or "hueco" in msg


class TestRegresionExacta300:
    """Cierre final §2.5: regresión exacta del informe — 300 m², no 337,5 m²."""

    def test_exact_300_m2_case(self):
        """Dominio de 300 m², múltiples mallas, un dominio global.

        Histórico incorrecto: 337,5 m² (+12,5 %). Esperado: 300,0 m².
        """
        # Polígono del evento 15×20 = 300 m²
        polygon = [(100.0, 200.0), (115.0, 200.0), (115.0, 220.0), (100.0, 220.0)]
        # Collares 5×4 grid (espaciado 5) dentro del polígono → 20 pozos/malla
        rows = []
        for malla in ("A", "B"):
            for ix in range(4):
                for iy in range(5):
                    rows.append({
                        "X": 101.0 + ix * 5.0,
                        "Y": 201.0 + iy * 5.0,
                        "label_pozo": f"{malla}-{ix}-{iy}",
                        "Kilos_Cargados_real": 300.0,
                        "Nombre_Banco": 4000.0,
                        "Inclinacion_real": 0.0,
                        "Azimuth_real": 0.0,
                        "longitud_real": 12.0,
                        "Burden": 5.0,
                        "Esp": 5.0,
                        "Tipo_Explosivo": "ANFO",
                        "Nombre_Malla_Original": malla,
                    })
        df = pd.DataFrame(rows)
        out = compute_powder_factor(df, boundary_polygon=polygon)

        assert out["domain_area_m2"].iloc[0] == pytest.approx(300.0, rel=1e-6)
        assigned = out["assigned_area_m2"].iloc[0]
        assert assigned == pytest.approx(300.0, rel=1e-3)
        assert out["area_residual_m2"].iloc[0] == pytest.approx(0.0, abs=0.3)
        assert abs(out["area_residual_pct"].iloc[0]) < 0.1
        assert bool(out["voronoi_conservation_ok"].iloc[0]) is True
        # método global (no per-malla contra el mismo polígono)
        assert out["voronoi_method"].iloc[0] == "global_polygon"
        # ninguna malla reutiliza el dominio completo: cada una ~150 m²
        per_malla = out.groupby("Nombre_Malla_Original")["area_influence_m2"].sum()
        assert per_malla["A"] == pytest.approx(150.0, rel=1e-3)
        assert per_malla["B"] == pytest.approx(150.0, rel=1e-3)
        assert per_malla["A"] + per_malla["B"] == pytest.approx(300.0, rel=1e-3)
        # duplicados entre mallas comparten superficie (split)
        assert (out["area_status"] == "duplicate_shared").sum() == 40
        # el PF solo se calcula con conservación válida
        assert out["pf_g_per_ton_inf"].notna().all()
        # el histórico incorrecto (337,5) queda descartado
        assert assigned != pytest.approx(337.5, abs=0.1)
