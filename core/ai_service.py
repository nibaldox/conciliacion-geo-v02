"""
AI service for generating geotechnical reports using local LLMs.
Supports Ollama (localhost:11434) and LM Studio (localhost:1234).
Both use the OpenAI-compatible chat completions API.
"""

import json
from typing import Generator, Optional

from openai import OpenAI


# Provider configurations
PROVIDERS = {
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",  # Ollama doesn't need a real key
        "default_model": "llama3.1:8b",
    },
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "api_key": "lm-studio",  # LM Studio doesn't need a real key
        "default_model": "loaded-model",  # Uses whatever is loaded
    },
}

SYSTEM_PROMPT = """Eres un Ingeniero Geotécnico Senior con 20 años de experiencia en minería a cielo abierto. 
Tu especialidad es la conciliación geotécnica: comparar el diseño planificado vs la topografía real (as-built).

Tu trabajo es analizar datos de conciliación y generar informes ejecutivos profesionales en español.

Reglas:
1. NUNCA inventes datos que no estén en el contexto proporcionado
2. Usa terminología técnica minera correcta (bancos, taludes, bermas, ángulo interrampas, etc.)
3. Sé directo y profesional — los ingenieros leen esto, no gerentes de marketing
4. Clasifica el estado de cada parámetro como: CUMPLE, FUERA DE TOLERANCIA, o NO CUMPLE
5. Las tolerancias son: Altura ±(1.0m/1.5m), Ángulo ±5°, Berma mínima 6m, Ángulo interrampas ±(3°/2°), Ángulo general ±2°
6. Proporciona recomendaciones accionables específicas basadas en los datos
7. Formato: Markdown con secciones claras (Resumen, Análisis, Recomendaciones)
8. Idioma: Español técnico
"""


def get_available_models(provider: str) -> list[str]:
    """Try to fetch available models from the provider."""
    config = PROVIDERS.get(provider)
    if not config:
        return []
    try:
        client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        models = client.models.list()
        return [m.id for m in models.data]
    except Exception:
        return [config["default_model"]]


def check_provider_health(provider: str) -> dict:
    """Check if a provider is reachable."""
    config = PROVIDERS.get(provider)
    if not config:
        return {"available": False, "error": f"Unknown provider: {provider}"}
    try:
        client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        models = client.models.list()
        model_list = [m.id for m in models.data]
        return {
            "available": True,
            "provider": provider,
            "models": model_list,
            "base_url": config["base_url"],
        }
    except Exception as e:
        return {
            "available": False,
            "provider": provider,
            "error": str(e),
            "base_url": config["base_url"],
        }


