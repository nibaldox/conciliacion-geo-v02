"""Tests for the Streamlit tronadura enrichment + per-section projection.

Confirms the g(exp)/ton powder factor (incl. the Voronoi influence-area
variant) is computed at upload time and surfaced by the per-section
projection kernel used by the correlation tab.
"""
import numpy as np
import pandas as pd
import pytest

from core.calculo_tronadura import procesar_pozos
from ui.blast_analysis import project_powder_factor_per_section
from ui.modulo_tronadura.enrichment import enrich_processed


def _enax_df(n=16, malla="M1"):
    rows = []
    for ix in range(4):
        for iy in range(4):
            rows.append({
                "label_pozo": f"P-{ix}-{iy}",
                "Latitud_Geo": float(ix * 8.0),
                "Longitud_Geo": float(iy * 8.0),
                "Nombre_Banco": 4200.0,
                "Inclinacion_real": 0.0,
                "Azimuth_real": 0.0,
                "longitud_real": 15.0,
                "Kilos_Cargados_real": 200.0,
                "Nombre": "ANFO",
                "Nombre_Malla_Original": malla,
                "fecha_tronadura": "2026-05-01",
            })
    return pd.DataFrame(rows)


class TestEnrichProcessedPF:
    def test_adds_powder_factor_columns(self):
        dfc, *_ = procesar_pozos(_enax_df(), incl_convention="from_vertical")
        enriched = enrich_processed(dfc)
        for col in ("pf_g_per_ton", "pf_g_per_ton_net", "pf_g_per_ton_inf",
                    "area_influence_m2", "pf_vol_kgm3", "pf_area_kgm2", "energy_mj"):
            assert col in enriched.columns
        assert enriched["pf_g_per_ton_inf"].notna().any()
        assert enriched["area_influence_m2"].notna().any()

    def test_pf_values_positive(self):
        dfc, *_ = procesar_pozos(_enax_df(), incl_convention="from_vertical")
        enriched = enrich_processed(dfc)
        valid = enriched["pf_g_per_ton_inf"].dropna()
        assert (valid > 0).all()


class _FakeSection:
    def __init__(self, name, origin, azimuth, length=200.0):
        self.name = name
        self.origin = origin
        self.azimuth = azimuth
        self.length = length


class TestProjectOneExposesGTon:
    def test_row_dict_carries_g_per_ton_keys(self):
        dfc, *_ = procesar_pozos(_enax_df(), incl_convention="from_vertical")
        enriched = enrich_processed(dfc)
        sec = _FakeSection("S1", np.array([0.0, 0.0]), 90.0)
        rows = project_powder_factor_per_section(
            enriched, enriched, [sec], kg_col="Kilos_Cargados_real", tolerance=30.0,
        )
        assert len(rows) == 1
        row = rows[0]
        for key in ("pf_g_per_ton_avg", "pf_g_per_ton_net_avg", "pf_g_per_ton_inf_avg"):
            assert key in row
            value = row[key]
            assert value is None or isinstance(value, float)
        assert row["num_pozos"] > 0
        assert row["pf_g_per_ton_avg"] > 0
        assert row["pf_g_per_ton_inf_avg"] > 0
