"""Tests for core.ai_v2 prompt loader and templates."""
from __future__ import annotations

import re

import pytest

import api.ai_agent_conversations as conversations
from core.ai_v2.agent.catalog import AGENT_TOOLS
from core.ai_v2.agent.models import ToolRisk
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


_RULE_4_FRAGMENT = (
    "`generate_sections_auto` / `generate_sections_curve` / "
    "`generate_sections_manual` / `add_section_click`"
)

_RULE_5_LINE = (
    "5. **Secciones y resultados existentes**: "
    "`generate_sections_auto`, `generate_sections_curve` y `add_section_click` AÑADEN secciones a las existentes; "
    "`generate_sections_manual` REEMPLAZA todas. "
    "Cualquier cambio de secciones invalida el análisis previo, y `run_reconciliation` reemplaza TODOS los resultados "
    "usando la configuración de detección guardada en la sesión. "
    "Si ya hay secciones o resultados, `generate_sections_auto`, `generate_sections_curve`, `generate_sections_manual` "
    "y `run_reconciliation` pedirán confirmación; `add_section_click` pide confirmación solo si ya hay resultados. "
    "Explica qué se añade, qué se reemplaza y qué se invalida, y espera la decisión."
)


def test_agent_system_prompt_production_loader_rule_5(monkeypatch):
    monkeypatch.setattr(conversations, "_agent_system_prompt_cache", None)
    text = conversations.agent_system_prompt()
    assert "AÑADEN secciones" in text
    assert "`add_section_click` pide confirmación solo si ya hay resultados" in text
    assert "`add_section_click` se ejecuta sin confirmación" not in text
    assert "generar secciones reemplaza TODAS" not in text
    assert "procées" not in text
    assert _rule_line(text, 5) == _RULE_5_LINE


def test_agent_system_prompt_rule_4_flow_lists_curve(monkeypatch):
    monkeypatch.setattr(conversations, "_agent_system_prompt_cache", None)
    text = conversations.agent_system_prompt()
    assert _RULE_4_FRAGMENT in _rule_line(text, 4)


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

_RULE_13_LINE = (
    "13. **Tronadura**: para pozos, factor de carga o sobreexcavación usa "
    "`get_blast_summary`, `get_blast_correlation` y `get_blast_damage_model`; son solo lectura. "
    "Cita el factor de carga en g/t con su estado y su origen, y declara los supuestos: "
    "densidad de roca (si su estado es DEFAULT, di que el factor de carga es provisorio porque usa 2,7 t/m³ por defecto), "
    "altura de banco y convención de inclinación. "
    "Los explosivos desconocidos no tienen energía y nunca se tratan como ANFO. "
    "La cobertura energética es una fracción de 0 a 1, no una masa. "
    "La sobreexcavación y el déficit están en metros. "
    "No afirmes que la tronadura causó un daño en la berma o la cresta sin un ajuste del modelo de daño con puntos suficientes; "
    "si `n_points` es 0 o no hay ajuste, dilo. "
    "La tolerancia de proyección de pozos está en metros (15 m por defecto)."
)

_RULE_14_LINE = (
    "14. **Editar y borrar secciones**: para corregir una sección usa `update_section` con su section_id "
    "y solo los campos que cambian; si ya hay resultados pedirá confirmación. "
    "Para eliminarla usa `delete_section`, que siempre pide confirmación y borra una sola sección por llamada. "
    "Antes de editar o borrar, confirma el nombre y el section_id con `list_sections` y nombra la sección al usuario; "
    "avisa que el análisis quedará invalidado. "
    "Después de borrar, los section_id posteriores bajan en 1: vuelve a consultar `list_sections` antes de otra edición. "
    "Para generar secciones a lo largo de una cresta o curva usa `generate_sections_curve` "
    "con los puntos de la polilínea y el espaciamiento en metros (como máximo 200 secciones por curva)."
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
    assert numbers == list(range(1, 16))
    for new_text in (
        _rule_line(text, 5),
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


def test_agent_system_prompt_rule_13_blast_tools(monkeypatch):
    monkeypatch.setattr(conversations, "_agent_system_prompt_cache", None)
    text = conversations.agent_system_prompt()
    rule_13 = _rule_line(text, 13)
    assert rule_13 == _RULE_13_LINE
    assert _RULE_13_LINE in text
    for tool in ("get_blast_summary", "get_blast_correlation", "get_blast_damage_model"):
        assert f"`{tool}`" in rule_13, tool
    for word in _VOSEO_FORBIDDEN:
        assert word not in rule_13.lower(), (word, rule_13)


def test_agent_system_prompt_rule_14_edit_delete_and_curve(monkeypatch):
    monkeypatch.setattr(conversations, "_agent_system_prompt_cache", None)
    text = conversations.agent_system_prompt()
    rule_14 = _rule_line(text, 14)
    assert rule_14 == _RULE_14_LINE
    for tool in ("update_section", "delete_section", "list_sections", "generate_sections_curve"):
        assert f"`{tool}`" in rule_14, tool
    for word in _VOSEO_FORBIDDEN:
        assert word not in rule_14.lower(), (word, rule_14)


def test_agent_system_prompt_mentions_every_write_tool(monkeypatch):
    monkeypatch.setattr(conversations, "_agent_system_prompt_cache", None)
    text = conversations.agent_system_prompt()
    write_tools = sorted(
        spec.name
        for spec in AGENT_TOOLS
        if spec.risk not in (ToolRisk.READ, ToolRisk.EXPORT)
    )
    assert write_tools
    for name in write_tools:
        assert f"`{name}`" in text, name


def test_horizontal_deviation_rule(monkeypatch):
    monkeypatch.setattr(conversations, "_agent_system_prompt_cache", None)
    text = conversations.agent_system_prompt()
    assert "15. **Desviación horizontal dH**" in text
    assert "Negativo = faltante (roca que falta excavar), positivo = sobreexcavación" in text
    assert 'Las muestras "sin medición" no indican cumplimiento ni cero' in text
