# Continuidad para agentes de codificación

Actualizado el **17 de octubre de 2026**, zona **America/Santiago**. Este documento sintetiza el código y la bitácora local; no certifica una release.

## Reanudación — 18 de octubre (usuario: "continua")

- Pausa del 17/10 23:02 levantada por solicitud explícita. Orden T12 → T13 → T14; sin commit/push/despliegue.
- Verificado al retomar: 457/457 hashes idénticos al snapshot `pause-20261017-230219/`; `t12-db-second-diagnostic/` no existe (el diagnóstico interrumpido no dejó parciales); puertos 8000/5181/5173 libres; HEAD `7348b8c`.
- Paso actual: diagnóstico (sin cambios de producción) del `database is locked` restante en arranque paralelo real con la factory y rutas reales, en datos aislados. Dos subagentes en paralelo: reproducción dinámica y auditoría estática de ciclo de vida de conexiones/transacciones.
- **Diagnóstico cerrado (coordinador, `t12-db-second-diagnostic/`):** las matrices iniciales del subagente usaban instrumentación pesada y potencia insuficiente (`synchronous=OFF` 0 fallos en una sola corrida; baseline también dio 0–3 en algunas). Harness mínimo `harness_v9_stacks.py`: API real en proceso, cliente en proceso separado, watchdog >2,5 s con `eu-stack` nativo. **Pilas nativas:** el tenedor del lock está siempre en `fsync`: (1) `pagerWalFrames` del COMMIT (sync FULL o sync de cabecera al reiniciar WAL) y (2) `sqlite3WalClose → sqlite3WalCheckpoint` cuando se cierra la última conexión (checkpoint + borrado de WAL con lock exclusivo). Los demás hilos esperan en `sqliteDefaultBusyCallback` hasta 5 s. Filesystem `/home` btrfs (zstd); `chattr +C` no lo resuelve.
- **Matriz factorial (12 000 peticiones c/u, cliente externo):** baseline 209 y 123 × 500; solo `synchronous=NORMAL` 278 × 500; solo conexión persistente 72 y 116 × 500; **conexión persistente + NORMAL: 0/12 000 y 0/12 000, latencia máx 0,098 s**, pared 21 s frente a 86–238 s. Ambas medidas son necesarias. Refutadas además: instrumentación como causa (harness mínimo reproduce), nocow, snapshot, pragma WAL, event loop.
- Propuesta aprobada por el usuario (trade-off de durabilidad aceptado): `PRAGMA synchronous=NORMAL` en `get_connection` + una conexión centinela abierta durante el lifespan (cerrada al apagar). NORMAL en WAL no corrompe ni pierde datos ante caída de la app; ante corte de energía/caída del SO puede revertir las últimas transacciones confirmadas.
- **Fix aplicado (`deleg_85f388b1`)**: `api/database.py` (`synchronous=NORMAL`, `open_sentinel`/`close_sentinel` con lock, rebind por DB_PATH) y `api/main.py` (sentinel tras `init_db`, cierre último en `finally` anidado). Test nuevo `tests/api/test_sqlite_durability.py` (4 casos, RED 4 → GREEN). Logs `t12-db-fix/`.
- **Verificado por el coordinador:** objetivo 62 PASS; suite Python completa 2533 → **2537 passed / 12 skipped** (log del worker). Estrés con código de producción sin parches del harness: **0/12 000 y 0/12 000**, latencia máx 0,097 s, `-wal` limpio al apagar. API real :8000 + Vite :5181 (datos `t12-runtime-20261018-dbfix`): probe de arranque paralelo **1200/1200 200**, máx 0,205 s.
- **T12 CERRADA: smoke combinado 11/11 PASS dos veces consecutivas**, 0 retries, 0 flaky, consola estricta y API reales (`t12-dbfix-smoke/`: `browser-report-run1.json`, `smoke-run1.log`, `smoke-run2.log`, `run2/`). Servicios propios cerrados (Vite requirió TERM a npm/node propios verificados por cwd); puertos 8000/5181/5173 libres.
- Siguiente: T13 (bordes y coste de interacción) y revisión independiente del fix SQLite, en paralelo; después T14.
- **T13 cerrada (`deleg_179caeda`)**: nuevos `sections/__tests__/curveSelection.edges.test.ts` (10) y `mesh/__tests__/curvePicking.edges.test.ts` (7), sin cambios de producción y sin defectos reales. Coordinador: 17/17. Coste por movimiento (Node 22, jsdom): 1000 candidatos 0,07 ms; activa + 21 000 ajenos 0,88 ms med / 2,1 ms p95; 100 000 candidatos 4,3 ms. Observación: el picking proyecta todos los candidatos antes de filtrar por curva activa; no se optimiza sin necesidad demostrada (lo evalúa el revisor de calidad de T14). Evidencia `t13-edges/`.
- **Revisión fix SQLite: PASS** sin bloqueantes; comprobado empíricamente que la conexión centinela no retiene transacción y un checkpoint PASSIVE completa 609/609 frames. Sugerencias menores no aplicadas: posible fd abierto si el arranque fallara entre `open_sentinel` y `yield`, y cierre de `conn` si fallara `SELECT 1`; documentar durabilidad (la regla de no añadir comentarios lo deja en HANDOFF).
- **Gates T14 del coordinador (`t14-gates/`)**: frontend **721 / 79 archivos**, dominio 100% (194/194), `tsc -b --force`, ESLint y build+PWA PASS; Python 2537/12 skip; smoke 11/11 ×2 (sin cambios de producción posteriores, solo pruebas). Dos revisores de solo lectura (especificación y calidad) en curso, `deleg_6b8a1daf`.
- **T14 CERRADA — plan de selección continua T01–T14 completo.** Revisión de especificación **PASS** (12/12 criterios con evidencia; `core/section_cutter.py` y `api/routers/sections.py` sin cambios, comprobado por el coordinador). Revisión de calidad **PASS** (precisión UTM restando centro, CSS px sin DPR, Escape/listeners/dispose correctos, E2E sin anclas sembradas). Manifiesto final `t14-gates/final-source-manifest.json` (74 archivos). Sin commit/push/despliegue.
- **Pendientes no bloqueantes (no iniciados):** (1) medir en navegador el coste de oclusión por `pointermove` (`curveScenePicking.ts:64,75`: `Raycaster` nuevo + `intersectObjects(topo)` sin BVH; umbral de búsqueda derivado de `camera.far` ≈466 u.m., `:260`) antes de cualquier optimización; (2) `Mesh3DViewer.tsx:134` usa `previewRef` declarado en `:279` (subirlo); (3) handlers/snapshot/colores recreados por render; (4) `cancel`/`generated` devuelven estado nuevo aunque ya esté vacío; (5) ancla obsoleta sin limpieza proactiva si el formulario está desmontado (no es generable); (6) marcador en Float32 vs payload double (~1e-4 m); (7) dos robusteces menores del centinela SQLite. Validación con el archivo real del usuario sigue recomendada.

