"""Prompt template loader for the AI agent v2."""
from __future__ import annotations

from pathlib import Path

_TEMPLATES_DIR: Path = Path(__file__).parent


def get_all_template_names() -> list[str]:
    return [
        "system_role.md",
        "executive_summary.md",
        "blast_enrichment.md",
    ]


def load_prompt_template(name: str) -> str:
    path = _TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt template not found: {name} (looked in {path})"
        )
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **kwargs: str) -> str:
    try:
        return template.format(**kwargs)
    except KeyError as exc:
        missing = exc.args[0] if exc.args else "unknown"
        raise KeyError(
            f"Missing placeholder '{missing}' for prompt template. "
            f"Required keys: see template; provided: {sorted(kwargs.keys())}"
        ) from exc