from dataclasses import replace
from types import SimpleNamespace

import pytest

from core.report_data import ParameterSummary, ReportFilters, build_report_data
from core.report_texts import (
    fmt_es,
    headline_text,
    heatmap_position_note,
    kpi_definitions,
    scope_lines,
)

NNBSP = "\u202f"
OFFICIAL_ONLY = "Solo valores oficiales; la medición guiada no se incluye."
NO_FILTERS = "Sin filtros: todas las secciones y cotas"


def _data(**changes):
    base = build_report_data([], {}, changes.pop("filters", ReportFilters()), {})
    return replace(base, **changes)


def _headline(cumple=0, fuera=0, no_cumple=0, unknown=0, geometry=0, only_missing=0):
    return {
        "profiles": {
            "CUMPLE": cumple,
            "FUERA": fuera,
            "NO_CUMPLE": no_cumple,
            "UNKNOWN": unknown,
        },
        "nc_by_geometry": geometry,
        "nc_only_missing_extra": only_missing,
        "benches": {
            "match_by_status": {"CUMPLE": 0, "FUERA": 0, "NO_CUMPLE": 0, "UNKNOWN": 0},
            "missing": 0,
            "extra": 0,
        },
    }


def _summary(median):
    return SimpleNamespace(median_m=median)


class TestFmtEs:
    def test_decimal_comma_default_one_decimal(self):
        assert fmt_es(48.14) == "48,1"

    def test_decimals_argument(self):
        assert fmt_es(3.14159, 3) == "3,142"
        assert fmt_es(12.6, 0) == "13"

    def test_thousands_use_narrow_no_break_space(self):
        assert fmt_es(12410, 0) == f"12{NNBSP}410"
        assert fmt_es(1234567.89, 2) == f"1{NNBSP}234{NNBSP}567,89"

    def test_unit_after_normal_space(self):
        assert fmt_es(12410, 0, "m³") == f"12{NNBSP}410 m³"
        assert fmt_es(1.5, 1, "m") == "1,5 m"

    def test_degree_and_percent_are_attached(self):
        assert fmt_es(48.1, 1, "°") == "48,1°"
        assert fmt_es(96.875, 1, "%") == "96,9%"

    @pytest.mark.parametrize(
        "value", [None, float("nan"), float("inf"), float("-inf"), "abc", True]
    )
    def test_missing_or_non_finite_is_dash(self, value):
        assert fmt_es(value) == "—"
        assert fmt_es(value, 1, "m") == "—"

    def test_negative_uses_minus_sign_and_never_negative_zero(self):
        assert fmt_es(-1.25, 2) == "\u22121,25"
        assert fmt_es(-0.01, 1) == "0,0"

    def test_numeric_string_and_int_are_accepted(self):
        assert fmt_es("2.5") == "2,5"
        assert fmt_es(7) == "7,0"


class TestHeadlineText:
    def test_real_session_like_counts(self):
        data = _data(
            headline=_headline(cumple=93, no_cumple=3, geometry=3, only_missing=0),
            profile_counts={"CUMPLE": 93, "FUERA": 0, "NO_CUMPLE": 3},
        )
        assert headline_text(data) == (
            "93 de 96 perfiles cumplen; 3 no cumplen por geometría y 0 solo por "
            "banco no construido o adicional."
        )

    def test_zero_profiles_never_divides(self):
        assert headline_text(_data()) == "Sin perfiles evaluados."
        assert headline_text(_data(headline={}, profile_counts={})) == (
            "Sin perfiles evaluados."
        )

    def test_fuera_de_tolerancia_is_reported(self):
        data = _data(
            headline=_headline(cumple=5, fuera=2, no_cumple=3, geometry=1, only_missing=2)
        )
        assert headline_text(data) == (
            "5 de 10 perfiles cumplen; 2 fuera de tolerancia; 1 no cumple por "
            "geometría y 2 solo por banco no construido o adicional."
        )

    def test_all_compliant_has_no_failure_clause(self):
        data = _data(headline=_headline(cumple=4))
        assert headline_text(data) == "4 de 4 perfiles cumplen."

    def test_singular_profile(self):
        data = _data(headline=_headline(cumple=1))
        assert headline_text(data) == "1 de 1 perfil cumple."

    def test_unknown_profiles_are_reported_not_hidden(self):
        data = _data(headline=_headline(cumple=2, unknown=1))
        assert headline_text(data) == "2 de 3 perfiles cumplen; 1 sin evaluar."

    def test_falls_back_to_profile_counts_without_headline(self):
        data = _data(headline={}, profile_counts={"CUMPLE": 2, "FUERA": 0, "NO_CUMPLE": 1})
        assert headline_text(data) == "2 de 3 perfiles cumplen; 1 no cumple."


