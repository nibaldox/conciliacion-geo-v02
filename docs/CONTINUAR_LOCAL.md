# Estado local — 3 de octubre de 2026

## Reanudación — sesión de perfiles y portable matching, 3 de octubre (America/Santiago)

El usuario cerró por hoy y pidió guardar el avance. Todo lo descrito abajo es estado local; no se hizo commit ni push. Se trabajó en código, API, frontend y portable durante la sesión; esta actualización solo registra lo ocurrido.

- Se investigó el reporte de perfiles vacíos/sin banco emparejado, incluido el caso de la captura con una cara gris en topografía. En `core/profile_compliance.py`, el matching ahora separa elegibilidad vertical (`abs(delta midpoint Z) < DETECTION.gap_match_threshold`, por defecto 8 m) del ranking horizontal, conserva monotonía y ajusta dinámicamente la penalización para candidatos inelegibles. Caso dx=10 m con cotas iguales: MATCH. En `core/horizontal_deviation.py`, rampas cubiertas (`is_ramp`) pueden medirse si tienen cobertura y un cruce único, sin cambiar su clasificación; tres bloqueos previos podían ocultar una cara válida.
- `core/section_cutter.py` añade `cut_mesh_with_section_diagnostics`, también reexportado desde `core`; el wrapper legacy conserva `OptionalProfileResult`. Los diagnósticos detectan desconexión/ambigüedad, no interpolan puentes ni insertan NaN y preservan paredes verticales. `api/routers/process.py` expone `profile_warnings` por superficie y sección y evita mostrar una línea reconciliada cacheada si el perfil es inválido. El heatmap conserva ambigüedad en cortes desconectados, deja `deviation` nulo y no crea parches. El fixture de punto medio usa el helper real; conserva 100 celdas medidas.
- La interfaz mantiene zoomout/ROI topográfico en perfiles; Resumen, detalle y los tres estados quedan sincronizados, con `UNKNOWN` visible; el selector de cota base de diseño y la tabla filtrada continúan disponibles. Se añadieron mensajes ES/EN para no intersección, datos insuficientes, corte desconectado/ambiguo, error de corte y error de procesamiento. El estado ausente se muestra como `MISSING/UNKNOWN`; cuando corresponde, el texto dice «sin banco topográfico emparejado», sin concluir que falte topografía global.
- No se recuperó el caso exacto de la captura. Que `is_ramp` haya bloqueado una cara es una causa probable, no confirmada.
- QA registrado: frontend 466/466; cobertura del dominio de perfiles 100% en sentencias/ramas/funciones/líneas; TypeScript y ESLint correctos. Backend completo inicial: 2.301 aprobadas, 5 omitidas, 1 fallo en 629,8 s. Se corrigió después el fallo del diagnóstico de heatmap y el archivo heatmap quedó 8/8; no se repitió toda la suite tras el cambio acotado de API. Geometría horizontal/corte: 47 pruebas focalizadas; matching/API: 34. `test_pipeline.py` completo aprobó usando Python `-X utf8` para evitar un problema de consola CP1252 con un checkmark.
- Portable nuevo: `dist-portable/conciliacion-portable-windows-2026-10-03-matching.exe`, 220.286.506 bytes, SHA-256 `eb8e846e6a5a895f8ad522fe3b89a96ece5047fcbfadccc0ffab4afe6ed9dc19`; hash e instrucciones están en su `.sha256` y `LEEME-matching.txt`. Sidecar aislado: `dist-portable/matching-build/conciliacion-api.exe`; recurso empaquetado nuevo, SHA-256 `f8804cde11fb093b1478f8dd94430d02361d8b67003f86a8e22f7639b0afb268`. El CArchive contiene 432 archivos, sin mismatch ni DB del usuario ni service worker. El build fue aislado por un bloqueo en `dist/conciliacion-api.exe`; se eliminó la configuración temporal de Electron. El log registra un aviso opcional de `SciPy.special._cdflib` inexistente en el hook del entorno; no se cambió el spec.
- Smoke del EXE nuevo **pendiente**: el puerto 57890 estaba ocupado por PID 11924 (`dist/conciliacion-api.exe`, creado 2026-10-03 22:41:38 hora local; proceso padre 30544 ya ausente). No se encontró instancia Electron portable del proyecto ni clientes `ESTABLISHED`; 8000, 5174 y 9238 estaban libres. No se pudo confirmar propiedad de PID 11924 y no se cerró. PID/puerto son el último estado observado: comprobarlos al retomar, no asumir que siguen activos. Tampoco iniciar el smoke hasta resolver titularidad/autorización y confirmar que 57890 está libre; no cerrar API automáticamente.
- Para el smoke autorizado cuando se retome: usar el EXE matching, DB y perfil aislados y una fixture abierta triangulada con cara de 70°, topografía desplazada +10 m y cotas iguales. Antes de pausar, la fixture ya había dado MATCH, `delta_crest/delta_toe = -10 m` y tres muestras `dH = -10 m`; el extractor la clasifica `is_ramp=False` (las rampas sí tienen cobertura en pruebas unitarias). No reutilizar datos de usuario ni una DB normal.
- La captura reportada se copió sin modificar a `data/local-review-logs/profile-matching-user-2026-10-03.png` para que no dependa de Temp. Los demás logs e informes quedaron bajo `data/local-review-logs/`; localizar sus nombres exactos con `rg` (`matching*`, `portable*`, `profile*`) y verificar que existan antes de referenciarlos. No se cerró PID 11924. Las entradas anteriores de este archivo se conservan como historial.

## Portable con miniatura de detalle de perfiles — 3 de octubre

- Build web portable completado con `VITE_PWA=false`, `VITE_BASE=/` y `VITE_API_URL=/api/v1`; el sidecar PyInstaller incluye los bundles actuales de `web/dist` y el endpoint de detalle ROI. Sin service worker en el build.
- Validación frontend: 462/462 pruebas; cobertura de `ProfileView/domain` 100% (194/194 statements, 216/216 branches, 49/49 functions, 171/171 lines); TypeScript y ESLint correctos.
- EXE nuevo: `dist-portable/conciliacion-portable-windows-2026-10-03-perfiles.exe` (220,274,220 bytes), SHA-256 `89da03b22750acfe56a0c19bf6f9eca4adbcabbed4bc8da97a2c8472d968622f`; huella y guía `LEEME-perfiles.txt` junto al ejecutable. Los EXE anteriores se conservaron.
- QA confirmó ROI real con HTTP 200 (59.999 caras, 30.211 vértices y bbox/rango Z correctos) y continúa capturas visuales de demo. El smoke de este EXE no se pudo arrancar: antes de lanzar nada, el puerto 57890 estaba ocupado por PID 21460 (`conciliacion-api.exe`, bajo `%TEMP%\3KBtihuEXja5Lp2e5oRgJeY6jQv\resources`), una instancia preexistente que se dejó intacta. El smoke no verificó health/frontend/ruta ROI a través del EXE ni el flujo UI real empaquetado; evidencia: `data/local-review-logs/portable-perfiles-smoke.log`. Para repetirlo, cerrar voluntariamente la instancia anterior y usar APPDATA/SQLite aislados. No repetir pruebas sintéticas pesadas de 220 MiB.
- Trabajo local, sin commit ni push.

## STL de 220 MB — límite ampliado a 250 MiB

- El usuario reportó el rechazo de un STL de 220 MB y autorizó ampliar el límite a 250 MiB. `core/mesh_handler.py` permite ahora 262.144.000 bytes, tanto para diseño como para topografía. El límite HTTP predeterminado sigue siendo 500 MiB.
- La interfaz anunciaba 500 MB y ocultaba el detalle del error STL. Ahora informa el límite STL de 250 MiB, muestra el motivo devuelto por la API y conserva el aviso al reemplazar una superficie cargada, también en modo compacto. Se mantiene la superficie anterior ante rechazo.
- Validación: 58 pruebas focalizadas del backend y 453 del frontend aprobadas; TypeScript, ESLint y compilación correctos. El cargador y la API real aceptaron una topografía sintética de 230.686.684 bytes (220 MiB), 4.613.732 triángulos y 2.309.909 vértices. Las pruebas de límite aceptan 220 y 250 MiB y rechazan 250 MiB + 1 byte. La geometría real del archivo del usuario no se recibió ni se validó.
- EXE actualizado: `dist-portable/conciliacion-portable-windows-2026-10-03-dxf-stl250.exe` (220.268.310 bytes). SHA-256: `440f54055dba39ddf7f8f2a09db71877a8f19e3baa35802dbd8f31a003402cc6`. Huella e instrucciones junto al EXE. Se compararon 430 fuentes/activos empaquetados sin diferencias; el sidecar Electron coincide con el compilado y no incluye la base del usuario.
- Prueba del EXE final aprobada, con APPDATA y SQLite aislados: carga del STL sintético de 220 MiB desde la interfaz; selección de capas DXF, unidades conocidas/desconocidas y conversión mm → m; procesamiento de secciones generado desde CSV en la interfaz; mapa de calor (78/90 celdas medidas, máximo 0,5 m); Excel/Word/PDF/DXF; persistencia de opciones al reiniciar y reconstruir desde SQLite; ausencia de service worker y liberación del puerto al cerrar. Informe: `data/local-review-logs/portable-dxf-smoke-report.json`; registros `stl250-*` y capturas `stl250-upload-state.png`, `portable-dxf-*.png`.
- La revisión encontró errores en el script de prueba: transferencia del archivo grande, cierre automático del panel de superficies, caché/sesiones al escribir por API y número insuficiente de secciones. Se corrigió el script para seleccionar el archivo local por CDP y generar/procesar las secciones desde la interfaz. La visualización de la malla grande puede tardar más que la carga; no se amplió el alcance a optimizar decimación.
- La instancia anterior del usuario ya había liberado el puerto al comenzar la prueba; no se cerró. Solo se cerraron instancias de prueba propias. Cambios sin commit ni push; `app.py` y `ui/` intactos.

