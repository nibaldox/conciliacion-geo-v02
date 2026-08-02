"""Tests for ui.modulo_tronadura.warnings — visible physical warnings.

Cierre final §2.3: warnings must be visible components (st.error /
st.warning / st.info), never hidden in logs, tooltips or closed
expanders. ``collect_data_warnings`` is the pure, testable generator;
the UI renders its output.
"""
import numpy as np
import pandas as pd
import pytest

from ui.modulo_tronadura.warnings import collect_data_warnings


def _df(**overrides):
    row = {
        "X": 0.0, "Y": 0.0, "Z_collar": 4015.0, "Incl": 0.0, "Az": 0.0, "Len": 15.0,
        "Burden": 5.0, "Esp": 6.0, "Kilos_Cargados_real": 300.0,
        "Tipo_Explosivo": "ANFO", "bench_height_m": 15.0,
        "bench_height_status": "PROVIDED", "bench_height_user_confirmed": True,
        "bench_height_validation_message": "",
        "inclination_validation_status": "EXPLICIT",
        "inclination_validation_message": "",
        "inclination_user_confirmed": True,
        "voronoi_conservation_ok": True,
        "area_residual_pct": 0.5,
        "explosive_status": "VALIDATED",
    }
    row.update(overrides)
    return pd.DataFrame([row])


class TestCollectDataWarnings:
    def test_clean_frame_no_warnings(self):
        assert collect_data_warnings(_df()) == []

    def test_missing_bench_height_warning(self):
        ws = collect_data_warnings(_df(bench_height_status="MISSING",
                                       bench_height_user_confirmed=False))
        assert any(w["level"] == "warning" and "altura" in w["message"].lower() for w in ws)
        w = next(w for w in ws if "altura" in w["message"].lower())
        assert "afectado" in w and "cómo corregir" in w["fix"].lower() or "declare" in w["fix"].lower()

    def test_invalid_bench_height_warning(self):
        ws = collect_data_warnings(_df(bench_height_status="INVALID"))
        assert any(w["level"] == "warning" and "inválida" in w["message"].lower() for w in ws)

    def test_explicit_assumption_is_info(self):
        ws = collect_data_warnings(_df(bench_height_status="EXPLICIT_ASSUMPTION",
                                       bench_height_user_confirmed=True))
        assert any(w["level"] == "info" and "supuesto" in w["message"].lower() for w in ws)

    def test_angular_out_of_range_warning(self):
        ws = collect_data_warnings(_df(inclination_validation_status="OUT_OF_RANGE"))
        assert any(w["level"] == "warning" and "rango" in w["message"].lower() for w in ws)

    def test_unconfirmed_convention_error(self):
        ws = collect_data_warnings(_df(inclination_user_confirmed=False,
                                       inclination_validation_status="NOT_CONFIRMED"))
        assert any(w["level"] == "error" and "convenci" in w["message"].lower() for w in ws)

    def test_voronoi_conservation_failure_error(self):
        ws = collect_data_warnings(_df(voronoi_conservation_ok=False,
                                       area_residual_pct=12.5))
        assert any(w["level"] == "error" and "voronoi" in w["message"].lower() for w in ws)
        w = next(w for w in ws if "voronoi" in w["message"].lower())
        assert "pf" in w["affected"].lower()

    def test_unknown_explosive_warning(self):
        ws = collect_data_warnings(_df(explosive_status="UNKNOWN"))
        assert any(w["level"] == "warning" and "explosivo" in w["message"].lower() for w in ws)

    def test_unvalidated_explosive_info(self):
        ws = collect_data_warnings(_df(explosive_status="UNVALIDATED_REFERENCE"))
        assert any(w["level"] == "info" and "validaci" in w["message"].lower() for w in ws)

    def test_blocked_indicators_warning(self):
        ws = collect_data_warnings(_df(pf_vol_kgm3=np.nan, bench_height_status="MISSING"))
        assert any("bloque" in w["message"].lower() for w in ws)

    def test_warning_persists_in_results(self):
        """§2.3: warnings must be reproducible — carried in the result frame."""
        df = _df(bench_height_status="MISSING")
        df = collect_data_warnings(df, attach=True)
        assert "data_warnings" in df.columns
        assert "altura" in df["data_warnings"].iloc[0].lower()