def build_analysis_prompt(results: list[dict], sections: list[dict], settings: dict) -> str:
    """Build the analysis prompt from results data."""

    # Compute summary statistics
    total = len(results)
    if total == 0:
        return "No hay resultados de análisis disponibles. Solicita al usuario que ejecute el procesamiento primero."

    # Count by status
    height_ok = sum(
        1 for r in results
        if "CUMPLE" in r.get("height_status", "").upper()
        and "NO" not in r.get("height_status", "").upper()
    )
    angle_ok = sum(
        1 for r in results
        if "CUMPLE" in r.get("angle_status", "").upper()
        and "NO" not in r.get("angle_status", "").upper()
    )
    berm_ok = sum(
        1 for r in results
        if "CUMPLE" in r.get("berm_status", "").upper()
        and "NO" not in r.get("berm_status", "").upper()
    )

    height_warn = sum(1 for r in results if "FUERA" in r.get("height_status", "").upper())
    angle_warn = sum(1 for r in results if "FUERA" in r.get("angle_status", "").upper())
    berm_warn = sum(1 for r in results if "FUERA" in r.get("berm_status", "").upper())

    height_nok = sum(1 for r in results if "NO CUMPLE" in r.get("height_status", "").upper())
    angle_nok = sum(1 for r in results if "NO CUMPLE" in r.get("angle_status", "").upper())
    berm_nok = sum(1 for r in results if "NO CUMPLE" in r.get("berm_status", "").upper())

    # Missing/Extra
    missing = sum(1 for r in results if r.get("type") == "MISSING")
    extra = sum(1 for r in results if r.get("type") == "EXTRA")
    matched = sum(1 for r in results if r.get("type") == "MATCH")

    # Sections info
    section_names = sorted(set(r.get("section", "") for r in results))

    # Detailed deviations
    worst_height = sorted(
        [r for r in results if r.get("height_dev") is not None],
        key=lambda r: abs(r.get("height_dev", 0)),
        reverse=True,
    )[:5]
    worst_angle = sorted(
        [r for r in results if r.get("angle_dev") is not None],
        key=lambda r: abs(r.get("angle_dev", 0)),
        reverse=True,
    )[:5]

    prompt = f"""## DATOS DE CONCILIACIÓN GEOTÉCNICA

### Resumen General
- Total de comparaciones: {total}
- Bancos matched: {matched} | Missing (diseño sin correspondencia): {missing} | Extra (adicional no diseñado): {extra}
- Secciones analizadas: {len(section_names)} ({', '.join(section_names[:10])}{'...' if len(section_names) > 10 else ''})

### Cumplimiento por Parámetro
| Parámetro | CUMPLE | FUERA TOL. | NO CUMPLE | % Cumplimiento |
|-----------|--------|------------|-----------|----------------|
| Altura Banco | {height_ok} | {height_warn} | {height_nok} | {height_ok / total * 100:.1f}% |
| Ángulo Talud | {angle_ok} | {angle_warn} | {angle_nok} | {angle_ok / total * 100:.1f}% |
| Ancho Berma | {berm_ok} | {berm_warn} | {berm_nok} | {berm_ok / total * 100:.1f}% |

### Mayores Desviaciones en Altura
"""
    for r in worst_height:
        prompt += (
            f"- {r.get('section', '?')}-B{r.get('bench_num', '?')}: "
            f"desv={r.get('height_dev', 0):+.2f}m ({r.get('height_status', '')})\n"
        )

    prompt += "\n### Mayores Desviaciones en Ángulo\n"
    for r in worst_angle:
        prompt += (
            f"- {r.get('section', '?')}-B{r.get('bench_num', '?')}: "
            f"desv={r.get('angle_dev', 0):+.1f}° ({r.get('angle_status', '')})\n"
        )

    tolerances = settings.get("tolerances", {})
    if tolerances:
        prompt += "\n### Tolerancias Aplicadas\n"
        prompt += f"- Altura: {tolerances.get('bench_height', {})}\n"
        prompt += f"- Ángulo: {tolerances.get('face_angle', {})}\n"
        prompt += f"- Berma mínima: {tolerances.get('berm_width', {})}\n"

    prompt += "\nGenera el informe ejecutivo de conciliación geotécnica basado en estos datos reales."
    return prompt


def stream_report(provider: str, model: str, user_prompt: str) -> Generator[str, None, None]:
    """Stream a geotechnical report from the local LLM."""
    config = PROVIDERS.get(provider)
    if not config:
        yield f"⚠️ Proveedor desconocido: {provider}. Usa 'ollama' o 'lmstudio'."
        return

    try:
        client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            timeout=120.0,
        )

        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
            temperature=0.3,  # Low temperature for technical accuracy
            max_tokens=4096,
        )

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except ConnectionError:
        yield f"\n\n⚠️ No se pudo conectar a {provider} en {config['base_url']}.\n"
        yield f"**Asegúrate de que {provider} esté ejecutándose:**\n"
        if provider == "ollama":
            yield "- Instala: `curl -fsSL https://ollama.com/install.sh | sh`\n"
            yield "- Ejecuta: `ollama serve`\n"
            yield "- Descarga modelo: `ollama pull llama3.1:8b`\n"
        else:
            yield "- Descarga LM Studio desde https://lmstudio.ai\n"
            yield "- Carga un modelo y habilita el servidor local en el puerto 1234\n"
    except Exception as e:
        yield f"\n\n⚠️ Error: {str(e)}"
