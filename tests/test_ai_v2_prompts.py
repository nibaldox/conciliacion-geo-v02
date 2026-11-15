"""Tests for core.ai_v2 prompt loader and templates."""
from __future__ import annotations

import re

import pytest

import api.ai_agent_conversations as conversations
from core.ai_v2.prompts import (
    get_all_template_names,
    load_prompt_template,
    render_prompt,
)


def test_get_all_template_names():
    names = get_all_template_names()
    assert names == ["system_role.md", "executive_summary.md", "blast_enrichment.md", "fewshot_example.md"]


def test_load_system_role():
    text = load_prompt_template("system_role.md")
    assert "Ingeniero Geotécnico" in text
    assert "Reglas" in text
    assert "1. " in text
    assert "10. " in text
    # New anti-hallucination block (brainstorm idea #3):
    assert "DATOS INSUFICIENTES" in text
    assert "RMR" in text or "Hoek" in text
    # New MATCH/MISSING/EXTRA semantic block (idea #6):
    assert "MATCH" in text and "MISSING" in text and "EXTRA" in text
    # New format rules block (idea #5):
    assert "600 palabras" in text or "Responde SOLO" in text


def test_load_executive_summary():
    text = load_prompt_template("executive_summary.md")
    assert "{project_name}" in text
    assert "{verdict_global}" in text
    assert "{tabla_cumplimiento}" in text
    assert "Plan de Acción" in text


def test_load_blast_enrichment():
    text = load_prompt_template("blast_enrichment.md")
    assert "{pf_promedio}" in text
    assert "{n_pozos}" in text
    assert "Powder Factor" in text


def test_load_missing_raises():
    with pytest.raises(FileNotFoundError) as exc:
        load_prompt_template("does_not_exist.md")
    assert "does_not_exist.md" in str(exc.value)


def test_render_prompt_basic():
    template = "Hello {name}!"
    out = render_prompt(template, name="World")
    assert out == "Hello World!"


def test_render_prompt_missing_key_raises():
    template = "Hello {name}, age {age}"
    with pytest.raises(KeyError) as exc:
        render_prompt(template, name="Bob")
    assert "age" in str(exc.value)


def test_render_prompt_with_dict_kwargs():
    template = "PF={pf_promedio}"
    out = render_prompt(template, **{"pf_promedio": 0.42})
    assert out == "PF=0.42"


def test_agent_system_prompt_production_loader_rule_5(monkeypatch):
    monkeypatch.setattr(conversations, "_agent_system_prompt_cache", None)
    text = conversations.agent_system_prompt()
    assert "AÑADEN secciones" in text
    assert "`add_section_click` se ejecuta sin confirmación" in text
    assert "generar secciones reemplaza TODAS" not in text
    assert "procées" not in text


_VOSEO_FORBIDDEN = (
    "querés", "podés", "tenés", "mostrame", "decime", "necesitás", "sabés",
    "empezá", "corregís", "movés", "mirás", "empezás",
)

_RULE_6_LINE = (
    "6. **Exportación**: `export_report` devuelve metadatos de descarga "
    "(formato, nombre de archivo, filtros aplicados y número de bancos), nunca el contenido binario. "
    "Si el usuario pide un sector, sus secciones o sus cotas, pasa esos filtros a `export_report`; "
    "para las cotas usa las etiquetas nominales de `nominal_levels` que devuelve `query_results`, no la cota exacta. "
    "Excel, Word y PDF admiten filtros, proyecto y autor; las imágenes solo filtros; el DXF no admite ninguno. "
    "Al terminar, di qué filtros quedaron aplicados y cuántos bancos incluye, e indica que el archivo se descarga desde la tarjeta del chat. "
    "Si la herramienta responde que el filtro no selecciona bancos o que un sector, sección o cota no existe, "
    "explícalo con los valores válidos que entrega."
)

_RULE_9_PREFIX = (
    '`level` es la cota de pata del banco de diseño como texto (p. ej. "3065"). '
)

