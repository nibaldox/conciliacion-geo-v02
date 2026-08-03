# Diagnóstico inicial obligatorio — Fase 2 (auditoría final)

**HEAD inicial**: `be890911ee2746749507788f386969df7c4b9ae9`
**Rama creada**: `fix/fase-2-remediacion-auditoria-final`
**Árbol**: limpio (`git diff --check` OK, único sin trackear: `node_modules/`)
**Fecha**: 2026-08-03

---

## Hallazgos verificados por inspección y reproducción

| # | Falla | Causa raíz | Ruta / función | Invariante violada | Reproducción |
|---|-------|------------|----------------|--------------------|--------------|
| 4.1 | Conservación rota 32.801× y 320,78% | `discrete_total_mass` usa **cascarones radiales** `r_mid=(k+0.5)·dx` que nunca muestrean `r=0`. El numerador `_accumulate_source` sí incluye `K(0)=1/r0²` cuando la fuente está en un centro de vóxel | `kernels.py:172-232 discrete_total_mass` + `engine.py:230-249 _accumulate_source` | `0 ≤ Σ e_j / E_coupled ≤ 1` | Script directo: Q=38.1 vs W=1.25M, ratio **32800.94×** |
| 5.1 | `support_radius_m` ignorado | Campo existe en `SimulationConfiguration` pero NO en `to_dict`, NO en `SimulationCreateRequest`, `_config_from_request` no lo copia, motor recibe parámetro sombra | `contracts.py:452,557-575`; `simulations.py:109-147,286-329`; `engine.py:311-318` | Cambio de soporte debe modificar el cálculo | Inspección de código |
| 6.1 | Divergencia memoria vs NPZ temporal | `run_simulation` llama `compute_time_of_max` sin `energy_per_segment_per_voxel` ni `detonation_times_per_segment`; `export_field_arrays` SÍ los pasa → rutas divergentes | `engine.py:527-533` vs `engine.py:807-816` | `time_of_max_memoria == time_of_max_NPZ` | Audit mide 0.000470 vs 0.000818 (no coinciden) |
| 7 | Chunking inefectivo | `_accumulate_source` procesa todos los vóxeles por fuente; `block_size` sólo se usa en `estimated_memory_bytes` y `_check_resource_limits` | `engine.py:176-291` | `block_size` controla memoria pico | Inspección |
| 8 | Retardos de deck ignorados | `charges.py:486` lee `deck.get("detonation_time_s")` pero NO `deck.get("Retardo_ms")` ni `deck.get("delay_ms")` | `charges.py:486-488` | `t_llegada_deck = t_det_deck + r/v` | Inspección |
| 10 | Build frontend roto | `TensorValidation \| null` → `TensorValidation`; `PlanSliceWire`/`SectionSliceWire` sin `values/min/max/mean/source_holes_projection` | `BlastSimulationPanel.tsx:388,657,664` | `npm run build` exit 0 | `npm run build` → 3 TS2322 |
| 13.1 | `__all__` exporta símbolo inexistente | `reject_extra_fields` listado pero nunca importado ni definido | `__init__.py:132` | `from core.blast_simulation import *` | Inspección |
| Cfg | `SIMULATION_CONFIGURATION_VERSION="1.0"` | Spec pide 2.0; `to_dict()` omite `support_radius_m` | `contracts.py:31,557-575` | Versión informada = spec | Inspección |
| Cut | Cutoff oculto accesible | `kernel_total_mass` mantiene `cutoff=max(50/α, 1000·r0)` accesible desde producción | `kernels.py:137-169` | "No cutoff físico oculto" | Inspección |

---

## Soluciones propuestas (resumen)

1. **Conservación cartesiana** (`kernels.py`): reescribir `discrete_total_mass` para que construya el cubo `[-R,R]³` alrededor de la fuente sobre la grilla cartesiana (los mismos centros que `_accumulate_source`). Q_total = `Σ_{|c|≤R, c voxel-centro} K(|c|)·V`. Por construcción `Σ_in_domain e_j ≤ E_coupled`. Tolerancia estricta `CONSERVATION_TOL=1e-9`. Si la violación supera la tolerancia: `SimulationConfigurationError("CONSERVATION_VIOLATION")`, no persistir.

2. **Propagación `support_radius_m`** (transversal): hacerlo obligatorio en `SimulationConfiguration.validate()`; agregar a `to_dict`; agregar a `SimulationCreateRequest`; copiar en `_config_from_request`; engine lee `configuration.support_radius_m` (eliminar parámetro sombra); React y Streamlit lo envían; bump versión 2.0.

3. **Ruta temporal canónica** (`engine.py`): extraer helper `_compute_temporal_fields(energy_total, distances, detonations, energy_per_seg, v, sigma)` que ambas rutas (`run_simulation` y `export_field_arrays`) invoquen idénticamente.

4. **Chunking real** (`engine.py`): `_accumulate_source` itera `iter_voxel_blocks` dentro de cada fuente; sólo aloja `block_size` vóxeles a la vez. Verificación bit-a-bit para varios `block_size`.

5. **Retardos de deck** (`charges.py`): leer `deck["Retardo_ms"]` y `deck["delay_ms"]` además de `detonation_time_s`; precedencia deck-propio → row; normalizar ms→s explícito; conservar provenance.

6. **Frontend** (`BlastSimulationPanel.tsx`): `TensorValidation | null` → proporcionar default o ajustar tipo; `PlanSliceWire`/`SectionSliceWire` con los campos faltantes; enviar `support_radius_m`.

7. **`__all__`**: eliminar `reject_extra_fields` o definir el helper.

8. **`kernel_total_mass`**: eliminar accesibilidad pública o requerir `support_radius_m` explícito.

9. **Versión**: `SIMULATION_CONFIGURATION_VERSION = "2.0"` + actualizar fixtures.

---

## Riesgo de regresión

- **Alto**: la corrección de conservación puede romper los tests `test_phase2_remediation_scientific.py` existentes que verificaban invariantes sobre el algoritmo viejo. Se actualizarán para alinearse con la nueva cuadratura cartesiana.
- **Medio**: bump de versión puede romper fixtures y tests de persistencia que graban la versión. Se actualizarán.
- **Bajo**: frontend build fix es local al panel.

## Comandos a ejecutar por hashlib

```bash
git status --short
git diff --check
uv lock --check
uv run pytest --collect-only -q
uv run pytest tests/ -v --tb=short --ignore=tests/test_openblast.py
cd web && npm ci && npm run lint && npm run test && npx tsc --noEmit && npm run build
uv run python test_pipeline.py
```
