# Auditoría Clean Code + Clean Architecture — `46-conciliacion-geo-v02`

**Fecha:** 20 junio 2026
**Commit base:** `a8ba76f` (Fases 0-14 aplicadas, 370/370 tests pasando)
**Alcance:** análisis estructural del repositorio completo (core/, ui/, api/, tests/, raíz).

---

## Resumen ejecutivo

- **8 archivos huérfanos eliminados** de la raíz (`verify_*.py`, `check_*.ps1`, `pytest_out.txt`, `Conciliacion_Resultados.xlsx`)
- **Cobertura de tests global: 76%** (2837 statements, 680 missed)
- **Arquitectura: capas claras** (api, core, ui, web) pero con imports directos a submódulos en lugar de la API pública
- **Duplicaciones críticas identificadas** pero todas en archivos en lista NO-TOUCH (no se pueden refactorizar sin violar `CONTRIBUTING.md`)
- **Magic strings/numbers**: 5 ubicaciones con status strings literales (`"CUMPLE"`, `"FUERA DE TOLERANCIA"`, `"NO CUMPLE"`) que podrían consolidarse

---

## 1. Limpieza aplicada

### Archivos eliminados (`git rm`)

| Archivo | Líneas | Razón |
|---|---|---|
| `verify_azimuth_convention.py` | 65 | Script one-shot de validación inicial, no usado por código de producción ni tests |
| `verify_azimuth_logic.py` | 79 | Idem |
| `verify_changes.py` | 113 | Idem |
| `check_proc.ps1` | 30 | Script PowerShell Windows, no usado por código Python |
| `check_procs.ps1` | 19 | Idem |
| `kill_uvicorn.ps1` | 36 | Idem |
| `pytest_out.txt` | — | Output de pytest, no usado |
| `Conciliacion_Resultados.xlsx` | — | Output, ya estaba gitignored por `*.xlsx` |

**Total eliminado:** ~342 líneas de archivos que no aportaban al proyecto.

### Archivos evaluados y mantenidos

- `app.py`, `cli.py`, `entry_api.py`, `dev.sh` — entry points verificados
- `test_pipeline.py` — test end-to-end (verificado con `grep -r`)
- `enaex_pozos_tronadura_2026.xlsx` — archivo de prueba del usuario
- `pyproject.toml`, `requirements*.txt`, `packages.txt` — config

---

## 2. Cobertura de tests

```
Name                           Stmts   Miss  Cover
----------------------------------------------------
core/__init__.py                   6      0   100%
core/ai_service.py               113     46    59%   ← atención
core/alert_system.py              45      0   100%
core/blast_advisor.py            175     16    91%
core/blast_correlation.py        203     10    95%
core/blast_metrics.py            208      6    97%
core/blast_model.py              137     17    88%
core/calculo_tronadura.py        143      3    98%
core/config.py                   122      4    97%
core/excel_writer.py             316    281    11%   ← crítica baja
core/explosive_properties.py      55      2    96%
core/geology.py                   73      0   100%
core/geom_utils.py                48     34    29%   ← crítica baja
core/mesh_handler.py             102     52    49%   ← baja
core/param_extractor.py          460     29    94%
core/report_generator.py         401    152    62%   ← baja
core/section_cutter.py           117     25    79%
core/stability_analysis.py       113      3    97%
----------------------------------------------------
TOTAL                           2837    680    76%
```

### Observaciones

- **Líderes de cobertura**: `alert_system.py`, `geology.py`, `__init__.py`, `calculo_tronadura.py`, `stability_analysis.py`, `blast_metrics.py`, `blast_correlation.py`, `config.py` — todos ≥ 95%
- **Cobertura intermedia**: `blast_advisor.py` (91%), `blast_model.py` (88%), `param_extractor.py` (94%)
- **Cobertura crítica baja**:
  - `core/excel_writer.py` (11%) — 281 de 316 líneas sin tests
  - `core/geom_utils.py` (29%) — 34 de 48 líneas sin tests
  - `core/mesh_handler.py` (49%) — 52 de 102 líneas sin tests
  - `core/ai_service.py` (59%) — 46 de 113 líneas sin tests (la parte de llamada al LLM no se testea, esperado)
  - `core/report_generator.py` (62%) — 152 de 401 líneas sin tests (Excel/Word writing)
  - `core/section_cutter.py` (79%) — razonable

