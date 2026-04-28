# AGENTS.md — Conciliación Geotécnica v02

## Proyecto

Herramienta de conciliación automática de parámetros geotécnicos para taludes en minería a cielo abierto.
Compara superficies 3D de diseño vs topografía real (STL), genera secciones transversales y evalúa cumplimiento contra tolerancias.

**Stack Backend**: Python 3.10+, Streamlit, FastAPI, trimesh, numpy, scipy, plotly, openpyxl
**Stack Frontend**: React 19, Vite, CesiumJS, TypeScript
**Deploy**: Streamlit Community Cloud + FastAPI backend

---

## Build/Lint/Test Commands

```bash
# Instalar dependencias (necesita libspatialindex-dev)
pip install -r requirements.txt

# Test de integración (superficies sintéticas, crea STL en /tmp/)
python test_pipeline.py

# Unit tests
pytest tests/ -v

# Un solo test
pytest tests/test_param_extractor.py::TestParamExtractor::test_extract_parameters -v
pytest tests/test_api.py::TestMeshUpload::test_upload_design -v

# Lanzar Streamlit
streamlit run app.py

# API dev server
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# CLI batch
python cli.py --design diseno.stl --topo topo.stl --auto --start "1000,2000" --end "1500,2000" --n 10 --azimuth 0 --length 200
python cli.py --design diseno.stl --topo topo.stl --config ejemplo_secciones.json
```

**No hay linting configurado** (sin flake8, black, isort, mypy, pre-commit). El código sigue convenciones implícitas.

---

## Code Style Guidelines

### Idioma
- **Código**: Inglés (variables, funciones, docstrings en inglés)
- **Interfaz/Labels**: Español

### Convenciones de Nomenclatura
| Elemento | Convención | Ejemplo |
|----------|------------|---------|
| Funciones | snake_case | `load_mesh`, `cut_mesh_with_section` |
| Clases/Dataclasses | PascalCase | `SectionLine`, `ProfileResult`, `BenchParams` |
| Constantes | UPPER_SNAKE_CASE | `HEADER_FILL`, `FILL_OK` |
| Módulos | snake_case | `mesh_handler.py`, `section_cutter.py` |

### Imports
```python
# Siempre desde core, nunca desde submodules
from core import load_mesh, SectionLine, cut_mesh_with_section, extract_parameters

# Ejemplo completo de orden
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from scipy.interpolate import interp1d
from core import extract_parameters
```

### Type Hints
- Usar en firmas de funciones públicas
- `np.ndarray` para arrays
```python
def azimuth_to_direction(azimuth_deg: float) -> np.ndarray:
    ...
```

### Docstrings
- Google-style
```python
def cut_mesh_with_section(mesh, section):
    """Cut a mesh with a vertical section plane.

    Args:
        mesh: trimesh mesh object
        section: SectionLine defining the cut plane

    Returns:
        ProfileData with distances and elevations
    """
```

### Dataclasses
```python
from dataclasses import dataclass, field

@dataclass
class BenchParams:
    bench_number: int
    crest_elevation: float
    toe_elevation: float
    face_angle: float
    berm_width: float
    is_ramp: bool = False
    ramp_gradient: Optional[float] = None

# Configuración inmutable via frozen
@dataclass(frozen=True)
class DefaultTolerances:
    bench_height: float = 15.0
    face_angle: float = 5.0
```

### Logging y Error Handling
```python
# Logging por módulo
logger = logging.getLogger(__name__)

# Retornar None en fallo; except Exception: con comentario cuando es intencional
try:
    mesh = _load_dxf(filepath)
except Exception as e:
    logger.warning(f"ezdxf fallback: {e}")
    mesh = trimesh.load(filepath)
```

---

## Project Structure