## Superficies DXF — 3 de octubre

- Implementación realizada con tres subagentes GPT-6-luna, por petición del usuario. Guía: `docs/DXF_SUPERFICIES.md`; plan: `docs/design/2026-10-03-soporte-dxf-superficies.md`.
- `core/dxf_import.py` admite 3DFACE, POLYFACE y MESH plano, bloques anidados y MINSERT, capas, transformaciones y unidades explícitas. Conserva float64, rechaza recortes/transformaciones y polígonos ambiguos, registra descartes y acota expansión. `load_mesh(filepath)` conserva coordenadas sin conversión implícita.
- La API añade inspección y confirmación de DXF con temporales por sesión y vencimiento de 15 minutos. Una migración aditiva guarda opciones e informe; reconstrucción desde SQLite respeta las capas y escala. La superficie anterior se conserva al cancelar o fallar. No se modificaron los límites de carga.
- La interfaz web/portable revisa capas, unidades, extensión y advertencias antes de importar, en ambos roles. Incluye diagnóstico de archivos sin superficie compatible y protege contra respuestas de inspección obsoletas.
- Validación: backend completo 2.283 aprobadas / 6 omitidas (2.289 recopiladas), pipeline sintético aprobado; frontend 451 aprobadas, TypeScript y ESLint correctos; Playwright Edge DXF 1/1 aprobado. Integración sin mocks: DXF/DXF y DXF/STL producen los mismos perfiles y parámetros que STL equivalente dentro de 1e-6 m; mapa con sector y sin sector, Excel/Word/PDF/DXF aprobados.
- Nuevo EXE generado: `dist-portable/conciliacion-portable-windows-2026-10-03-dxf.exe` (220.267.867 bytes), con SHA-256 e instrucciones. Comparados 429 archivos empaquetados (424 del frontend y 5 fuentes DXF/API) sin diferencias; sidecar Electron idéntico al compilado, sin base de datos de sesiones en el EXE.
- La prueba del EXE final necesita liberar el puerto 57890: al intentar iniciarla se encontró una instancia del usuario abierta en `%TEMP%/3K9eh29nr7KIGhhDH3EBGuMhbof/Conciliación Geotécnica.exe`. No se cerró; se pidió al usuario cerrarla o autorizar su cierre. Scripts, fixtures sintéticos, logs y capturas de esta entrega: `data/local-review-logs/*dxf*`. Falta validar los DXF reales del usuario antes de atribuir compatibilidad a su programa exportador.
- Cambios locales sin commit ni push; `app.py` y `ui/` intactos.

## Mapa de calor del portable — 2 de octubre

- El usuario decidió conservar los límites de carga y reportó el selector deshabilitado con superficies reales ya procesadas. Diagnóstico de solo lectura en la base del portable: ambas superficies y 51 secciones completas, todas con `sector=""`.
- La interfaz descartaba sectores vacíos y bloqueaba la consulta por longitud cero. Ahora el grupo vacío aparece como «Sin sector» / “No sector”, se conserva `sector=""` en la petición y se distingue de la ausencia de secciones mediante `null`. Los IDs de demo siguen bloqueados; un flag de demo residual ya no bloquea superficies reales.
- No se cambiaron la geometría, el backend de cálculo ni los límites: STL 200 MiB en el cargador y petición HTTP 500 MiB. No se modificó la base del portable del usuario.
- Cuatro pruebas Playwright aprobadas: mapa con sector, sin sector, superficies reales tras demo y muestras/selección de perfiles. TypeScript/build portable, ESLint y `git diff --check` correctos. Prueba con frontend de producción y API real: 130/150 celdas medidas, máximo dH 0,5 m, sin errores JavaScript. Captura: `data/local-review-logs/portable-map-no-sector.png`.
- Los 424 archivos del frontend empaquetado fueron comparados con los compilados y coinciden. Nuevo EXE separado: `dist-portable/conciliacion-portable-windows-2026-10-02-mapa.exe`; logs y diagnóstico en `data/local-review-logs/portable-map-*`. La instancia anterior permanece abierta para el usuario. Cambios locales, sin commit ni push.

## Portable Windows — 2 de octubre

- Portable x64 generado con todos los cambios locales: `dist-portable/conciliacion-portable-windows-2026-10-02.exe` (220.191.621 bytes), sin firma digital ni instalación de Python/Node.
- Frontend compilado con `VITE_PWA=false`, `VITE_BASE=/`, `VITE_API_URL=/api/v1`; backend PyInstaller y Electron 32.3.3. La base SQLite local se excluyó del spec; el portable crea sus datos en `%APPDATA%/conciliacion`.
- Corregido el cierre Windows en `electron/main.js`: espera a `taskkill /T /F` para terminar el árbol del backend antes de salir. Tiempo máximo de arranque ampliado a 60 segundos.
- Validación: 19 pruebas Electron aprobadas y 3 omitidas por plataforma; paquete real procesó dos superficies STL sintéticas y exportó Excel, Word, PDF y DXF. La prueba del EXE final desde una carpeta independiente verificó interfaz, ausencia de service worker y liberación del puerto al cerrar; arranque en 26,3 segundos.
- Scripts, logs, capturas y resultados: `data/local-review-logs/portable-*`. SHA-256 e instrucciones junto al EXE en `dist-portable/`. Sin commit ni push. API de desarrollo y web conservadas en 8000 y 5174.

## Reanudación del 1 de octubre — estado actual

El usuario retomó el trabajo. Esta sección prevalece sobre la pausa y los PID históricos siguientes. Se conserva la delegación a GPT-6-luna con razonamiento máximo. Cambios locales, sin commit ni push; `app.py` y `ui/` permanecen intactos.

- Exportar terminado: informe Markdown GFM a ancho disponible, botones de exportación arriba, alineación de columnas numéricas y tablas con desplazamiento propio en móvil. HTML raw se muestra como texto. Verificado en Edge con respuesta simulada, temas claro/oscuro y móvil, sin solicitar un informe nuevo al LLM.
- Frontend: 445 pruebas en 52 archivos aprobadas; dominio de perfiles, 118 pruebas y cobertura del 100%; TypeScript, ESLint, build y E2E de Exportar aprobados. Capturas: `docs/design/export-after.png`, `export-after-dark.png`, `export-after-mobile.png` y `export-after-mobile-report.png`.
- Prueba real reutilizó la sesión `d14142a1-bfe9-4faf-ad4a-4e652cd7a0ec` y sus dos superficies y 19 secciones. Procesamiento actualizado: 19 secciones y 77 registros de comparación. No se reprocesó la sesión original del usuario.
- Se encontró y corrigió otra causa del perfil incorrecto: `_correct_toe_with_spill` entregaba algunas caras ascendentes al proyector en el sentido contrario. Ahora recorta y orienta los puntos desde la cresta hacia la pata física antes de corregir derrames. La regresión verifica ambos sentidos del recorrido.
- El mapa real reveló un `KeyError` por dos fórmulas de redondeo del punto intermedio. Se unificó el cálculo del índice de estación y se añadió una regresión con separación de 20 m y paso de 2 m.
- Mapa actualizado a 2 m longitudinal / 1 m vertical: 6.752 de 9.794 celdas medidas. Las demás conservan razones explícitas de falta de referencia o ambigüedad; no se relajaron las condiciones de medición.
- Artefactos de prueba y scripts reproducibles: `data/local-review-logs/`. La API actual ejecuta el código corregido en 8000 (PID 32596); frontend en 5174. Los PID son informativos y deben comprobarse tras cerrar el equipo.
- Backend completo: 2.256 pruebas recogidas, 2.249 aprobadas y 7 omitidas, excluyendo OpenBlast; duración 15 min 36 s. Log: `data/local-review-logs/backend-final.log`. Las 191 pruebas dirigidas de geometría también aprobaron.
- Los 19 perfiles rich mantienen recorrido monotónico y metadata alineada; los DTO legacy siguen ordenados. Invertir los 589 puntos reales de S-01 produjo coordenadas rich idénticas. Los cierres de piso coinciden con el perfil fuente dentro de 0,0003 m.
- Edge aislado: S-01 renderizado con escala H=V (error 1,11×10⁻¹⁶), miniatura de ubicación cargada, selección desde tabla y perfiles/mapa 3D reales en ambos temas. Capturas: `docs/design/real-profile-*.png` y `real-horizontal-deviation-3d-*.png`. API consultada con respuestas 200 y sin errores de JavaScript; la fuente remota de Google quedó bloqueada por el entorno y se usó la fuente alternativa.
- Clic de marcador corregido y comprobado con S-01 real: cuando una muestra superpuesta de desviación horizontal sin banco intercepta el evento, el círculo visible de un único marcador permite seleccionar ese banco. La detección exige que el puntero quede dentro del círculo y excluye pozos, trazas genéricas y círculos superpuestos. El clic centrado abre Banco 01 sin recurrir a la tabla.
- Chequeos del ajuste de marcador: 29 pruebas dirigidas de ProfileChart/ProfileView.selection aprobadas, incluida una nueva regresión; TypeScript sin emisión, ESLint completo, `tsc -b` y build final Vite/PWA aprobados. El frontend contiene ahora 446 pruebas (445 aprobadas en la suite completa previa más la nueva regresión aprobada).
- Cierre: los tres pendientes de la pausa quedaron resueltos y verificados. `git diff --check` correcto; no hay cambios en `app.py` ni `ui/`. Servidores locales conservados en 8000 y 5174. Próximo paso: revisión visual del usuario; en su sesión original debe pulsar «Procesar» para actualizar las extracciones guardadas con la corrección. No se realizó commit ni push.