## Estado previo — PAUSADO por el usuario, 17 de octubre, 23:02 −03:00

- El usuario pidió terminar por hoy. **No reanudar diagnóstico, ediciones, pruebas, aprobaciones ni T13/T14 hasta una nueva solicitud explícita.** Esta pausa prevalece sobre las autorizaciones anteriores y cualquier resultado o aviso de proceso que llegue tarde.
- Snapshot `data/qa-curve-selection/pause-20261017-230219/`: **457 fuentes**, todas idénticas al último manifiesto congelado; no se descartó código ni evidencia. Branch `main`, cambios locales sin commit/push/despliegue.
- **Interrupción confirmada** de `sa-0-a99666ac` / `deleg_cdb8d944`: estado final `interrupted`, cuatro llamadas; terminó esperando respuesta del modelo. Entrega parcial sin diagnóstico concluido ni GREEN verificable. No se inspeccionaron ni ejecutaron parciales tras la pausa; preservarlos bajo `t12-db-second-diagnostic/` si existen para una reanudación explícita. Esta notificación tardía se registra sin retomar trabajo.
- **Servicios QA propios cerrados y verificados:** API `proc_6d9f00932e48`; Vite `proc_b58731c8c7cb`. Primer kill de Vite incompleto; se reconfirmó cwd/comando y envió TERM al Node propio 7592. Verificación final: 7533/7592/19178 ausentes y ningún listener en 8000/5181/5173. No tocar procesos ajenos ni reutilizar esos PID al retomar.
- Estado: T01–T11 cerradas; **T12 pausada e incompleta** por `database is locked` en el arranque concurrente real; T13/T14 pendientes. Layout y fixtures de fuentes tienen doble revisión PASS; gates frontend **704/77**, dominio100 y tsc/lint/PWA; API aislada **58 PASS**; probe fuentes **32/32**. Último navegador real **9/11 anterior a DB/fuentes**; el probe posterior de boot falló y el nuevo smoke completo no se ejecutó.
- Al retomar: leer el resultado final de interrupción, inspeccionar evidencia parcial, comparar hashes con este snapshot y diagnosticar el bloqueo con factory/rutas reales aisladas antes de cualquier nuevo fix. Revalidar entorno/servicios propios desde cero; no confundir la prueba de UNIQUE/cierre aprobada con una solución demostrada de todos los locks.

## Historial — reanudación del usuario, 17 de octubre, 21:57 −03:00

