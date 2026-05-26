# CONTEXT.md — Conciliación Geotécnica: Diseño vs As-Built

Contexto técnico completo del proyecto para asistentes de IA y nuevos desarrolladores. Referencia rápida de arquitectura, módulos, algoritmos y convenciones.

---

## 1. Qué es este proyecto

Herramienta para conciliación automática de parámetros geotécnicos de taludes en minería a cielo abierto. Compara superficies 3D (diseño vs topografía real as-built), genera secciones transversales, extrae parámetros geométricos (altura de banco, ángulo de cara, ancho de berma) y evalúa cumplimiento contra tolerancias de diseño.

**Interfaces disponibles**:
- `app.py` — Aplicación web interactiva (Streamlit)
- `cli.py` — Línea de comandos para automatización
- `api/main.py` — API REST (FastAPI) para integración con frontend externo

---

## 2. Estructura de archivos

```
├── app.py                    # UI Streamlit (~2000 líneas, 83KB)
├── cli.py                    # CLI (~220 líneas)
├── test_pipeline.py          # Test de integración con datos sintéticos
├── requirements.txt
├── packages.txt              # Deps de sistema para Streamlit Cloud
├── ejemplo_secciones.json    # Config de secciones de ejemplo
├── .streamlit/config.toml
│
├── core/
│   ├── __init__.py           # Re-exports públicos
│   ├── mesh_handler.py       # Carga STL/OBJ/DXF, decimación (~213 líneas)
│   ├── section_cutter.py     # Definición de secciones, corte de mallas (~242 líneas)
│   ├── param_extractor.py    # Detección de bancos, comparación (~528 líneas)
│   ├── excel_writer.py       # Exportación Excel formateado (~360 líneas)
│   ├── geom_utils.py         # Utilidades geométricas (~95 líneas)
│   ├── report_generator.py   # Informe Word + imágenes (~196 líneas)
│   └── ai_reporter.py        # Informe ejecutivo vía LLM (~83 líneas)
│
└── api/
    ├── __init__.py
    └── main.py               # Endpoints FastAPI (~672 líneas)
```

---

## 3. Pipeline de procesamiento (flujo de datos)

```
Archivos STL (Diseño + Topografía)
         │
         ▼
   load_mesh()  →  objetos Trimesh
         │
         ▼
  Definir secciones  (Manual / Auto / Click / Archivo CSV o DXF)
         │
         ▼
  cut_mesh_with_section()  →  ProfileResult(distances, elevations) por sección
         │
         ▼
  extract_parameters()  →  ExtractionResult(bancos, ángulos) por sección
         │
         ▼
  compare_design_vs_asbuilt()  →  List[Dict] con MATCH / MISSING / EXTRA
         │
         ▼
  Exportaciones:
    - Excel  (openpyxl)
    - Word   (python-docx)
    - DXF    (ezdxf)
    - ZIP imágenes  (matplotlib)
    - Informe LLM   (OpenAI / local)
```

---

## 4. Módulos core — referencia rápida

### 4.1 `core/mesh_handler.py`

Carga y manipulación de mallas 3D.

| Función | Descripción |
|---------|-------------|
| `load_mesh(filepath)` | Carga STL/OBJ/PLY/DXF con trimesh |
| `get_mesh_bounds(mesh)` | Bounding box, centroide y estadísticas |
| `decimate_mesh(mesh, target_faces)` | Reduce complejidad para visualización |
| `mesh_to_plotly(mesh, name, color, opacity)` | Convierte trimesh a traza Plotly 3D |
| `load_dxf_polyline(file_path)` | Extrae LWPOLYLINE/POLYLINE de DXF |

**Decimación**: usa `fast_simplification` (quadric decimation) como principal; fallback a vertex clustering manual por grid.

---

### 4.2 `core/section_cutter.py`

Define planos de corte verticales y extrae perfiles 2D.

**Clases**:
```python
@dataclass
class SectionLine:
    name: str
    origin: np.ndarray   # [X, Y]
    azimuth: float       # grados desde Norte, sentido horario
    length: float        # metros
    sector: str = ""

@dataclass
class ProfileResult:
    distances: np.ndarray    # distancia a lo largo de la sección (m)
    elevations: np.ndarray   # elevación Z (m)
```

