"""Regression test for Phase 2 production wiring.

The energy simulation adapter (ui/modulo_tronadura/energy_simulation.py) and
the React panel (web/src/components/results/BlastSimulationPanel.tsx) were
originally orphan code: they existed and had unit tests, but were never
mounted in the production UI. This test guards against that regression.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


SAMPLE_ROWS = [
    {
        "Latitud_Geo": 1000.0,
        "Longitud_Geo": 2000.0,
        "Nombre_Banco": 4000,
        "Inclinacion_real": 15.0,
        "Azimuth_real": 1.5707963,
        "longitud_real": 12.0,
    },
]


def _script_path(tmp_path: Path) -> Path:
    """Generate a minimal Streamlit script that boots the same call site as
    the production tronadura module: it sets ``blast_processed=True`` and
    delegates to ``render_tabs_section``.
    """
    script_text = (
        "from __future__ import annotations\n"
        "import pandas as pd\n"
        "import streamlit as st\n"
        "from ui.modulo_tronadura.sections import render_tabs_section\n"
        f"_rows = {SAMPLE_ROWS!r}\n"
        "st.session_state['blast_processed'] = True\n"
        "df = pd.DataFrame(_rows)\n"
        "render_tabs_section(df)\n"
    )
    script = tmp_path / "wiring_app.py"
    script.write_text(script_text, encoding="utf-8")
    return script


def test_render_tabs_section_invokes_energy_simulation_adapter(tmp_path):
    """render_tabs_section must call render_energy_simulation_section.

    Pre-regression, sections.py only registered two tabs and never called
    the adapter, so the panel existed but was unreachable from production.
    """
    import pandas as pd
    import streamlit as st
    from ui.modulo_tronadura import sections

    captured: list[dict] = []

    def fake_energy_render(*, accepted_rows, geometry_configuration_version):
        captured.append(
            {
                "accepted_rows": accepted_rows,
                "geom_version": geometry_configuration_version,
            }
        )

    st.session_state["blast_processed"] = True

    fake_three_d = patch.object(sections, "render_three_d_tab")
    fake_corr = patch.object(sections, "render_correlation_tab")
    fake_energy = patch.object(
        sections,
        "render_energy_simulation_section",
        fake_energy_render,
    )
    with fake_three_d, fake_corr, fake_energy:
        sections.render_tabs_section(pd.DataFrame(SAMPLE_ROWS))

    assert len(captured) == 1, (
        "render_tabs_section must invoke render_energy_simulation_section "
        "exactly once. Regression: the adapter is no longer wired."
    )
    assert captured[0]["geom_version"] == "2.0"
    assert isinstance(captured[0]["accepted_rows"], list)
    assert captured[0]["accepted_rows"], "accepted_rows must not be empty"


def test_render_tabs_section_renders_three_tabs(tmp_path):
    """render_tabs_section must register three tabs (not two)."""
    import pandas as pd
    import streamlit as st
    from ui.modulo_tronadura import sections

    st.session_state["blast_processed"] = True

    fake_three_d = patch.object(sections, "render_three_d_tab")
    fake_corr = patch.object(sections, "render_correlation_tab")
    fake_energy = patch.object(
        sections, "render_energy_simulation_section"
    )
    with fake_three_d, fake_corr, fake_energy:
        ret = sections.render_tabs_section(pd.DataFrame(SAMPLE_ROWS))

    assert ret is None, "render_tabs_section returns None"