- El usuario pidió retomar y continuar el proyecto. Se levanta la pausa de las 19:04; se conserva el orden T12 → T13 → T14, sin commit/push/despliegue. Los 450 hashes actuales coinciden con el snapshot de pausa; solo CSS y legado difieren del último árbol verificado. Nueva línea base y copias en `data/qa-curve-selection/t12-resume-20261017-215744/`.
- El runtime temporal de Node 22 ya no existía y el sistema usa Node 26.11.1. Se restauró Node **22.23.3** únicamente en el scratch del perfil, verificando SHA256 contra el manifiesto HTTPS oficial; sin instalaciones ni cambios de dependencias en el repo. Chrome y Python 3.11.15 disponibles.
- **RED central al retomar, ya superado: 2 PASS / 1 FAIL** del legado. Selector de Reset ya correcto. Fallo real en `project-entry.spec.ts:152`: extremo derecho de acción 266,46875 frente a límite 259 del contenedor. Se preserva RED en `t12-resume-20261017-215744/resume-report.json` y sus trazas/captura. No es el viejo fallo de selector ni una prueba de payload completo del tercer flujo.
- **Layout entregado (`deleg_cb0fd64b`)** y diff central verificado: solo CSS y refuerzo del legado, sin alterar goldens. Espacio horizontal insuficiente de la fila; gap/padding ajustados, altura automática para etiqueta completa, toggles ≥28 y vecino 1001 probado. Worker 3/3 y ESLint; captura 640 inspeccionada por el coordinador. Padre repitió **704/77, dominio 100%, compiler/lint/PWA PASS** y **53 API PASS**; logs `t12-resume-fixed-{frontend,api}-gates.log`.
- **Smoke central posterior: 9 PASS / 2 FAIL**, sin retries, preservado completo en `t12-resumed-attempt-01-failed/`; copia de trabajo `t12-resumed-final-evidence/`. Los tres casos del legado ampliado pasan, incluidos los bounds/texto. Ambos fallos nativos ocurren en la aserción final de consola vacía, después de geometría y POST/GET; no se descartan como flake ni se ocultan. Manifiesto previo a las nuevas reparaciones `t12-resumed-final-source-manifest.json` (450).
- **Dos clases de errores identificadas en trazas:** 500 de API en GET status/settings/sections/results, con `database is locked` en `get_or_create_session:135`; y dos fuentes WOFF2 de fonts.gstatic.com inalcanzables (CSS de Google 200). La carrera de creación de la misma sesión ya se reprodujo de forma determinista; ello no demuestra por sí solo el origen de todos los locks históricos, que requiere replay real tras reiniciar API.
- **Reparación DB entregada (`deleg_fbccb7ef`) y combinada centralmente: 58 PASS**, una deprecación. Dos hilos con SELECT ausente sincronizado producen UNIQUE en la fuente anterior; nuevo conflicto dirigido a `id` conserva al ganador, fastpath lectura y defaults, con `finally` que cierra también tras fallos INSERT/commit. Cinco regresiones reales nuevas; `None`/vacío conservan delegación. Padre retiró un comentario nuevo prohibido y repitió 58 PASS + `tokenize.COMMENT=0` + diff check. Log final `t12-db-race-coordinator-final-gates.log`. **Dos revisiones DB PASS** (`deleg_891f3a3e`) sin bloqueantes, limitadas a esa clase de carrera/cierre y a la fuente integrada. Su referencia a runtime anterior corresponde al momento de despacho, no al estado actual. No acreditan resolución del boot real, que volvió a fallar tras el reinicio posterior.
- **Fuentes entregadas (`deleg_c5f5772c`) y verificadas centralmente:** 32/32 en Chrome aislado importando el helper real; siete faces cargadas, métricas distintas de fallback, consola vacía. Padre verificó bytes/hash contra el trace y ambas licencias oficiales OFL; recuperó fuente nativa anterior desde el trace con hash de baseline y constató solo import/call/dos metadatos nuevos. Añadió el mismo helper al `prepare` legado (dos líneas), sin tocar aserciones. Gates integrados nuevos **704/77, dominio 100%, tsc/lint/PWA y ESLint E2E PASS**; log `t12-font-integrated-frontend-gates.log`. **Dos revisiones estáticas de fuentes PASS** (`deleg_c8d19700`): familias/pesos/CORS/procedencia correctos, sin interceptar API ni debilitar asserts; sugerencias opcionales no se aplican. No cambios de fuentes/CSS de producción, dependencias, timeout, esquema ni cálculos. Este PASS sigue siendo más estrecho que el replay montado pendiente.
- **Dos revisiones del delta CSS/legado recibidas: PASS** (`deleg_61b2746d`), sin bloqueantes. Confirman límites internos, etiquetas, alturas y conservación de goldens. Sugerencias no bloqueantes (longitud positiva de toggles, selector de clases, snapshot de ancho fuera del loop) no motivan refactor. Esto cierra la reparación responsive, **no** T12 completa: último smoke navegador 9/11 anterior a DB/fuentes, y el posterior probe de boot volvió a fallar.
- **Nuevo bloqueo real tras reinicio:** detenido el servicio propio anterior y arrancado `proc_6d9f00932e48` (API observado 19178) con datos nuevos `t12-runtime-session-font-fixed`. Salud directa/proxy 200; probe de lotes de cuatro GET concurrentes por ID nuevo compartido logró varios lotes 200 y luego volvió a registrar `database is locked:135`; cliente terminó por timeout 15 s. **No se ejecutó el nuevo smoke 11.** Config preparada `t12-session-font-final-evidence/`, resumen fallido explícito allí; log íntegro del proceso disponible por su handle. Fuente congelada en `t12-session-font-final-source-manifest.json` (**457**); las 450 previas solo difieren en getter DB y dos specs esperados. Import nuevo confirma ON CONFLICT en bytecode y SQLite 3.53.1, sin afirmar inspección del bytecode vivo.
- **Diagnóstico acotado, sin fixes adicionales (`deleg_cdb8d944`)**: usar factory `db.get_connection` real, no su copia del test, y luego un TestClient/lifespan compartido con las cuatro rutas en DB aislada. Capturar BUSY/BUSY_SNAPSHOT y transacciones si reproduce; no tocar API/DB vivas, fuentes de producción, timeouts ni esquema. El fix de UNIQUE/cierre sigue respaldado por 58 tests, pero no se considera solución demostrada del boot real.
- QA actual: Vite propio 5181 (`proc_b58731c8c7cb`, Node observado 7592), API propia 8000 `proc_6d9f00932e48`. Comprobar propiedad antes de acciones futuras; nunca usar PID históricos como autorización. Revisiones DB/fuentes integradas; únicamente diagnóstico aislado `deleg_cdb8d944` pendiente, sin autorización para cambiar producción ni los servicios propios.
- T12 sigue abierta por los errores de consola/DB/red, no por un verde integral actual. T13/T14 pendientes; no se ha medido rendimiento ni cambiado geometría/cálculos. La ampliación DB es mínima y justificada por 500 reales, no conveniencia del frontend.

