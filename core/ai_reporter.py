

import os
import streamlit as st

def generate_geotech_report(stats, api_key, model, base_url=None):
    """
    Generate a geotechnical executive report using an LLM.
    
    Args:
        stats (dict): Dictionary containing calculated statistics and metrics.
        api_key (str): OpenAI API Key or "local" for local models.
        model (str): Model name (e.g., "gpt-4", "qwen-2.5-7b").
        base_url (str, optional): Custom API URL for local models (e.g., "http://localhost:1234/v1").
        
    Yields:
        str: Chunks of the generated response.
    """
    
    # Client Configuration
    if not api_key:
        yield "⚠️ Error: Por favor ingresa una API Key o configura la URL local."
        return

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=base_url if base_url else None
        )
    except Exception as e:
        yield f"⚠️ Error al configurar el cliente: {str(e)}"
        return

    # Construct the Prompt
    # We'll create a concise summary of the stats to send to the LLM
    
    # 1. Global Compliance
    global_stats = stats.get('global_stats', {})
    compliance_text = ""
    for k, v in global_stats.items():
        compliance_text += f"- {k}: {v}\n"

    # 2. Critical Sections (Mockup logic if stats doesn't have it explicitly, 
    # but assuming we pass the full 'comparisons' list or a summary)
    # For now, let's assume 'stats' has a 'critical_sections' list or we summarize it.
    # If not, we'll keep it generic.
    
    prompt = f"""
    Actúa como un Ingeniero Geotécnico Senior experto en conciliación (Diseño vs As-Built).
    Tu tarea es escribir un **Informe Ejecutivo** breve y profesional basado en los siguientes datos de la semana.

    ### Datos del Proyecto
    - Total de Bancos Analizados: {stats.get('n_total', 'N/A')}
    - Tramos/Bancos Validados: {stats.get('n_valid', 'N/A')}
    
    ### Estadísticas Globales
    {compliance_text}

    ### Instrucciones
    1.  **Resumen Ejecutivo**: Da un veredicto general sobre la adherencia al diseño (¿Es buena, regular o mala?).
    2.  **Análisis de Desviaciones**: Menciona qué parámetro (Altura, Ángulo, Berma) presenta mayores problemas.
    3.  **Recomendaciones**: Sugiere 2-3 acciones operativas para corregir las desviaciones detectadas (ej. "Revisar perforación en bancos superiores" si hay sobre-excavación).
    4.  **Tono**: Técnico, directo y profesional. Usa formato Markdown (negritas, listas).
    5.  **Idioma**: Español.

    Genera el informe ahora.
    """

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

    except Exception as e:
        yield f"\n\n⚠️ Error al generar el informe: {str(e)}"