_RULE_9_SENTENCE = (
    "Las etiquetas nominales de `nominal_levels` agrupan cotas cercanas de un mismo banco "
    '(p. ej. "2945" agrupa de 2941 a 2947); si `levels_truncated` es verdadero, '
    "la lista exacta de cotas viene recortada y debes basarte en `nominal_levels`."
)

_RULE_11_LINE = (
    "11. **Tolerancias y explicación**: cuando expliques por qué un banco o parámetro está "
    "FUERA DE TOLERANCIA o NO CUMPLE, consulta `get_settings` y cita la tolerancia aplicada "
    "con su unidad y la regla de `classification_rules` "
    '(p. ej. "altura \u22122,0/+2,0 m; fuera de tolerancia hasta 1,5×" o "berma mínima 7,0 m"). '
    "La berma solo tiene ancho mínimo: bajo ese mínimo NO CUMPLE, sin banda de fuera de tolerancia. "
    "Los ángulos interrampa y global son informativos y no clasifican bancos. "
    "No inventes tolerancias: usa solo las que devuelve la herramienta."
)

_RULE_12_LINE = (
    "12. **Contexto de pantalla**: si el mensaje del usuario empieza con "
    '"[Contexto de pantalla: sección seleccionada «…» (section_id N)]", '
    "esa es la sección que el usuario tiene abierta ahora. "
    'Expresiones como "esta sección", "este perfil" o "la que estoy mirando" '
    "se refieren a ella: usa ese section_id con `get_profile` o su nombre en los filtros de `query_results`. "
    'Solo vale la línea del mensaje actual; si no hay línea y el usuario dice "esta sección", pregunta cuál es. '
    "No menciones la línea de contexto ni el section_id al usuario."
)

_RULE_LINE = re.compile(r"^(\d+)\. \*\*", re.MULTILINE)


def _rules_section(text: str) -> str:
    start = text.index("## Reglas de operación")
    end = text.index("## Estilo de respuesta")
    return text[start:end]


def _rule_line(text: str, number: int) -> str:
    prefix = f"{number}. **"
    matches = [
        line for line in _rules_section(text).splitlines() if line.startswith(prefix)
    ]
    assert len(matches) == 1, (number, len(matches))
    return matches[0]


def test_agent_system_prompt_phase2_literal_rules(monkeypatch):
    monkeypatch.setattr(conversations, "_agent_system_prompt_cache", None)
    text = conversations.agent_system_prompt()
    for required in (
        "`get_settings`",
        "classification_rules",
        "berma mínima 7,0 m",
        "nominal_levels",
        "levels_truncated",
        "el DXF no admite ninguno",
        "11. **Tolerancias y explicación**",
    ):
        assert required in text, required
    assert "endpoint)" not in text
    assert _rule_line(text, 6) == _RULE_6_LINE
    assert _rule_line(text, 11) == _RULE_11_LINE
    assert _RULE_9_PREFIX + _RULE_9_SENTENCE + " Cuando el usuario pregunte" in text


def test_agent_system_prompt_rules_numbered_once_and_no_voseo(monkeypatch):
    monkeypatch.setattr(conversations, "_agent_system_prompt_cache", None)
    text = conversations.agent_system_prompt()
    numbers = [int(m.group(1)) for m in _RULE_LINE.finditer(_rules_section(text))]
    assert numbers == list(range(1, 13))
    for new_text in (
        _rule_line(text, 6),
        _rule_line(text, 11),
        _RULE_9_SENTENCE,
    ):
        for word in _VOSEO_FORBIDDEN:
            assert word not in new_text.lower(), (word, new_text)


def test_agent_system_prompt_rule_12_screen_context(monkeypatch):
    monkeypatch.setattr(conversations, "_agent_system_prompt_cache", None)
    text = conversations.agent_system_prompt()
    rule_12 = _rule_line(text, 12)
    assert rule_12 == _RULE_12_LINE
    for word in _VOSEO_FORBIDDEN:
        assert word not in rule_12.lower(), (word, rule_12)