---

## 3. Hallazgos de clean code

### 3.1 Duplicación de STATUS strings (severidad ALTA)

`core/blast_correlation.py:23-25` define constantes:

```python
STATUS_CUMPLE = "CUMPLE"
STATUS_FUERA = "FUERA DE TOLERANCIA"
STATUS_NO_CUMPLE = "NO CUMPLE"
```

Pero **NO se reusan** en:
- `core/param_extractor.py:740-742` — retorna literales `"CUMPLE"`, `"FUERA DE TOLERANCIA"`
- `core/excel_writer.py:49-55, 148, 160, 162, 163, 262, 269, 271, 272, 295, 326` — usa literales directamente
- `core/ai_service.py:116, 121, 126, 134-136` — usa `"CUMPLE" in r.get(...)` directamente

**Recomendación:** refactorizar para que `STATUS_CUMPLE` etc. sean la única fuente de verdad. Pero todos los archivos afectados están en lista NO-TOUCH. **No aplicable.**

### 3.2 Magic numbers en `core/blast_advisor.py` (severidad MEDIA)

`1.5` aparece 4 veces como magic number:
- Línea 64: `upper_bound = pf_optimal * 1.5`
- Línea 109: `upper = POWDER_FACTOR.pf_optimal_kgm3 * 1.5`
- Línea 111: mensaje al usuario
- Línea 449/473: defaults `max_pf_kgm3 = 1.50`

**Recomendación:** extraer a `ADVISOR.pf_upper_bound_factor = 1.5` en `core/config.py`. **No aplicable** (`blast_advisor.py` y `config.py` están en NO-TOUCH).

### 3.3 Tabla de explosivos duplicada (severidad MEDIA)

`core/explosive_properties.py:12-21` define:

```python
PIREX_ENERGY_MJ_KG = {'Pirex-930': 3.05, 'Pirex-920': 2.95, 'Pirex-950': 3.15, 'Pirex-970': 3.25}
PIREX_DENSITY_G_CM3 = {'Pirex-930': 1.20, 'Pirex-920': 1.15, 'Pirex-950': 1.23, 'Pirex-970': 1.25}
```

`core/config.py:118-122` define `ExplosiveEnergy` con los mismos valores:

```python
anfo_energy: float = 3.72
emulsion_energy: float = 2.78
heavy_anfo_energy: float = 3.40
bulk_emulsion_energy: float = 3.05
```

**Recomendación:** consolidar. `core/explosive_properties.py` debería importar los valores de `ExplosiveEnergy` o de un catálogo único. **No aplicable** (`config.py` está en NO-TOUCH).

### 3.4 Cohesión: `core/param_extractor.py` (1185 líneas, severidad ALTA)

Es el archivo más grande del repo. Tiene múltiples responsabilidades:
- `ramer_douglas_peucker` (RDP simplification)
- Detección de bancos, bermas, rampas
- Hungarian matching
- Compliance tripartita (CUMPLE/FUERA/NO_CUMPLE)
- Generación de `ReconciledProfile`

**Recomendación:** split en 3-4 archivos (`core/rdp.py`, `core/bench_detection.py`, `core/profile_matching.py`, `core/compliance.py`). **No aplicable** (NO-TOUCH).

### 3.5 Acoplamiento UI → core (severidad MEDIA)

`ui/` importa directamente de submódulos `core/`:

```
$ grep -rn "^from core\.[a-z_]\+ import" ui/ | grep -v __pycache__ | wc -l
24
$ grep -rn "^from core import" ui/ | grep -v __pycache__ | wc -l
4
```

