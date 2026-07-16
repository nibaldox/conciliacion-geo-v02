"""Step 2 sections package."""
from ui.step2_sections.renderer import render_step2_inner


def render_step2() -> None:
    """Render Paso 2: section definition."""
    render_step2_inner()


__all__ = ["render_step2", "render_step2_inner"]