| Función | Descripción |
|---------|-------------|
| `azimuth_to_direction(az_deg)` | Azimut → vector 2D. N=0°→[0,1], E=90°→[1,0] |
| `cut_mesh_with_section(mesh, section)` | Corta malla con plano vertical → `ProfileResult` |
| `cut_both_surfaces(mesh_d, mesh_t, section)` | Corta diseño y topo en una llamada |
| `compute_local_azimuth(mesh, point_xy, r=50)` | Azimut de mayor pendiente local (ajuste de plano) |
| `generate_sections_along_crest(...)` | Genera N secciones equiespaciadas a lo largo de una línea |
| `generate_perpendicular_sections(...)` | Secciones perpendiculares a una polilínea con espaciado dado |

**Algoritmo de corte**:
1. Plano vertical definido por normal perpendicular al azimut en el origen
2. `trimesh.intersections.mesh_plane()` → segmentos de intersección
3. Proyectar puntos a distancia-sobre-sección vs Z
4. Filtrar por longitud, ordenar, eliminar duplicados cercanos (< 0.003 m)

---

### 4.3 `core/param_extractor.py`

Detección de bancos y comparación diseño vs as-built. **Módulo central.**

**Clases**:
```python
@dataclass
class BenchParams:
    bench_number: int
    crest_elevation: float
    crest_distance: float
    toe_elevation: float
    toe_distance: float
    bench_height: float
    face_angle: float       # grados
    berm_width: float       # metros
    is_ramp: bool = False

@dataclass
class ExtractionResult:
    section_name: str
    sector: str
    benches: List[BenchParams]
    inter_ramp_angle: float
    overall_angle: float
```

**Funciones clave**:

| Función | Descripción |
|---------|-------------|
| `ramer_douglas_peucker(points, epsilon)` | Simplificación RDP (ε=0.1 m por defecto) |
| `extract_parameters(distances, elevations, ...)` | Extrae bancos de un perfil 2D |
| `build_reconciled_profile(benches)` | Reconstruye perfil idealizado desde bancos detectados |
| `compare_design_vs_asbuilt(params_d, params_t, tolerances)` | Compara por algoritmo húngaro → lista de resultados |
| `_evaluate_status(deviation, tol_neg, tol_pos)` | `"CUMPLE"` / `"FUERA DE TOLERANCIA"` / `"NO CUMPLE"` |

**Algoritmo de extracción** (`extract_parameters`):
1. Simplificar perfil con RDP (ε=0.1 m)
2. Calcular ángulo de cada segmento simplificado
3. Clasificar: **Cara** (≥ `face_threshold`=40°) | **Berma** (≤ `berm_threshold`=20°)
4. Fusionar segmentos consecutivos del mismo tipo
5. Extraer parámetros por banco:
   - Cresta = punto más alto de la cara
   - Pie = punto más bajo de la cara
   - Ángulo = promedio ponderado de segmentos de cara
6. Calcular anchos de berma (distancia horizontal entre pie[i] y cresta[i+1])
7. Filtrar bermas irrealistas (> `max_berm_width`=50 m)
8. Detectar rampas (ancho 15–42 m)
9. Calcular ángulo inter-rampa y global

**Algoritmo de comparación** (Algoritmo Húngaro):
- Matriz de costos: `|elevación_diseño[i] - elevación_topo[j]|`
- `scipy.optimize.linear_sum_assignment` minimiza costo total
- Umbral de match: diferencia < 8.0 m (mitad de altura de banco típica)
- Clasificar residuos: MISSING → "NO CONSTRUIDO", EXTRA → "BANCO ADICIONAL"

**Evaluación tripartita**:
- `CUMPLE`: dentro de tolerancia
- `FUERA DE TOLERANCIA`: entre tolerancia y 1.5× tolerancia
- `NO CUMPLE`: excede 1.5× tolerancia

---

### 4.4 `core/excel_writer.py`

Genera workbook Excel con 5 hojas.

| Función | Hoja generada |
|---------|---------------|
| `export_results(...)` | Función principal (entry point) |
| `_write_summary_sheet(...)` | **Resumen**: info de proyecto + tabla de tolerancias |
| `_write_sector_summary(...)` | **Resumen Ejecutivo**: cumplimiento por sector |
| `_write_bench_sheet(...)` | **Bancos**: altura, ángulo, berma por banco |
| `_write_interramp_sheet(...)` | **Inter-Rampa**: ángulos inter-rampa y global |
| `_write_dashboard_sheet(...)` | **Dashboard**: resumen de cumplimiento general |

Colores de estado: Verde (CUMPLE), Amarillo (FUERA), Rojo (NO CUMPLE), Gris (NO CONSTRUIDO), Púrpura (EXTRA/RAMPA).