## Punto de reanudación más reciente — pausa del 1 de octubre

El usuario pidió detener el trabajo para cerrar el PC y continuar más tarde. Se detuvieron los subagentes; no continuar implementación, pruebas ni procesamiento hasta que el usuario retome. Los cambios están guardados localmente, sin commit ni push. Esta sección prevalece sobre los estados y PID históricos de abajo.

Continuar como orquestador y delegar las mejoras a subagentes GPT-6-luna con razonamiento máximo, según preferencia expresa del usuario para cuidar su cuota. Conservar todos los cambios previos; no modificar `app.py` ni `ui/`.

### Corrección de la línea conciliada

- Guardada en `core/profile_extract.py` y `api/routers/process.py`, con regresiones en `tests/test_reconciled_profile_orientation.py`. **92 pruebas dirigidas aprobadas**.
- Corrige el orden de muestras de cada cara desde cresta hacia pata, invierte bancos monotónicos cuando su orden contradice el recorrido y toma el cierre del piso del perfil fuente. El serializer legacy mantiene arrays ascendentes y coloca ese piso en su posición correcta. Se conservan las rampas; no se cambiaron extractor, matching ni tolerancias.
- **Pendiente comprobar con los archivos reales.** El reinicio final no llegó a completarse: el último listener API observado, PID 33024, ejecutaba la versión anterior al último ajuste. Health `ok` no prueba que el código final esté cargado. Al retomar, iniciar/reiniciar la API desde este workspace y verificar el DTO real, además de OpenAPI.
- Se detectó antes un daemon antiguo que no publicaba el endpoint horizontal; el primer reinicio sí publicó `/api/v1/meshes/{topo_id}/horizontal-deviation`. Si `Get-NetTCPConnection` devuelve «Acceso denegado», no interpretar eso como ausencia de listener; inspeccionar con permisos adecuados y comprobar el comando antes de detener procesos.

### Prueba de funcionamiento con los archivos del usuario

Originales, sin modificar, en `C:/Users/nibal/Downloads/input-conciliacion/`:

- `perfiles_f9w.csv`: 43 puntos XYZ, sin encabezado, usados como alineación para generar cortes.
- `f9w_real.stl`: 103.884.334 bytes, 2.077.685 caras y 1.039.926 vértices.
- `f09w_diseño.stl`: 214.684 bytes y 4.292 caras.

Se corrigió la pérdida del primer punto del CSV en `api/routers/sections.py`; regresiones en `tests/api/test_sections_csv_reader.py`. **4 pruebas dirigidas aprobadas**, incluyendo lectura con y sin encabezado. El archivo real conserva sus 43 puntos.

Las cargas ya se completaron una sola vez, con HTTP 200, en una sesión de prueba separada de la sesión del usuario. Reutilizar estos datos al retomar, sin repetir cargas salvo que realmente no estén disponibles:

- `X-Session-ID`: `d14142a1-bfe9-4faf-ad4a-4e652cd7a0ec`.
- Diseño: `34202ae5-c3a1-439c-8231-2afaf8d9e450`.
- Topografía: `a60eaba1-95c4-43a5-883d-bd000c4c00ee`.
- `/sections/from-file` generó 19 secciones: sector `Principal`, separación 20 m, longitudes arriba/abajo 30 m (total 60 m), dirección perpendicular.
- S-01: section id `0`, origen `[92354.749498, 21787.058755]`, azimut aproximadamente 8,39°, comparable con la captura del usuario.
- **No se ejecutó `POST /process` ni se consultaron los perfiles o el mapa de calor de esta sesión.** No hay un script o log específico guardado de esta prueba real.

Pendientes, en orden:

1. Arrancar API actualizada en 8000 y web en 5174 con los comandos de abajo; conservar `data/conciliacion.db`. Los PID no serán válidos tras cerrar el PC.
2. Ejecutar el procesamiento en la sesión aislada y leer S-01. Verificar líneas rich y legacy sin retrocesos ni diagonal artificial cresta→piso, cierre sobre el perfil fuente y metadata alineada. Comprobar también el sentido inverso.
3. Revisar en navegador aislado los perfiles reales, selección de bancos, escala H=V y mapa horizontal a igual cota. Calcular el mapa con pasos 2 m longitudinal/1 m vertical; cruces ambiguos o sin referencia deben quedar sin evaluar.
4. Guardar capturas reales y registrar resultados, sin reemplazar la revisión que el usuario tiene abierta ni enviar sus superficies a un servicio externo.

### Exportar: Markdown y ancho del informe

El usuario pidió renderizar la respuesta del LLM en Markdown, aprovechar el ancho completo disponible y mantener los botones de exportación arriba. La opinión comunicada fue que esa disposición mejora la lectura de informes largos.

- Implementación guardada, **todavía pendiente de validación final**, en `web/src/App.tsx`, `web/src/components/export/AIResultPanel.tsx`, `ExportPanel.tsx` y `AIConfigForm.tsx`: reporte a ancho disponible, acciones arriba, configuración más compacta y Markdown GFM sin ejecutar HTML raw. Conservar streaming, copiar/descargar y filtros existentes.
- `react-markdown` ya existía; se instaló `remark-gfm@^4.0.1`. Cambios guardados en `web/package.json` y `web/package-lock.json`.
- Pruebas añadidas/ajustadas en `AIReporter.test.tsx`, `ExportPanel.filters.test.tsx` y `web/e2e/export-report-markdown.spec.ts`.
- Primera corrida dirigida: 15 aprobadas y 1 fallo en una expectativa de HTML seguro; el contenido se escapaba correctamente. La expectativa se corrigió, pero **no quedó confirmado el resultado final de la repetición**.
- Captura anterior guardada: `docs/design/export-before.png`.
- Pendiente: pruebas dirigidas definitivas, TypeScript, ESLint, build, E2E del reporte renderizado y captura `docs/design/export-after.png`. Revisar ancho, botones superiores, tablas/listas, tema oscuro/claro y móvil. Probar presentación con respuesta simulada o existente; no hace falta solicitar un informe nuevo al LLM.

Las validaciones y capturas anteriores del mapa/perfil fueron con API simulada; no confundirlas con la prueba pendiente de estos STL originales. Al retomar, si Node/npm no están en PATH, localizar el runtime disponible con `load_workspace_dependencies`; no depender únicamente de rutas temporales de sesiones anteriores.

---

## Punto de reanudación para el 1 de octubre de 2026

El usuario pidió terminar por hoy y dejar todo registrado para continuar mañana. El trabajo de implementación queda detenido aquí. Esta sección resume el estado más reciente; los recuentos anteriores corresponden a verificaciones realizadas durante el día.

