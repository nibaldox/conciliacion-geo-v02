# Change: reconciled-profile-v2-default

> **Status**: draft → proposal
> **Slice**: A + E (from the exploration; other options B/C/D/F explicitly deferred)
> **Risk class**: additive, low — no removals, no signature changes to legacy callers

## Why

El dominio del perfil conciliado (`core/`) expone dos builders con un split
deliberado que mantiene la paridad Streamlit↔API documentada en
`docs/UI_PARITY_AUDIT.md` Causa 2:

- `build_reconciled_profile_v2(...)` — devuelve un `ReconciledProfile` rico
  con `ReconciledPoint` (crest / berm_top / face / toe / ramp), bermas
  explícitas y muestreo opcional del perfil entre cresta y toe. Es el
  builder preferido.
- `build_reconciled_profile(...)` (legacy) — devuelve la tupla
  `(distances, elevations)` ordenada por distancia. Lo consumen cuatro
  callsites que **no podemos tocar**:
  `scripts/generate_demo_data.py:127`, `ui/step3_analysis.py:80`,
  `ui/tabs/export.py:415`, `api/routers/export.py:412`.

El problema es doble. Primero, `core/__init__.py` (líneas 10-12 y 20) sólo
re-exporta el builder legacy; los callsites de v2 deben importar
`from core.param_extractor import build_reconciled_profile_v2`, ruta
explícitamente prohibida por la guía legacy-stable. El nuevo módulo
`core/profile_extract.py` (líneas 47-88) define `ReconciledPoint` y
`ReconciledProfile` pero no expone serialización: el reporte Word
(`core/report_generator.py:87-118`), la integración API
(`api/routers/process.py:451,461,583`) y la UI React 19
(`web/src/components/results/ProfileView`) re-implementan a mano la
extracción de n_benches, n_ramps, n_wedge_risks, height_range, etc.
Segundo, la advertencia de deprecación actual
(`core/profile_compliance.py:97-104`) dice "preserved for one release
cycle" pero no fija horizonte concreto ni identifica `build_reconciled_profile_v2`
como sucesor canónico, lo cual frena la migración interna.

El resultado: el consumidor del reporte (mantenedor Streamlit) y el módulo
Word repiten lógica de serialización; los consumidores web tienen que
reconstruir el `ReconciledProfile` desde cero para graficar. Aditivo
puro: ningún callsite legacy cambia, la tupla legacy sigue
byte-for-byte idéntica, y se gana un sucesor canónico accesible desde
`from core import build_reconciled_profile_v2` con horizonte de
deprecación explícito.

## What changes

- `from core import build_reconciled_profile_v2` funciona: `core/__init__.py`
  añade la importación y la entrada correspondiente en `__all__`.
- `from core import build_reconciled_profile` sigue funcionando **idéntico**;
  el docstring de `core/profile_compliance.py:56-96` se actualiza para
  declarar el horizonte "scheduled for removal in 2 release cycles;
  use `build_reconciled_profile_v2` instead", y el texto del
  `warnings.warn(...)` (líneas 97-104) menciona el mismo horizonte para
  que los warnings que ven los contribuidores sean accionables.
- `ReconciledProfile` gana tres métodos públicos:
  - `summary(self, *, benches: list[BenchParams] | None = None) -> dict`
    con shape flat documentada (ver Acceptance Criteria).
  - `to_dataframe(self, *, benches: list[BenchParams] | None = None) -> pd.DataFrame`
    con una fila por `ReconciledPoint` y columnas en inglés.
  - `to_dict(self) -> dict` round-trip JSON-able (numpy → list,
    `ReconciledPoint` → dict).
- `ReconciledProfile` gana un campo opcional `benches: list[BenchParams] | None = None`
  (dataclass, default al final de la lista de campos para mantener
  compatibilidad con constructores posicionales existentes en
  `core.ai_v2.builder.py` y tests). Es opcional: si está presente,
  alimenta `summary()` y `to_dataframe()` con `overhang_m`,
  `wedge_risk`, `toppling_risk`, `n_detection_methods_agreeing`,
  `is_ramp`, `face_angle`; si está ausente, esos campos del summary se
  omiten y `to_dataframe()` no incluye las columnas de hazard.

## Capabilities

> Esta sección es el CONTRATO entre la propuesta y la fase de specs.
> El agente `sdd-spec` la lee para saber exactamente qué archivos de
> spec crear o actualizar. `openspec/specs/` está vacío al día de hoy
> (verificado), así que toda capacidad introducida es **nueva**.

### New Capabilities

- `reconciled-profile-serialization`: superficie de serialización del
  perfil conciliado v2. Cubre (1) la re-exportación canónica de
  `build_reconciled_profile_v2` desde `core/__init__.py`, (2) el
  horizonte de deprecación explícito de dos ciclos para
  `build_reconciled_profile`, y (3) los tres métodos
  `summary() / to_dataframe() / to_dict()` de `ReconciledProfile`,
  incluyendo su contrato con el campo opcional `benches`.

### Modified Capabilities