class TestKpiDefinitions:
    def _real_like(self):
        parameters = (
            ParameterSummary("height", "Altura de banco", "m", 200, 50, 80.0, 15.0, 250, 40),
            ParameterSummary("angle", "Ángulo de cara", "°", 200, 50, 80.0, 70.0, 250, 40),
            ParameterSummary("berm", "Ancho de berma", "m", 100, 140, 41.7, 8.0, 240, 40),
        )
        return _data(
            headline=_headline(cumple=93, no_cumple=3, geometry=3),
            parameters=parameters,
            counts={"n_rows": 290, "n_match": 250, "n_missing": 30, "n_extra": 10, "n_sections": 96},
        )

    def test_pairs_of_non_empty_strings(self):
        entries = kpi_definitions(self._real_like())
        assert isinstance(entries, tuple)
        assert len(entries) == 6
        for name, definition in entries:
            assert isinstance(name, str) and name
            assert isinstance(definition, str) and definition.endswith(".")
        assert len({name for name, _ in entries}) == len(entries)

    def test_profiles_denominator(self):
        text = dict(kpi_definitions(self._real_like()))["Perfiles por estado"]
        assert "96 perfiles evaluados" in text

    def test_weighted_score_weights_and_threshold(self):
        text = dict(kpi_definitions(self._real_like()))["Puntaje ponderado"]
        assert "berma 60" in text and "altura 30" in text and "ángulo 10" in text
        assert "≥ 70" in text

    def test_parameter_percentage_uses_d11_denominator(self):
        text = dict(kpi_definitions(self._real_like()))["% de cumplimiento por parámetro"]
        assert "bancos comparados" in text
        assert "altura 250" in text and "berma 240" in text
        assert "30 no construidos" in text and "10 adicionales" in text
        assert "aparte" in text

    def test_design_achievement_volumes_and_nominal_level(self):
        entries = dict(kpi_definitions(self._real_like()))
        assert "cresta 40" in entries["Logro de diseño"]
        assert "ancho de influencia" in entries["Volúmenes de excavación"]
        assert "separación real entre secciones" in entries["Volúmenes de excavación"]
        assert "⅓" in entries["Cota nominal"]

    def test_empty_data_has_no_fake_counts(self):
        entries = dict(kpi_definitions(_data()))
        assert len(entries) == 6
        assert "perfiles evaluados" in entries["Perfiles por estado"]
        assert "0 perfiles" not in entries["Perfiles por estado"]
        assert "bancos comparados" in entries["% de cumplimiento por parámetro"]