- Todos los cambios están guardados en disco, en la rama `main`, sobre `2c67e3a`. No se hizo commit ni push. Conservar los cambios y archivos nuevos existentes al retomar.
- Completado: actualización de dependencias, frontend oscuro/claro, formularios de ingreso compactos y coherentes, vista 3D ampliada, escala 1:1 en los perfiles, cumplimiento alineado con Streamlit, planos en resumen/informes, zoom de la zona evaluada y nombres separados.
- Últimos cambios: filtro múltiple por banco en Resumen, carga CSV de Tronadura dividida en selección/configuración confirmada/envío y plano del detalle ampliado a una columna de 380–420 px.
- Última validación web: **419 pruebas aprobadas en 51 archivos**, build/TypeScript, ESLint y `git diff --check` correctos. Seis pruebas e2e afectadas aprobadas, incluida la escala 1:1 tras ampliar el plano.
- Backend: suite completa previa con **2.210 aprobadas y 7 omitidas**; después se agregó una regresión de puntajes filtrados, incluida en **16 pruebas dirigidas aprobadas**. No se repitió la suite completa tras ese último cambio.
- No se modificaron `app.py` ni `ui/`. El trabajo activo está en el frontend y las capas compartidas/API compatibles.
- Capturas y propuestas: `docs/design/frontend-options-2026-09-30/`. Detalle de mejoras: `docs/MEJORAS_LOCAL.md`.

### Próximo paso

Probar con las mallas y el CSV reales del usuario: elegir uno o varios bancos en Resumen y revisar indicadores/plano/informe; cargar pozos mediante «Seleccionar CSV» → revisar y confirmar geometría → «Cargar pozos»; comprobar la legibilidad del plano ampliado al navegar entre perfiles. Corregir cualquier observación que aparezca antes de preparar un commit.

### Arranque si se cerró el equipo

API, desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Frontend, en otra terminal:

```powershell
cd web
$env:VITE_API_URL = '/api/v1'
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Abrir `http://127.0.0.1:5174/conciliacion-geo-v02/`. Si los puertos siguen ocupados, reutilizar los servidores existentes. Al cerrar la sesión estaban activos en 5174 y 8000. Si `npm` no está en PATH, el CLI disponible en esta sesión fue `node 'C:/Users/nibal/AppData/Local/Temp/geotradarsim-review-tools/package/bin/npm-cli.js' run dev -- --host 127.0.0.1 --port 5174 --strictPort`.

---

Se retomó el trabajo y se corrigieron los pendientes de la sesión anterior.

## Cambios guardados

- Repositorio: `nibaldox/conciliacion-geo-v02`, rama `main`, commit base `2c67e3a`.
- Entorno local preparado: `.venv` con Python 3.12 y dependencias web instaladas.
- Dependencias web actualizadas: Plotly 4.1.1, Vitest/cobertura 4.1.11, Axios 1.20.0, Vite 6.4.3 y MapLibre 6.9.0.
- Actualización adicional del 30 de septiembre: `brace-expansion` 1.1.21 en las dependencias de ESLint.
- Adaptación de tipos de Plotly en `ProfileChart.tsx` y `plotlyTheme.ts`.
- Requisito Node >=22 en el frontend, workflows, Dockerfile y documentación.
- Eliminación de la preoptimización de `mersenne-twister`, que el nuevo Plotly ya no instala.
- Medición de duración del servicio de informes con `perf_counter_ns`, de mayor resolución en Windows. Las pruebas verifican milisegundos para duraciones cero, submilisegundo y superiores a un segundo mediante un proveedor simulado.
- Lectura explícita UTF-8 en las pruebas que inspeccionan fuentes React/Streamlit.
- Nuevas pruebas del dominio para ordenación de valores de diseño ausentes, estados inesperados, geometría de derrame y coordenadas no finitas. Se mantuvo el umbral del 100%.
- Cambios locales guardados; no se crearon commits ni se hizo push.

## Validación del 30 de septiembre

- Instalación limpia con `npm ci`: correcta, **0 vulnerabilidades**.
- TypeScript y ESLint: correctos. ESLint se repitió tras la actualización de `brace-expansion`.
- Frontend: **397 pruebas aprobadas** en 45 archivos.
- Cobertura del dominio: **100%** de sentencias, ramas, funciones y líneas.
- Pruebas Python afectadas: **72 aprobadas**, sin necesidad de `-X utf8`.
- Suite Python completa: **2.199 pruebas aprobadas, 7 omitidas, 0 fallos**, en 5 minutos 54 segundos. Se excluyó el archivo opcional `tests/test_openblast.py`.
- README actualizado con los recuentos actuales de pruebas.
- `git diff --check`: correcto.

## Validaciones realizadas el 29 de septiembre

- Compilación web completa: TypeScript, Vite y PWA finalizaron con código 0.
- Prueba en Edge sin ventana: dashboard, grilla y detalle de perfiles renderizaron gráficos con datos sin errores de JavaScript.
- Pipeline Python sintético: procesamiento y exportaciones Excel/Word correctos.

## Comandos locales