## Historial — pausa del usuario, 17 de octubre, 19:04 −03:00

- El usuario pidió salir y continuar después: **no retomar ediciones, pruebas, aprobaciones ni T13/T14 hasta nueva solicitud explícita**. Esta pausa prevalece sobre la autorización y el reenvío de aprobación anteriores.
- **Interrupción confirmada** de `sa-0-d6e90530` / `deleg_0b53d55b`: estado final `interrupted`, 31 llamadas; se detuvo esperando respuesta del modelo. Sin GREEN de cierre. Su última salida menciona un selector incorrecto (`/RESET SELECCI/` frente a «RESTABLECER SELECCIÓN») y expresa intención de corregirlo/repetir, pero no acredita ejecución posterior. Al retomar, inspeccionar el parcial y ese selector antes de ejecutar la regresión. Se registra este resultado tardío sin reanudar trabajo.
- Se conservan los parciales de `web/src/styles/globals.css` y `web/e2e/project-entry.spec.ts`. Snapshot durante la solicitud de pausa: `data/qa-curve-selection/pause-20261017-190446/`, manifiesto de **450 fuentes**, copias de ambos archivos y `pause.json`. Son los únicos dos archivos distintos frente al árbol T12 previamente verificado; no se revirtieron cambios.
- Último árbol centralmente verificado, **anterior a estos parciales**: frontend **704/704**, dominio obligatorio 100%, compiler/lint/PWA; API **53 PASS**; navegador **11/11**, con lectura HTTP posterior exacta. Ese verde no certifica la reparación layout2 actual. T12 sigue abierta por la corrección READY entre alturas; T13/T14 pendientes, solo preparación de lectura.
- **Servicios QA propios cerrados y verificados:** API `proc_f9fa465f5f6f`; Vite `proc_74e7cd688c36`. El primer cierre de Vite fue incompleto; tras reconfirmar propiedad se envió TERM únicamente a npm 12528 / Node 12560. Comprobación posterior: ambos PID ausentes y ningún listener en 8000/5181/5173. No se terminaron procesos ajenos. Estos PID son históricos, no reutilizarlos al retomar.
- Al reanudar: leer resultado de interrupción, comparar hashes actuales con snapshot y manifiesto verificado, inspeccionar parciales sin descartarlos y ejecutar primero la regresión de layout ampliada sobre fuentes estables. Solo después repetir gates, revisión del delta y avanzar en orden. Sin commit, push ni despliegue.

## Historial — verificaciones autorizadas a las 18:32 −03:00

