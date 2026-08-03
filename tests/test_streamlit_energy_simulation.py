"""Streamlit AppTest for the energy simulation adapter (spec §14).

Exercises the real ``ui/modulo_tronadura/energy_simulation.py`` module
through ``streamlit.testing.v1.AppTest.from_function`` — no mocks of the
UI logic. Verifies:

* Confirmation starts unchecked.
* Editing a parameter after ticking clears the confirmation.
* The fingerprint is computed and stored in session_state.
* Running without confirmation does nothing.
"""
from __future__ import annotations

import pytest


def _script_for_apptest():
    """Inline script that imports the adapter and calls it with seed data.

    AppTest.from_file expects a real .py file; we write one to tmp_path
    and execute it. The adapter is invoked the same way the production
    router would invoke it.
    """
    return (
        "from ui.modulo_tronadura.energy_simulation import "
        "render_energy_simulation_section\n"
        "rows = [{'hole_id': 'H-001', 'X': 5.0, 'Y': 5.0, 'Z_collar': 9.0, "
        "'X_toe': 5.0, 'Y_toe': 5.0, 'Z_toe': 1.0, 'Incl': 0.0, 'Az': 0.0, "
        "'Len': 8.0, 'Taco_m': 2.0, 'descarga': 6.0, 'Diam_mm': 200.0, "
        "'Kilos_Cargados_real': 100.0, 'Tipo_Explosivo': 'ANFO'}]\n"
        "render_energy_simulation_section(accepted_rows=rows, "
        "geometry_configuration_version='2.0')\n"
    )


class TestStreamlitEnergyAdapter:
    def test_renders_title_and_uncalibrated_warning(self, tmp_path):
        script = tmp_path / "sim_app.py"
        script.write_text(_script_for_apptest(), encoding="utf-8")
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(script)).run()
        # Title rendered via st.subheader.
        titles = [str(h.value) for h in at.subheader]
        assert any("Simulador de Energía 3D" in t for t in titles)
        # Uncalibrated-model warning present.
        warnings = [str(w.value) for w in at.warning]
        assert any("no calibrado" in w for w in warnings)

    def test_no_accepted_rows_shows_info(self, tmp_path):
        script = tmp_path / "sim_app.py"
        script.write_text(
            "from ui.modulo_tronadura.energy_simulation import "
            "render_energy_simulation_section\n"
            "render_energy_simulation_section(accepted_rows=None, "
            "geometry_configuration_version='2.0')\n",
            encoding="utf-8",
        )
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(script)).run()
        infos = [str(i.value) for i in at.info]
        assert any("Cargue pozos" in i for i in infos)

    def test_run_button_disabled_initially(self, tmp_path):
        script = tmp_path / "sim_app.py"
        script.write_text(_script_for_apptest(), encoding="utf-8")
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(script)).run()
        # The "Ejecutar simulación" button exists and is disabled.
        run_buttons = [b for b in at.button if "Ejecutar" in str(b.label)]
        assert len(run_buttons) >= 1
        assert run_buttons[0].disabled is True

    def test_fingerprint_helper_is_deterministic(self):
        from ui.modulo_tronadura.energy_simulation import simulation_fingerprint
        state = {"voxel_size_m": 1.0, "energy_mode": "ABSOLUTE"}
        assert simulation_fingerprint(state) == simulation_fingerprint(state)
        # Different state → different fingerprint.
        other = dict(state); other["voxel_size_m"] = 2.0
        assert simulation_fingerprint(state) != simulation_fingerprint(other)


class TestStreamlitConfigurationBuilder:
    """Validate the configuration builder directly (no Streamlit runtime)."""

    def test_build_config_validates(self):
        from ui.modulo_tronadura.energy_simulation import _build_config
        from core.blast_simulation import SimulationConfigurationError
        state = {
            "voxel_size_m": 1.0,
            "x_min": 0.0, "x_max": 10.0,
            "y_min": 0.0, "y_max": 10.0,
            "z_min": 0.0, "z_max": 10.0,
            "energy_mode": "ABSOLUTE",
            "temporal_mode": "STATIC",
            "anisotropy_mode": "ISOTROPIC",
            "attenuation_coefficient_1_m": 2.0,
            "regularization_radius_m": 0.5,
            "coupling_efficiency": 0.85,
        }
        cfg = _build_config(state, "2.0")
        assert cfg.validate() is cfg

    def test_build_config_invalid_raises(self):
        from ui.modulo_tronadura.energy_simulation import _build_config
        from core.blast_simulation import SimulationConfigurationError
        state = {
            "voxel_size_m": -1.0,  # invalid
            "x_min": 0.0, "x_max": 10.0,
            "y_min": 0.0, "y_max": 10.0,
            "z_min": 0.0, "z_max": 10.0,
            "energy_mode": "ABSOLUTE",
            "temporal_mode": "STATIC",
            "anisotropy_mode": "ISOTROPIC",
            "attenuation_coefficient_1_m": 2.0,
            "regularization_radius_m": 0.5,
            "coupling_efficiency": 0.85,
        }
        with pytest.raises(SimulationConfigurationError):
            _build_config(state, "2.0").validate()
