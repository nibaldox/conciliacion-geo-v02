# Continuidad para agentes de codificación

Actualizado el **7 de octubre de 2026**, zona **America/Santiago**. Este documento sintetiza el código y la bitácora local; no certifica una release ni una suite ejecutada hoy.

## Última hora — estabilización web publicada (7 de octubre de 2026)

- La rama **`wip/web-stabilization-2026-10-07`** (remota, en `https://github.com/nibaldox/conciliacion-geo-v02`, pública) traslada el árbol de la fase de estabilización web para continuar en otro equipo; `main` local permanece en `cc8b95c`. La publicación fue autorizada puntualmente por el usuario; no es un permiso permanente de push ni de despliegue.
- **Handoff portátil (leer primero): `docs/CONTINUAR_WEB.md`** — estado verificado con límites, trabajo de navegador pendiente, puesta en marcha en un PC nuevo y comandos de reanudación.
- Resumen de esa fase (histórico, no re-ejecutado hoy): backend 2447 passed / 8 skipped sobre el árbol certificado por hash; frontend Node 22 480/480 con cobertura obligatoria al 100%; revisión estática del árbol PASS. La validación de navegador quedó **parcial** (12/15 E2E seleccionados; 3 specs con expectativas desactualizadas; 1 timeout por triajar; `project-entry` sin correr; PWA A/B y offline sin ejecutar) y el CI remoto no se ejecutó: **no es una release**.
- Alcance vigente: solo web (sin Streamlit/Electron/CLI). El material histórico de más abajo se conserva tal cual.

## Leer al retomar

1. Leer `AGENTS.md` y el pedido actual del usuario; estos determinan el alcance autorizado.
2. Leer `README.md` para capacidades, ejecución y reglas de evaluación.
3. Usar este archivo como mapa del estado y de los pendientes.
4. Consultar `docs/CONTINUAR_LOCAL.md` por fecha. Su encabezado dice 3 de octubre, pero las entradas más recientes están al final y corresponden al **4 de octubre**. Contiene pausas, preferencias de delegación y PID históricos: no tratarlos como órdenes nuevas ni estado vivo.
5. Revisar `git status --short` y el diff antes de editar. Confirmar archivos, entornos y procesos actuales; no asumir que un servidor sigue activo porque aparece en la bitácora.

La primera tarea del 7 de octubre fue **documentación**: actualización de README, creación de este handoff y enlace desde AGENTS. Después, el usuario pidió consolidar todos los cambios en Git local y usar `gh` para obtener la identidad. Esa solicitud autoriza el commit local; no autoriza por sí sola ejecutar el backlog, reprocesar datos reales, cerrar procesos, publicar o retomar empaquetado.

## Estado del workspace

- Rama de consolidación: `main`; base anterior al commit del 7 de octubre: `2c67e3a` (`fix(streamlit): harden dashboard achievement display`, 31 de agosto de 2026). Consultar `git log -1` para el HEAD actual.
- Se consolidaron los cambios acumulados en dominio, API, frontend, pruebas, workflows y documentación, incluidas las capturas de `docs/design/`. Verificar `git status --short` al retomar; no usar `reset`, `clean` o restauraciones generales.
- Las funcionalidades recientes están en el árbol local. No se comprobó que estén en el remoto, Pages, Render o un portable distribuido.
- La prioridad registrada el 4 de octubre es **finalizar la versión web**. El nuevo empaquetado Electron queda pospuesto hasta que el usuario lo retome.
- Entorno Python local: `.venv/Scripts/python.exe`. Se observó Node disponible mediante un runtime de Codex; npm/Python globales pueden faltar en PATH. Localizar runtimes, no fijar rutas temporales de otra sesión.
- Evidencia local en `data/local-review-logs/` y `data/web-dev/`; ambos quedan fuera de Git por `data/`. Las capturas de `docs/design/` se incluyeron en el commit local. Otro clon no dispondrá de los datos y logs ignorados: verificar existencia antes de depender de ellos.
- Se excluyeron cachés de IA, pnpm, Vite, pytest y salidas Playwright mediante `.gitignore`. Se verificaron sintaxis Python, JSON y whitespace del contenido a confirmar. No se repitieron suites funcionales, no se modificó SQLite ni se reiniciaron servidores. El commit usa la cuenta `nibaldox` identificada con `gh` y su correo noreply de GitHub; no se hizo push.