- El usuario autorizó y aprobó las solicitudes antes bloqueadas. **Gates integrados centrales PASS:** frontend **704/704 en 77 archivos**, dominio obligatorio **100%**, `tsc -b --force`, ESLint y build PWA; API curvas/settings/cutter **53 aprobadas**, una deprecación Starlette/httpx. Tres avisos conocidos de navegación JSDOM, no fallos. Logs `data/qa-curve-selection/t12-integrated-{frontend,api}-gates.log`.
- **Navegador central combinado: 11/11 PASS, sin retries/skips/flaky**, cuatro casos nativos en DPR 1 y 2 más tres de legado. Config, script, reporte JSON, log y `coordinator-summary.json` bajo `data/qa-curve-selection/t12-final-evidence/`. No se ejecutó cobertura/build durante este smoke. Manifiesto `t12-integrated-source-manifest.json`: **450 fuentes**, sin cambios tras gates/smoke; frente a T11 solo cambió CSS de producción, además de los dos specs de QA.
- Métrica B2 ya corregida y repetida centralmente: A-centro a B-centro **10,180886 px CSS**, igual a settle; B con profundidad positiva, dentro del Canvas y sobre el Canvas real antes del clic negativo. Error de marcadores tras zoom **0,044647306 px CSS** en ambos DPR. Se mantienen payload XY exacto, orden invertido y media separación desde el nuevo inicio.
- **Lectura HTTP independiente del coordinador:** los dos GET posteriores devuelven seis secciones y coinciden exactamente con el campo `sections` del POST correspondiente. Evidencia `independent-api-readback.json`. No comparar con el array enriquecido `apiReadback.sections` de diagnósticos ni con el wrapper completo del POST: los dos primeros intentos de ese chequeo adicional usaron representaciones incorrectas y se corrigieron tras leer `curve-selection.spec.ts:1355–1358`, sin cambiar la aplicación.
- **Revisiones T12 recibidas (`deleg_04e3d7a8`):** selección/payload y calidad PASS, pero cierre **BLOCK por layout READY**: overflow real 74 px a 1280×721, 27 px a 1366×768 y 19 px a 1280×640. JSON y probe en `t12-review-spec/`, leídos por el coordinador. El 11/11 anterior no medía estos estados listos. El probe buscó Reset con un nombre equivocado y su caja es null; no usarlo como prueba de recorte de ese botón ni confundir visible en viewport con visible dentro del contenedor.
- **T12-layout2 delegada (`deleg_0b53d55b`):** un escritor solo sobre `globals.css` y `project-entry.spec.ts`, con regresión READY de 640 a 1000 px y ambos lados de breakpoints, acciones medidas dentro del contenedor, sin relajar las aserciones originales. Medirá reserva de navegación y posibles márgenes Tailwind 4 acumulados; ninguna modificación de geometría, parámetros o handlers. Los gates anteriores describen la fuente previa a esta reparación y se repetirán sobre su entrega estable. No ejecutar otro navegador, cobertura ni build mientras edita.
- T13 solo tiene preparación de lectura: inventario previo y contrato exacto del futuro probe (`deleg_8a6d2811`). Sin pruebas nuevas ni rendimiento ejecutados; T13 no comienza hasta cerrar T12.
- API QA anterior finalizó (`agent_close`, código −15). Nueva API propia `proc_f9fa465f5f6f`, PID inicial 161873, puerto 8000, datos frescos `data/qa-curve-selection/t12-runtime-20261017-183440`; Vite previo 5181, Node 12560. Health directo/proxy y HTML HTTP 200 antes del smoke. Comprobar propiedad/estado antes de cualquier acción futura; no terminar procesos ajenos.
- El lock SQLite histórico sigue documentado: código DB no cambió y el escritor que lo desencadenó no está identificado. El probe artificial no reproduce la causa concreta de QA; no se amplió alcance ni se cambió timeout. La corrida central actual no registró ese 500. Sin commit, push ni despliegue; T13 y T14 pendientes.

## Historial de reanudación — 17 de octubre, 08:18 −03:00

