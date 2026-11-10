"""Tests for the deterministic voseo -> neutral Spanish normalizer."""
from __future__ import annotations

import pytest

from core.ai_v2.agent.style import neutralize_spanish


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            "Si querés, podés exportar el reporte.",
            "Si quieres, puedes exportar el reporte.",
            id="present",
        ),
        pytest.param(
            "Empezá cargando el mesh y revisá el perfil.",
            "Empieza cargando el mesh y revisa el perfil.",
            id="imperative",
        ),
        pytest.param(
            "Vos podés decidir cuántas secciones.",
            "Tú puedes decidir cuántas secciones.",
            id="pronoun",
        ),
        pytest.param(
            "Decime qué cota buscás y te la muestro.",
            "Dime qué cota buscas y te la muestro.",
            id="pronoun_suffix_imperative",
        ),
        pytest.param(
            "Mostrame el corte y fijate el ángulo.",
            "Muéstrame el corte y fíjate el ángulo.",
            id="accents_restored",
        ),
        pytest.param(
            "Seguí la misma ruta y exportá el informe.",
            "Sigue la misma ruta y exporta el informe.",
            id="imperative_monosyllabic",
        ),
    ],
)
def test_replaces_voseo_categories(raw: str, expected: str) -> None:
    assert neutralize_spanish(raw) == expected


def test_preserves_token_case() -> None:
    assert neutralize_spanish("Tenés razón.") == "Tienes razón."
    assert neutralize_spanish("si sos nuevo, empezá acá") == (
        "si eres nuevo, empieza acá"
    )


def test_sentence_start_title_case_becomes_neutral() -> None:
    assert neutralize_spanish("Sos el responsable de la cuadrilla.") == (
        "Eres el responsable de la cuadrilla."
    )


def test_leaves_inline_code_untouched() -> None:
    assert neutralize_spanish("El texto `tenés` queda igual.") == (
        "El texto `tenés` queda igual."
    )


def test_leaves_fenced_code_blocks_untouched() -> None:
    fenced = "```\ntenés\nquerés\n```"
    assert neutralize_spanish(fenced) == fenced


def test_leaves_numbers_sections_and_percentages_untouched() -> None:
    original = "La sección S-01 en la cota 3065 rinde 17,5 %."
    assert neutralize_spanish(original) == original


def test_leaves_urls_untouched() -> None:
    assert neutralize_spanish(
        "Empezá en https://ejemplo.com/tenés?q=seguí y revisá el informe."
    ) == (
        "Empieza en https://ejemplo.com/tenés?q=seguí y revisa el informe."
    )


def test_is_idempotent() -> None:
    raw = "Empezá de nuevo, vos podés, y revisá la cota 3065."
    once = neutralize_spanish(raw)
    assert neutralize_spanish(once) == once


def test_neutral_text_is_unchanged() -> None:
    original = (
        "Tienes el resultado. Puedes revisar la sección y abrir el informe."
    )
    assert neutralize_spanish(original) == original


def test_words_marked_as_invariant_are_unchanged() -> None:
    original = "¿Cómo estás? Dale, continuamos con la cuadrilla."
    assert neutralize_spanish(original) == original


def test_uppercase_acronym_mid_sentence_is_untouched() -> None:
    result = neutralize_spanish("El protocolo SOS exige que revisás el drenaje.")
    assert result == "El protocolo SOS exige que revisas el drenaje."


def test_word_fragments_are_never_replaced() -> None:
    assert neutralize_spanish("No hay nada que sospechar aquí.") == (
        "No hay nada que sospechar aquí."
    )
    assert neutralize_spanish("Vosotros tenéis el control.") == (
        "Vosotros tenéis el control."
    )


def test_empty_string_is_unchanged() -> None:
    assert neutralize_spanish("") == ""