## Restricciones que debe conservar el siguiente agente

- `app.py` y `ui/` están protegidos. La excepción `ui/modulo_tronadura/` solo permite adaptadores/presentación; dominio en `core/`.
- Preservar la API legacy. Si un símbolo está en `core/__init__.py::__all__`, importarlo desde `core`; los demás desde su submódulo.
- Usar `build_reconciled_profile_v2` para código nuevo. El retorno legacy de tuplas continúa disponible con `DeprecationWarning`.
- Código y docstrings en inglés; UI en español y traducciones en `web/src/locales/es.json` **y** `en.json`. Sin comentarios nuevos de código salvo petición.
- Metros, grados y porcentaje; X Este, Y Norte, Z Elevación; azimut horario desde Norte.
- Mantener `value + unit + status + source + assumptions + warnings` en magnitudes sensibles. Datos no medidos permanecen nulos/con diagnóstico; no convertirlos en cumplimiento, cero o medición válida.
- No inferir altura de banco de 15 m ni explosivo ANFO. La altura es atributo del evento y las convenciones/unidades deben confirmarse.
- Mantener Cesium en `web/public/Cesium/`; no añadirlo como dependencia npm. Estilos con tokens del tema y Tailwind.
- No mezclar npm/pnpm sobre las dependencias instaladas. Una sesión anterior movió paquetes a `.ignored` antes de fallar; se restauraron. Comprobar el entorno antes de reinstalar.
- Confirmar propiedad y autorización antes de cerrar procesos. Los PID de la bitácora ya no acreditan propiedad. Usar datos y perfiles aislados para QA.
- Commits convencionales, sin `Co-Authored-By` ni atribución IA. No confirmar o publicar todos los cambios acumulados sin revisar su alcance.

## Qué está implementado y dónde continuar

| Área | Implementación y archivos relevantes | Regresiones/evidencia |
|---|---|---|
| DXF de superficies | `core/dxf_import.py`, `core/mesh_handler.py`, `api/dxf_uploads.py`, `api/routers/meshes.py`, `api/database.py`, `api/schemas.py`, `web/src/components/mesh/DxfImportDialog.tsx`, `MeshUpload.tsx` | `tests/test_dxf_import.py`, `tests/api/test_dxf_upload.py`, `test_dxf_pipeline.py`, `web/e2e/dxf-upload.spec.ts`; guía `docs/DXF_SUPERFICIES.md` |
| Corte y recuperación | `core/section_cutter.py`, `core/config.py`, `api/routers/process.py` | `tests/test_section_cutter.py`, `tests/test_api.py`; conservar el wrapper legacy y los avisos por superficie |
| Perfil conciliado | `core/profile_extract.py`, `core/profile_compliance.py`, serializers de `api/routers/process.py` | `tests/test_reconciled_profile_orientation.py`, `tests/test_reconciled_profile_serialization.py` |
| Matching e identidad | `core/profile_compliance.py`, `web/src/components/results/ProfileView/domain/` | `tests/test_comparison.py`, `tests/test_comparison_identity.py` y tests del dominio web |
| dH y mapa horizontal | `core/horizontal_deviation.py`, `api/routers/meshes.py`, `api/routers/process.py`, `web/src/utils/horizontalDeviation.ts`, `web/src/components/results/HorizontalDeviation*`, `Mesh3DViewer.tsx` | `tests/test_horizontal_deviation.py`, `tests/test_horizontal_heatmap.py`, `web/e2e/horizontal-deviation.spec.ts` |
| Puntajes y filtros | `core/reconciliation_summary.py`, `api/routers/export.py`, `Dashboard.tsx`, `BenchFilter.tsx`, `CompliancePlanView.tsx` | `tests/test_reconciliation_summary.py`, `tests/test_export_plan_view.py`, `web/e2e/compliance-plan.spec.ts` |
| Caché y estados de carga | `web/src/api/hooks.ts`, `ProfileView/presentation/ProfilesGrid.tsx`, `ProfileView.tsx` | `web/src/api/hooks.profiles.test.tsx`, `ProfilesGrid.test.tsx`, `ProfileView.selection.test.tsx` |
| Perfil, inspector y plano | `ProfileView/presentation/ProfileChart.tsx`, `BenchInspector.tsx`, `BenchTable.tsx`, `ProfilePlanThumbnail.tsx`, `planGeometry.ts` | Tests de presentación y `web/e2e/profile-scale.spec.ts` |
| Temas y controles | `web/src/stores/theme.ts`, `web/src/styles/globals.css`, `web/src/components/layout/`, `web/src/components/ui/ProjectControls.tsx` | Tests de layout/utils y `web/e2e/project-entry.spec.ts` |
| Tronadura | Dominio `core/calculo_tronadura.py`, `blast_*`, `explosive_properties.py`; adaptadores API y `BlastUploader.tsx` | Tests de procesamiento/procedencia; `web/e2e/dashboard-blast-upload.spec.ts` |
| Energía 3D | `core/blast_simulation/`, `api/routers/simulations.py` | Contratos científicos y auditorías Fase 2; `docs/BLAST_ENERGY_SIMULATION_PHASE_2.md` |
| Informes e IA | `core/report_generator.py`, `core/pdf_report.py`, `core/ai_v2/`, `web/src/components/export/` | `web/e2e/export-report-markdown.spec.ts`, `docs/MIGRATION_AI_V2.md` |
| Plotly bajo demanda | `web/src/components/charts/Plot.tsx`, `web/src/types/plotly-cartesian.d.ts`, `web/vite.config.ts` | `docs/MEJORAS_LOCAL.md`; ampliar el runtime si se añade un tipo de gráfico ajeno al bundle cartesiano |
| Portable | `entry_api.py`, `conciliacion-api.spec`, `electron/main.js`, `electron/builder.config.js`, workflows | Artefactos previos en `dist-portable/`; empaquetado nuevo pospuesto |

