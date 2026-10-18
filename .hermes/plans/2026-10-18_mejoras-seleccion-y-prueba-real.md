# Plan — Mejoras post-T14 de selección continua y prueba con archivos reales

Fecha: 18 de octubre de 2026 (America/Santiago). Base: `d198f50` (main, árbol limpio salvo `data/` ignorado).
Autorización: el usuario pidió commit (hecho: `d4073c6`, `05f47ad`, `dd8f81d`, `d198f50`), este plan y su implementación con subagentes. Usuario AFK: sin `sudo`, sin push/despliegue, sin commit adicional no solicitado.

## 1. Objetivo

1. Validar la selección continua con archivos reales del usuario, de extremo a extremo y con eventos de puntero reales.
2. Medir con esos archivos el coste real por `pointermove` (incluida la oclusión) antes de decidir optimizaciones.
3. Resolver los pendientes no bloqueantes de T14 que tienen efecto verificable, sin cambiar cálculos científicos.

## 2. Datos reales

- Diseño: `/home/xod/Descargas/input-perfil/f12b_v1.stl` (215 KB). Alternativo: `f09w_v12.1.stl`.
- Topografía: `/home/xod/Descargas/input-perfil/TOPO_OCTUBRE_161026_relimit.stl` (27 MB).
- Los archivos no se copian al repositorio; la evidencia queda en `data/qa-real-file/` (ignorado).

## 3. Aislamiento de QA

La prueba real corre sobre un **git worktree de `d198f50`** en `cache/scratch/cgv02-head` (enlace a `web/node_modules`; `.venv` del repo principal), con API propia en 8000 y Vite en 5181 (el proxy de Vite apunta a 8000 fijo). Así los escritores del árbol principal no provocan HMR ni cambian el código medido. `CONCILIACION_DATA_DIR` fresco bajo `data/qa-real-file/runtime-*`. Servicios propiedad del coordinador; cerrar y verificar puertos al final.

## 4. Entregas

### R1 — Prueba real y medición (QA, sin cambios de producción)
**Archivos propios:** `data/qa-real-file/` (script Playwright `.cjs/.ts` parametrizado por rutas, config, evidencia).
**Pasos:** subir diseño y topografía (vía UI si es viable; si no, vía API declarada como preparación programática), cargar contornos/curvas del diseño, elegir una línea de cresta o pata real con clics de puntero reales, fijar inicio y fin dentro de la misma curva, generar secciones, leer GET de secciones y comprobar: puntos finitos, extremos del payload sobre la polilínea (distancia XY ≤ 1e-6 m respecto del segmento de origen), orden inicio→fin, recuento de secciones coherente con spacing/longitud. Luego ejecutar el proceso de conciliación de esas secciones y comprobar resultados > 0 y sin errores 5xx. Consola sin errores.
**Medición:** trazado CDP (`devtools.timeline`) durante un barrido de 200 `pointermove` reales sobre la curva y fuera de ella, con la topografía cargada: duración de `EventDispatch` de `pointermove` (mediana/p95/máx), intervalos de frame y frames > 16,7 ms; número de candidatos y tamaño de la malla. Registrar entorno (CPU, GPU si disponible, Chrome).
**Aceptación:** evidencia JSON + capturas pre/post generación; ningún ancla sembrada en el store.
**Regla de decisión para I1:** implementar I1 solo si `pointermove` p95 > 8 ms o > 5 % de frames > 16,7 ms durante el barrido. Si no, registrar la medición y cerrar I1 como no necesario.

### I1 — Coste de oclusión (condicional a R1)
**Archivos propios:** `web/src/components/mesh/curveScenePicking.ts` + test nuevo `__tests__/curveScenePicking.occlusion.test.ts`.
**Cambio permitido:** reutilizar un `Raycaster` por instancia en vez de crear uno por candidato; derivar el umbral de búsqueda del radio en píxeles a la distancia de la cámara en lugar de `camera.far`; sin BVH ni dependencias nuevas. Mismos resultados de selección en los tests existentes y nuevos.

### I2 — Higiene del visor
**Archivos propios:** `web/src/components/mesh/Mesh3DViewer.tsx`.
**Cambio:** declarar `previewRef` antes del `useFrame` que lo usa; memoizar `getCurveGeometrySnapshot` (`useMemo` por `designMeshId`/contornos) y los colores de tema; estabilizar handlers con `useCallback`. Sin cambio de comportamiento: suites existentes y smoke 11/11.

### I3 — Estado estable en acciones vacías
**Archivos propios:** `web/src/components/sections/curveSelectionState.ts` + su test existente (solo añadir casos).
**Cambio:** `cancel` y `generated` devuelven la misma referencia cuando el estado ya está vacío. RED previo obligatorio.

### I4 — Limpieza proactiva de anclas obsoletas
**Archivos propios:** `web/src/stores/session.ts` + `web/src/stores/__tests__/session.curve-selection.test.ts` (añadir casos).
**Cambio:** cuando cambie la identidad de geometría (contornos/mesh) aunque el formulario esté desmontado, invalidar la selección con la acción existente del reductor. Si exige tocar otro archivo, detenerse y reportar. RED previo obligatorio.

### I5 — Robustez del centinela SQLite
**Archivos propios:** `api/database.py`, `api/main.py`, `tests/api/test_sqlite_durability.py` (añadir casos).
**Cambio:** cerrar la conexión si falla la lectura inicial en `open_sentinel`; garantizar `close_sentinel` si falla el arranque entre `open_sentinel` y `yield`. Sin cambiar pragmas ni timeouts.

### Descartado con justificación
- Marcador Float32 frente a payload double (~1e-4 m): sin efecto visible ni en payload; no se cambia.
- Comentarios de durabilidad en código: la regla del proyecto de no añadir comentarios prevalece; queda en HANDOFF.

### V — Integración y cierre (coordinador)
Tras I2–I5 (+I1 si procede): focalizadas, `test:coverage` (sin Vite activo), `tsc -b --force`, lint, build, suite Python, smoke T12 11/11 en el árbol principal, y repetición de R1 sobre el árbol principal final. Dos revisores de solo lectura (especificación y calidad) del delta. Actualizar HANDOFF y este plan. No commit salvo nueva solicitud.

## 5. Orden y paralelismo

| Tanda | Entregas | Regla |
|---|---|---|
| 1 | R1 (worktree) ∥ I2 ∥ I3 ∥ I4 ∥ I5 | Archivos disjuntos; R1 aislado en worktree |
| 2 | I1 si R1 lo exige | Tras medición |
| 3 | V | Sin escritores activos |

## 6. Contrato de delegación

Raíz absoluta, archivos propios exactos, sin comentarios nuevos ni `as any`, sin dependencias/config, sin commit/push, sin `sudo`, sin servidores salvo indicación, Node 22 en `/home/xod/.hermes/profiles/orchestrator/cache/scratch/node-v22.23.3-linux-x64/bin`, Python `env -u PYTHONPATH -u PYTHONHOME UV_NO_SYNC=1 .venv/bin/python`. Informe ≤250 palabras en español con RED/GREEN reales y rutas.
