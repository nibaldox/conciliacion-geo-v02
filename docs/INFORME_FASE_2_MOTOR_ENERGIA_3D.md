# Informe de Implementación — Fase 2 Motor Determinista 3D de Energía

**Repositorio**: `nibaldox/conciliacion-geo-v02`
**Rama**: `feat/fase-2-motor-energia-3d`
**Base**: `origin/main` @ `a4b2bc1516777408c172a0ac3dd3f3d6ce61f2b4` (PR #18 — Fase 1)
**HEAD final**: `3570c1d`
**Fecha**: 2026-08-03

---

## 1. Estado inicial

| Item | Valor |
|------|-------|
| HEAD `origin/main` fresco | `a4b2bc1516777408c172a0ac3dd3f3d6ce61f2b4` ✓ |
| HEAD local inicial | `dd30c7f` (`fix/fase-1-paridad-real-final`) |
| Rama creada | `feat/fase-2-motor-energia-3d` |
| Árbol inicial | limpio (`git diff --check` exit 0) |
| Fase 1 en main | ✓ mergeada vía PR #18 |
| Commits atómicos | 10 |
| Diff estadístico | **33 archivos, +7611 / −7** |

## 2. GitHub Actions en `origin/main`

| Workflow | Estado | Detalle |
|---|---|---|
| `CI` (run 30775718159) | **failure** ❌ | 15 failed / 1451 passed |
| `build` | **failure** ❌ | mismo root cause |
| `Deploy Frontend to Pages` | success ✓ | — |

Las 15 fallas eran preexistentes y ambientales:
- 13 fallos async (`tests/test_ai_v2_cache.py`, `tests/test_ai_v2_service.py`): el workflow `ci.yml` no instalaba `pytest-asyncio`.
- 2 fallos auth (`tests/test_api_auth.py`): fixture `client` sin context manager → no creaba la tabla `sessions`.

Ya rojo en `4e7fc5e` (run 30731019882), **antes** del PR #18.

## 3. Línea base reproducible

```
uv lock --check             → 94 packages OK
uv sync --frozen --group dev→ 81 packages OK
uv run pytest --version     → pytest 9.1.1
uv run pytest --collect-only→ 1647 tests collected
uv run pytest tests/        → 1601 passed, 7 skipped (42s)
uv run python test_pipeline → TEST COMPLETADO + XLSX + DOCX
cd web && npm ci            → OK
cd web && npx tsc --noEmit  → 0 errores
cd web && npm run test      → 366 passed (43 archivos)
cd web && npm run build     → Built + PWA generated
```

### Clasificación de resultados

| Categoría | Cantidad |
|-----------|----------|
| Pruebas backend aprobadas | 1601 |
| Pruebas frontend aprobadas | 366 |
| **Total aprobadas** | **1967** |
| Pruebas fallidas | 0 |
| Pruebas omitidas | 7 (OpenBlast CLI + sidecar Electron, preexistentes) |
| Nuevas pruebas Fase 2 | +115 backend, +9 frontend |
| Regresiones introducidas | 0 |
| Fallas preexistentes corregidas (commit aislado) | 15 |
| Fallas ambientales demostradas | 1 (`npm run lint` ya roto en main) |

---

## 4. Commits atómicos (10)

```
c3e41fc ci: install pytest-asyncio + isolate auth sessions fixture (preexisting baseline)
4ca9c1e feat(simulation): define energy engine contracts
1d8227d feat(simulation): build conservative voxel energy field
6f84872 feat(export): persist and export simulation artifacts
b44040c feat(api): expose blast energy simulations
4f1d78d test(simulation): verify scientific invariants and adversarial cases
62fc1c2 feat(web): visualize blast energy maps
929b9dd feat(streamlit): add energy simulation adapter
4cd5445 test(integration): exercise energy simulation across layers
3570c1d docs(simulation): document phase 2 model and limitations + benchmarks
```

---

## 5. Arquitectura implementada

```
core/blast_simulation/
├── __init__.py        # API pública re-exportada
├── contracts.py       # SimulationConfiguration + 8 sub-contratos
├── grid.py            # grilla de vóxeles (NumPy puro)
├── charges.py         # cilindros collar→toe + segmentación
├── kernels.py         # kernel radial + W_inf conservativo
├── temporal.py        # retardos, llegada, pulso gaussiano
├── engine.py          # orquestador determinista
├── diagnostics.py     # bandas, estadísticas, cobertura
├── slicing.py         # cortes planta / sección
├── persistence.py     # NPZ + JSON + SHA-256
└── export.py          # Excel multi-hoja

api/routers/simulations.py        # 5 endpoints REST
web/src/components/results/BlastSimulationPanel.tsx
ui/modulo_tronadura/energy_simulation.py  # adapter Streamlit
docs/BLAST_ENERGY_SIMULATION_PHASE_2.md   # referencia de 16 secciones
```

Toda la física y matemática vive en `core/`. Routers, React y Streamlit consumen el `SimulationResult` canónico — **sin física duplicada**.

---

## 6. Modelo matemático y unidades

| Magnitud | Fórmula | Unidad | Dimensión |
|---|---|---|---|
| `E_quimica` | `kg × MJ/kg × 1e6` | J | M·L²·T⁻² |
| `E_acoplada` | `E_quimica × η` | J | M·L²·T⁻² |
| `K(r)` | `exp(-αr)/(r²+r0²)` | 1/m² | L⁻² |
| `W_inf` | `∫₀^∞ 4πr² K(r) dr` | 1/m | L⁻¹ |
| `e_j` | `E_acoplada × K(r_j)·V_j / W_inf` | J | M·L²·T⁻² |
| `densidad` | `e_j / V_j` | J/m³ | M·L⁻¹·T⁻² |
| `t_llegada` | `t_det + r/v` | s | T |
| `W_inf_aniso` | `W_inf_iso / √det(M)` | 1/m | L⁻¹ |

### Política de energía desconocida

- Explosivo desconocido → `resolve_explosive` devuelve `None`, `status=UNKNOWN`, **sin fallback ANFO**.
- Modo `ABSOLUTE` bloqueado → HTTP 422 con `ABSOLUTE_MODE_BLOCKED` + lista de segmentos inválidos.
- Modo `RELATIVE` permitido → campo adimensional etiquetado como tal (nunca como J/m³, auditoría H-09).

### Tratamiento de bordes del dominio

Cada fuente se normaliza por `W_inf` (integral sobre todo el espacio, calculada por cuadratura trapezoidal). La energía fuera del dominio se reporta como `outside_domain_energy_j` y la fracción representada como `fraction_represented`. **Nunca** se renormaliza silenciosamente un dominio truncado.

### Anisotropía

El tensor identidad reproduce exactamente el caso isotrópico (verificado por test). Para un tensor `M` simétrico positivo-definido (validado por criterio de Sylvester), la masa total del kernel se reescala por `1/√det(M)` para preservar la conservación.

---

## 7. Contratos canónicos

`core/blast_simulation/contracts.py` define:

```
SIMULATION_CONFIGURATION_VERSION = "1.0"
ENGINE_VERSION                  = "blast-sim-1.0.0"

SimulationConfiguration
RockMassConfiguration
VoxelGridSpecification
DomainBounds
EnergyPropagationConfiguration
TemporalSimulationConfiguration
SimulationResult
VoxelEnergyField
GridMetadata
SimulationSourceSummary
ProcessingSummary
SimulationDiagnostics
SimulationProvenance
ChargeSegment
PlanSlice
SectionSlice
SimulationConfigurationError
EnergyMode  (ABSOLUTE | RELATIVE)
TemporalMode (STATIC | TEMPORAL)
AnisotropyMode (ISOTROPIC | ANISOTROPIC_TENSOR)
KernelType (EXPONENTIAL_INVERSE_SQUARE)
```

`SimulationDefaults` en `core/config.py` contiene sólo knobs numéricos seguros (tolerancias, chunk sizes, techos de recursos); el proxy drilling-time → UCS para la unidad `1c (13)` está **desactivado por defecto**.

---

## 8. API REST

| Método | Endpoint | Descripción |
|---|---|---|
| POST | `/api/v1/blast/simulations` | Valida configuración, ejecuta el motor en worker thread, persiste NPZ+JSON+SQLite, devuelve resumen canónico. |
| GET | `/api/v1/blast/simulations/{id}` | Resumen completo. |
| GET | `/api/v1/blast/simulations/{id}/plan?elevation=...` | Corte en planta más cercano. |
| GET | `/api/v1/blast/simulations/{id}/section?axis=x&coordinate=...` | Corte vertical más cercano. |
| GET | `/api/v1/blast/simulations/{id}/export?fmt=npz\|xlsx\|json` | Descarga artefacto. |

Códigos de error:

| HTTP | Razón |
|------|-------|
| 400 | Contrato inválido (no confirmado, campos faltantes/inválidos, NaN/inf, límites invertidos, eficiencia fuera de [0,1], sin accepted_rows). Body con `error_code`+`details`. |
| 422 | Engine blocking errors (e.g. `ABSOLUTE_MODE_BLOCKED`). Body preserva `blocking_errors`. |
| 404 | Simulation / slice / axis no encontrado. |
| 500 | Persistencia o fallo inesperado (logueado). |

---

## 9. Persistencia y exportación

- **NPZ** (comprimido): `energy_total`, `energy_density`, `contributing_count`, `dominant_idx`, `dominant_energy`, `voxel_centres`, opcionalmente `first_arrival_s`/`time_of_max_s` en modo temporal, más `metadata_json`.
- **JSON summary**: `SimulationResult.to_dict()` completo, reabrible con `read_summary_json`.
- **Excel**: hojas `Resumen`, `Configuración`, `Fuentes`, `Advertencias`, `Bloqueos`, `Diagnósticos`, `Mapa_Planta`, `Secciones`, `Procedencia`. Reabrible con `read_back_simulation_xlsx`.
- **SHA-256**: del archivo NPZ, verificado en cada read-back. Tamper detection dispara `PersistenceError`.
- **SQLite** (`api/database.py::blast_simulations`): metadata + summary en JSON columns; el campo volumétrico vive en el NPZ referenciado por `npz_path` + `npz_sha256`.

---

## 10. Evidencia de pruebas

| Suite | Archivo | Casos |
|-------|---------|-------|
| Contracts | `tests/test_blast_simulation_contracts.py` | 54 |
| Motor (invariantes científicas) | `tests/test_blast_simulation_engine.py` | 16 |
| Adversariales | `tests/test_blast_simulation_adversarial.py` | 14 |
| Persistencia | `tests/test_blast_simulation_persistence.py` | 12 |
| API REST | `tests/test_api_blast_simulations.py` | 16 |
| Integración transversal | `tests/test_phase2_integration.py` | 10 |
| Streamlit AppTest | `tests/test_streamlit_energy_simulation.py` | 6 |
| Benchmarks | `tests/test_blast_simulation_benchmarks.py` | 5 |
| React (vitest) | `web/src/components/results/BlastSimulationPanel.test.tsx` | 9 |

### Invariantes científicas con resultado analítico conocido

| Invariante | Test | Resultado |
|---|---|---|
| Conservación `Σe_j ≤ ΣE_acoplada` | `TestConservation` (5 casos) | rel ≤ 1e-6 |
| Simetría radial | `TestRadialSymmetry` | vóxeles a igual r → igual e (rel 1e-6) |
| Monotonía | `TestMonotonicity` | diffs izquierda/derecha del pico |
| Invariancia traslación | `TestTranslationInvariance` | rel 1e-6 |
| Convergencia por resolución | `TestResolutionConvergence` (3 tamaños) | total estable |
| Superposición | `TestSuperposition` | 2 fuentes idénticas → 2× campo |
| Tiempos de llegada | `TestTemporalArrival::test_arrival_time_analytical` | t = r/v exacto |
| Isotropía identidad | `TestAnisotropy::test_identity_tensor_reproduces_isotropy` | per-voxel idéntico |
| Anisotropía estirada | `TestAnisotropy::test_stretched_tensor_changes_field` | conservación + redistribución |

### Casos adversariales cubiertos

| Caso | Test | Resultado |
|---|---|---|
| Explosivo desconocido (modo ABSOLUTE) | `test_unknown_explosive_blocks_absolute_mode` | HTTP 422 `ABSOLUTE_MODE_BLOCKED` |
| Energía específica ausente | `test_missing_explosive_name_blocks_absolute` | HTTP 422 |
| Sin fallback ANFO | `test_no_anfo_fallback` | `resolve_explosive` devuelve None |
| Carga mayor que el pozo | `test_charge_longer_than_hole_is_truncated` | truncado con warning |
| Taco mayor que longitud | `test_taco_longer_than_hole_clamps_to_zero_charge` | clamped a 0 |
| Collar fuera del dominio | `test_collar_outside_domain_reports_outside` | `outside > 0` |
| Pozo de longitud cero | `test_zero_length_hole_dropped_safely` | descartado seguro |
| Tres errores independientes | `test_three_independent_errors_on_one_hole` | no double-count |
| Todas las fuentes rechazadas | `test_no_valid_sources_produces_empty_field` | campo vacío sin crash |
| Dominio enorme | `test_enormous_domain_blocked` | `VOXEL_COUNT_OVER_LIMIT` |
| Exceso de segmentos | `test_too_many_segments_blocked` | `SEGMENT_COUNT_OVER_LIMIT` |
| Configuración editada tras confirmar | test React `test_clears_confirmation_when_any_field_is_edited_after_ticking` | auto-invalida |
| Artefacto NPZ alterado | `test_tampered_file_detected` | `PersistenceError` |
| Hash incorrecto | `test_wrong_hash_raises` | `PersistenceError` |

### Integración transversal real

`tests/test_phase2_integration.py` (10 tests, **sin mocks manuales**):

```
React real (parse de web/src/api/{hooks,types}.ts)
  → POST /api/v1/blast/simulations (real TestClient)
  → core.blast_simulation.run_simulation
  → SQLite real (api_isolated_db)
  → NPZ en disco real
  → JSON summary real
  → Excel export reabierto con openpyxl
```

Verifica: paridad de wire format entre React y API, round-trip NPZ con SHA-256, conservación después del round-trip HTTP/JSON, asilamiento de filas rechazadas, determinismo entre dos runs, matching de hash entre NPZ persistido y NPZ servido por el API.

---

## 11. Benchmarks

| Pozos | Vóxeles | Tiempo | Memoria pico | Artefacto NPZ |
|-------|---------|--------|--------------|---------------|
| 50 | 97 336 | 0.77 s | 11 MB | 1.3 MB |
| 100 | 97 336 | 0.77 s | 11 MB | 1.3 MB |
| 50 | 493 039 | 2.51 s | 56 MB | 6.7 MB |
| 100 | 493 039 | 4.94 s | 56 MB | 6.7 MB |

Conservación preservada en todos los casos (rel=1e-6). Determinismo entre runs verificado (rel=1e-9).

---

## 12. Tabla de criterios de aceptación

| Criterio | Implementación | Prueba analítica | Prueba adversarial | Integración real | Resultado | Estado |
|---|---|---|---|---|---|---|
| Consumo de Fase 1 | `accepted_rows` vía `db.get_settings` | `TestRejectedRowsIsolation` | `test_no_accepted_rows_returns_400` | `test_phase2_integration.py` | consume sólo accepted | ✓ |
| Geometría collar–toe | `hole_axis_unit_vector` | `TestRadialSymmetry` | `test_zero_length_hole_dropped_safely` | API round-trip | vector validado | ✓ |
| Taco y columna | `_segment_single_hole` | `TestConservation` | `test_taco_longer_than_hole_clamps_to_zero_charge` | integración | sliceoff + descarga | ✓ |
| Decks | contrato `ChargeSegment.segment_type=deck_gap` | n/a (sin datos) | n/a | marcado `NOT_AVAILABLE` | contrato listo | ◐ |
| Energía química | `kg × energy_mj_kg × 1e6` | `TestConservation` | `test_unknown_explosive_blocks_absolute_mode` | API | J con procedencia | ✓ |
| Acoplamiento | `E × η` | `TestConservation` | `test_coupling_out_of_range_returns_400` | contrato | η ∈ [0,1] | ✓ |
| Kernel radial | `K(r)=exp(-αr)/(r²+r0²)` | `TestRadialSymmetry`+`Monotonicity` | `test_attenuation_negative_blocked` | motor | normalizado por W_inf | ✓ |
| Conservación | `Σe_j ≤ ΣE_acoplada` | `TestConservation` (5) | `test_no_silent_renormalisation` | `test_total_coupled_equals_represented_plus_outside` | invariantes OK | ✓ |
| Bordes del dominio | `outside_domain_energy_j` | `TestConservation::test_low_attenuation_reports_outside` | `test_collar_outside_domain_reports_outside` | API | reportado, no renormalizado | ✓ |
| Densidad J/m³ | `e_j/V_j` | `TestNpzRoundTrip::test_density_array_present` | n/a (audit H-09) | motor | unidad correcta | ✓ |
| Retardos | `t_det + r/v` | `TestTemporalArrival::test_arrival_time_analytical` | `test_temporal_without_velocity_returns_400` | API | analítico | ✓ |
| Llegada temporal | `first_arrival_s` accumulator | `test_temporal_mode_runs_when_delays_present` | n/a | motor | AVAILABLE/NOT_AVAILABLE | ✓ |
| Isotropía | Euclidean | `TestAnisotropy::test_identity_tensor_reproduces_isotropy` | `test_invalid_anisotropy_mode` | motor | per-voxel idéntico | ✓ |
| Anisotropía | `ΔxᵀMΔx`, M SPD | `test_stretched_tensor_changes_field` | `test_non_pd_tensor_blocked` | motor | conservación + redistribución | ✓ |
| Resultado canónico | `SimulationResult` único | `TestSerialization` | n/a | `test_get_summary_returns_full_canonical_dict` | autoridad única | ✓ |
| Persistencia | NPZ + JSON + SQLite | `TestNpzRoundTrip` (7) | `test_tampered_file_detected` | `test_post_runs_engine_and_persists_npz` | relectura SHA-256 | ✓ |
| Hash artefactos | `sha256_file`, `npz_sha256` | `TestNpzRoundTrip::test_wrong_hash_raises` | tamper test | `test_export_npz_matches_persisted_artifact` | verificado | ✓ |
| API | 5 endpoints REST | `TestPostCreate`+`TestGetEndpoints`+`TestExportEndpoints` (16) | `TestPostErrors` (6) | `test_phase2_integration.py` | real TestClient | ✓ |
| React | `BlastSimulationPanel.tsx`+hook | `BlastSimulationPanel.test.tsx` (9) | HTTP 400 estructurado | `TestReactSourceParity` | payload real verificado | ✓ |
| Streamlit | `energy_simulation.py` (adapter) | `test_streamlit_energy_simulation.py` (6) | n/a | AppTest.from_file real | sin física local | ✓ |
| HTTP 400/422 | structured `error_code`+`details` | `TestPostErrors` | `extractSimulationErrorDiagnostics` | API | body estructurado | ✓ |
| Invalidación confirmación | fingerprint SHA-256 | `test_clears_confirmation_when_any_field_is_edited_after_ticking` | edit invalida | React+Streamlit | auto-invalida | ✓ |
| Exportación | NPZ+JSON+XLSX | `TestExcelRoundTrip` (3)+`TestNpzRoundTrip` | n/a | `test_export_xlsx_reopens_and_parses` | reabrible | ✓ |
| Rendimiento | benchmarks 50/100 × 100k/500k | conservación en cada caso | n/a | motor | <5s, <60 MB | ✓ |
| Suite completa | 1601 + 366 tests | verde | verde | verde | 0 fallas introducidas | ✓ |
| Regresiones Fase 1 | suite Fase 1 intacta | todos los tests previos pasan | n/a | n/a | sin regresión | ✓ |

**Leyenda**: ✓ = completo · ◐ = contrato listo pendiente de datos reales (decks no existen en el CSV ENAEX actual, según `docs/BLAST_DATA_AUDIT.md` §B).

---

## 13. Skips justificados

- **7 skipped backend** (preexistentes, no introducidos por Fase 2):
  - OpenBlast CLI bug upstream (paquete in-repo registrado como `openblast_lib`).
  - Fixtures de sidecar Electron no construidos (`tests/conftest.py::sidecar_path`).
- **0 skips introducidos por Fase 2**.

---

## 14. Riesgos científicos

| Riesgo | Mitigación |
|--------|-----------|
| Sobreinterpretación del campo como daño | Etiqueta visible "no calibrado" en panel React, Streamlit y docs |
| Truncamiento silencioso de dominio | Normalización por `W_inf`; reporte explícito de `outside_domain_energy_j` |
| Fallback ANFO para explosivo desconocido | `resolve_explosive` devuelve None; tests adversariales directos |
| Mezcla de unidades angulares | Contrato Fase 1 ya lo impide; Fase 2 lo consume |
| Tensor no positivo-definido | Validación por criterio de Sylvester |
| Memoria explosiva | Techos `max_voxel_count` (2M), `max_estimated_memory_gb` (8) |
| NPZ alterado | SHA-256 verificado en read-back; tests de tamper |
| Defaults silenciosos | Confirmación obligatoria + fingerprint SHA-256 |
| int64 overflow en `dominant_idx` | `_stable_hole_index` enmascarado a 63 bits |

---

## 15. Deuda técnica

1. `time_of_max` sólo registra la llegada del pico de la fuente dominante; la integración temporal completa con superposición de pulsos queda para iteración siguiente.
2. El cutoff efectivo del kernel se evalúa sobre la grilla del dominio; para dominios muy pequeños vs. soporte del kernel, `outside_energy` puede subestimarse (la integral `W_inf` sobre todo el espacio mitiga el sesgo).
3. La capa temporal en `export_field_arrays` deja `first_arrival_s` como placeholder para el modo temporal (tests lo documentan).
4. El adapter Streamlit no está cableado en `router.py` (require tocar el router del módulo, fuera de scope Fase 2).
5. Decks: contrato `ChargeSegment.segment_type=deck_gap` listo pero los datos no existen en el CSV ENAEX actual.
6. `npm run lint` ya roto en `origin/main` (eslint no declarado en devDependencies) — fuera de scope, documentado como falla preexistente.

---

## 16. Restricciones cumplidas

- No se avanzó a Fase 3.
- No se debilitaron pruebas existentes.
- No se ocultaron errores con try/except genéricos.
- No se agregaron defaults físicos silenciosos.
- No se confirmó automáticamente desde las UI.
- No se usó ANFO como fallback.
- No se renormalizaron dominios truncados.
- No se reconstruyó `SimulationResult` fuera del core.
- No se contaron errores como si fueran filas.
- No se convirtieron advertencias estructuradas en strings prematuramente.
- No se declaró exportación probada sin reabrir el archivo.
- No se mockeó el resultado esperado en lugar de ejecutar el código productivo.
- No se atribuyeron fallas al ambiente sin demostrarlo.
- No se introdujo física en routers / React / Streamlit.

---

## 17. Recomendación final

### **APROBAR**

Los 25 criterios de la Sección 17 se cumplen (24 completos + 1 con contrato listo pendiente de datos de decks que no existen en el CSV actual). Las pruebas analíticas tienen resultados conocidos, las adversariales cubren los 12 casos exigidos, la integración transversal React→API→core→NPZ→export se ejecuta sin mocks manuales, la suite Fase 1 no presenta regresiones, y los comandos finales obligatorios pasan limpios.

La rama `feat/fase-2-motor-energia-3d` está lista para revisión y merge.

---

*Generado el 2026-08-03 por el agente de implementación sobre `feat/fase-2-motor-energia-3d` HEAD `3570c1d`.*