Las rutas de frontend abreviadas se resuelven bajo `web/src/components/results/`, salvo que se indique otro directorio. Para nombres completos usar `rg --files`.

## Contratos geométricos y de cumplimiento

- Altura/ángulo conservan tres estados: `CUMPLE`, `FUERA DE TOLERANCIA` hasta 1,5× el límite, `NO CUMPLE`. La berma cumple al alcanzar el mínimo configurado.
- Puntaje del banco `MATCH`: **berma 60 + altura 30 + ángulo 10**; puntaje del perfil = promedio de sus MATCH, aprobado desde **70**. Puntaje global = promedio de perfiles evaluables con igual peso. Sin datos evaluables: `SIN DATOS`.
- `MISSING`/`EXTRA` no entran al promedio. Filtrar bancos exige recalcular puntajes y colores del plano en UI/export; no reutilizar un puntaje global sin filtrar.
- El matching separa elegibilidad vertical del ranking horizontal; ventana de cota media estrictamente menor que `DETECTION.gap_match_threshold` (8 m por defecto). Conserva orden monotónico. No relajar ese contrato para ocultar bancos sin pareja.
- `bench_num` identifica diseño; `bench_num_topo` identifica topografía. No emparejar por número ni unir MISSING a un banco real ambiguo.
- Perfiles rich siguen recorrido físico de cresta a pata; arrays legacy conservan su contrato de orden. No usar el piso extendido como pata física al calcular dH.
- Corte: recortar primero al dominio de la sección, analizar conectividad después. La recuperación máxima es `min(resolution, DETECTION.max_profile_reversal_repair)`; el default del límite es 0,1 m. Preservar cotas y verticales; avisar `minor_profile_reversal_normalized`.
- Orígenes XY/XYZ finitos son válidos; usar XY para el plano vertical. Rechazar formas de 1 o 4 componentes y valores no finitos.
- dH = `(dTopo - dDiseño) * sign(dCresta - dPata)` a igual cota. Positivo sobreexcavación, negativo faltante; muestras 20/50/80% desde la pata de diseño. Medición independiente del matching; requiere cruce único.
- El heatmap conserva ausencia/ambigüedad con `deviation` nulo, sin patch medido. Los tramos entre cortes compatibles se interpolan; no extrapolar. Sector vacío `""` es seleccionable y se distingue de `null`.
- Query key de perfil incluye ambos IDs de malla; al completar reproceso, invalidar `['profile']`. No sustituir un error terminal por spinner indefinido.
- El motor de energía es un modelo comparativo no calibrado; no presentar su campo como daño/PPV/estabilidad. Preservar unidades, bloqueo del modo absoluto ante datos faltantes y aislamiento de sesión.