class TestScopeLines:
    def test_without_filters(self):
        assert scope_lines(_data()) == (NO_FILTERS, OFFICIAL_ONLY)

    def test_level_by_sector(self):
        filters = ReportFilters(levels_by_sector=(("Norte", ("3110",)),))
        lines = scope_lines(_data(filters=filters))
        assert lines[0] == "Sector Norte: cota 3110"
        assert NO_FILTERS not in lines
        assert lines[-1] == OFFICIAL_ONLY

    def test_level_without_sector(self):
        filters = ReportFilters(levels_by_sector=(("", ("3110",)),))
        assert scope_lines(_data(filters=filters))[0] == "Cota 3110"

    def test_global_levels_plural(self):
        filters = ReportFilters(levels=("3110", "3125"))
        assert scope_lines(_data(filters=filters))[0] == "Cotas 3110, 3125"

    def test_sector_without_level_selection(self):
        filters = ReportFilters(sectors=("Norte", "Sur"), levels_by_sector=(("Sur", ("3125", "3110")),))
        lines = scope_lines(_data(filters=filters))
        assert lines[:2] == ("Sector Norte: todas las cotas", "Sector Sur: cotas 3125, 3110")

    def test_sector_with_global_levels(self):
        filters = ReportFilters(sectors=("Norte",), levels=("3110",))
        assert scope_lines(_data(filters=filters))[0] == "Sector Norte: cota 3110"

    def test_empty_sector_selection_is_not_a_filter(self):
        filters = ReportFilters(levels_by_sector=(("Norte", ()),))
        assert scope_lines(_data(filters=filters))[0] == NO_FILTERS

    def test_sections_and_benches(self):
        filters = ReportFilters(sections=("S-01", "S-02"), benches=(2,))
        lines = scope_lines(_data(filters=filters))
        assert "Secciones: S-01, S-02" in lines
        assert "Banco: 2" in lines

    def test_long_section_list_is_capped_with_count(self):
        names = tuple(f"S-{i:02d}" for i in range(1, 31))
        line = scope_lines(_data(filters=ReportFilters(sections=names)))[0]
        assert line.startswith("Secciones (30): S-01, S-02")
        assert line.endswith("…")
        assert "S-30" not in line

    def test_level_warnings_and_heatmap_notes_in_order(self):
        data = _data(
            level_warnings=("Advertencia de cota.",),
            heatmap_notes=("Mapa de calor no calculado; calcúlelo en la vista 3D para incluirlo.",),
        )
        assert scope_lines(data) == (
            NO_FILTERS,
            "Advertencia de cota.",
            "Mapa de calor no calculado; calcúlelo en la vista 3D para incluirlo.",
            OFFICIAL_ONLY,
        )

    def test_excluded_sections_count(self):
        states = (
            ("S-01", "Norte", True, "CUMPLE"),
            ("S-02", "Norte", False, "UNKNOWN"),
            ("S-03", "Norte", False, "UNKNOWN"),
        )
        data = _data(
            filters=ReportFilters(sections=("S-01",)), section_plan_states=states
        )
        assert "Secciones excluidas por los filtros: 2 de 3." in scope_lines(data)

    def test_no_excluded_line_when_none_excluded(self):
        data = _data(section_plan_states=(("S-01", "Norte", True, "CUMPLE"),))
        assert not any("excluidas" in line for line in scope_lines(data))


class TestHeatmapPositionNote:
    def test_none_without_median(self):
        assert heatmap_position_note(_summary(None)) is None
        assert heatmap_position_note(None) is None
        assert heatmap_position_note(_summary(float("nan"))) is None

    def test_near_design(self):
        assert heatmap_position_note(_summary(0.3), level_label="3110") == (
            "La pared quedó en promedio cerca de la posición de diseño (mediana +0,3 m)."
        )
        assert heatmap_position_note(_summary(-0.5)) == (
            "La pared quedó en promedio cerca de la posición de diseño (mediana \u22120,5 m)."
        )

    def test_behind_design(self):
        assert heatmap_position_note(_summary(1.5), level_label="3110") == (
            "La forma del banco se evalúa por altura, ángulo y berma; la posición de la "
            "pared es otra medida: en la cota 3110 la pared quedó en promedio ~1,5 m más "
            "atrás que el diseño (sobreexcavación)."
        )

    def test_ahead_of_design(self):
        assert heatmap_position_note(_summary(-1.5), level_label="3110") == (
            "La forma del banco se evalúa por altura, ángulo y berma; la posición de la "
            "pared es otra medida: en la cota 3110 la pared quedó en promedio ~1,5 m más "
            "adelante que el diseño (falta excavar)."
        )

    def test_without_level_label(self):
        assert heatmap_position_note(_summary(0.51)) == (
            "La forma del banco se evalúa por altura, ángulo y berma; la posición de la "
            "pared es otra medida: la pared quedó en promedio ~0,5 m más atrás que el "
            "diseño (sobreexcavación)."
        )

    def test_accepts_mapping_summary(self):
        assert heatmap_position_note({"median_m": 0.0}) == (
            "La pared quedó en promedio cerca de la posición de diseño (mediana 0,0 m)."
        )


class TestBenchScorePass:
    def test_threshold_is_the_report_data_constant(self):
        import core.report_data as report_data
        import core.report_texts as report_texts

        assert report_texts.BENCH_SCORE_PASS is report_data.BENCH_SCORE_PASS
        assert report_data.BENCH_SCORE_PASS == 70.0

    def test_definition_prints_the_threshold_without_decimals(self):
        text = dict(kpi_definitions(_data()))["Puntaje ponderado"]

        assert "≥ 70." in text
        assert "70.0" not in text and "70,0" not in text

    def test_definition_follows_the_constant(self, monkeypatch):
        import core.report_texts as report_texts

        monkeypatch.setattr(report_texts, "BENCH_SCORE_PASS", 72.5)
        assert "≥ 72,5." in dict(kpi_definitions(_data()))["Puntaje ponderado"]