Desde la raíz del repositorio, en PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_openblast.py -q --tb=short
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000
```

En otra terminal, desde `web/`, con Node >=22 y npm disponibles:

```powershell
npm run dev
npm run test:domain
npm audit
```

## Mejoras implementadas después de la validación inicial

- Plotly compartido mediante un bundle cartesiano: JavaScript reducido de 4,81 MB a 1,51 MB, aproximadamente un 69%.
- La compilación ya no emite los avisos de tamaño de bundle ni módulos Node externalizados.
- Se conservaron la carga bajo demanda y la exclusión del bundle Plotly del precache PWA.
- Se corrigieron las referencias antiguas de `ARCHITECTURE.md` y los textos de carga en ambos idiomas.
- Se repitieron las 397 pruebas web, la cobertura del dominio al 100%, TypeScript y ESLint.
- Edge verificó barras, histogramas, grilla, detalle de perfil, zoom y exportación PNG sobre la compilación de producción, sin errores de JavaScript.
- Detalles y mediciones: [MEJORAS_LOCAL.md](MEJORAS_LOCAL.md).

`openblast` sigue siendo opcional y su archivo de pruebas se excluye del comando anterior. Los procesos temporales de vista previa y navegador se cerraron. Los cambios continúan guardados localmente, sin commit ni push.

## Prueba manual iniciada

Se iniciaron los servidores locales para la prueba del usuario:

- Web: http://127.0.0.1:5174/conciliacion-geo-v02/
- API: http://127.0.0.1:8000
- Salud y configuración verificadas a través del proxy web, con respuestas HTTP 200.
- Se usó el puerto 5174 porque GeotRadarSim ya ocupa el 5173; esa aplicación se dejó funcionando.
- Los servidores de esta prueba se dejan activos. La prueba con las mallas reales la realizará el usuario.

## Propuestas visuales del frontend

El usuario confirmó que la aplicación funciona y solicitó opciones visuales generadas con imágenes para reorganizar el frontend.

- Se generaron tres propuestas: clara corporativa, oscura analítica y flujo guiado.
- Se recomienda el flujo guiado para ordenar las etapas y ampliar el espacio de análisis.
- Galería y tres PNG finales: `docs/design/frontend-options-2026-09-30/README.md`.
- Prompts exactos: `docs/design/frontend-options-2026-09-30/PROMPTS.md`.
- Se utilizó el generador integrado de imágenes; son conceptos con datos ilustrativos.
- El usuario eligió la propuesta oscura analítica; ya se implementó en el frontend local.

## Frontend oscuro implementado — 30 de septiembre

- Navegación de vistas integrada en el lateral izquierdo; acceso a todas las vistas también con el panel contraído.
- Tema de grafito con acentos azules, encabezados más legibles y controles de carga compactos.
- Perfil amplio, inspector de banco con valores reales y de diseño, y tabla completa debajo del gráfico. Se conservan las columnas de cota, piso y puntaje.
- Selección por clic y teclado. Se corrigió un efecto que borraba la selección en cada render; ahora se limpia al cambiar de sección.
- Zoom, restablecer ejes y descargar PNG mediante la barra del gráfico; etiquetas y controles en español e inglés.
- Adaptación móvil con navegación contraíble y tabla desplazable.
- Validación: 403 pruebas web en 48 archivos aprobadas; cobertura del dominio al 100%; TypeScript, ESLint y build PWA correctos.
- Edge verificó grilla, detalle, navegación entre secciones, inspector, filtros y distribución de escritorio/móvil sin errores de JavaScript.
- Capturas: `docs/design/frontend-options-2026-09-30/implementacion-oscura.png` e `implementacion-movil.png`.
- Servidores de prueba conservados: web http://127.0.0.1:5174/conciliacion-geo-v02/ y API http://127.0.0.1:8000.
- Cambios guardados localmente, sin commit ni push. No se modificó Streamlit ni el cálculo geotécnico en esta fase.

## Ajuste de carga inicial compacta

- A solicitud del usuario se redujeron las tarjetas de diseño y topografía a filas de 54 px en el lateral, conservando selector de archivos, arrastre, progreso, errores, reemplazo y eliminación.
- El demo ocupa un botón pequeño y los formatos aceptados se muestran una sola vez.
- Se eliminó el límite fijo del 55% para los controles del proyecto. En ventanas de hasta 850 px de altura, la navegación de resultados usa dos columnas.
- Edge comprobó que todos los controles iniciales caben sin desplazamiento interno a 1366×768, 1280×720 y 1024×640. También verificó el selector por teclado y la carga del demo, sin errores de JavaScript.
- Validación final: 403 pruebas web aprobadas, TypeScript/build PWA y ESLint correctos.
- Captura del lateral: `docs/design/frontend-options-2026-09-30/carga-compacta.png`.
- Los cambios siguen guardados localmente, sin commit ni push.

## Corrección de tamaño de la vista 3D

- Se reprodujo el fallo con datos demo: el panel tenía 402 px de altura y el canvas WebGL solo 150 px.
- La vista 3D ahora recibe una altura definida desde el layout y el canvas ocupa el panel completo mediante posicionamiento absoluto. Las otras vistas mantienen su desplazamiento.
- En una ventana de 1920×1080 el panel mide 899 px y el canvas 897 px; también se comprobó su ajuste a 1366×768, 1024×640 y 390×844, sin desbordamiento ni errores JavaScript.
- Build/TypeScript y ESLint correctos. La revisión de perfiles confirmó filtros, selección, zoom, PNG y navegación de escritorio/móvil. No se repitieron pruebas unitarias para este cambio de distribución visual.
- Captura: `docs/design/frontend-options-2026-09-30/vista-3d-ampliada.png`.
- Cambios locales guardados, sin commit ni push.

## Tema claro y selector visible — 30 de septiembre

- Se añadió un botón de sol/luna con las acciones «Claro» y «Oscuro» en el encabezado, visible también en móvil y accesible por teclado.
- La preferencia se guarda en el navegador y se aplica antes de mostrar la página. El tema claro adapta fondos, textos, tablas, gráficos Plotly, miniaturas y escena 3D.
- Cambiar de tema conserva la sección y el banco seleccionados. La vista 3D mantiene el tamaño ampliado del ajuste anterior.
- Validación: 405 pruebas web en 49 archivos aprobadas; las 110 pruebas del dominio de perfiles mantienen cobertura del 100%; TypeScript/build PWA y ESLint correctos.
- Edge verificó persistencia, selección, colores de gráficos y botón móvil sin desbordamiento. La escena 3D se comprobó renderizada con WebGL por software en un contexto nuevo, sin errores de JavaScript. Se usaron datos demo; la carga de mallas reales queda para la prueba del usuario.
- Capturas reales: modo-claro-perfiles.png, modo-claro-resumen.png y modo-claro-3d.png en docs/design/frontend-options-2026-09-30/.
- Servidores de prueba conservados: http://127.0.0.1:5174/conciliacion-geo-v02/ y API en el puerto 8000.
- Cambios guardados localmente, sin commit ni push.

## Selección de banco desde el gráfico — 1 de octubre

- [x] El marcador y los puntos muestreados de la línea topográfica identificados dentro de un único intervalo cresta–pie actualizan la tarjeta lateral y resaltan la fila. Los límites compartidos entre bancos y los clics en líneas genéricas o pozos no se asignan a un banco.
- La línea topográfica conserva sus coordenadas originales y usa el mismo popup completo traducido del marcador en puntos identificados; los puntos sin banco mantienen el popup de coordenadas.
- Los marcadores tienen prioridad si Plotly devuelve varios bancos en el mismo clic. La selección gráfica no desplaza la página hasta la tabla, para mantener visible la tarjeta.
- La traza Terreno estaba interceptando hover y clic porque Plotly mostraba `hovertemplate: 'skip'` como texto literal. Se quitó ese template de Terreno y de los rellenos decorativos; `hoverinfo: 'skip'` sigue desactivando sus eventos.
- Validación dirigida: 25 pruebas ProfileChart/ProfileView aprobadas; TypeScript y ESLint dirigidos correctos. En Edge, el clic DOM en Banco 02 actualizó el inspector desde vacío y tras seleccionar Banco 01; el popup mostró ángulos 47,5°/46,8° y bermas 8,5/8,5 m.
- Cambios guardados localmente, sin commit ni push.
- Cambios guardados localmente, sin commit ni push.

## Corrección de escala de perfiles — 30 de septiembre

- Se reprodujo la deformación al pasar de la grilla al detalle: el gráfico demo usaba 1,77 píxeles por metro horizontal y 5,35 vertical, una exageración de aproximadamente 3×.
- Se eliminó la exageración calculada a partir del contenedor. El detalle ahora mantiene una escala 1:1 entre distancia y elevación, igual que las miniaturas; Plotly amplía el rango visible para conservar la geometría completa.
- Se actualizan explícitamente las dimensiones del gráfico cuando cambia su contenedor, incluido el panel lateral. Los datos y cálculos geotécnicos se conservan.
- La prueba de regresión web/e2e/profile-scale.spec.ts verifica la escala realmente renderizada al abrir, ampliar, restablecer, cambiar sección/tema y ajustar a escritorio/móvil. Aprobada en Edge con datos demo; medición final: 2,01 píxeles por metro en ambos ejes.
- Validación: 100 pruebas de presentación de perfiles aprobadas, build/TypeScript y ESLint correctos; git diff --check correcto.
- Captura: docs/design/frontend-options-2026-09-30/perfil-escala-corregida.png.
- Referencia de escala Plotly: https://plotly.com/javascript/reference/layout/yaxis/#layout-yaxis-scaleratio.
- Cambios guardados localmente, sin commit ni push. Servidores conservados en los puertos 5174 y 8000.

## Cumplimiento y planos de evaluación — 30 de septiembre

- [x] Alinear el resumen web con el motor que usa Streamlit: berma 60, altura 30 y ángulo 10. Se toma el puntaje calculado por el motor cuando está disponible; los perfiles cumplen desde 70/100.
- [x] Promediar los bancos MATCH de cada perfil y luego los perfiles con igual peso. Los bancos ausentes o adicionales no distorsionan ese puntaje; los indicadores de sector cuentan los parámetros evaluados, como Streamlit.
- [x] Agregar al resumen la topografía real y las líneas de los perfiles procesados, con colores de cumplimiento y coordenadas Este/Norte a la misma escala.
- [x] Incluir el plano en los informes Word y PDF pasando las secciones y la topografía de la sesión. Se corrigieron dos fallos que impedían insertar las imágenes en PDF y el puntaje global del informe ahora representa todos los perfiles.
- [x] Respetar también los filtros actuales al exportar el PDF.
- Validación: 2.210 pruebas Python aprobadas y 7 omitidas, excluyendo openblast; Word generado con siete imágenes y PDF real de tres páginas con el plano visible. No se modificaron app.py ni ui/.

## Ingreso de datos con un diseño uniforme

- [x] Usar controles compartidos de 32 px, etiquetas legibles, colores del tema y espaciado coherente en Secciones y Parámetros; Procesamiento usa botones del mismo tamaño.
- [x] Organizar Superficies, Secciones, Parámetros y Procesar en un selector de dos filas, dejando más espacio para completar los formularios.
- [x] Reducir la carga CSV/TXT/DXF a una fila compacta, con selector por teclado, arrastre y eliminación del archivo seleccionado.
- [x] Agrupar sector, separación y longitudes en dos columnas. Las instrucciones de selección del tramo y las secciones existentes se pueden desplegar cuando se necesitan.
- [x] Mostrar la lista lateral con tarjetas compactas que conservan edición de coordenadas, azimut, longitudes, sector y eliminación. Los ángulos globales de tolerancia permanecen accesibles en un desplegable.
- [x] Adaptar la navegación a una fila de iconos con etiquetas emergentes en ventanas de hasta 700 px de altura.
- Edge verificó que los formularios básicos caben sin desplazamiento a 1366×768, 1280×720 y 1024×640. La ayuda, los parámetros adicionales y las listas desplegadas pueden necesitar scroll.
- Tres pruebas e2e verifican selección de archivo por teclado, envío de la geometría completa, selección del tramo, edición de secciones y guardado de parámetros/tolerancias con API simulada, sin alterar la sesión del usuario.

## Mejoras de ubicación solicitadas y completadas

- [x] Abrir el plano del resumen con zoom sobre la zona evaluada, calculada con los cortes reales de los perfiles visibles. Se mantiene la escala métrica y un margen de contexto.
- [x] Separar los nombres de los perfiles a ambos lados del plano y conectarlos a sus líneas. Se comprobó que los 32 nombres de una evaluación concentrada no se superponen.
- [x] Permitir alternar entre «Zona evaluada» y «Superficie completa».
- [x] Agregar al detalle de perfiles una miniatura de ubicación en planta: topografía real, perfil activo en azul, hasta siete perfiles cercanos del mismo sector en gris y flecha Norte. La miniatura sigue la navegación sin cambiar el banco seleccionado.
- Se reutilizan las consultas y la caché de perfiles; no se agregan cálculos al motor geotécnico.
- Validación web: 415 pruebas unitarias aprobadas (suite de 413 más las dos pruebas nuevas de encuadre), siete pruebas e2e aprobadas, TypeScript/build PWA, ESLint y git diff --check correctos.
- Capturas en docs/design/frontend-options-2026-09-30/: perfil-con-miniatura.png, plano-zona-evaluada-32-perfiles.png, ingreso-archivo-compacto.png, ingreso-parametros-compacto.png e ingreso-curvas-claro.png.
- Servidores conservados: frontend en http://127.0.0.1:5174/conciliacion-geo-v02/ y API en http://127.0.0.1:8000. La API fue reiniciada para cargar las correcciones de informes.
- Cambios guardados localmente; sin commit ni push. La prueba pendiente del usuario es revisar sus mallas reales, el encuadre y la legibilidad de los nombres con su número habitual de perfiles.


## Filtro por banco, carga de Tronadura y plano ampliado — 30 de septiembre

- [x] Resumen: selector visible «Filtrar por banco», con búsqueda, selección múltiple y «Restablecer». Sin bancos seleccionados se muestran todos, como en Streamlit. Los indicadores, gráficos, perfiles contados y colores del plano se recalculan con los bancos elegidos.
- [x] Informes: al filtrar por banco se recalcula el puntaje por perfil para evitar que el plano conserve el puntaje de todos los bancos. Las comparaciones originales de la sesión permanecen intactas.
- [x] Tronadura: «Seleccionar CSV» abre el selector desde el inicio, por ratón o teclado. Elegir el archivo abre la configuración geométrica; tras revisarla y confirmarla, «Cargar pozos» envía el archivo. Volver a elegir un archivo o editar la configuración invalida la confirmación. Se conservan las convenciones, unidades independientes y diagnósticos 400/422; no se asume altura de banco.
- [x] Detalle del perfil: columna del plano ampliada de 260 a 380–420 px. La vista en planta tiene proporción 10:9 y mantiene la escala de la geometría, el perfil activo azul, sus vecinos y la flecha Norte. Medida en escritorio 1600 px: 394 × 355 px frente a los 160 px de altura anteriores. En móvil se adapta al ancho disponible.
- Validación: 419 pruebas unitarias web aprobadas; 16 pruebas Python de resumen/exportación aprobadas. ESLint, TypeScript/build PWA correctos. Navegador Edge: filtro por banco, selector CSV por teclado, envío FormData de geometría confirmada, cambio de perfil/tema y adaptación móvil verificados en sesiones aisladas.
- Capturas: docs/design/frontend-options-2026-09-30/perfil-planta-ampliada.png y resumen-filtro-banco.png.
- API reiniciada para aplicar los puntajes de exportación filtrados (puerto 8000, PID 14416). Frontend conservado en http://127.0.0.1:5174/conciliacion-geo-v02/.
- Cambios guardados localmente, sin commit ni push. Prueba con datos reales: seleccionar los bancos del resumen; cargar un CSV de pozos confirmando sus convenciones; verificar la ubicación del perfil en el plano ampliado.

- Cierre: seis pruebas e2e afectadas aprobadas; la escala 1:1 del gráfico se mantiene tras ampliar el plano. Captura adicional tronadura-carga-csv.png revisada. API responde 200 y git diff --check correcto.

## Ajuste del 1 de octubre — detalle de perfiles

- [x] Se quitó la columna «Estado» para evitar repetir el estado junto al puntaje y los indicadores por parámetro. Se conservan el punto junto al banco, el puntaje y los estados coloreados de altura, ángulo y berma.
- Validación: 11 pruebas de BenchTable aprobadas; TypeScript, ESLint dirigido y `git diff --check` correctos.

## Popup de parámetros al pasar sobre el banco — 1 de octubre

- [x] El popup del marcador conserva cota y diferencias de cresta/piso, e incluye ángulo real/planificado y berma real/planificada con unidades. Los valores ausentes o no finitos aparecen como «—».
- Las etiquetas del popup se traducen entre español e inglés. El número de banco sigue en `customdata[0]` para conservar la vinculación con la tabla y la selección.
- Validación: 18 pruebas de `ProfileChart.test.ts` aprobadas; TypeScript sin emisión y ESLint dirigidos correctos; `git diff --check` correcto. Vitest necesitó ejecución fuera del sandbox porque esbuild no pudo leer la configuración de Vite dentro del sandbox.
- Cambios guardados localmente, sin commit ni push.

## Causa de `ΔCr` / `ΔPa` N/A — 1 de octubre

- [x] La captura corresponde al banco topo EXTRA #2 (altura 12.15 m, ángulo 69.5°, berma 14.91 m) y al banco de diseño MISSING #2 (ángulo planificado 74.8°, berma 9.4 m). El costo de comparación fue ~8.19, sobre el umbral 8.0; por eso no hay pareja y las diferencias de cresta/pata deben seguir como N/A.
- Se añadió `bench_num_topo` como identidad explícita del banco topo sin cambiar `bench_num` de diseño ni el criterio de matching. Para resultados legacy se infiere asociación solo con huella real única y bidireccional; MISSING nunca se une a un banco topo, y los casos ambiguos quedan sin asociación. El popup conserva los datos reales y explica «Sin banco de diseño asociado» / “No design bench associated” cuando corresponde.
- Validación: 117 pruebas de dominio frontend con 100% de cobertura; 23 pruebas de `ProfileChart`; 7 regresiones backend de identidad y 17 pruebas comparator aprobadas; TypeScript, ESLint dirigido y `git diff --check` correctos.
- No se reprocesó la sesión ni se modificó la base SQLite. Cambios locales, sin commit ni push.

## Desviación horizontal en perfiles y mapa 3D — 1 de octubre

- [x] Los perfiles muestran diferencias horizontales entre diseño y topografía a igual cota. La API requiere una intersección única del perfil topográfico y limita la intersección del diseño a la cara de diseño; no empareja bancos de topografía por número ni por el resultado del matching.
- [x] El signo es dH = (dTopo − dDiseño) × sign(dCresta − dPata) en el sistema local del perfil: positivo indica sobreexcavación y negativo indica faltante. Las muestras se ubican al 20%, 50% y 80% de la altura física crest–pata, medidas desde la pata de diseño; la altura es abs(cota cresta − cota pata), sin incluir el piso local extendido.
- [x] La vista 3D permite activar o desactivar el mapa horizontal y elegir sector, banco de diseño o todos los bancos, además de los pasos longitudinal y vertical. Los valores iniciales son 2 m y 1 m. El topo real permanece como contexto gris; las celdas medidas se dibujan encima. Cruces topográficos ausentes o ambiguos y esquinas faltantes quedan sin patch coloreado.
- Las categorías usan magnitudes en metros: dentro de tolerancia hasta 1 m; menor hasta 1,8 m; moderada hasta 3 m; severa sobre 3 m. Los colores conservan el sentido: subexcavación amarillo/naranja/rojo, sobreexcavación cian/azul/azul oscuro y no medido gris.
- El endpoint 3D es GET /api/v1/meshes/{topo_id}/horizontal-deviation. Mide sobre cortes de las mallas originales y declara que la superficie entre cortes se interpola. No extrapola fuera de las secciones configuradas, exige dos cortes compatibles del sector e informa la resolución efectiva. Un topo con varios cruces válidos a la misma cota queda sin medir.
- Validación backend: 15 pruebas de tests/test_horizontal_deviation.py y 7 pruebas de tests/test_horizontal_heatmap.py aprobadas. Las regresiones del mapa cubren desplazamientos ±8,19 m en ambas orientaciones de cara, sectores intercalados, cruces ambiguos, huecos sin cerrar, conteo por celda y aislamiento de sesión.
- La API local está activa en el puerto 8000 (PID 10028) y respondió HTTP 200 en /api/v1/health. Vite sigue activo en el puerto 5174 (PID 28616). No se ejecutó procesamiento ni reproceso y no se modificó la base SQLite del usuario; la prueba de aislamiento utilizó una base temporal.
- Validación frontend dirigida: 74 pruebas en 4 archivos aprobadas; dominio de perfiles con 118 pruebas y cobertura del 100%; TypeScript, build de Vite y ESLint final aprobados. Dos pruebas Playwright en Edge aprobaron con las rutas API simuladas: overlay 3D fuera del modo demo; muestras a igual cota h=3, 7,5 y 12 m, conectores horizontales y escala H=V; el clic en B2 actualiza el inspector a Banco 02.
- Los colores de desviación se ajustaron para mantener contraste sobre el tema oscuro. Tailwind excluye los directorios generados test-results y playwright-report del escaneo de fuentes mediante @source not.
- Capturas verificadas: `docs/design/horizontal-deviation-3d.png`, `docs/design/horizontal-deviation-profile.png` y `docs/design/horizontal-deviation-b2-inspector.png`.
- Cambios locales guardados, sin commit ni push.

## Portable Windows — matching, warnings y dH — 3 de octubre de 2026

- [x] Build frontend portable sin service worker: `VITE_PWA=false`, `VITE_BASE=/`, `VITE_API_URL=/api/v1`. El bundle incluye las etiquetas `es`/`en` de avisos de perfil desconectado/ambiguo y los datos de dH.
- [x] PyInstaller compiló sidecar nuevo en una ruta aislada porque otra instancia mantenía abierto `dist/conciliacion-api.exe`. SHA-256 del sidecar: `f8804cde11fb093b1478f8dd94430d02361d8b67003f86a8e22f7639b0afb268`. Electron `win-unpacked/resources/conciliacion-api.exe` coincide exactamente. Inspección CArchive: 432 archivos verificados, cero faltantes o diferencias y ninguna base de datos local incluida.
- [x] Portable final: `dist-portable/conciliacion-portable-windows-2026-10-03-matching.exe`, 220.286.506 bytes, SHA-256 `eb8e846e6a5a895f8ad522fe3b89a96ece5047fcbfadccc0ffab4afe6ed9dc19`. Checksum y LEEME acompañan al ejecutable.
- [x] Prevalidación local con fixture abierta: matching de un banco con cota coincidente y desplazamiento horizontal de 10 m; delta de cresta/pata −10 m; tres muestras dH medidas en −10 m; cortes conectados sin avisos. El extractor no clasificó esa cara como rampa. Las regresiones de dH en rampas se verificaron en las pruebas focalizadas de core.
- [ ] Smoke del portable no ejecutado contra la API: el listener del puerto 57890 pertenece al PID 11924 (`dist/conciliacion-api.exe`), instancia que ya estaba corriendo. No se enviaron fixtures ni datos a ese proceso y no se cerró. El `APPDATA` de smoke aislado quedó sin datos de sesión.
- QA: 2.301 pytest aprobados, 5 omitidos y un fallo inicial de status ambiguo en heatmap; tras la corrección, 8/8 pruebas heatmap, 47 pruebas core horizontal, 34 pruebas matching/API y pipeline sintético pasaron. No se repitió la suite backend completa tras la corrección. Frontend: 466/466, cobertura del dominio de perfiles 100%, TypeScript y ESLint correctos.
- Cambios y artefacto guardados localmente, sin commit ni push. La geometría sintética valida los cálculos; falta la prueba del usuario con el perfil real porque no se recuperó la sesión portable anterior.

## Carga de perfiles portable — 4 de octubre de 2026

- La captura de la portable mostraba las tarjetas de grilla con spinner; los logs confirmaron HTTP 500 en GET /process/profiles/{id} por usar el origen XYZ guardado como coordenada XY. Backend corrigió la proyección con origin[:2] y verificó respuestas 200 con perfiles guardados XY/XYZ.
- Frontend: las tarjetas ahora muestran error terminal y reintento bilingüe, conservan el gráfico cacheado si falla una actualización y distinguen respuesta exitosa sin puntos. Regresión: pendiente, error/retry, perfil válido, payload vacío y dato cacheado en fallo de actualización.
- QA frontend: 471/471 en 54 archivos; regresión focal 5/5; dominio de perfiles 122/122 con 100% en sentencias, ramas, funciones y líneas; 	sc --noEmit y ESLint aprobaron.
- Durante QA,
pm.cmd no estaba disponible. El comando pnpm.cmd exec vitest run src/components/results/ProfileView/presentation/__tests__/ProfilesGrid.test.tsx movió dependencias preexistentes de web/node_modules a .ignored antes de encontrar EACCES al registry. Se interrumpió sin instalar ni descargar paquetes y se restauraron desde .ignored todos los paquetes desplazados a destinos ausentes con Move-Item; los 11 directorios de scope vacíos quedaron intactos. Se verificó que
ode_modules/vitest/vitest.mjs ejecutó las pruebas.
- No se usó ni cerró la portable ni se alteró su sesión. Cambios locales sin commit ni push.

## Prioridad de versión web — 4 de octubre de 2026

- La instrucción más reciente es trabajar exclusivamente en la versión web hasta que quede final; el empaquetado Electron/portable queda pospuesto.
- Build web ejecutado desde los binarios locales de Node con `VITE_PWA=false`, `VITE_BASE=/` y `VITE_API_URL=/api/v1`; Vite generó correctamente `web/dist` sin service worker. QA frontend de la corrección de perfiles: 471/471, 5/5 focal, dominio 122/122 al 100%, TypeScript y ESLint limpios.
- Antes de la pausa se completaron PyInstaller y `electron-builder` en rutas aisladas: `dist-portable/xyz-build/conciliacion-api.exe` y `dist-portable/xyz-package/win-unpacked/`. El sidecar empacado coincide por SHA-256 con el build aislado; CArchive confirmó 425 archivos web y `core/section_cutter.py` sin diferencias, y ausencia de base SQLite. Estos resultados son intermedios; no se publican ni se presentan como portable final.
- El smoke inició el sidecar empaquetado con `--port 57991` y datos/APPDATA aislados. `/api/v1/health` respondió 200. El listener reportado por `netstat` es PID 11908; el proceso lanzador propio era PID 15132. No se completó el smoke de carga de perfiles XYZ. La solicitud para terminar PID 15132 con `/T` fue rechazada por auto-review porque no se verificó que el listener PID 11908 perteneciera a ese árbol; no se intentó otra forma de terminación. El puerto activo de la portable del usuario 57890 no fue solicitado ni modificado.
- Se eliminó únicamente el archivo de configuración temporal de electron-builder. Se conservan los bundles y outputs parciales en sus rutas aisladas para retomar cuando la versión web esté final. La captura original del spinner se preservó en `data/local-review-logs/profile-loading-user-2026-10-04.png`.
- Seguimiento de limpieza del smoke: consulta CIM de solo lectura confirmó que PID 11908 era el listener 127.0.0.1:57991, hijo de mi lanzador PID 15132; ambos ejecutaban el sidecar empaquetado en `dist-portable/xyz-package/win-unpacked/resources/conciliacion-api.exe` con `--port 57991` (inicio 08:41:03 y 08:41:07, respectivamente). La petición autorizada `Stop-Process -Id 11908` falló con `Object reference not set to an instance of an object`; la comprobación posterior aún mostró el listener PID 11908 en 57991. No se intentó otro mecanismo. PID 6296/57890 quedó intacto.
- Limpieza completada: `Stop-Process -Id 11908` sin elevación ni `-PassThru` terminó correctamente. Verificación: puerto 57991 libre y PID 15132 ya no existe. PID 6296/57890 no se modificó.

## Versión web local abierta para pruebas — 4 de octubre de 2026

- Se inició API desde el código actual con `.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000`. PID lanzador: 14744; PID listener: 26352. Su SQLite está aislada en `data/web-dev/conciliacion.db` mediante `CONCILIACION_DATA_DIR`; no usa la base general `data/conciliacion.db` ni la sesión portable.
- Se inició Vite directamente con el Node local y `web/node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173`. PID listener: 8096. Variables: `VITE_API_URL=/api/v1`, `VITE_BASE=/conciliacion-geo-v02/`, `VITE_PWA=false`. Logs: `data/local-review-logs/web-dev-api-2026-10-04.stdout.log`, `data/local-review-logs/web-dev-api-2026-10-04.stderr.log`, `data/local-review-logs/web-dev-vite-2026-10-04.stdout.log`, `data/local-review-logs/web-dev-vite-2026-10-04.stderr.log`.
- Verificación: `GET http://127.0.0.1:8000/api/v1/health` HTTP 200 (`{"status":"ok","version":"2.0.0"}`); proxy `GET http://127.0.0.1:5173/api/v1/health` HTTP 200 con el mismo resultado; página base HTTP 200. URL exacta para revisar: `http://127.0.0.1:5173/conciliacion-geo-v02/`.
- La página quedó abierta en Codex In-app Browser y el DOM accesible confirma el título “Conciliación Geotécnica — Diseño vs As-Built”. Ambos servidores quedan ejecutándose para pruebas, como pidió el usuario. La portable en 57890 y el smoke aislado en 57991 no se tocaron.