## Validación conocida y sus límites

Resultados provenientes de `docs/CONTINUAR_LOCAL.md`, **no ejecutados nuevamente el 7 de octubre**:

| Fecha | Resultado | Límite |
|---|---|---|
| 3 oct. | Backend: 2.307 recopiladas, 2.301 aprobadas, 5 omitidas y 1 fallo inicial de ambigüedad en heatmap | Arreglo posterior con focalizadas correctas; suite completa no repetida |
| 3 oct. | Frontend 466/466; dominio 100%; pipeline sintético aprobado | Anterior a cambios del 4 oct. |
| 4 oct. | Frontend 471/471 en 54 archivos; dominio 122/122 al 100%; TypeScript/ESLint correctos | Última suite web completa registrada, anterior a recuperación final |
| 4 oct. | Recorte: core 34; API 4 y heatmap 8; hooks/grilla 7 aprobadas | Etapa previa al parche final de retrocesos |
| 4 oct. | Mapa XY/XYZ: heatmap 10/10 y consulta real HTTP 200 | Inspección visual del overlay pendiente |
| 4 oct. | Recuperación final: cutter 36, API/recarga/heatmap 3, ProfileView 7 aprobadas | TypeScript y ESLint dirigido; sin build portable ni revisión visual final |

En la revisión documental del 7 de octubre se comprueban enlaces locales, coherencia con el código/configuración y whitespace del diff. No inferir que los recuentos históricos equivalen al total actual.

### Casos reales registrados para revisar

No reutilizar una sesión por UUID copiado de una entrada vieja: identificar primero la sesión actual y sus superficies/configuración.

- Caso de 28 secciones tras recorte: 110 comparaciones, diseño extraído en 28/28 y topo en 28/28; S03/S10/S12/S26 respondieron con 631–632 puntos topográficos y sin avisos. La inspección visual final de grilla quedó pendiente.
- Consulta de mapa con 70 orígenes XYZ: 2.930 celdas, 1.737 medidas y 1.193 no medidas; HTTP 200. No constituye verificación del overlay renderizado.
- Caso más reciente de 35 secciones: 103 filas después del reproceso. S26: 430 puntos raw/117 conciliados; S30: 426/111. Ambos: 2 bancos topográficos, 2 MATCH + 1 MISSING y aviso recuperable. Debe seguir visible el banco sin pareja.
- Configuración de ese caso de 35 secciones: resolución 0,1 m, umbral cara 28°, berma 5°, altura ±2 m, ángulo ±5°, berma mínima 7 m, inter-rampa/global ±5°. Son valores de esa sesión, **no nuevos defaults**.

## Pendientes, en orden sugerido para una futura tarea autorizada

1. **Revisión visual final web.** Recargar la página para descartar caché previa y verificar grilla/detalle de S03/S10/S12/S26 y, en el caso correspondiente, S30. Criterio: líneas diseño/topo presentes cuando el DTO tiene puntos, escala H=V, aviso recuperable legible, MISSING explícito y estados de error/reintento correctos.
2. **Overlay horizontal real.** Verificar render de sectores con nombre y sin sector, orígenes XY/XYZ, cambio de banco, leyenda y celdas no medidas. Criterio: selección e indicadores coherentes con payload, sin huecos coloreados como mediciones válidas y sin errores JavaScript.
3. **Validación integral del código final.** Repetir backend excluyendo OpenBlast, pipeline, frontend completo con cobertura, typecheck, lint, build web y E2E relevantes. Registrar fecha, comando, counts, skips/fallos y logs. No declarar todo verde con solo pruebas focalizadas.
4. **Archivos reales DXF/STL.** Validar capas/unidades y equivalencia del flujo concreto del usuario; las fixtures sintéticas no certifican todo exportador ni rendimiento de archivos reales grandes.
5. **Coherencia de despliegue antes de publicar.** Revisar los puntos detectados por lectura del código que se enumeran abajo. No se modificaron en esta tarea.
6. **Portable cuando el usuario lo retome.** Generar web sin PWA, sidecar y Electron con el código final; smoke completo aislado, archivos empaquetados/hash, persistencia y liberación del puerto. No presentar los outputs intermedios XYZ como release final.

### Inconsistencias de configuración para revisar