- `None` — no hay capabilities previas en `openspec/specs/`. El cambio
  en `core/__init__.py` no modifica el comportamiento de la API
  legacy ya documentada; sólo añade un símbolo y endurece un mensaje
  de deprecación. `sdd-spec` lo trata como parte de la capability
  nueva arriba, no como delta de algo preexistente.

## Files affected

| Path | Δ | One-liner |
|---|---|---|
| `core/__init__.py` | modify (additive) | Importar `build_reconciled_profile_v2` desde `core.param_extractor` y añadirlo a `__all__`. No remover nada. |
| `core/profile_extract.py` | modify (additive) | Añadir campo opcional `benches: list[BenchParams] \| None = None` a `ReconciledProfile` y los tres métodos `summary` / `to_dataframe` / `to_dict`. Respetar convenciones de `@dataclass` ya presentes (líneas 47-88). |
| `core/profile_compliance.py` | modify (additive) | Endurecer docstring y mensaje de `warnings.warn(...)` en `build_reconciled_profile` con el horizonte "2 release cycles". El comportamiento del warning es el mismo (`stacklevel=2`, `DeprecationWarning`); sólo cambia el texto. |
| `tests/test_reconciled_profile_serialization.py` | new | ~6-10 tests cubriendo: import canónico `from core import build_reconciled_profile_v2`; shape de `summary()` con/sin benches; round-trip `to_dataframe()` con `pd.read_csv`/`to_csv`; round-trip JSON de `to_dict()`; byte-for-byte identity del legacy tuple; emisión del warning endurecido. |
| `openspec/specs/reconciled-profile-serialization/spec.md` | new (downstream) | Creado por `sdd-spec`, no por `sdd-propose`. Mencionado aquí como punto de creación posterior. |

## Out of scope (explicit)

- `web/**` — UI React no se toca en este slice; queda como consumer
  futuro de los nuevos métodos.
- `api/**` — routers FastAPI no se modifican; ya importan
  `build_reconciled_profile_v2` desde el submódulo.
- `app.py`, `ui/**`, `cli.py` — off-limits per `AGENTS.md`.
- No se remueve `build_reconciled_profile` legacy. No se cambia su
  firma. No se cambia su comportamiento de retorno. La tupla legacy
  sigue byte-for-byte idéntica.
- No se introduce una nueva hoja Excel ("Resumen Perfil v2") ni se
  modifican `excel_writer` / `report_generator`. Esos consumirían los
  métodos nuevos en un slice posterior.
- No se toca `core/param_extractor.py` — sigue siendo el compat shim
  que re-exporta ambos builders (`__all__` línea 64).
- No se cambia `openspec/specs/` en esta fase (lo hace `sdd-spec`).

## Approach (aditivo, low-risk)

Orden de ediciones para `sdd-apply`:

1. **`core/__init__.py`** — añadir `build_reconciled_profile_v2` al
   bloque `from core.param_extractor import (...)` y a la lista
   `__all__`, respetando orden alfabético.
2. **`core/profile_compliance.py`** — actualizar docstring de
   `build_reconciled_profile` (líneas 56-96) y mensaje de
   `warnings.warn(...)` (líneas 99-101) con el horizonte
   "scheduled for removal in 2 release cycles". Sin cambio de
   `stacklevel` (ya es 2), sin cambio de categoría de warning.
3. **`core/profile_extract.py`** — extender `ReconciledProfile`:
   - Campo `benches: list[BenchParams] | None = None` al final de
     la dataclass (default para no romper instanciación posicional
     en `core.ai_v2.builder.py` y `tests/`).
   - Método `summary(...)` que computa los contadores a partir de
     `self.points` (siempre) y de `self.benches` (cuando provisto).
   - Método `to_dataframe(...)` que itera `self.points`, deriva
     `is_ramp` del `segment_type == "ramp"`, y si `benches` está
     presente enriquece con `overhang_m`/`wedge_risk`/`toppling_risk`
     por match en `bench_number`.
   - Método `to_dict(...)` que convierte numpy arrays a listas y
     `ReconciledPoint` a `dict`; metadata en sub-dict.
4. **`tests/test_reconciled_profile_serialization.py`** — nuevo
   archivo, sigue la convención `test_<module>.py` del repo.
   Tests prioritarios:
   - `test_build_reconciled_profile_v2_importable_from_core_package`
   - `test_legacy_tuple_unchanged` (assert allclose sobre fixtures
     existentes en `tests/test_process_reconciled_alignment.py`)
   - `test_summary_shape_with_benches`
   - `test_summary_shape_without_benches` (campos derivados de benches
     ausentes o en None)
   - `test_to_dataframe_columns_english_and_roundtrip_csv`
   - `test_to_dict_roundtrip_json`
   - `test_deprecation_warning_message_mentions_two_cycles`
5. **NO se modifican** tests existentes. Si el round-trip CSV/JSON
   necesita fixtures, se importan los builders y se construyen en el
   propio test (los `BenchParams` tienen defaults razonables).

## Acceptance criteria

Comprobaciones concretas que `sdd-verify` ejecutará:

- [ ] `from core import build_reconciled_profile_v2` ejecuta sin
      `ImportError` y el símbolo aparece en `core.__all__`.
