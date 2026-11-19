# Plan de optimización de procesos — N100 con 10 usuarios simultáneos

> **Para Hermes:** ejecutar tarea por tarea con `subagent-driven-development`. El coordinador no edita código del repo (ni de una línea): orquesta, corre los gates y verifica. Tareas básicas (scripts de medición, wiring de configuración) → `claude-haiku-5-5`; el resto → modelo de delegación configurado.

**Objetivo:** que el N100 (4 núcleos, 16 GB) atienda 10 personas procesando a la vez, con tiempos de segundos y sin rozar el límite de memoria, sin cambiar ningún resultado geotécnico.

**Arquitectura:** primero se ataca el cuello medido (el corte de secciones recorre la malla completa en cada sección), luego el costo de recargar mallas (reparseo del STL de 160 MB con pico de 2 GB) y por último la concurrencia (hilos sin tope, escrituras de estado por sección). El paso a varios procesos queda tras una compuerta: sólo si las fases 1–3 no alcanzan la meta.

**Stack:** Python 3.14, trimesh, numpy, FastAPI, SQLite (WAL). Rama `perf/process-optimization`, worktree `/home/xodla/archivos/12_WindSurf/46-conciliacion-geo-v02-rendimiento` (base `origin/main` 931adcb).

---

## 1. Línea base medida (15-nov-2026)

Datos: sesión real `TOPO_NOVIEMBRE_131126_relimit.stl` (1.674.108 vértices / 3.349.455 caras, 160 MB) + `f12b_v2.2.1.stl` + 50 secciones. Copia local (gitignored) en `data/perf-real/` de este worktree.

| Escenario | N100 (prod, contenedor aparte) | Ryzen 9 9900X |
|---|---|---|
| 1 usuario × 50 secciones | 6,1 s | 1,6 s |
| 3 usuarios simultáneos | 15,6 s | 4,8 s |
| 10 usuarios simultáneos | **48,8 s c/u** | 20,2 s |
| Carga de la topo (`load_mesh`) | 5,8 s, pico 2,0 GB | 2,6 s, pico 2,0 GB |
| 3 topos distintas cargando a la vez | OOM con tope 5 GB | pico 5,3 GB |
| 6 topos distintas | — | pico 10,1 GB, estable 3,5 GB |
| 10 topos distintas | — | OOM con tope 16 GB (≈17 GB extrapolado) |

Perfil (cProfile, 9900X, serie de 50 secciones × 2 mallas): **corte 4,32 s (96 %)**, extracción 0,16 s. Dentro del corte: `trimesh.intersections.mesh_plane` 3,6 s (de ello `ndarray.sort` 1,36 s y `triangle_cases` 2,4 s acumulado, sobre las 3,35 M caras en cada llamada) y el bucle Python de recorte `section_distance` 304.159 llamadas.

Prototipos ya validados (sin tocar el repo, `data/perf-real/proto_grid_reference.py`):

| Prototipo | Resultado |
|---|---|
| Índice de rejilla XY de caras (celda 5 m) + `mesh_plane` sobre submalla | **42× más rápido** (3,61 s → 0,086 s en 50 cortes), ~9.500 caras por sección, segmentos dentro del tramo **idénticos** en las 50 secciones. Índice: 0,6 s y 51 MB, una vez por malla |
| Filtro por máscara bbox sobre todas las caras (sin rejilla) | 0,8× (más lento): descartado |
| Recarga desde arrays ya procesados (`np.savez` vértices float64 + caras int32) | **0,02 s**, 77 MB, sin el pico de 2 GB del parseo |
| `trimesh.load(process=False)` | 0,1 s pero 10 M vértices sin fusionar: no sirve como reemplazo directo |

Diagnóstico de memoria (código en `origin/main`):
- `api/database.py:604` `get_trimesh_by_id` usa `functools.lru_cache(maxsize=4)` **fuera** del presupuesto en bytes (`CONCILIACION_MESH_CACHE_MB=4096`): hasta 4 trimesh (≈0,5–0,8 GB c/u ya usados) + 4 GB de payloads + transitorios. Con 10 usuarios hay recargas constantes de 6 s y 2 GB de pico cada una.
- `api/routers/process.py:494` `ThreadPoolExecutor()` sin `max_workers` (8 hilos en el N100) por petición: 10 peticiones ⇒ 80 hilos compitiendo por el GIL.
- `api/routers/process.py:503` escribe `update_process_status` en SQLite por cada sección (50 escrituras por proceso). HANDOFF ya registra `database is locked` con peticiones concurrentes en `get_or_create_session`.
- La subida STL (`api/routers/meshes.py:1008`) parsea en `asyncio.to_thread` sin semáforo; el DXF sí tiene `_parse_slots = BoundedSemaphore(2)` (`api/dxf_uploads.py:11`).

## 2. Ya aplicado en producción (fuera del repo)

- `cg-api`: memoria **8 GB → 11 GB en caliente** con `docker update --memory 11g --memory-swap 22g cg-api` (sin reinicio: `StartedAt` intacto, no se ejecutó `cleanup_old_sessions`). `~/conciliacion/docker-compose.yml` `mem_limit: 11g` para que una recreación lo conserve.
- Verificado: `memory.max=11811160064`, health 200 local y público.
- Respaldo y rollback: `~/conciliacion/despliegues/mem-11g-20261115-071741/` (`DEPLOY.txt`, `docker-compose.yml.bak`).

## 3. Criterios de aceptación (medidos en el N100, contenedor de QA aparte con tope 11 GB)