## Regresión de superficies en grilla y diagnósticos de corte — 4 de octubre de 2026

- La grilla no filtra ni transforma las líneas: dibuja directamente `design` y `topo` que devuelve `GET /process/profiles/{section_id}`. La topo ausente se originaba en el cutter: analizaba conectividad sobre el plano infinito antes de recortar los segmentos a la longitud de la sección. Componentes disjuntos situados cientos de metros fuera podían invalidar una cadena topográfica válida dentro del tramo (observado en S03/S10/S12). El cutter ahora recorta primero y evalúa conectividad dentro del dominio de la sección; conserva avisos por superficie para cortes realmente disjuntos o ambiguos.
- El runtime cuantiza las distancias de referencia a milímetros. S26 tenía una reversión inferior a esa resolución, no un retroceso geométrico real; core normaliza esas reversiones diminutas a precisión milimétrica antes de analizar la cadena. Core reportó 34/34 pruebas focalizadas de corte aprobadas.
- Se corrigió también una causa independiente de datos obsoletos en web: el query key de perfil omitía `topoMeshId`, y el éxito de reprocesar no invalidaba perfiles. `profileQueryOptions` incluye ahora ambos IDs de malla, y `useProcess` invalida la familia `['profile']` al completar. La grilla vuelve a pedir la respuesta del par actual de superficies.
- Antes del reproceso, la caché persistida tenía extracciones de diseño en 23/28 secciones y 10 bancos de topo en 28 secciones, con 9 comparaciones. Una lectura intermedia después del recorte y antes de la normalización final de S26 dio diseño 28/28 y topo 27/28; no representa el estado final. Tras recargar la API y reprocesar con la configuración guardada, `POST /process` terminó en 2,02 s con estado `complete`, cero avisos por superficie y 110 comparaciones. La caché final contiene extracción de diseño en 28/28 secciones (109 bancos) y topo en 28/28 (85 bancos). Esos conteos de bancos extraídos no son conteos de puntos crudos de los perfiles ni de comparaciones.
- Después del reproceso, `GET /process/profiles/{id}` para S03, S10, S12 y S26 devolvió topo con 631–632 puntos y sin avisos de corte. Esto confirma que la geometría cruda topográfica está presente en las cuatro secciones revisadas; el número de bancos clasificados es otra medida (85 en las 28 secciones).
- Validación contra el parche final de core: API focal `tests/test_api.py -k "profile_warnings or xyz_origin_profiles or profiles_success or profiles_out_of_range"`: 4 aprobadas, 34 deselectadas; `tests/test_horizontal_heatmap.py`: 8 aprobadas. Web focal de transiciones hook + grilla: 7 aprobadas (2 de cambio de malla/reproceso y 5 estados de grilla). `tsc -p web/tsconfig.json --noEmit` y ESLint para los archivos web tocados aprobaron. Aviso restante de las pruebas Python: `StarletteDeprecationWarning` sobre `httpx` en TestClient.
- La inspección visual final de la grilla no se pudo completar: Computer Use informó inventarios vacíos (`apps: []`, `browsers: []`) y no había una pestaña enlazable. No se creó otra pestaña ni se usó CDP. La página abierta puede conservar resultados en la caché de TanStack Query; al revisar, recargar `http://127.0.0.1:5173/conciliacion-geo-v02/` para volver a pedir las líneas tras el reproceso. No se reinició ningún servidor desde esta revisión ni se empaquetó la portable; la portable de usuario sigue intacta.