- El usuario pidió continuar los trabajos. Se retoma la secuencia T10–T14, sin autorización de commit, push ni despliegue; la pausa previa de las 05:47 queda como antecedente histórico.
- **T10 cerrada:** coordinador **704/704 en 77 archivos**, dominio obligatorio **100%**, TypeScript, lint y build aprobados; dos revisiones independientes PASS (`deleg_25937ecd`). Resúmenes revalidados T02/contexto/curva, Escape sin robo de foco, borradores vacíos sin coerción a cero y límites UI existentes; contexto incoherente bloquea generación. La indicación de éxito de una petición anterior puede persistir tras reset/nueva selección: sugerencia no bloqueante, no se altera el guard de éxito tardío.
- Log `data/qa-curve-selection/t10-frontend-gates.log`; manifiesto `t10-source-manifest.json` con **447 archivos**. Solo cambiaron los cuatro archivos previstos de la línea base T09, más el test nuevo de feedback; aserciones originales preservadas salvo consultas de botón. Quince claves nuevas coincidentes ES/EN, y solo tres pasos de ayuda anteriores modificados.
- **T11 cerrada:** seis regresiones de API existentes, GREEN inicial sin RED inventado. Coordinador sobre archivo final: **53 aprobadas** al combinar settings/cutter, **1 aviso de deprecación de Starlette/httpx**; dos revisiones PASS. Log `data/qa-curve-selection/t11-final-api-gates.log`; manifiesto `t11-source-manifest.json` con **448 archivos**, fuentes T10 intactas. Geometría, azimut, asimetría y POST→GET exacto verificados; solo se añadió el test, sin cambios API/core.
- **T12a/b1 verificadas: 3/3 PASS**, repetidas por el coordinador. A conserva error de marcador ≤0,391384 px CSS y GET==POST con seis secciones. B1 añade hover sin confirmación (error máximo real **0,000029401 px CSS**), prioridad A frente a vecina separada 3,333870 px, clic fuera de radio sin cambio y arrastre con movimiento positivo de cámara sin elegir punto. Reset/Escape preservan contexto y borrador 25, enfocan summary al cancelar y no roban foco sin curva. Producción T11 intacta; consola/pageerrors se asertan vacíos. Evidencia B1 en `data/qa-curve-selection/t12b1-evidence/`.
- **T12b2 repetida centralmente: 8/8 PASS (58,4 s)**, cuatro casos en DPR 1/2 reales. Zoom nativo y recorrido invertido con API real; distancia relevante de B a la línea A tras zoom **10,180886 px CSS**, sin fallback. Se detectó un error adicional del reporte QA: `abCenterGapPx`/`gapAfterZoomPx` usan A al 20 % en vez del centro y registran 347,106547 px; no presentar esa cifra como separación de curvas. Corregir la medición y añadir coherencia con `gapSettledPx` antes de cerrar T12. El rechazo ya tiene una aserción independiente de distancia a la línea, pero se añadirá también precondición explícita de B en pantalla.
- **T12c ahora repetida centralmente: 3/3 PASS (8,3 s)**, incluidas aserciones finales de XY, XYZ de anclas y parámetros/tolerancias. RED previo: 35 px vacío y 75 px seleccionado a **1280×720**; la atribución anterior de 35 px a 1366×768 era incorrecta. Los probes previos registran también 19 px vacío a 1024×640 y overflow de tolerancias. `/process/results` del fixture se corrigió a `[]`, sin alterar la aplicación.
- **Reparación de layout verificada** (`deleg_e839f9a9`): solo `globals.css`, media compacta 700→720 px, espaciado y alturas de controles. Formulario y LeftSidebar idénticos por hash a la línea base; único cambio frente a T11 es CSS. Diff/check aprobados; captura `t12-layout-evidence/selected-720-after.png` inspeccionada: Generar/Reset y navegación visibles, coordenadas aún truncadas horizontalmente con su valor original intacto. Los JSON `probe-layout-out.json` y `probe-test1-out.json` contienen **mediciones previas al fix**, no presentarlos como métricas finales; el PASS posterior procede de los 3 E2E estrictos. La suite focalizada 23/23, compiler/lint del worker aún no se han repetido centralmente.
- **Incidencia SQLite observada, no descartada como flake:** el worker reportó un 500 aislado durante el smoke. Log de API verificado por el coordinador muestra `sqlite3.OperationalError: database is locked` en `api/database.py:135`, llamado desde `list_sections`. Diagnóstico de solo lectura y repro en DB nueva delegado; prohibido tocar DB/API QA vivas o modificar backend por ahora. Paralelamente se corrige la métrica B2 con RED real y replay nativo, ambos en `deleg_c492638b`.
- Fixture T12a: solo rutas GET de mallas interceptadas con geometría sintética; preparación de IDs/cámara declarada, nunca de anclas. Generación/persistencia de API reales; no acredita carga/extracción de mallas del usuario. Spec nuevo `web/e2e/curve-selection.spec.ts`; evidencia y `run-t12a.sh` bajo `data/qa-curve-selection/t12-evidence/`. Manifiesto de **450 archivos**, producción T11 intacta en esa corrida. Baseline completo preservado en `t12a-baseline/`; snapshot del spec legado en `project-entry.before.ts`, migración T12c aprobada y cierre global de T12 aún pendiente.
- Servicios QA propios: API `proc_0ca333c7ddc9` en 127.0.0.1:8000 y Vite `proc_74e7cd688c36` en 127.0.0.1:5181, base `/conciliacion-geo-v02/`, datos `data/qa-curve-selection/t12-runtime-20261017-0851`. Tras una interrupción del proveedor se verificaron de nuevo a las **12:03 −03:00**: salud directa y vía proxy HTTP 200; API PID 12512 y Node 12560 observados entonces, no son autorización para matar procesos futuros. El coordinador conserva su ciclo de vida; el worker no inicia/cierra servidores. Antes de retomar, comprobar propiedad/estado actual. No generar cobertura/build ni editar fuentes de aplicación durante QA.
- Sin commit, push ni despliegue. T12 pendiente de métrica QA, diagnóstico SQLite, gates/replay y revisión. T13 solo tiene preparación de cobertura de **solo lectura** delegada (`deleg_7f69e587`), sin iniciar pruebas nuevas ni medición; T14 pendiente.

## Continuación autorizada — T03 a T14, en orden

- El usuario autorizó continuar con todas las tareas restantes del plan `.hermes/plans/2026-10-16_182605-seleccion-continua-diseno.md`, secuencialmente desde T03 hasta T14. No se necesita volver a pedir permiso entre esas entregas; no incluye commit, push ni despliegue.
- Historial de T09: 690/690 en 76 archivos y hashes de 446 fuentes; corregidos identidad del inicio parcial y spans no transformables. Chrome aislado con JSX/CSS reales confirmó offsets −18/+18 px; su diagnóstico previo de 0/0 px no fue un RED de aserción. T10 ya quedó cerrada con la verificación más reciente del encabezado. La línea base de traducciones anterior a T10 está en `$TMPDIR/t10-locales-before.json`; el bloque 1 y dH se preservaron.
- Se mantienen fuera de alcance Streamlit, Electron, CLI y cambios científicos. Los cambios anteriores del bloque 1 y dH deben preservarse. La integración visual está en curso; todavía no está certificada con clics reales.

## 16 de octubre — T02 de selección continua, terminada y verificada