- [ ] `from core import build_reconciled_profile` sigue ejecutando; la
      tupla retornada es byte-for-byte idéntica a la producida por la
      versión actual para los mismos `benches` (regression: usar
      fixtures de `tests/test_process_reconciled_alignment.py`).
- [ ] `warnings.warn(...)` en `build_reconciled_profile(return_v2=False)`
      emite `DeprecationWarning` con `stacklevel=2` y el mensaje
      contiene la frase "2 release cycles" (o equivalente
      inequívoco).
- [ ] `ReconciledProfile(...).summary()` retorna dict con keys:
      `n_benches, n_ramps, n_overhangs, n_wedge_risks,
      n_toppling_risks, n_consensus_benches, height_range_m,
      total_berm_width_m, avg_face_angle_deg, max_overhang_m,
      source`. Las keys dependientes de `benches` son `None` o
      ausentes cuando el campo `benches` es `None`.
- [ ] `ReconciledProfile(...).to_dataframe()` retorna `pd.DataFrame`
      con columnas exactas: `bench_number`, `segment_type`,
      `distance_m`, `elevation_m`, `is_ramp`, `source`. Si
      `self.benches` está presente, añade `overhang_m`,
      `wedge_risk`, `toppling_risk`. Round-trip:
      `pd.read_csv(io.StringIO(df.to_csv(index=False)))` produce el
      mismo `pd.testing.assert_frame_equal`.
- [ ] `ReconciledProfile(...).to_dict()` retorna dict JSON-serializable
      (`json.dumps(d)` no lanza); round-trip
      `json.loads(json.dumps(d))` preserva `distances` (como lista),
      `elevations` (como lista), `points` (lista de dicts) y los
      campos metadata.
- [ ] Todos los tests existentes en `tests/test_param_extractor.py`,
      `tests/test_profile_compliance.py` y
      `tests/test_reconciled_berm_top_descent.py` siguen pasando
      sin modificación.
- [ ] `pytest tests/ -v --tb=short` pasa completo (suite existente
      ≈772 tests + nuevos 6-10).
- [ ] `python test_pipeline.py` (smoke E2E) sigue pasando.

## Risks

| Riesgo | Likelihood | Mitigation |
|---|---|---|
| Cambio en `__all__` rompe un importador que usa `from core import *` | muy baja | `__all__` es aditivo; los importadores existentes siguen resolviendo sus símbolos. Verificar con `pytest tests/`. |
| Añadir `benches` a `ReconciledProfile` rompe un constructor posicional en `core.ai_v2.builder` u otros | baja | Campo va **al final** con `default=None`; constructores posicionales existentes (`ReconciledProfile(distances, elevations, points)`) siguen funcionando. |
| `to_dataframe()` requiere pandas en runtime | baja | `core/` ya no depende de pandas para nada del pipeline principal; verificar con `pyproject.toml` que pandas siga como dep transitiva (lo es vía openpyxl y el reporte Excel). Si no, documentar `to_dataframe` como import lazy dentro del método. |
| Warning endurecido ahoga logs en CI | baja | El warning ya se emite hoy; sólo cambia el texto. Sin cambio de categoría ni de `stacklevel`. |
| Slice A+E agranda demasiado el PR | baja | ~3 archivos de `core/` tocados (dos additive-modify, uno additive-extend), 1 archivo nuevo de tests, sin tocar UI/API. Estimación: ~150-200 LOC de código nuevo + ~200 LOC de tests. |
| El "2 release cycles" sin changelog versionado | media | Documentar el horizonte en el docstring + warning message; en slice posterior (archive) se confirmará con el versionado real del proyecto. |

## Rollback plan

Reversible en un commit:

1. Revertir cambios en `core/__init__.py` (quitar la línea de import y
   la entrada de `__all__`).
2. Revertir docstring + warning en `core/profile_compliance.py`.
3. Revertir `core/profile_extract.py` al commit previo (la dataclass
   vuelve a su shape original de tres campos; los tres métodos
   desaparecen).
4. Borrar `tests/test_reconciled_profile_serialization.py`.

Sin migraciones de datos; sin cambios de schema; sin impacto en
fixtures. Las llamadas legacy (`build_reconciled_profile`) siguen
funcionando porque su comportamiento no cambia en este slice.

## Links

- Exploración: observación Engram
  `sdd/conciliacion-geo-v02/explore-reconciled-profile` (id 43;
  pipeline mapeado, 6 opciones A-F, usuario eligió A+E).
- `openspec/sdd-init/conciliacion-geo-v02/init-report.md` — contexto
  del proyecto y off-limits.
- `openspec/sdd-init/conciliacion-geo-v02/testing-capabilities.md` —
  layout pytest (≈772 tests, command `pytest tests/ -v --tb=short`).
- `openspec/config.yaml` — reglas de propuesta (rollback obligatorio
  para cambios en `core/`, intact API legacy).
- `AGENTS.md` raíz — convenciones de import, off-limits dirs, detección
  defaults.
- `docs/UI_PARITY_AUDIT.md` Causa 2 — justificación histórica del
  split legacy/v2. **No modificar.**