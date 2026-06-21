"""Tests for core.ai_v2 prompt loader and templates."""
from __future__ import annotations

import pytest

from core.ai_v2.prompts import (
    get_all_template_names,
    load_prompt_template,
    render_prompt,
)


def test_get_all_template_names():
    names = get_all_template_names()
    assert names == ["system_role.md", "executive_summary.md", "blast_enrichment.md"]


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