**24 imports a submódulos vs 4 a la API pública (`core/__init__.py`).** El brief original del proyecto (`AGENTS.md`) documenta esto como convención intencional ("must import from the submodule directly: `azimuth_to_direction`, `compute_local_azimuth`, etc."). Es por diseño, no un anti-pattern. **Mantener como está.**

---

## 4. Hallazgos de clean architecture

### 4.1 Capas (severidad BAJA — sin acción)

El repo tiene capas claras:

```
web/   → React frontend
api/   → FastAPI
ui/    → Streamlit (legacy, off-limits per CONTRIBUTING.md)
core/  → Domain (independiente de UI/API)
tests/ → pytest suite
```

**Inversión de dependencias** verificada con `grep`:
- `core/` no importa nada de `ui/` o `api/` ✓
- `core/` no importa nada de `web/` ✓
- `ui/` importa de `core/` ✓ (esperado)
- `api/` importa de `core/` ✓ (esperado)
- `tests/` importa de `core/`, `ui/`, `api/` ✓

**No hay violaciones de capas.** Clean architecture mantenida.

### 4.2 Acoplamiento (severidad BAJA)

- `ui/` consume `core/` con imports directos (24 vs 4). **Es por diseño del proyecto** (ver AGENTS.md).
- `tests/` consume `core/` con imports absolutos — bien.
- `core/` es completamente independiente — bien.

### 4.3 Archivos candidatos a split (severidad MEDIA — no aplicable por NO-TOUCH)

| Archivo | Líneas | Responsabilidades | Split propuesto |
|---|---|---|---|
| `core/param_extractor.py` | 1185 | RDP, detección, matching, compliance | `rdp.py`, `bench_detection.py`, `profile_matching.py`, `compliance.py` |
| `core/report_generator.py` | 401 | Excel + Word + PNG zip | `excel_report.py`, `word_report.py`, `image_report.py` |
| `core/excel_writer.py` | 316 | Formato Excel | Sin split obvio (single-purpose) |
| `ui/modulo_tronadura.py` | 969 | Visualización 3D tronadura | NO-TOUCH (es legacy UI) |

---

## 5. Resumen final

### Lo aplicado

✅ 8 archivos huérfanos eliminados de la raíz (`-342 líneas`).

### No aplicado (y por qué)

| Hallazgo | Severidad | Razón |
|---|---|---|
| STATUS strings duplicados | ALTA | `param_extractor.py`, `excel_writer.py`, `ai_service.py` están en lista NO-TOUCH |
| Magic numbers en `blast_advisor.py` | MEDIA | `blast_advisor.py` y `config.py` están en NO-TOUCH |
| Tabla de explosivos duplicada | MEDIA | `config.py` está en NO-TOUCH |
| `param_extractor.py` muy grande (1185 ldc) | ALTA | NO-TOUCH |
| Cobertura < 50% en `excel_writer.py`, `geom_utils.py` | MEDIA | Ambos NO-TOUCH |

### Recomendación al usuario

Para limpiar más a fondo el repo (sin violar `CONTRIBUTING.md`):
1. **Coordinar con el mantenedor** del proyecto antes de hacer PRs que toquen `core/`, `ui/`, `app.py` — el repo tiene reglas explícitas que prohíben cambios en esas áreas.
2. **Agregar tests** para `excel_writer.py`, `geom_utils.py`, `mesh_handler.py` cuando se abra la restricción.
3. **Refactorizar duplicaciones** de STATUS strings como primer paso de un PR mayor coordinado con el mantenedor.

---

## 6. Conteo final

```
Working tree limpio (después de git rm):
  Archivos eliminados: 8 (raíz)
  Working tree additions: 2 sin commitear (docs/, imgs/)
  Coverage global: 76%
  Coverage core/: 76% (2837 statements)
  Tests pasando: 370/370
```

**No se commiteó nada** — el usuario revisará y commiteará manualmente con su mensaje.