---

### 4.5 `core/geom_utils.py`

Cálculos geométricos de perfil.

| Función | Descripción |
|---------|-------------|
| `calculate_profile_deviation(ref, eval)` | Distancia euclidiana 2D mínima por punto (KDTree) |
| `calculate_area_between_profiles(ref, eval)` | Área sobre-excavada / deuda (bajo diseño) entre perfiles |

---

### 4.6 `core/report_generator.py`

Informe Word y figuras matplotlib.

| Función | Descripción |
|---------|-------------|
| `create_section_plot(...)` | Figura matplotlib: diseño / topo / reconciliado + marcadores de banco → `BytesIO` |
| `generate_word_report(...)` | Genera `.docx` con resumen ejecutivo + tabla + secciones detalladas |
| `generate_section_images_zip(...)` | ZIP con todas las imágenes PNG de secciones |

---

### 4.7 `core/ai_reporter.py`

Genera informe ejecutivo vía LLM (streaming).

| Función | Descripción |
|---------|-------------|
| `generate_geotech_report(stats, api_key, model, base_url=None)` | Yield de chunks de texto del informe |

Soporta OpenAI API y modelos locales (LM Studio, Ollama) mediante `base_url`.

---

### 4.8 `core/__init__.py` — API pública

```python
from core import (
    load_mesh, get_mesh_bounds, mesh_to_plotly, decimate_mesh,
    load_dxf_polyline,
    SectionLine, cut_mesh_with_section, cut_both_surfaces,
    extract_parameters, compare_design_vs_asbuilt,
    generate_word_report, generate_section_images_zip,
)
```

---

## 5. Interfaz Streamlit (`app.py`)

Organización principal:

1. **Carga y visualización**: Upload de STL, vista 3D con Plotly
2. **Definición de secciones** (4 métodos):
   - Manual (origen, azimut, longitud)
   - Automático (línea inicio→fin, N secciones)
   - Click interactivo en vista de planta
   - Desde archivo (CSV o polilínea DXF)
3. **Configuración** (sidebar): umbrales, tolerancias, info de proyecto, LLM
4. **Procesamiento y resultados**: visor de perfiles interactivo, drag para editar perfil reconciliado
5. **Exportaciones**: Excel, Word, DXF 3D, ZIP imágenes, informe LLM (streaming)

**Estado de sesión**: `st.session_state` (no persistente entre recargas).

---

## 6. CLI (`cli.py`)

```bash
python cli.py --design diseno.stl --topo topo.stl \
  --auto --start "1000,2000" --end "1500,2000" --n 10 \
  --azimuth 0 --length 200 \
  --output resultados.xlsx --report informe.docx \
  --project "Sector Norte" --author "Ing. Apellido"
```

Argumentos de tolerancias: `--tol-height`, `--tol-angle`, `--tol-ir`, `--min-berm`.
Argumentos de detección: `--face-threshold`, `--berm-threshold`, `--resolution`.

---

## 7. API REST (`api/main.py`)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/health` | Estado del servidor |
| POST | `/api/upload/design` | Subir malla de diseño |
| POST | `/api/upload/topo` | Subir malla de topografía |
| GET | `/api/mesh/bounds` | Bounds y vértices submuestreados |
| POST | `/api/sections/manual` | Secciones manuales |
| POST | `/api/sections/auto` | Generación automática |
| POST | `/api/sections/from-file` | Desde CSV/DXF |
| POST | `/api/sections/add-click` | Sección por clic |
| GET/DELETE | `/api/sections` | Listar / limpiar secciones |
| POST | `/api/settings` | Umbrales de detección |
| POST | `/api/tolerances` | Tolerancias de comparación |
| POST | `/api/process` | Procesar todas las secciones |
| GET | `/api/profiles/{idx}` | Perfil de una sección |
| PUT | `/api/reconciled/{idx}` | Actualizar perfil reconciliado |
| GET | `/api/results` | Resultados de comparación |
| GET | `/api/export/excel` | Descargar Excel |
| GET | `/api/export/dxf` | Descargar DXF 3D |

Sesión en memoria (`SessionStore`). CORS habilitado para todos los orígenes.

---

## 8. Parámetros y tolerancias por defecto

### Detección de bancos

