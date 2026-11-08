from types import SimpleNamespace

import pandas as pd

from core.unified_dataframe import build_unified_dataframe


def test_measured_zero_blast_metrics_are_preserved(monkeypatch):
    row = SimpleNamespace(section_name="S", num_wells=1, pf_vol_avg_kgm3=0.0,
                          pf_g_per_ton_avg=0.0, total_kg=0.0,
                          avg_over_break=0.0, avg_under_break=0.0)
    monkeypatch.setattr("core.blast_correlation.compute_blast_geotech_correlation", lambda *a: [row])
    df = build_unified_dataframe([{"section": "S"}], df_pozos=pd.DataFrame([{"x": 1}]), sections=[object()])
    for field in ("pf_vol_kgm3", "pf_g_ton", "kg_total", "over_break_m", "under_break_m"):
        assert df.loc[0, field] == 0.0
