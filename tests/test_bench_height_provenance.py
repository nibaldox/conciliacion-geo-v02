"""Bench-height provenance and blocking tests (Fase 1.1 cierre §2.2).

The bench height must NEVER come from a silent 15 m fallback: it is
PROVIDED by the event, read from a validated column, DERIVED from
surfaces, or an EXPLICIT_ASSUMPTION authorised by the caller. When
MISSING or INVALID, height-dependent indicators are BLOCKED (NaN).
"""
import numpy as np
import pandas as pd
import pytest

from core.blast_correlation import compute_powder_factor
from core.calculo_tronadura import procesar_pozos
from core.blast_metrics import compute_subdrilling_ratio


def _df(**overrides):
    row = {
        "X": 0.0, "Y": 0.0, "Z_collar": 4015.0, "Incl": 0.0, "Az": 0.0, "Len": 15.0,
        "Burden": 5.0, "Esp": 6.0, "Kilos_Cargados_real": 300.0,
        "Tipo_Explosivo": "ANFO", "Nombre_Banco": 4000.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


class TestBenchHeightProvenance:
    def test_provided_by_event(self):
        out = compute_powder_factor(_df(), bench_height_m=12.0)
        assert out["bench_height_m"].iloc[0] == pytest.approx(12.0)
        assert out["bench_height_status"].iloc[0] == "PROVIDED"
        assert out["bench_height_source"].iloc[0] == "event_provided"
        assert bool(out["bench_height_assumption_flag"].iloc[0]) is False
        assert out["bench_height_validation_message"].iloc[0] == ""
        # height-dependent indicators computed with 12 m
        assert out["pf_vol_kgm3"].iloc[0] == pytest.approx(300.0 / (5.0 * 6.0 * 12.0))

    def test_from_data_column(self):
        df = _df()
        df["bench_height_m"] = 12.5
        out = compute_powder_factor(df)
        assert out["bench_height_status"].iloc[0] == "PROVIDED"
        assert out["bench_height_source"].iloc[0] == "data_column"
        assert out["pf_vol_kgm3"].iloc[0] == pytest.approx(300.0 / (5.0 * 6.0 * 12.5))

    def test_spatially_variable_column(self):
        df = pd.concat([_df(), _df(X=10.0)], ignore_index=True)
        df["bench_height_m"] = [12.0, 20.0]
        out = compute_powder_factor(df)
        assert out["pf_vol_kgm3"].tolist() == pytest.approx(
            [300.0 / (5.0 * 6.0 * 12.0), 300.0 / (5.0 * 6.0 * 20.0)]
        )

    def test_derived_from_surfaces(self):
        out = compute_powder_factor(
            _df(), bench_height_m=18.0, bench_height_source="derived_from_surfaces"
        )
        assert out["bench_height_status"].iloc[0] == "DERIVED"
        assert out["bench_height_source"].iloc[0] == "derived_from_surfaces"

    def test_missing_blocks_height_dependent(self):
        """No height, no assumption -> MISSING -> bench-height indicators blocked."""
        out = compute_powder_factor(_df())
        assert out["bench_height_status"].iloc[0] == "MISSING"
        assert bool(out["bench_height_assumption_flag"].iloc[0]) is True
        assert "bloque" in out["bench_height_validation_message"].iloc[0].lower()
        # blocked: indicators that depend on the bench height
        assert pd.isna(out["pf_vol_kgm3"].iloc[0])
        assert pd.isna(out["pf_g_per_ton_net"].iloc[0])
        # kept: indicators that do NOT depend on the bench height
        assert out["pf_g_per_ton"].iloc[0] > 0  # real hole height (Len×cos), valid
        assert out["pf_area_kgm2"].iloc[0] == pytest.approx(10.0)
        assert out["energy_mj"].iloc[0] == pytest.approx(300.0 * 3.72)

    def test_explicit_assumption_authorised(self):
        """Caller authorises the config assumption -> EXPLICIT_ASSUMPTION."""
        out = compute_powder_factor(_df(), allow_bench_height_assumption=True)
        assert out["bench_height_status"].iloc[0] == "EXPLICIT_ASSUMPTION"
        assert bool(out["bench_height_assumption_flag"].iloc[0]) is True
        assert "supuesto" in out["bench_height_validation_message"].iloc[0].lower()
        assert out["bench_height_m"].iloc[0] == pytest.approx(15.0)  # visible config value
        assert out["pf_vol_kgm3"].iloc[0] > 0  # computed, but flagged

    def test_invalid_heights_block(self):
        for bad in (0.0, -3.0):
            out = compute_powder_factor(_df(), bench_height_m=bad)
            assert out["bench_height_status"].iloc[0] == "INVALID"
            assert pd.isna(out["pf_vol_kgm3"].iloc[0])

    def test_nan_height_blocks(self):
        out = compute_powder_factor(_df(), bench_height_m=np.nan)
        assert out["bench_height_status"].iloc[0] == "MISSING"
        assert pd.isna(out["pf_vol_kgm3"].iloc[0])
        assert pd.isna(out["pf_g_per_ton_net"].iloc[0])

    def test_subdrilling_ratio_blocked_without_height(self):
        """Low-level metric: missing height -> NaN (blocked), no silent 15."""
        df = pd.DataFrame({
            "Z_collar": [4015.0], "Z_toe": [3998.0], "Burden": [5.0],
        })
        out = compute_subdrilling_ratio(df)
        assert pd.isna(out.iloc[0])
        out12 = compute_subdrilling_ratio(df, bench_height=12.0)
        assert out12.iloc[0] == pytest.approx(((4015.0 - 12.0) - 3998.0) / 5.0)

    def test_processed_holes_carry_provenance(self):
        """procesar_pozos records how the collar elevation height was obtained."""
        df = pd.DataFrame([{
            "Latitud_Geo": 0.0, "Longitud_Geo": 0.0, "Nombre_Banco": 4000.0,
            "Inclinacion_real": 0.0, "Azimuth_real": 0.0, "longitud_real": 12.0,
        }])
        out, *_ = procesar_pozos(df, bench_height_m=15.0)
        assert out["bench_height_status"].iloc[0] == "PROVIDED"
        out2, *_ = procesar_pozos(df)  # no height -> transformation BLOCKED
        assert out2["bench_height_status"].iloc[0] == "MISSING"
        assert out2["Z_collar"].iloc[0] == 4000.0  # never auto +15


class TestCierreFinalAltura:
    """Cierre final §2.1: confirmación explícita persistida, bloqueo total."""

    def _enaex_hole(self):
        return pd.DataFrame([{
            "Latitud_Geo": 0.0, "Longitud_Geo": 0.0, "Nombre_Banco": 4000.0,
            "Inclinacion_real": 0.0, "Azimuth_real": 0.0, "longitud_real": 12.0,
        }])

    def test_z_collar_not_transformed_without_confirmed_height(self):
        """Ausencia de modificación automática de Z_collar (bloqueo)."""
        out, *_ = procesar_pozos(self._enaex_hole(), incl_convention="from_vertical")
        assert out["Z_collar"].iloc[0] == 4000.0  # NOT 4015
        assert out["Z_collar_semantic"].iloc[0] == "bench_elevation_untransformed"
        assert out["bench_height_status"].iloc[0] == "MISSING"
        assert bool(out["bench_height_user_confirmed"].iloc[0]) is False
        assert "bloque" in out["bench_height_validation_message"].iloc[0].lower()
        assert pd.isna(out["Z_toe"].iloc[0])  # toe blocked too

    def test_confirmed_height_transforms_and_records(self):
        out, *_ = procesar_pozos(
            self._enaex_hole(), incl_convention="from_vertical", bench_height_m=15.0
        )
        assert out["Z_collar"].iloc[0] == 4015.0
        assert out["bench_height_status"].iloc[0] == "PROVIDED"
        assert bool(out["bench_height_user_confirmed"].iloc[0]) is True
        assert out["Z_toe"].iloc[0] == pytest.approx(4003.0)

    def test_explicit_assumption_requires_authorisation_flag(self):
        """EXPLICIT_ASSUMPTION solo con autorización explícita del caller."""
        out = compute_powder_factor(
            _df(), allow_bench_height_assumption=True
        )
        assert out["bench_height_status"].iloc[0] == "EXPLICIT_ASSUMPTION"
        assert bool(out["bench_height_user_confirmed"].iloc[0]) is True
        assert "supuesto" in out["bench_height_validation_message"].iloc[0].lower()

    def test_unconfirmed_missing_blocks_all_dependent(self):
        out = compute_powder_factor(_df())
        assert bool(out["bench_height_user_confirmed"].iloc[0]) is False
        assert pd.isna(out["pf_vol_kgm3"].iloc[0])
        assert pd.isna(out["pf_g_per_ton_net"].iloc[0])
        assert pd.isna(out["height_net_m"].iloc[0])

    def test_pasadura_stats_no_default_height(self):
        """compute_pasadura_stats() nunca usa una altura por defecto."""
        from core.blast_correlation import compute_pasadura_stats

        df = pd.DataFrame({"Z_collar": [4015.0], "Z_toe": [3998.0], "bench_height_m": [15.0]})
        stats = compute_pasadura_stats(df)
        assert stats["mean"] == pytest.approx(2.0)
        df2 = df.drop(columns=["bench_height_m"])
        stats2 = compute_pasadura_stats(df2)
        assert stats2["bench_height_status"] == "MISSING"
        assert pd.isna(stats2["mean"])

    def test_pasadura_stats_event_height_param(self):
        from core.blast_correlation import compute_pasadura_stats

        df = pd.DataFrame({"Z_collar": [4012.0], "Z_toe": [3995.0]})
        stats = compute_pasadura_stats(df, bench_height_m=12.0)
        assert stats["mean"] == pytest.approx(5.0)
        assert stats["bench_height_status"] == "PROVIDED"
