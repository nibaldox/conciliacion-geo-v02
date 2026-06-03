# CLAUDE.md — Conciliación Geotécnica: Diseño vs As-Built

## Descripción del Proyecto

Herramienta para conciliación automática de parámetros geotécnicos de taludes en minería a cielo abierto. Compara superficies 3D de diseño vs topografía real (as-built), genera secciones transversales, extrae parámetros geométricos y evalúa cumplimiento.

**Usuario**: Ingeniero geotécnico en operaciones mineras (Latinoamérica). Trabaja con Vulcan, Campbell Scientific CR300, radar IBIS, piezómetros de cuerda vibrante. Prefiere comunicación en español.

## Stack Tecnológico

- **Backend**: Python 3.10+
- **Frontend**: Streamlit
- **Mallas 3D**: trimesh
- **Geometría**: numpy, scipy, shapely
- **Visualización**: plotly
- **Export Excel**: openpyxl
- **Deploy**: Streamlit Community Cloud

## Arquitectura

```
├── app.py                 # Interfaz Streamlit (entrada principal)
├── cli.py                 # Interfaz línea de comandos
├── core/
│   ├── __init__.py        # Re-exports públicos
│   ├── mesh_handler.py    # Carga STL/OBJ, decimación, conversión a plotly
│   ├── section_cutter.py  # Generación de secciones y corte de mallas
│   ├── param_extractor.py # Detección de bancos, extracción de parámetros
│   └── excel_writer.py    # Exportación de resultados a Excel formateado
├── test_pipeline.py       # Test con superficies sintéticas
├── ejemplo_secciones.json # Ejemplo de configuración de secciones
├── requirements.txt
├── packages.txt           # Dependencias de sistema (Streamlit Cloud)
└── .streamlit/config.toml # Configuración de tema y servidor
```

## Pipeline de Procesamiento

1. **Carga de mallas** (`mesh_handler.py`): Lee STL/OBJ con trimesh
2. **Corte de secciones** (`section_cutter.py`): Plano vertical definido por origen + azimut interseca las mallas. Produce perfiles 2D (distancia vs elevación)
3. **Extracción de parámetros** (`param_extractor.py`):
   - Suaviza y resamplea el perfil
   - Calcula ángulos locales entre puntos consecutivos
   - Clasifica segmentos como "cara" (>40°) o "berma" (<20°)
   - Extrae: altura de banco, ángulo de cara, ancho de berma
   - Calcula ángulos inter-rampa y global
4. **Comparación** (`param_extractor.py`): Evalúa desviación diseño vs real contra tolerancias → CUMPLE / FUERA DE TOLERANCIA / NO CUMPLE
5. **Exportación** (`excel_writer.py`): Genera Excel con hojas Resumen, Bancos, Inter-Rampa, Dashboard

## Parámetros de Diseño de Referencia

| Parámetro | Valor | Tolerancia |
|-----------|-------|------------|
| Altura de banco | 15 m | -1.0 / +1.5 m |
| Ángulo cara de banco | 70° | ±5° |
| Ancho de berma | 9 m | -1.0 / +2.0 m |
| Ángulo inter-rampa | 48° | -3° / +2° |
| Ángulo global | 42° | ±2° |
| Ancho de rampa | 25 m | -2 / +0 m |
| Gradiente de rampa | 10% | 0 / +2% |

## Decisiones de Diseño Tomadas

- **Formato de entrada**: STL como formato principal (exportado desde Vulcan). Trimesh soporta OBJ y PLY también.
- **Detección de bancos**: Basada en umbrales de ángulo local (face_threshold=40°, berm_threshold=20°). Son configurables desde la UI y CLI.
- **Secciones**: Se definen por punto de origen [X,Y], azimut y longitud. Se pueden definir manualmente o generar equiespaciadas a lo largo de una línea.
- **Evaluación tripartita**: CUMPLE (dentro de tolerancia), FUERA DE TOLERANCIA (hasta 1.5x la tolerancia), NO CUMPLE (excede 1.5x).
- **Interfaz dual**: Streamlit para uso interactivo, CLI para automatización/scripting.

## Estado Actual y Problemas Conocidos

### Funcional
- ✅ Carga de STL y visualización 3D
- ✅ Generación de secciones (manual y automática)
- ✅ Corte de superficies y extracción de perfiles
- ✅ Detección de bancos y extracción de parámetros
- ✅ Comparación diseño vs as-built
- ✅ Exportación a Excel con formato condicional
- ✅ Dashboard de cumplimiento con gráficos
- ✅ Test con datos sintéticos pasa correctamente

### Problemas conocidos / Mejoras pendientes
- ⚠️ **Detección de bermas**: En superficies sintéticas, el algoritmo a veces detecta bermas con anchos irrealistas (>50m) cuando hay zonas planas extensas entre bancos. Necesita filtrado por ancho máximo razonable.
- ⚠️ **Correspondencia de bancos**: La comparación diseño vs as-built asume que banco N del diseño corresponde a banco N del as-built (por orden). Debería usar correspondencia por elevación para ser más robusto.
- ⚠️ **Rampas**: La detección de rampas NO está implementada en el extractor automático. La hoja de Rampas en el Excel se alimenta manualmente. Es un desarrollo pendiente.
- ⚠️ **Secciones en bordes**: Si la sección pasa cerca del borde de la malla, puede generar perfiles incompletos o con artefactos.

### Mejoras futuras deseadas
- 📋 Soporte para archivos DXF 3D faces
- 📋 Detección automática de rampas en perfiles
- 📋 Correspondencia de bancos por elevación (no por índice)
- 📋 Exportación de secciones transversales como imágenes/PDF
- 📋 Filtro de ancho máximo de berma configurable
- 📋 Vista de planta con ubicación de secciones superpuesta a la topografía
- 📋 Soporte para múltiples dominios geotécnicos con tolerancias diferentes
- 📋 Generación automática del informe Word con datos reales

## Comandos Útiles

```bash
# Instalar dependencias
pip install -r requirements.txt

# Correr tests
python test_pipeline.py

# Lanzar Streamlit localmente
streamlit run app.py

# CLI con generación automática de secciones
python cli.py --design diseno.stl --topo topo.stl --auto --start "1000,2000" --end "1500,2000" --n 10 --azimuth 0 --length 200

# CLI con archivo de secciones
python cli.py --design diseno.stl --topo topo.stl --config ejemplo_secciones.json
```

## Convenciones

- **Idioma del código**: Inglés (nombres de variables, funciones, docstrings)
- **Idioma de la interfaz**: Español (labels, títulos, mensajes al usuario)
- **Unidades**: metros (m), grados (°), porcentaje (%) para gradientes
- **Coordenadas**: Este (X), Norte (Y), Elevación (Z) — sistema minero estándar
- **Azimut**: Grados desde Norte, sentido horario (N=0°, E=90°, S=180°, W=270°)

## Entregables Adicionales (ya generados)

Además de esta herramienta, se generaron dos archivos estáticos de referencia:
- `Conciliacion_Diseno_vs_AsBuilt.xlsx` — Plantilla Excel con datos de ejemplo y fórmulas
- `Informe_Conciliacion_Geotecnica.docx` — Informe Word plantilla con 10 secciones

Estos archivos son independientes de la herramienta y sirven como referencia de formato.
