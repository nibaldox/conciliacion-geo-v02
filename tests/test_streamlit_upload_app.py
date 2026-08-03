from streamlit.testing.v1 import AppTest


APP = r'''
import pandas as pd
import streamlit as st
import ui.modulo_tronadura.upload as upload
from core.processing_result import ProcessingResult

df = pd.DataFrame([{
    "Latitud_Geo": 1000.0,
    "Longitud_Geo": 2000.0,
    "Nombre_Banco": 4000.0,
    "Inclinacion_real": 15.0,
    "Azimuth_real": 1.5707963267948966,
    "longitud_real": 12.0,
}])
mapping = {
    "X": "Latitud_Geo",
    "Y": "Longitud_Geo",
    "Z_collar": "Nombre_Banco",
    "Incl": "Inclinacion_real",
    "Az": "Azimuth_real",
    "Len": "longitud_real",
}

def capture_processor(source_df, column_map, **kwargs):
    config = kwargs["geometry_configuration"]
    accepted = pd.DataFrame([{
        "X": 1000.0, "Y": 2000.0, "Z_collar": 4015.0,
        "X_toe": 1003.10582854123, "Y_toe": 2000.0,
        "Z_toe": 4003.40889008453, "Len": 12.0,
        "Incl": 15.0, "Az": 90.0,
        "_captured_geometry_configuration": config.to_dict(),
    }])
    return ProcessingResult.from_rejections(
        accepted_dataframe=accepted,
        accepted_rows=accepted.to_dict("records"),
        rejected_rows=[],
        event_warnings=[],
        spatial_diagnostics={"source": "streamlit-production-harness"},
        geometry_configuration=config.to_dict(),
        rows_received=1,
        scatter_lines=((), (), ()),
    )

upload.procesar_pozos = capture_processor
upload.render_upload_section(df, mapping)
'''


def _select(at: AppTest, label: str, value: str) -> AppTest:
    widget = next(item for item in at.selectbox if item.label == label)
    widget.select(value)
    return at.run()


def _checkbox(at: AppTest):
    return next(item for item in at.checkbox if item.label.startswith("Confirmo"))


def test_real_streamlit_upload_requires_selection_and_invalidates_confirmation():
    at = AppTest.from_string(APP, default_timeout=30).run()
    assert not at.exception
    assert _checkbox(at).value is False
    assert _checkbox(at).disabled is True

    at = _select(at, "Convención de inclinación", "Desviación desde la vertical")
    at = _select(at, "Tratamiento del signo (controla la geometría)", "Usar valor absoluto")
    at = _select(at, "Convención de azimut (controla la geometría)", "Horario desde el Norte")
    at = _select(at, "Unidad angular de INCLINACIÓN", "Grados")
    at = _select(at, "Unidad angular de AZIMUT", "Radianes")
    next(item for item in at.number_input if item.label.startswith("Altura de banco")).set_value(15.0)
    at = at.run()

    assert _checkbox(at).disabled is False
    _checkbox(at).check()
    at = at.run()
    assert _checkbox(at).value is True
    process = next(item for item in at.button if "Procesar Pozos" in item.label)
    assert process.disabled is False

    at = _select(at, "Unidad angular de AZIMUT", "Grados")
    assert _checkbox(at).value is False
    assert next(item for item in at.button if "Procesar Pozos" in item.label).disabled is True

    at = _select(at, "Unidad angular de AZIMUT", "Radianes")
    _checkbox(at).check()
    at = at.run()
    next(item for item in at.button if "Procesar Pozos" in item.label).click()
    at = at.run()

    captured = at.session_state["blast_df_clean"].iloc[0]["_captured_geometry_configuration"]
    assert captured["geometry_configuration_version"] == "2.0"
    assert captured["geometry_user_confirmed"] is True
    assert captured["inclination_unit"] == "DEGREES"
    assert captured["azimuth_unit"] == "RADIANS"
    assert captured["inclination_source_column"] == "Inclinacion_real"
    assert captured["azimuth_source_column"] == "Azimuth_real"