| ID | Criterio | Hoy | Meta |
|---|---|---|---|
| A1 | 10 usuarios × 50 secciones simultáneos, misma malla | 48,8 s | **≤ 8 s** |
| A2 | 10 usuarios, cada uno con su topo (ya subida), procesando a la vez | no cabe | **pico ≤ 8,8 GB** (pico × 1,25 ≤ 11 GB), sin OOM |
| A3 | Recarga de una malla expulsada del caché | 5,8 s / 2 GB | **≤ 0,5 s**, pico ≤ 0,3 GB |
| A4 | Resultados | — | JSON de comparación por sección **idéntico** a la línea base (mismos campos, diferencias ≤ 1e-9) en la sesión real y en fixtures sintéticos |
| A5 | Suites | — | `pytest tests/ --ignore=tests/test_openblast.py` y `python test_pipeline.py` verdes; conteo de tests actualizado en README |
| A6 | 10 sesiones HTTP concurrentes (subida ya hecha → proceso → resultados) | sin medir | 0 errores 5xx, 0 `database is locked` en logs |

## 4. Dependencias y colisiones

- **Retención — RESUELTO 15-nov 09:13:** r8 se integró a `main` (`e8b4c2d`, PR #48: "30 días desde el último uso", commit `d0a9722`) y otra sesión lo desplegó en el N100 (`despliegues/r8-20261115-0853/`). El `mem_limit: 11g` sobrevivió a la recreación porque ya estaba en el compose. Esta rama debe rebasarse sobre `origin/main` (`e8b4c2d`) tras cerrar la fase 1; r8 también tocó `core/config.py`.
- ~~**Retención (bloqueante para el despliegue, no para desarrollar):**~~ el código desplegado borra en cada reinicio las sesiones con `created_at` > 24 h (hoy borraría `be11bfad…`, 2 mallas y 425 resultados). El cambio a "30 días desde el último uso" está **sin commitear** en el worktree `46-conciliacion-geo-v02-fixes` (`fix/prod-qa-r8`, modifica `api/database.py` y `api/main.py`). Esta rama **no toca** `cleanup_old_sessions`; antes de desplegarla, r8 debe estar integrada en `main` y esta rama rebasada.
- **Colisión de archivo:** r8 también modifica `api/database.py`. Las tareas T2.x tocan otras funciones del mismo archivo; rebasar antes de la fase 2 si r8 ya se integró, o resolver el merge al final.
- `core/` es compartido con Streamlit (`app.py`/`ui/` fuera de límites). Todo cambio en `core/` mantiene firmas y salidas; la UI legada se beneficia sin tocarla.
- Docs: AGENTS.md dice que `azimuth_to_direction` vive en `core.geom_utils`; realmente está en `core/section_cutter.py:38`. Corregir en la tarea de documentación (T6.3).

## 5. Contratos congelados

Productores y consumidores usan exactamente estos nombres.

```python
# core/config.py  (dataclass nueva, frozen, singleton SECTION_INDEX)  — crea T1.1
@dataclass(frozen=True)
class SectionIndexDefaults:
    cell_size_m: float = 5.0          # celda de la rejilla XY
    min_faces: int = 50_000           # bajo esto se usa el camino completo (mallas de diseño)
    pad_m: float = 1.0                # holgura sobre el tramo de la sección

# core/section_index.py  — crea T1.2
@dataclass(frozen=True)
class FaceGridIndex:
    origin_xy: np.ndarray       # (2,) float64, mínimo XY de las caras
    cell_size_m: float
    ny: int                     # celdas en Y
    max_face_span_m: float      # mayor extensión XY de una cara
    sorted_keys: np.ndarray     # (n_faces,) int64, clave de celda ordenada
    order: np.ndarray           # (n_faces,) int64, índice de cara en ese orden

def build_face_grid_index(mesh: trimesh.Trimesh, cell_size_m: float = SECTION_INDEX.cell_size_m) -> FaceGridIndex: ...
def get_face_grid_index(mesh: trimesh.Trimesh) -> FaceGridIndex: ...   # memoizado por objeto malla
def candidate_faces(index: FaceGridIndex, start_xy: np.ndarray, end_xy: np.ndarray, pad_m: float) -> np.ndarray: ...
# Garantía: superconjunto de toda cara cuyo bbox XY intersecta el bbox del tramo [start,end] ampliado en pad_m.
```

- `cut_mesh_with_section_diagnostics(mesh, section) -> ProfileCutDiagnostics` **no cambia** de firma ni de semántica de warnings.
- Memo del índice: `mesh._cache` de trimesh se invalida al mutar la malla; preferirlo (clave `"conciliacion_face_grid"`) y, si no es viable, `weakref.WeakKeyDictionary` con fallback por `id()` + verificación de `len(faces)`. La tarea T1.2 documenta cuál quedó y por qué.

```sql
-- api/database.py init_db (aditiva)  — crea T2.2
CREATE TABLE IF NOT EXISTS mesh_arrays (
    mesh_id TEXT PRIMARY KEY REFERENCES meshes(id) ON DELETE CASCADE,
    format INTEGER NOT NULL,          -- 1 = np.save (allow_pickle=False) de vertices float64 (n,3) y faces int32 (m,3)
    vertices BLOB NOT NULL,
    faces BLOB NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

```python
# api/database.py  — crea T2.2
MESH_ARRAYS_FORMAT = 1
def save_mesh_arrays(mesh_id: str, mesh: trimesh.Trimesh) -> None: ...
def load_mesh_arrays(mesh_id: str) -> Optional[trimesh.Trimesh]: ...   # Trimesh(process=False) o None si no hay fila / formato distinto
```

```python
# Variables nuevas (todas leídas en core/config.py; prod compose las agrega a mano)  — T2.4, T2.5, T3.1, T3.2
CONCILIACION_TRIMESH_CACHE_MB        # default 2048; presupuesto en bytes de get_trimesh_by_id
CONCILIACION_UPLOAD_PARSE_CONCURRENCY # default 2; parseos STL simultáneos
CONCILIACION_PROCESS_THREADS          # default 4; hilos por petición /process
CONCILIACION_PROCESS_CONCURRENCY      # default 2; pipelines /process simultáneos por proceso
```

`get_trimesh_by_id` conserva `.cache_clear()` (lo llaman `tests/conftest.py:306`, `tests/api/conftest.py:173,179`, `tests/api/test_dxf_pipeline.py:110`, `tests/api/test_dxf_upload.py:56`, `tests/api/test_meshes.py:280`, `tests/api/test_byte_cache.py:223`).

## 6. Fases y tareas

Comando de tests (siempre con este prefijo; ver pitfall del venv):

```bash
cd /home/xodla/archivos/12_WindSurf/46-conciliacion-geo-v02-rendimiento
PYTHONPATH=. /home/xodla/archivos/12_WindSurf/46-conciliacion-geo-v02/.venv/bin/python -m pytest <tests> -v --tb=short
```

### Fase 0 — Arnés de medición (prerrequisito de todo)

**T0.1 Script de benchmark del pipeline** (Haiku)
- Crear: `scripts/perf/bench_process.py`.
- Modos: `--mode load`, `--mode process --users N [--distinct]`, `--mode profile`. Lee `--data-dir` (por defecto `$CONCILIACION_PERF_DATA` o `data/perf-real`): `design.stl`, `topo.stl`, `sections.json` (formato de `sessions.sections`).
- Usa sólo la API pública (`from core import load_mesh, SectionLine, extract_parameters`, `from core.section_cutter import cut_mesh_with_section_diagnostics`) y replica el patrón de `api/routers/process.py:437-505`.
- Salida: una línea JSON por escenario `{mode, users, distinct, wall_s, per_user_max_s, peak_rss_mb, steady_rss_mb, n_sections, git_sha}`.
- Verificación: `... scripts/perf/bench_process.py --mode process --users 1` imprime JSON válido con `n_sections=50`.

**T0.2 Volcado y comparación de resultados** (Haiku)
- Crear: `scripts/perf/dump_results.py` con `--out <json>` y `--compare <baseline.json>`. Por sección: extracción diseño/topo (`_extraction_to_dict` de `api/routers/process.py:104`) y comparaciones de `_guided_comparison`. Floats redondeados a 1e-9. `--compare` sale con código 1 e imprime la primera diferencia.
- Verificación: dos corridas seguidas sobre el mismo commit → `--compare` sale 0.

**T0.3 Línea base registrada** (coordinador)
- Correr T0.1 (1, 3 y 10 usuarios; misma y distintas topos) en el 9900X bajo `systemd-run --user --scope -p MemoryMax=16G -p MemorySwapMax=0` y en el N100 en contenedor aparte (`docker run --rm --memory 11g ... conciliacion-api:<candidato>` con el arnés montado read-only).
- Guardar `data/perf-real/baseline-931adcb.json` (T0.2) y los JSON de tiempos en `data/perf-real/runs/`. Anotar en la tabla de seguimiento.

### Fase 1 — Corte de secciones con índice espacial (mayor impacto)

**T1.1 Configuración** (Haiku)
- Modificar: `core/config.py` — `SectionIndexDefaults` + singleton `SECTION_INDEX` (sin variable de entorno).
- Test: en `tests/test_section_index.py` (no existe `tests/test_config.py`) — valores por defecto e inmutabilidad (`FrozenInstanceError`).

**T1.2 Índice de rejilla — TDD**
- Crear: `core/section_index.py`, `tests/test_section_index.py`.
- Tests RED primero:
  1. `candidate_faces` es superconjunto de la máscara bruta (bbox de cara ∩ bbox del tramo) en mallas aleatorias, secciones de azimut 0/45/90/137/270, tramos asimétricos y caras más grandes que la celda.
  2. Tramo fuera de la malla → arreglo vacío `int64`.
  3. Malla de 1 cara y malla con todas las caras en una celda.
  4. Memo: dos llamadas a `get_face_grid_index` sobre el mismo objeto devuelven el mismo índice; otra malla, otro índice.
- Implementación: binning por centroide del bbox XY, `np.argsort(kind="stable")`, búsqueda por columna con `np.searchsorted`; holgura efectiva `pad_m + max_face_span_m / 2`. Referencia funcional: `data/perf-real/proto_grid_reference.py` (función `candidates`; su línea `m = ...` sobra).

**T1.3 Integración en el cortador — TDD**
- Modificar: `core/section_cutter.py:48-106` (`cut_mesh_with_section_diagnostics`).
- Con `len(mesh.faces) >= SECTION_INDEX.min_faces`: candidatos del tramo `[origin + lower·dir, origin + upper·dir]`, submalla compacta (`np.unique(faces[idx], return_inverse=True)` → `Trimesh(vertices[uv], inv.reshape(-1,3), process=False)`) y `mesh_plane` sobre ella. Sin candidatos → mismo diagnóstico `no_section_intersection`. Cualquier excepción del camino indexado → camino completo actual.
- Tests nuevos en `tests/test_section_cutter.py`: igualdad de `ProfileResult` (distancias/elevaciones `allclose` 1e-9) y de warnings entre camino indexado y completo sobre `pit_mesh_design`/`pit_mesh_asbuilt` (forzando `min_faces=0` vía monkeypatch) y sobre una malla subdividida > 50.000 caras; los 36 tests existentes siguen verdes.
- Verificación adicional (coordinador): `scripts/perf/dump_results.py --compare data/perf-real/baseline-931adcb.json` → 0.

**T1.4 Recorte vectorizado (condicional)**
- Sólo si el perfil post-T1.3 muestra el bucle `section_distance` / `node_for` > 15 % del tiempo de corte. Vectorizar `core/section_cutter.py:80-104` con numpy, mismas tolerancias. Mismos tests de igualdad.

**T1.5 Compuerta de fase 1** (coordinador)
- Repetir T0.3. Esperado: 1 usuario N100 ≈ 0,5–1 s; 10 usuarios ≤ 8 s (A1). Igualdad A4. Si A1 se cumple aquí, la fase 4 se descarta.

### Fase 2 — Mallas preprocesadas y caché en bytes

**T2.1 Tests RED de arrays persistidos**
- Crear: `tests/api/test_mesh_arrays.py`.
  1. `save_mesh_arrays` + `load_mesh_arrays` devuelven vértices/caras idénticos (`array_equal`, dtypes float64/int32→int64 al reconstruir).
  2. Borrar la sesión borra la fila (CASCADE con `PRAGMA foreign_keys=ON`, `api/database.py:34`).
  3. `get_trimesh_by_id` usa los arrays sin parsear el STL (monkeypatch de `load_mesh` que falla si se llama).
  4. Malla antigua sin fila: primera llamada parsea y crea la fila; segunda no parsea.
  5. Malla DXF (`import_options` con capas): los arrays guardados son los posteriores a `import_dxf_surface`.
  6. Formato desconocido → se ignora y se reparsea.

**T2.2 Tabla y funciones**
- Modificar: `api/database.py` (`init_db` + `save_mesh_arrays`/`load_mesh_arrays`). `np.save(..., allow_pickle=False)` a `BytesIO`; `np.load(..., allow_pickle=False)`.

**T2.3 Escribir arrays al subir**
- Modificar: `api/routers/meshes.py:1008-1030` (STL) y `:1099-1125` (DXF): tras `save_mesh`, `save_mesh_arrays(mesh_id, mesh)` vía `run_db`. Si falla, log y seguir (el backfill lo repara).
- Tests: subida STL y DXF crean la fila (extender `tests/api/test_meshes.py`, `tests/api/test_dxf_upload.py`).

**T2.4 `get_trimesh_by_id` con arrays y presupuesto en bytes**
- Modificar: `api/database.py:604-635`, `api/byte_cache.py` (presupuesto propio `CONCILIACION_TRIMESH_CACHE_MB`, tamaño = `vertices.nbytes + faces.nbytes` + índice de rejilla si existe), `core/config.py` (leer la variable).
- Mantener `.cache_clear()` y `.cache_info()`.
- Tests: `tests/api/test_byte_cache.py` — expulsión por bytes con mallas de distinto tamaño; con 6 mallas y presupuesto para 2, las otras se recargan desde arrays.

**T2.5 Semáforo de parseo STL** (Haiku)
- Modificar: `api/routers/meshes.py:1008`, `core/config.py`. Patrón de `api/dxf_uploads.py:11`.
- Test: 3 subidas concurrentes con límite 1 → nunca hay 2 parseos simultáneos (contador instrumentado).

**T2.6 Compuerta de fase 2** (coordinador)
- A3: recarga ≤ 0,5 s. A2: 10 topos distintas en N100 QA, pico ≤ 8,8 GB. A4 igualdad. Medir crecimiento de la BD (≈ +77 MB por topo) y anotarlo.

### Fase 3 — Concurrencia y SQLite

**T3.1 Hilos acotados y estado con throttle**
- Modificar: `api/routers/process.py:494-505` — `ThreadPoolExecutor(max_workers=PROCESS_THREADS)`; `update_process_status` como máximo cada 0,5 s y siempre en la última sección.
- Tests: `tests/api/` — el estado final sigue siendo `completed == total`; con 50 secciones hay ≤ 10 escrituras intermedias (contar con monkeypatch).

**T3.2 Limitador de pipelines**
- Modificar: `api/_async_db.py` (`run_process_limited`, igual que `run_blast_limited:68`), `api/routers/process.py:545` y la ruta del agente IA que llama `_run_pipeline_sync` vía `asyncio.to_thread` (`process.py:370`).
- Tests: crear `tests/api/test_process_concurrency.py` como espejo de `tests/api/test_blast_concurrency.py`.

**T3.3 Prueba de carga HTTP** (Haiku escribe, coordinador ejecuta)
- Crear: `scripts/perf/load_test.py` — N sesiones (`X-Session-ID` desechables), subida de topo+diseño, `POST /sections` con `sections.json`, `POST /process`, `GET /process/results`; reporta tiempos p50/p95, códigos HTTP y borra las sesiones al final.
- Ejecutar contra instancia QA en el N100 (contenedor aparte, copia de la BD, tope 11 GB) con N = 10. Revisar logs por `database is locked` (A6).

### Fase 4 — Varios procesos (compuerta: sólo si A1/A6 fallan tras la fase 3)

No se planifica en detalle hasta tener los números. Opciones a evaluar en un documento de decisión:
1. **Pool de procesos de cálculo** con arrays en `.npy` mapeados en memoria (`np.load(mmap_mode="r")`): el page cache se comparte entre procesos y la API sigue siendo un solo proceso (no rompe el almacén de confirmaciones del chat IA ni `dxf_uploads`).
2. `CONCILIACION_WORKERS > 1`: exige mover a almacenamiento compartido las confirmaciones pendientes del chat (`api/routers/ai.py:354-468` hoy lo bloquea), `api/dxf_uploads.py:9` `_uploads`, el rate limiter (`api/middleware_ratelimit.py:78`, memoria por proceso) y multiplica cachés por worker. Se desaconseja.

### Fase 5 — Otros endpoints pesados (medir primero)

**T5.1 Medición** (coordinador + Haiku para el script): extender el arnés a `GET /meshes/{id}/horizontal-deviation` (`api/routers/meshes.py:433`, hasta `heatmap_max_cuts` cortes: se beneficia de la fase 1 automáticamente), `vertices?step=150000`, `contours`, `roi`, `/blast/holes/3d`. Registrar pico y tiempo antes/después de las fases 1–2.
**T5.2** Pozos de tronadura fuera de `sessions.settings`: ya registrado como pendiente en `docs/HANDOFF.md`; plan aparte, no en esta rama.

### Fase 6 — Integración y despliegue

**T6.1** Rebase sobre `main` con r8 (retención por último uso) integrada. Gates completos A5.
**T6.2** Despliegue según la skill `conciliacion-n100-deploy`: ensayo de `init_db` (tabla `mesh_arrays`) sobre copia del respaldo, variables nuevas en `~/conciliacion/docker-compose.yml`, listado de sesiones que la regla vigente borraría, respaldo, retag, verificación pública. El backfill de arrays es perezoso (primer uso de cada malla), nunca en el arranque.
**T6.3** Docs: `docs/HANDOFF.md` (estado y mediciones), AGENTS.md (`azimuth_to_direction` en `core.section_cutter`, variables nuevas, tabla `mesh_arrays`), README (conteo de tests).

## 7. Commits y publicación

- Commits locales por tarea, hechos por el coordinador tras revisión de especificación y calidad, con allowlist explícita de rutas y conventional commits (`perf:`, `test:`, `feat:`), sin atribución IA.
- Push, PR, merge y despliegue: **requieren autorización explícita del usuario** en su momento.
- Nunca commitear `data/perf-real/` (datos reales de la faena; ya está en `.gitignore`).

## 8. Riesgos

| Riesgo | Mitigación |
|---|---|
| El índice devuelve menos caras que el camino completo en geometrías raras (caras gigantes, mallas no planas) | Holgura `max_face_span/2`, `min_faces` para mallas chicas, fallback al camino completo ante excepción, tests de igualdad con fixtures y malla real |
| `mesh._cache` de trimesh limpia el índice en cada acceso a propiedades mutables | T1.2 lo verifica con test de memo; alternativa weakref documentada |
| La BD crece ≈ 77 MB por topo | Medido en T2.6; la retención borra en cascada; evaluar no duplicar el STL a futuro |
| Pico de la primera subida sigue en 2 GB | Semáforo de parseo (T2.5); un parser STL propio queda fuera de alcance salvo que A2 falle por subidas |
| Merge con r8 en `api/database.py` | Rebase temprano; tareas tocan funciones distintas |
| Benchmarks en el N100 compiten con producción | Contenedor aparte con tope, `nice -n 10`, fuera de horario y verificando `docker logs --since 30m` sin actividad antes de correr |

## 9. Arbitraje

Revisión de solo lectura `deleg_2dd1501c` (15-nov, claude-haiku-5-5): **APROBAR CON CORRECCIONES**. Verificó 50/50 secciones idénticas con la submalla y 0 violaciones del superconjunto sobre la topo real. Correcciones aceptadas; **prevalecen sobre el texto anterior**:

| # | Corrección | Afecta |
|---|---|---|
| B1 | `estimate_size` cobra 64 B a un `Trimesh` (`api/byte_cache.py:175`): T2.4 añade a `ByteLruCache` un parámetro `sizer: Callable[[Any], int] | None = None` usado en `_store`, y `trimesh_nbytes(m) = vertices.nbytes + faces.nbytes + Σ nbytes de m._cache.cache`. Test con un `Trimesh` real | T2.4 |
| I1 | `/process` no infla `_cache` (10 × `mesh_plane` sin claves nuevas), pero `face_normals` suma 383 MB y adyacencias llegan a 1,1 GB. T2.4 construye el índice eager en `get_trimesh_by_id` antes de almacenar; T5.1 mide endpoints que usan normales/adyacencia y decide `m._cache.clear(exclude=["conciliacion_face_grid"])`. A2 cubre sólo `/process` | T2.4, T5.1 |
| I2 | Memo **sólo** en `mesh._cache["conciliacion_face_grid"]` (se invalida en mutación vía `Cache.verify`, `trimesh/caching.py:364-390`). Sin fallback por `id()` ni `WeakKeyDictionary`. trimesh ya está fijado en 4.12.2 (`requirements*.txt`); test de mutación in situ obligatorio | T1.2 |
| I3 | `candidate_faces` devuelve índices **ascendentes** (`np.sort`): el orden cambia IDs de nodos y desempates (`section_cutter.py:109-131, 162`) | Contrato §5, T1.2 |
| I4/I5 | El corte usa el índice si `len(faces) >= min_faces`; si no existe lo construye una vez bajo un `threading.Lock` de módulo con doble verificación (no 8 construcciones paralelas). Llamadas puntuales sobre mallas frescas pagan una vez ~0,6 s (aceptado; T1.5 lo mide). La API lo construye eager en T2.4 | T1.3 |
| I6 | horizontal-deviation recorta mallas por petición (`meshes.py:195-237, 468-469`): el índice no persiste. T5.1 es medición pura; el recorte O(F) por petición se evalúa allí | T5.1 |
| I7 | T3.2 usa un `ThreadPoolExecutor(max_workers=PROCESS_CONCURRENCY)` dedicado, no el executor por defecto que comparte `run_db`. Corregido el "80 hilos" de §1: el techo real es el executor por defecto | T3.2, §1 |
| I8 | `run_process` (`process.py:545`) llama SQLite síncrono en el event loop (`:566, 568, 576, 589, 592`): envolver con `run_db` en T3.1 | T3.1 |
| I9 | El limitador va alrededor de `_run_in_executor(_run_pipeline_sync…)` (`process.py:585-587`) después de `try_begin_process` (`:568`), conservando el 409. La ruta IA real es `api/ai_agent_write_handlers.py:307-308` (no `process.py:370`) y entra en T3.2 | T3.2 |
| I10 | Las variables nuevas se leen en `core/config.py`; no copiar el patrón de `api/_async_db.py:28,37` | T2.4, T2.5, T3.x |
| I11 | T1.1 se fusiona en T1.2 (mismo writer). T2.3 y T2.5 se serializan (`meshes.py:1008-1030`). T3.1 y T3.2 se serializan. r8 tiene **29 archivos sin commitear** (incluye `core/config.py`, `api/routers/export.py`, `api/routers/session.py`, `pyproject.toml`): exigir su commit antes de T2.x | Orden, §4 |
| I12 | T2.3 guarda los arrays **antes** del `del mesh` (`meshes.py:1021`), con `zeroblob` + `blobopen` como `save_mesh(data_path=...)`; medir bloqueo de escritores en A6 | T2.3 |
| M1 | `Trimesh(process=False)` reproduce vértices/caras/normales bit a bit; sólo se pierde `metadata` (no usada). Documentar en T2.2 | T2.2 |
| M2 | Guardar caras en **int64** (trimesh las usa así) o medir: la meta A3 de 0,3 GB es ajustada | T2.2, A3 |
| M3 | Single-flight de `byte_cache.py:249-253` libera el claim antes de `_store`: invertir el orden en T2.4 | T2.4 |
| M4 | `FaceGridIndex` con `@dataclass(frozen=True, eq=False)` | Contrato §5 |
| M5 | Tests: `monkeypatch.setattr(section_cutter, "SECTION_INDEX", dataclasses.replace(SECTION_INDEX, min_faces=0))`; el cortador lee el singleton en tiempo de llamada | T1.3 |
| M6 | Citas: el cortador ocupa `section_cutter.py:48-225` (inserción tras `:56`); la ruta de horizontal-deviation es `meshes.py:1365` (builder en `:433`) | T1.3, T5.1 |
| M7 | Tests de corte con igualdad **exacta** (`np.array_equal`); `dump_results --compare` compara valores crudos con `|a−b| ≤ 1e-9`, sin redondear antes | A4, T0.2, T1.3 |
| M8 | Mantener la submalla compacta: `mesh_plane(local_faces=...)` cuesta ~14 ms vs ~1,1 ms porque recalcula productos punto sobre todos los vértices | T1.3 |
| M9 | Otros llamadores del cortador cubiertos por los tests de igualdad: `blast.py:100`, `sections.py:155`, `meshes.py:1177/1254/1269/1447`, `export.py:677-678/1046-1047`, `process.py:699-707/928-929` | A4 |
| M10 | T6.3 actualiza el pitfall de AGENTS.md sobre "4 mallas" y la ubicación de `azimuth_to_direction` | T6.3 |

## 10. Seguimiento

| Tarea | Estado | Evidencia |
|---|---|---|
| Memoria cg-api 8 → 11 GB | Verificado por coordinador | `docker update` en caliente; `memory.max=11811160064`; health 200 local/público; respaldo `despliegues/mem-11g-20261115-071741/` |
| Rama + worktree | Verificado por coordinador | `perf/process-optimization` @ 931adcb en `46-conciliacion-geo-v02-rendimiento` |
| Datos reales para benchmark | Verificado por coordinador | `data/perf-real/` (topo 167.472.834 B, diseño, 50 secciones), gitignored |
| Prototipo índice de rejilla | Verificado por coordinador | 42×, segmentos idénticos en 50/50 secciones (9900X) |
| Revisión del plan | Verificado por coordinador | `deleg_2dd1501c`: APROBAR CON CORRECCIONES; arbitraje en §9 |
| Suite base | Verificado por coordinador | 931adcb: `4506 passed, 9 skipped` (219 s), `test_pipeline.py` rc=0; logs en `data/perf-real/runs/` |
| T0.1–T0.2 | Verificado por coordinador, commit `defef84` | `tests/test_perf_compare.py` 13 passed; `dump_results --compare` = equal (50 secciones); hashes 2a05fa9a… / b18ceb0b… / 1c7c8a6d… |
| T0.3 | Verificado (9900X); N100 se mide en T1.5 con el mismo arnés | `data/perf-real/baseline-931adcb.json`; `runs/baseline-931adcb-9900x.jsonl`: 1 usuario 1,60 s · 3 → 4,99 s · 10 → 19,88 s · 3 distintas 4,78 s / pico 5,5 GB · 6 distintas 10,89 s / pico 10,1 GB |
| T1.1–T1.3 | Verificado por coordinador, commit `0b46eeb` (rebasado sobre `e8b4c2d`) | Writer terra + corrección Haiku `deleg_095d581b` (hash sucio de `TrackedArray`: 3,3 s de 5 s, resuelto con vistas `np.asarray`). 49 tests de corte/índice; suite 4532 passed / 9 skipped antes del rebase; `--compare` = equal 50/50 antes y después del rebase. 9900X: 1u 1,60→1,11 s · 3u 4,99→1,86 s · 10u 19,88→4,48 s · 6 distintas 10,89→5,05 s |
| T1.5 | **Compuerta NO cumplida (A1)**, mejora 3,2× | N100 (contenedor aparte, misma imagen, código montado): 1u 6,14→2,57 s · 3u 16,28→5,36 s · **10u 49,48→15,57 s** (meta ≤ 8 s) · 3 distintas 16,33→5,38 s, pico 5,3→5,5 GB (lo domina la carga). Queda tiempo Python con GIL: bucles del cortador (~60 % del corte sin índice) + extracción/comparación. Siguiente: T1.4 (condición cumplida) en paralelo con la fase 2 |
| T1.4 | **Descartada** por el coordinador | Writer terra (`deleg_1046a5fc`): bit-idéntico (50×2 exactos) pero 10u 4,51→4,48 s (−0,7 %, ruido) a cambio de +84 líneas en el cortador y +256 de tests. Diff guardado en `.sandbox/T1.4-discarded.patch`; archivos restaurados a HEAD |
| T2.1–T2.5 | Verificado por coordinador (pendiente suite completa + commit) | Writer terra (`deleg_1046a5fc`; admitió TDD no estricto en parte). `tests/api` 390 passed; nuevos: mesh_arrays 9, upload_concurrency 2, byte_cache 24, dxf_upload 8. Sonda propia con topo real en BD temporal: guardar arrays 0,29 s, BD 275 MB (STL 160 + arrays 115); `load_mesh_arrays` **0,023 s, +119 MB**; `get_trimesh_by_id` con índice eager 0,70 s (índice 0,6 s), entrada de caché 174 MB; vértices/caras/normales idénticos a `load_mesh`, dtypes float64/int64. **Incidente:** la suite completa falló `test_ai_agent_handlers::TestReadOnlyInvariant::test_db_file_bytes_unchanged_after_every_handler` porque el backfill escribía en la ruta de lectura; corregido por Haiku (`deleg_da871a7e`): los arrays se escriben sólo al subir; sin fila, se reparsea sin escribir |
| T3.3 | Verificado por coordinador (sin commit aún) | Haiku `deleg_937bec49`: `scripts/perf/load_test.py` (sha 3340d2a8…), 2 usuarios locales OK, 14×200, 107 resultados/usuario. **Hallazgo:** con `MemoryMax=3G` dos subidas topo simultáneas (`UPLOAD_PARSE_CONCURRENCY=2`) llegaron a ~3,1 GB anónimos y OOM: cada parseo pesa ~1,5 GB. Para el N100 (T6.2): `CONCILIACION_MESH_CACHE_MB` 4096→2048, `TRIMESH_CACHE_MB` 2048, `UPLOAD_PARSE_CONCURRENCY` 2 ⇒ techo ≈ 2×2 + 2 + 2 + 1 base ≈ 9 GB < 11 GB |
| T3.1–T3.2 | Verificado por coordinador, commit `668455d` | Writer terra (`deleg_20dd5888`): `test_process_concurrency.py` 9 passed; suite 4577 passed / 9 skipped; `test_pipeline.py` rc=0 |
| A6 / T2.6 en N100 (QA aislado, tope 9 GB, 10 usuarios simultáneos, subida real por túnel) | **Primera corrida: mejora pero con 2 hallazgos** | **Base (r8, imagen prod): OOMKilled a los 23 s, 10/10 usuarios fallan.** **Nuevo (`668455d`): 8/10 OK**; subida p50 52 s / máx 81 s (red + parseo de a 2); proceso p50 5,8 s / máx 22 s; 2×500 `database is locked` (`save_sections`, `/process`); pico 9,2 GB (tope), reposo 7,4 GB anónimos. Réplica local (9900X, NVMe): 70/70 OK, sin locks, pico 9,7 GB, reposo 3,6 GB; `MALLOC_MMAP_THRESHOLD_=4 MiB` no cambia nada (3,46 GB). Causa del pico: la subida retiene la malla con cachés derivados de `centroid` (~550 MB c/u) mientras espera la BD; causa de los locks: timeout SQLite por defecto 5 s frente a escrituras de blobs de 160+115 MB. Corrección delegada a Haiku (`deleg_03178de2`) |
| Corrección de carga | Verificado por coordinador, commit `bf57be6` | Haiku `deleg_03178de2`: `mesh._cache.clear()` tras `get_mesh_bounds` en subida STL/DXF + `sqlite3.connect(timeout=30)`; 4 tests nuevos; suite 4581 passed / 9 skipped. Local 10u: pico 9,7→7,0 GB, reposo 3,6→2,7 GB, 70/70 OK |
| A6 en N100 (repetición con `bf57be6`) | **Cumplido** | QA aislado tope 9 GB, 10 usuarios simultáneos con subida real por túnel: **10/10 OK, 70×200, 0 locks, 0 errores**; subida p50 50,9 s / máx 73,0 s (red + parseo de a 2); **proceso p50 6,4 s / máx 10,6 s**; secciones ≤ 0,5 s; resultados ≤ 0,1 s; pico anónimo del proceso (VmHWM) **6,8 GB**, reposo 4,4 GB, sin OOM. Base r8 en el mismo escenario: OOMKilled, 0/10 |
| A1 (benchmark sintético 10u simultáneos misma malla ≤ 8 s) | No cumplido | 15,6 s en N100 (era 49,5). Lo que queda es Python con GIL en extracción/comparación y bucles del cortador; sólo la fase 4 (varios procesos) lo bajaría de forma sustancial |
| T5.1 | Pendiente | |
| T6.1–T6.3 | Pendiente: requiere autorización del usuario (push/PR/despliegue) | r8 ya está en `main` y en producción; la rama ya está rebasada sobre `e8b4c2d` |

## 11. Cierre de la tanda (15-nov-2026, 10:20)

- Rama `perf/process-optimization`, worktree `46-conciliacion-geo-v02-rendimiento`. Hay 6 commits locales sobre `e8b4c2d`: `df5fc0f`, `0b46eeb`, `e4c3818`, `5d66990`, `668455d` y `bf57be6`. No se hizo push.
- Suite completa en `bf57be6`: 4581 passed, 9 skipped; `test_pipeline.py` rc=0. La igualdad de resultados con la topo real se verificó en 50/50 secciones tras la fase 1; las fases siguientes no tocan el cálculo.
- Delegación restaurada a `claude-haiku-5-5` / `anthropic` / `xhigh`, que es el valor encontrado al inicio. No quedan subagentes vivos.
- N100: producción no se tocó en esta tanda; sólo hubo contenedores QA aislados, ya borrados. Queda sólo `~/qa/qa_up.sh`, sin datos.
- Configuración propuesta para desplegar en el N100: `CONCILIACION_MESH_CACHE_MB=2048`, `CONCILIACION_TRIMESH_CACHE_MB=2048`, `CONCILIACION_UPLOAD_PARSE_CONCURRENCY=2`, `CONCILIACION_PROCESS_CONCURRENCY=2`, `CONCILIACION_PROCESS_THREADS=4`, con `mem_limit 11g`.
- Pendiente: decisión del usuario sobre el despliegue (T6), la fase 5 (medir mapa de desviación horizontal, vértices y tronadura) y la fase 4 (varios procesos), que es sólo necesaria para la meta A1.

## 12. Despliegue r9 y fase 5 (15-nov-2026, 12:30–13:20)

**r9 en producción** (autorizado por el usuario): imagen `conciliacion-api:cand-20261115-bf57be6-r9` (`ad129f8b…`) → `:rl`; web sin cambios. Respaldo online `respaldos/r9-20261115-1230` (18 sesiones, 1188 resultados). Ensayo sobre copia: `mesh_arrays` creada, 0 sesiones borradas. Verificación pública, auth 401, variables nuevas dentro del contenedor, smoke con sesión desechable (16 resultados idénticos a local) y borrado por CASCADE. Detalle en `despliegues/r9-20261115-1230/DEPLOY.txt`. Rollback: `conciliacion-api:rollback-20261115-pre-r9`.

**T5.1 medición** (`scripts/perf/endpoint_bench.py`, commit `366e98e`): QA aislado en el N100, tope 9 GB, copia del respaldo r9, tronadura de be11bfad (15 448 pozos, settings 146 MB) clonada en las 6 sesiones con datos. Recorrido = lo que pide el visor 3D/dashboard. Variante `arrays`: las 12 mallas antiguas preprocesadas offline (52 s; BD 1,7→2,3 GB; topo 7,1 s c/u).

| Escenario | Resultado | Pico (VmHWM) | Pausa máx. del servidor |
|---|---|---|---|
| r8, 1 usuario | OK | 2,2 GB | 5,9 s |
| r9, 1 usuario | OK | 2,2 GB | 6,1 s |
| r9 + arrays, 1 usuario | OK | 2,0 GB | 6,2 s |
| r8, 10 usuarios / 5 sesiones | **OOMKilled a los 14 s, 0/10** | > 9 GB | — |
| r9, 10 usuarios | 10/10, 200×200 | **8,9 GB** | **33,8 s** |
| r9 + arrays, 10 usuarios | 10/10, 200×200 | **5,0 GB** | 33,7 s |

Tiempos (s) en frío / en caliente, mediana:

| Endpoint | r8 1u | r9 1u | r9+arrays 1u | r9 10u | r9+arrays 10u |
|---|---|---|---|---|---|
| desviación horizontal | 83,8 / 2,4 | 65,7 / 2,4 | 66,1 / 2,4 | 184 (máx 287) / 18,0 | 218 / 18,4 |
| vértices topo 150k | 13,5 / 0,8 | 14,6 / 0,8 | 9,3 / 0,9 | 56,2 / 9,9 | 43,6 / 9,9 |
| contornos topo | 5,0 / 0,2 | 5,1 / 0,2 | 5,1 / 0,2 | 14,7 / 2,7 | 14,3 / 2,7 |
| ROI miniatura | 1,5 / 0,6 | 1,5 / 0,6 | 1,5 / 0,6 | 5,8 / 3,3 | 6,0 / 3,9 |
| pozos 3D | 2,0 / 1,0 | 1,8 / 1,0 | 1,8 / 1,0 | 4,4 / 15,4 | 4,3 / 14,0 |
| pozos 3D sección | 3,3 / 3,2 | 3,5 / 3,1 | 3,1 / 3,2 | 6,6 (máx 117) / 28,8 | 5,9 / 27,1 |
| pozos sesión | 0,6 / 0,3 | 0,3 / 0,3 | 0,6 / 0,3 | 3,4 (máx 113) / 19,6 | 3,1 / 17,3 |

Diagnóstico (perfil en 9900X con datos reales, `cache/scratch/r9/profile_hd.py`, `measure_encode.py`):
- Desviación horizontal 20 s (28,6 con cProfile): drapeado 9,9 s (bucle Python por punto + TrackedArray), cortes 7,9 s (2926), intersecciones 3,9 s, extracción 1,8 s, decimación 3,6 s (compartida con el visor). Payload 15 MB.
- Pausas del servidor: endpoints `async` con `db.*` síncrono en el loop (sobre todo `get_settings` de 146 MB con LRU 3 < 5 sesiones) y serialización JSON de respuestas grandes en el loop (`jsonable_encoder` + render: 0,45 s por respuesta de vértices o de desviación en el 9900X, ~1,2 s en el N100).
- Pozos en caliente peor que en frío con 10 usuarios: el LRU de settings se vacía con 5 sesiones y `BLAST_CONCURRENCY=1` serializa; el arreglo de fondo es T5.2 (pozos en tabla propia, plan aparte).
- Los arrays persistidos bajan el pico con 10 usuarios de 8,9 a 5,0 GB: backfill único en producción recomendado (requiere autorización: escribe la BD).

Correcciones en curso (`deleg_b0e8338b`, terra): T5.3 drapeado vectorizado con payload bit-idéntico (`.sandbox/T5.3-drape.md`); T5.4 `run_db` para todo `db.*` en endpoints `async` fuera de meshes.py (`.sandbox/T5.4-event-loop.md`). Después: T5.5 serializar las respuestas grandes de meshes.py en el hilo de trabajo.