- `CONCILIACION_MAX_UPLOAD_MB` aparece en `render.yaml` y documentación histórica, pero no se encontró su lectura en `core/` o `api/`; el middleware HTTP y la inspección DXF usan `DEFAULTS.max_upload_mb` (500). No afirmar que cambiar esa variable modifica el límite actual.
- `render.yaml` declara `CONCILIATION_LOG_FORMAT` y `CONCILIATION_WORKERS`; `core/config.py` lee `CONCILIACION_LOG_FORMAT` y `CONCILIACION_WORKERS`. El prefijo no coincide. Revisar efecto antes de ajustar un despliegue.
- `deploy-frontend.yml` fija `VITE_API_URL` al host Render sin `/api/v1`; `resolveApiBaseUrl` conserva el valor y los hooks usan rutas como `/meshes`. Revisar si el host ofrece esas rutas antes de publicar; no se verificó el servicio remoto en esta tarea.
- `release.yml` busca AppImages en `electron/dist-portable/`, mientras `electron/builder.config.js` produce en `dist-portable/` de la raíz. Verificar captura del artefacto. El workflow manual `build-portable.yml` tiene un job que publica release; no usarlo como prueba inocua.
- `docs/BUILD.md`, `docs/PORTABLE.md` y algunos apartados de AGENTS conservan descripciones históricas de CI/Windows/recuentos. README describe los archivos de configuración actuales; al cambiar build, actualizar esas guías en el mismo trabajo.

Son hallazgos de documentación/inspección, no nuevas regresiones reproducidas ni autorización para desplegar.

## Comandos para retomar

Primero inspeccionar desde la raíz:

```powershell
git status --short
git diff --stat
Get-Command python,node,npm -ErrorAction SilentlyContinue
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -in 8000,5173,5174,57890,57991
```

No cerrar listeners solo por aparecer en esta lista. El último estado observado el 4 de octubre era API 8000 con `CONCILIACION_DATA_DIR=data/web-dev`, Vite 5173 y una instancia portable en 57890; **no se consultó su estado actual**.

Si se requiere un entorno nuevo, activar `.venv`, usar un directorio de QA nuevo y un puerto libre. El arranque habitual de web/API está en README; para trabajar con una sesión real pedir o seguir la autorización específica y preservar sus ajustes.

Regresiones backend focalizadas, desde la raíz:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_section_cutter.py tests/test_horizontal_deviation.py tests/test_horizontal_heatmap.py tests/test_comparison.py tests/test_comparison_identity.py tests/test_reconciled_profile_orientation.py tests/test_reconciled_profile_serialization.py tests/test_reconciliation_summary.py -v --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_api.py -k "profile_warnings or xyz_origin_profiles or profiles_success or profiles_out_of_range" -v --tb=short
```

Validación integral desde la raíz y luego `web/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v --tb=short --ignore=tests/test_openblast.py
.\.venv\Scripts\python.exe -X utf8 test_pipeline.py
Set-Location web
npm run test -- --coverage
npx tsc --noEmit
npm run lint
npm run build
npx playwright test
```

Playwright estándar puede iniciar o reutilizar API/Vite; aislar la base mediante `CONCILIACION_DATA_DIR` antes de ejecutarlo. La configuración Edge local `playwright.horizontal.config.ts` apunta a 5174 y requiere un servidor ya disponible. Algunas pruebas de integración web utilizan `uv`; comprobar sus prerrequisitos sin eliminar tests para conseguir un verde aparente.

Para la futura fase portable, las tres variables de build son `VITE_PWA=false`, `VITE_BASE=/`, `VITE_API_URL=/api/v1`; configurar todas antes de compilar. `entry_api.py` deriva y sobrescribe su directorio de datos desde APPDATA/XDG_DATA_HOME, por lo que un smoke del binario exige aislar ese perfil, no solo `CONCILIACION_DATA_DIR`.

## Cómo dejar el siguiente relevo

Actualizar este archivo con fecha/zona, resultado concreto, archivos editados, pruebas realmente ejecutadas y limitaciones pendientes. Conservar la evidencia histórica en `CONTINUAR_LOCAL.md`; no copiar PID o autorizaciones como permanentes. Vincular cualquier artefacto y comprobar que exista; indicar si queda ignorado por Git o si fue publicado. Diferenciar siempre implementación local, verificación por API, revisión visual y distribución final.