```
├── app.py                    # Entry point Streamlit (wizard de 4 pasos)
├── cli.py                    # CLI para automatización batch
├── api/                      # FastAPI backend
│   ├── main.py               # App factory + CORS + session middleware
│   ├── database.py           # SQLite session management
│   ├── schemas.py            # Pydantic models
│   └── routers/             # /meshes, /sections, /process, /export, /settings, /ai
├── core/                     # Lógica de negocio (importar desde core, NO de submodules)
│   ├── mesh_handler.py        # Carga STL/OBJ/PLY/DXF → trimesh
│   ├── section_cutter.py     # SectionLine dataclass, cut_mesh_with_section
│   ├── param_extractor.py    # Detección bancos, RDP simplification
│   ├── config.py             # Frozen dataclasses para defaults
│   ├── excel_writer.py       # Exportación Excel formateado
│   ├── report_generator.py   # Word report + ZIP de imágenes
│   ├── geom_utils.py         # Cálculos de desviación de perfil
│   ├── ai_reporter.py        # Integración OpenAI/LM Studio
│   └── ai_service.py
├── ui/                       # Componentes Streamlit
│   ├── tabs/                 # Dashboard, profiles, table, export, AI report
│   └── components/          # Upload, sidebar, processing, results, sections, viz
├── web/                      # Frontend React (alternative location)
├── frontend/                 # Frontend alternative
├── tests/                    # pytest test suite
│   ├── conftest.py          # Fixtures: pit_mesh_design, pit_mesh_asbuilt, sample_sections
│   ├── test_section_cutter.py
│   ├── test_param_extractor.py
│   ├── test_comparison.py
│   ├── test_mesh_handler.py
│   └── test_api.py          # 24 tests de endpoints
└── test_pipeline.py          # Test de integración con superficies sintéticas
```

---

## Domain Conventions

### Coordenadas
- **Este (X)**, **Norte (Y)**, **Elevación (Z)** — sistema minero estándar

### Azimut
- Grados desde Norte, sentido horario
- N=0°, E=90°, S=180°, W=270°

### Unidades
- Metros (m), grados (°), porcentaje (%) para gradientes

### Tolerancias de Diseño (referencia)
| Parámetro | Valor | Tolerancia |
|-----------|-------|------------|
| Altura banco | 15 m | -1.0 / +1.5 m |
| Ángulo cara | 70° | ±5° |
| Ancho berma | 9 m | -1.0 / +2.0 m |
| Ángulo inter-rampa | 48° | -3° / +2° |
| Ángulo global | 42° | ±2° |

### Evaluación tripartita
- **CUMPLE**: dentro de tolerancia
- **FUERA DE TOLERANCIA**: hasta 1.5x la tolerancia
- **NO CUMPLE**: excede 1.5x la tolerancia

---

## Patrones Clave

### Imports (REGLA CRÍTICA)
```python
# ✅ CORRECTO
from core import load_mesh, SectionLine, extract_parameters

# ❌ INCORRECTO
from core.mesh_handler import load_mesh
```

### Session State (Streamlit)
```python
_DEFAULTS = {
    'mesh_design': None, 'mesh_topo': None,
    'step': 1, 'sections': [], ...
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v
```

### Parallel Processing (ThreadPoolExecutor)
```python
# Nunca pasar objetos Streamlit a workers
def process_section(section, mesh):
    # trabajo pesado que no toca Streamlit
    return result

# En app.py:
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(process_section, s, mesh_copy) for s in sections]
    results = [f.result() for f in futures]
```

### Definición de Sección
```python
@dataclass
class SectionLine:
    name: str
    origin: np.ndarray  # [X, Y]
    azimuth: float     # degrees from North, clockwise
    length: float
    sector: str = ""
```

### API Session (FastAPI)
- Header `X-Session-ID` → `request.state.session_id`
- Middleware asigna session_id en cada request

### Pipeline de Procesamiento
1. `load_mesh(filepath)` → trimesh mesh
2. `cut_mesh_with_section(mesh, section)` → ProfileData
3. `extract_parameters(distances, elevations)` → ExtractionResult
4. `compare_design_vs_asbuilt(ep_d, ep_t, tolerances)` → ComparisonResult
5. `export_results(...)` → Excel

---

## Test Fixtures (tests/conftest.py)

```python
@pytest.fixture()
def pit_mesh_design():  # Synthetic pit, no noise

@pytest.fixture()
def pit_mesh_asbuilt():  # Synthetic pit, noise_std=0.3m

@pytest.fixture()
def sample_sections(pit_mesh_design):  # 5 auto-generated sections

@pytest.fixture()
def sample_tolerances():  # Standard tolerance dict

@pytest.fixture()
def mesh_stl_temp(pit_mesh_design):  # Temp file, auto-cleanup
```

---

## Problemas Conocidos

No modificar sin instrucción explícita:

- ⚠️ Detección de bermas con anchos irrealistas (>50m) en superficies sintéticas
- ⚠️ Rampas no detectadas automáticamente en el extractor
- ⚠️ Secciones cerca del borde de malla pueden producir perfiles incompletos

---

## Convenciones Git

- Commits convencionales: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
- No usar "Co-Authored-By" ni atribuciones AI
- No hacer build después de cambios