- El usuario autorizó continuar y cerrar **solo T02** del plan `.hermes/plans/2026-10-16_182605-seleccion-continua-diseno.md`. Nuevos archivos: `web/src/components/sections/curveAnchorGeometry.ts` y `web/src/components/sections/__tests__/curveAnchorGeometry.test.ts`. T03 no se inició.
- `createCurveAnchor` interpola XYZ sobre los puntos originales y calcula la distancia acumulada XY sin redondear. `projectCurveAnchor` proyecta una posición minera sobre el segmento 3D indicado, limita la fracción a `[0,1]` y reutiliza la primera función. No interpreta identificadores ni utiliza coordenadas Float32 de renderizado.
- Guardas para coordenadas y cálculos no finitos, índices enteros dentro de rango, fracción válida y longitud XY positiva. Se valida el segmento solicitado antes de normalizar: uno degenerado siempre devuelve `null`; un extremo interior pasa al siguiente segmento solo si este es válido; si el siguiente es degenerado, conserva el extremo actual. No hay saltos, renumeración ni cierre automático de estaciones en anillos.
- La primera implementación T02a se descartó por falta de RED de comportamiento y dos errores de normalización. El coordinador reprodujo el fallo real con un stub; se reimplementó y añadieron ambas regresiones. La proyección también pasó por un stub con fallo de aserción reportado por el subagente. No se presentan fallos de importación como prueba de comportamiento.
- Verificado por el coordinador sobre el árbol integrado: **20/20 pruebas T01+T02** (16 de geometría y 4 contractuales), frontend completo **605/605 en 68 archivos**, cobertura obligatoria del dominio de perfiles **100%**, `tsc -b --force`, ESLint y build web con PWA aprobados con Node **22.23.3**. La suite emitió tres avisos de navegación no implementada de JSDOM, sin fallos; no equivalen a una prueba de navegador. La cobertura del 100% corresponde al dominio obligatorio, no se afirma ese porcentaje para el helper nuevo.
- Dos revisores independientes: **PASS**, sin bloqueantes. Se comprobaron los hashes de **434 archivos fuente/pruebas preexistentes**, sin alteraciones. Los cambios anteriores del bloque 1 y dH se conservaron.
- Límites: proyección pura, todavía sin consumidores en el visor; no certifica elegibilidad del clic ni tolerancias en píxeles (T04). Segmentos sin estación XY y operaciones extremas que desbordan retornan `null`; validación y acumulación recorren los puntos, sin optimización de caché. No se repitieron backend, pipeline ni navegador porque no se modificaron sus rutas ni se conectó la interacción.
- Sin commit, push ni despliegue. **T02 cerrada.** La siguiente tarea del plan es T03 (recorte entre anclas), pendiente de autorización del usuario.

## 16 de octubre — T01 de selección continua, contrato terminado

- El usuario autorizó **solo T01** del plan `.hermes/plans/2026-10-16_182605-seleccion-continua-diseno.md`. Se crearon `web/src/components/sections/curveSelectionTypes.ts` y su prueba contractual; no se comenzó T02 ni se modificaron picking, visor, formulario, store, API o core.
- Contrato congelado: `MiningPoint3D` es una tupla XYZ readonly (Este/Norte/Elevación); `CurveSelectionContext` identifica malla y datos de curvas mediante `designMeshId` y `geometryKey`; `CurveAnchor` contiene contexto, curva, índice de segmento, fracción `t`, posición y distancia acumulada XY, todos readonly. `geometryKey` es identidad local opaca, no una revisión inventada de la API. Normalización, igualdad de contexto y cancelación se especifican en el plan; todavía no son comportamiento implementado.
- Verificación del coordinador: **4/4 pruebas contractuales**, frontend completo **589/589 en 67 archivos**, cobertura obligatoria del dominio **100%**, `tsc -b --force`, ESLint completo sin advertencias y build web con PWA aprobados. Dos revisores independientes reportaron PASS. Los 32 archivos fuente/pruebas del manifiesto previo permanecen intactos.
- Los tipos garantizan estructura, no validan en ejecución finitud, rango de `t`, pertenencia a una curva ni la semántica numérica de los ejes. Esa lógica corresponde a T02–T05; la mejora visible del clic aún está pendiente. No se repitieron backend ni navegador para esta entrega de tipos sin consumidores.
- Sin commit ni push. Los cambios del bloque 1 y dH se conservaron. Siguiente tarea del plan: T02, únicamente cuando el usuario autorice continuar.

## 16 de octubre — bloque 1 de paridad web, implementado y verificado localmente