## Mapa horizontal 3D con orígenes XYZ — 4 de octubre de 2026

- Causa confirmada en los logs de `data/local-review-logs/api-web-dev.stdout.log`: cuatro GET consecutivas a `/api/v1/meshes/{topo_id}/horizontal-deviation` devolvían 422. Al repetir en modo lectura el GET de la sesión web actual, la respuesta fue `Section origins must contain two finite coordinates`. Las 70 secciones guardadas tenían origen XYZ finito; el constructor del mapa rechazaba todo origen de tres coordenadas, aunque la sección vertical usa solo XY.
- `api/routers/meshes.py` valida ahora únicamente orígenes finitos de forma `[2]` o `[3]` y convierte ambos a XY para crear `SectionLine`. Z se valida si está presente y no se usa para ubicar el plano vertical; longitudes inválidas de 1 o 4 coordenadas continúan respondiendo 422.
- Validación: `tests/test_horizontal_heatmap.py` aprobó 10/10. Incluye 70 secciones XYZ, compara la respuesta con la misma configuración XY, y verifica 422 ante cuatro coordenadas. Aviso no bloqueante de Starlette/TestClient sobre `httpx`.
- La misma petición GET de la sesión real, después del cambio, respondió HTTP 200 en ~3,5 s: 2.930 celdas totales, 1.737 medidas, 1.193 celdas no medidas y 3.474 caras para el overlay; sin warnings de cálculo. Esto confirma el payload del mapa; la inspección visual del overlay en navegador queda pendiente.
- API web-dev activa y sana en el puerto 8000, PID listener 8276 e iniciador 26524, con `CONCILIACION_DATA_DIR=data/web-dev`. Nuevos logs: `data/local-review-logs/api-web-dev-originfix-20261004-115837.stdout.log` y `.stderr.log`. Vite 5173 permanece activo; la portable en 57890 no se tocó. La sesión SQLite del usuario no se reprocesó ni modificó.
- `git diff --check` aprobó los archivos del arreglo; cambios locales sin commit ni push.