| Parámetro | Valor | Variable |
|-----------|-------|----------|
| Ángulo mínimo de cara | 40° | `face_threshold` |
| Ángulo máximo de berma | 20° | `berm_threshold` |
| Berma máxima (filtro) | 50 m | `max_berm_width` |
| Resolución de perfil | 0.5 m | `resolution` |
| RDP epsilon | 0.1 m | hardcoded |
| Rango de rampas | 15–42 m | hardcoded |
| Umbral de match de banco | 8.0 m | hardcoded |

### Tolerancias de diseño

| Parámetro | Valor diseño | Tol. negativa | Tol. positiva |
|-----------|--------------|---------------|---------------|
| Altura de banco | 15 m | -1.0 m | +1.5 m |
| Ángulo cara de banco | 70° | -5° | +5° |
| Ancho de berma | 9 m | -1.0 m | +2.0 m |
| Ángulo inter-rampa | 48° | -3° | +2° |
| Ángulo global | 42° | -2° | +2° |
| Ancho de rampa | 25 m | -2 m | 0 m |
| Gradiente de rampa | 10% | 0% | +2% |

---

## 9. Convenciones del proyecto

- **Idioma del código**: Inglés (variables, funciones, docstrings)
- **Idioma de la UI**: Español (labels, títulos, mensajes)
- **Coordenadas**: X = Este, Y = Norte, Z = Elevación (sistema minero estándar)
- **Azimut**: grados desde Norte, sentido horario (N=0°, E=90°, S=180°, W=270°)
- **Unidades**: metros (m), grados (°), porcentaje (%) para gradientes

---

## 10. Dependencias principales

| Paquete | Uso |
|---------|-----|
| `trimesh` | Carga y operaciones de mallas 3D |
| `numpy` | Cálculos numéricos |
| `scipy` | Algoritmo húngaro, interpolación, KDTree |
| `plotly` | Gráficos 3D y 2D interactivos |
| `matplotlib` | Figuras estáticas para Word/ZIP |
| `streamlit` | UI web interactiva |
| `fastapi` + `uvicorn` | API REST |
| `openpyxl` | Exportación Excel |
| `python-docx` | Generación de informes Word |
| `ezdxf` | Lectura/escritura de archivos DXF |
| `fast_simplification` | Decimación de mallas (quadric) |
| `openai` | Cliente LLM para informes AI |

---

## 11. Problemas conocidos y deuda técnica

| Severidad | Descripción |
|-----------|-------------|
| ⚠️ Media | Anchos de berma irrealistas (> 50 m) en zonas planas extensas. Parcialmente filtrado con `max_berm_width`. |
| ⚠️ Media | Detección de rampas parcial (rango 15–42 m). Hoja de Rampas en Excel requiere datos manuales. |
| ⚠️ Baja | Secciones cerca del borde de malla pueden producir perfiles incompletos. Sin advertencia al usuario. |
| 🔧 Baja | `param_extractor.py` línea ~364: `return comparisons` huérfano (código muerto). |
| 🔧 Baja | Constantes mágicas dispersas (8.0 m umbral match, 0.1 m RDP). Deberían ser configurables. |
| 🔧 Baja | `app.py` monolítico (83 KB). Candidato a refactorización en componentes. |
| 🔧 Baja | API `SessionStore` no soporta múltiples usuarios simultáneos. |
| 🔧 Baja | Sin tests unitarios; solo test de integración (`test_pipeline.py`). |
| 🔧 Baja | Uso de `print()` en lugar de framework de logging. |

---

## 12. Mejoras pendientes (roadmap)

- 📋 Soporte para archivos DXF 3D faces como entrada
- 📋 Correspondencia de bancos por elevación (ya implementada con húngaro; mejorar filtrado)
- 📋 Detección automática de rampas en perfiles
- 📋 Exportación de secciones como imágenes/PDF
- 📋 Filtro de ancho máximo de berma configurable desde UI
- 📋 Vista de planta con ubicación de secciones sobre topografía
- 📋 Soporte para múltiples dominios geotécnicos con tolerancias independientes
- 📋 Generación automática del informe Word con datos reales (actualmente usa plantilla)

---

## 13. Entrypoints y comandos

```bash
# Tests
python test_pipeline.py

# Streamlit
streamlit run app.py

# CLI
python cli.py --design diseno.stl --topo topo.stl \
  --auto --start "1000,2000" --end "1500,2000" --n 10 \
  --azimuth 0 --length 200 --output resultados.xlsx

# API
uvicorn api.main:app --reload --port 8000
```

---

*Generado automáticamente el 2026-02-25. Mantener sincronizado con CLAUDE.md al evolucionar el proyecto.*