- El usuario autorizó comenzar la implementación desde el primer bloque del plan de paridad Streamlit → web, mediante tareas cortas delegadas y coordinación central. Plan: `.hermes/plans/bloque-1-paridad-resultados-web.md`. No se autorizó commit, push ni despliegue.
- Implementados localmente: tolerancias firmadas `crest_toe_deviation` en settings/API/formulario; cálculo de Logro Diseño en `core/design_achievement.py` y `GET /api/v1/process/design-achievement`; filtros compartidos sector/sección/cota/banco; columnas de sector, nivel, cresta, pata, derrame y berma efectiva; orden por sección/nivel; cinco histogramas con bandas configuradas y asimétricas, mínimo unilateral para berma; panel de Logro Diseño y traducciones ES/EN.
- Se conserva el criterio web de clasificación por perfil según el peor estado de banco. Logro Diseño (40/30/30 y crédito parcial) es una métrica distinta del score geotécnico existente. La web excluye estados no evaluables del denominador por elemento y devuelve nulos sin evidencia, a diferencia de algunos helpers Streamlit; Streamlit no fue modificado.
- Verificación realmente ejecutada y repetida: backend **2487 passed / 8 skipped / 11 warnings**, excluyendo OpenBlast y con `--skip-electron --benchmark-skip-slow`; pipeline sintético aprobado con Excel/Word, redirigiendo únicamente sus rutas literales `/tmp` al scratch mediante un arnés en memoria. Frontend final integrado: **585/585 en 66 archivos**, cobertura obligatoria **100%**, `tsc -b --force`, ESLint completo y build web con PWA aprobados. La corrida previa de 530 aprobadas/4 fallidas correspondía a mocks rotos ya corregidos del nuevo test del sidebar, no al resultado final.
- Las pruebas API nuevas deben funcionar también en colección combinada con settings/core. Se sustituyó la dependencia `client` del nuevo test de Logro por la fixture raíz `api_test_client`; la combinación antes fallida quedó **51 passed**. No se alteraron aserciones para ocultar el error.
- Corregida y probada la edición rápida de tolerancias: borrador local de valores y texto, acumulación de ambos lados antes del debounce y guardado sin pisar el borrador; 14 pruebas focalizadas aprobadas e incluidas en la suite completa. Dos revisiones independientes y una revisión adicional del delta final del sidebar reportaron PASS sin bloqueantes.
- Límite no bloqueante de la edición: una vez editado, el borrador local se mantiene durante la vida del sidebar; no sincroniza cambios posteriores hechos directamente en el servidor por otro actor. La reconciliación del borrador con actualizaciones externas queda para una futura mejora, no fue certificada aquí. GET settings incorpora defaults para claves ausentes, pero no sanea valores inválidos heredados ya guardados; el endpoint de Logro sí aplica fallback validado con advertencia.
- Smoke final con Chromium y API real: **21/21 comprobaciones aprobadas**, repetidas por el coordinador, en escritorio y móvil. Fixture sintética reconstruida mediante carga STL y procesamiento HTTP reales: 30 comparaciones evaluables, distribuidas en sectores A/B/sin sector. Verificados conteos filtrados, tabla, orden numérico por nivel, cinco histogramas y bandas configuradas. Sin errores de aplicación registrados; el arnés documenta el filtro de ruido de fuentes externas. La navegación al dashboard y parte de los filtros se inicializaron programáticamente: **no equivale al E2E completo de carga manual ni a una prueba con archivos reales del usuario**.
- Verificación adicional del coordinador: **6/6 comprobaciones aprobadas**, con clic real en el checkbox «sin sector», restablecimiento a todos, edición rápida de un par distinto del guardado, lectura posterior de settings y de las tolerancias aplicadas por Logro, restauración del par de QA y cinco histogramas presentes. Se inspeccionaron las capturas de escritorio, móvil y del panel de Logro. El primer arnés defectuoso y el fallo inicial de tipo del matcher del arnés adicional no son resultados finales.
- Evidencia preservada fuera del scratch en `data/qa-block1-final-evidence/` (ignorada por Git): `browser_evidence_final.json`, `coordinator_verification.json`, `api_fixture_final.json`, capturas, scripts y `source_manifest.json` con hashes de 32 archivos fuente/pruebas del árbol verificado. Los scripts conservan rutas del entorno de QA; ajustar runtimes y ubicaciones si se reutilizan en otro equipo. No se ejecutó la suite completa de Playwright ni se certificaron PWA offline, despliegue o release.
- QA usa datos aislados bajo `data/qa-block1-*` y artefactos en el scratch del perfil orchestrator; no son datos del usuario ni archivos distribuidos. Verificar existencia y propiedad de procesos al retomar; no reutilizar sus puertos/sesiones como estado vigente.
- Los cambios preexistentes de dH en `ProfileChart.tsx` y su test se conservaron. `app.py`, `ui/`, Electron y CLI permanecen fuera del alcance. El trabajo sigue sin commit ni push.
- Al cerrar se detuvieron únicamente la API y Vite creados para este QA y se verificaron libres los puertos 8000/5176. El listener preexistente en 5173 no se cerró. Las escrituras de cobertura HTML durante QA provocaban recargas de Vite; separar cobertura y smoke evita confundir ese efecto del entorno con una regresión de los filtros.

## Continuación desde main — 13 de octubre de 2026

Por solicitud explícita del usuario, la rama de estabilización web se integró en `main` mediante fast-forward, conservando todos los commits hasta `a29925a`. La rama de continuación para el otro PC pasa a ser **`main`**. La autorización de esta sesión incluye publicar estos cambios en GitHub; no certifica una release ni completa la validación de navegador pendiente. No se ejecutaron nuevas suites funcionales durante esta integración.

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