## Perfiles recuperados ante retrocesos locales — 4 de octubre de 2026

- El cutter normaliza retrocesos topográficos locales de hasta 0,1 m a un tramo vertical y conserva las cotas. Los pliegues mayores y las ramas siguen rechazándose; el perfil recuperado emite `minor_profile_reversal_normalized`. El API conserva ese aviso junto al perfil raw y a la extracción, y la web lo muestra como advertencia recuperable separada de los avisos que indican perfil omitido.
- `useProcess` invalida la caché de perfiles tras el reproceso. El aviso recuperable no hace que el heatmap descarte una medición con cruces únicos; cruces ausentes o ambiguos siguen sin medirse.
- Regresiones: cutter 36/36 (resultado del agente de core); API/profile reload y heatmap 3/3; ProfileView 7/7. TypeScript `--noEmit` y ESLint dirigido aprobaron. Vitest inicialmente necesitó permiso fuera del sandbox porque esbuild no podía leer la configuración Vite desde el sandbox. Pytest mostró el aviso conocido `StarletteDeprecationWarning` de `TestClient`/`httpx`.
- Se identificó la sesión real de 35 secciones por su estado y mallas, conservando sus valores: resolución 0,1 m, cara 28°, berma 5°, tolerancia de altura ±2 m, ángulo ±5°, berma mínima 7 m e inter-rampa/global ±5°. Antes del reproceso había 97 filas y S26/S30 no tenían perfil topo (`ambiguous_profile_geometry`). No se enviaron overrides ni se cambiaron secciones, ajustes o mallas.
- Reproceso final: 35 secciones, 103 filas. S26 entrega 430 puntos raw, 117 reconciliados, 2 bancos extraídos y 3 filas (2 MATCH, 1 MISSING). S30 entrega 426 puntos raw, 111 reconciliados, 2 bancos extraídos y 3 filas (2 MATCH, 1 MISSING). Ambas advierten `minor_profile_reversal_normalized`; las distancias raw son monótonas y el paso mínimo 0 m corresponde al tramo vertical. El banco que sigue como MISSING permanece explícito; no se informa cobertura completa.
- Verificación de persistencia tras el reproceso: 35 nombres de sección conservados, configuración guardada idéntica, IDs de ambas mallas idénticos y estado `complete`. La API sigue activa en 127.0.0.1:8000: lanzador PID 19928 (`.venv`) y listener PID 13408 (runtime Python hijo), con `CONCILIACION_DATA_DIR=data/web-dev`. Logs: `data/web-dev/api-profile-recovery.stdout.log` y `.stderr.log`. Vite 5173 y la portable 57890 no se reiniciaron ni modificaron. No se hizo inspección visual del navegador ni build portable.
- Cambios locales sin commit ni push.

## Consolidación en Git local — 7 de octubre de 2026

- Por solicitud del usuario, se guardaron en un commit local sobre main los cambios acumulados de core, API, web, pruebas, workflows, portable y documentación, incluidas las capturas de docs/design. Consultar `git log -1` para el identificador del commit.
- La identidad se obtuvo de la cuenta autenticada mediante `gh api user`: nibaldox, con correo noreply de GitHub; configuración limitada a este repositorio. No se hizo push ni publicación.
- README actualizado, guía docs/HANDOFF.md enlazada desde AGENTS.md y exclusiones añadidas para cachés y resultados temporales. Se conservan datos, logs y binarios ignorados en sus ubicaciones locales.
- Verificación de preparación: sintaxis de 43 archivos Python/spec, 4 JSON y diff sin errores de whitespace. No se ejecutaron suites funcionales nuevas ni se modificaron app.py/ui, bases de datos o servidores. Se mantienen los pendientes de validación visual/integral y el empaquetado pospuesto.
