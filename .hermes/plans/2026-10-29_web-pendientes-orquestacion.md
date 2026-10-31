# Plan — Pendientes de la versión web (orquestación con subagentes Haiku)

Fecha: 29 de octubre de 2026. Base: `main` = `origin/main` en `fa9da2a`.
Fuentes: `docs/HANDOFF.md` (24-oct y pendientes no bloqueantes), `.hermes/plans/2026-10-18_informes-word-pdf.md`, `docs/CONTINUAR_WEB.md` §3, `docs/UI_PARITY_AUDIT.md`, lectura del código actual.

## 1. Roles y reglas

- **Orquestador/revisor (Opus, sesión principal):** divide, redacta el brief de cada tarea, lanza subagentes con `model: haiku`, revisa cada diff (`git diff`), repite los tests focalizados, corre los gates completos al cierre de cada tanda y hace un commit por tarea aprobada.
- **Ejecutores (Haiku):** una tarea pequeña cada uno, con lista cerrada de archivos permitidos. No hacen commit, push, `git checkout`/`reset`/`stash`, ni instalan dependencias, ni levantan/cierran servidores salvo que el brief lo diga.
- **Alcance:** solo `web/` y `api/`; `core/` únicamente como soporte de exportes web (`report_*`, `web_*_report.py`). Prohibido: `app.py`, `ui/`, `electron/`, `cli.py`, cálculos científicos (`section_cutter`, extracción, `compute_section_scores`, `design_achievement`), generadores legacy de Streamlit.
- **Convenciones:** código en inglés, UI en español; toda cadena nueva en `web/src/locales/es.json` **y** `en.json`; sin comentarios en código; commits convencionales.
- **Paralelismo:** solo entre tareas con archivos disjuntos (columna «Archivos»). Mismo checkout; los ejecutores corren solo tests focalizados; los gates completos los corre el orquestador.
- **Criterio de rechazo:** si el diff toca archivos fuera de la lista, borra/relaja aserciones, o no trae test RED→GREEN cuando se pide, se rechaza y se reenvía con la observación (máx. 2 reintentos; luego lo toma el orquestador).
- Tareas marcadas **[O]** no se delegan a Haiku (dominio sensible o diseño): las hace o decide el orquestador. Tareas **[U]** requieren decisión o archivos del usuario.

## 2. Comandos de verificación (Windows / Git Bash)

```bash
# Frontend (desde web/)
npx tsc -b
npm run lint
npm run test -- <ruta-o-patrón>          # focalizado
npm run test:coverage                     # completo, dominio ProfileView 100 %
npm run build
# Backend (desde la raíz)
python -m pytest tests/<archivo> -q
python -m pytest tests/ -q --tb=short --ignore=tests/test_openblast.py --skip-electron --benchmark-skip-slow
```

Línea base esperada (HANDOFF 24-oct, Linux): Python 2627 passed / 8 skipped; frontend 748 / 83 archivos.

## 3. Tareas

### Tanda 0 — Línea base (bloquea todo lo demás)

| ID | Tarea | Archivos | Tipo |
|---|---|---|---|
| **W00** | Correr gates completos en este PC (Node/Python versiones, tsc, lint, test:coverage, build, pytest completo). Reportar conteos, fallos y avisos exactos. Sin editar nada. | solo lectura | Haiku |
| **W01** | Auditoría de solo lectura: para cada gap G01–G18 de `docs/UI_PARITY_AUDIT.md`, decir si está implementado en `web/` (archivo:línea como evidencia) o pendiente. | solo lectura | Haiku |
| **W02** | Auditoría de solo lectura de los 7 pendientes no bloqueantes de selección de curvas (HANDOFF, sección T14 «Pendientes no bloqueantes») y de las 4 inconsistencias de despliegue (HANDOFF «Inconsistencias de configuración»): ¿siguen vigentes en el código actual? Evidencia archivo:línea. | solo lectura | Haiku |

Si W00 falla en algo, la primera tarea de la Tanda 1 será arreglar ese fallo (se crea W0x ad hoc).

### Tanda 1 — Deudas de los exportes web (commit `a9831e4`)

| ID | Tarea | Archivos | Aceptación |
|---|---|---|---|
| **W10** | Exponer `Content-Disposition` y `X-Export-Filters-Applied` en CORS (`expose_headers`). Test que haga un GET de export con `Origin` permitido y verifique `Access-Control-Expose-Headers`. | `api/main.py`, `tests/api/test_cors_expose_headers.py` (nuevo) | RED→GREEN; tests CORS existentes verdes. Sin esto el nombre de archivo y el aviso de filtros no funcionan entre GitHub Pages y Render. |
| **W11** | Revisar que el aviso «Filtros aplicados» de `ExportPanel.tsx` y cualquier texto nuevo del panel estén traducidos ES/EN (sin cadenas fijas). Añadir claves faltantes y test que cambie idioma. | `web/src/components/export/ExportPanel.tsx`, `web/src/locales/{es,en}.json`, test del panel | Ninguna cadena visible fija; claves en ambos idiomas. |
| **W12** | En el plano del informe, dibujar en gris (sin estado) las secciones excluidas por filtros, con entrada de leyenda «Excluida por filtro». | `core/report_charts.py`, `tests/test_report_charts.py` | Test: con filtro de secciones, las no filtradas se marcan como excluidas; tests de Streamlit sin cambios. |
| **W13** | Robustez del render de gráficos: todas las figuras con `Figure()` (sin estado global de `pyplot`) y cerradas en `finally`; mantener la guarda de área de píxeles. Test: 50 renders seguidos no aumentan `plt.get_fignums()` y dos hilos en paralelo no fallan. | `core/report_charts.py`, `tests/test_report_charts.py` | Sin cambios de imagen salvo los inevitables; suite de informes verde. |
| **W14** | Informe Word: encabezado huérfano (aplicar `keep_with_next` a los títulos antes de tablas/figuras) y campo TOC marcado para actualizarse al abrir (`w:updateFields` en settings). | `core/web_word_report.py`, `tests/test_web_word_report.py` | Tests que inspeccionan el XML del docx. |
| **W15** | Informe Word: perfiles de no conformes a 1 por página con ancho completo; anexo 2 por página sin reducir por debajo de 16 cm de ancho. | `core/web_word_report.py`, `tests/test_web_word_report.py` | Depende de W14 (mismo archivo, secuencial). |
| **W16** [O] | Estación de la punta en la superposición de pozos inclinados (geometría de tronadura). Investigación Haiku de solo lectura → fix del orquestador. | `core/report_charts.py` | Revisión de dominio por el orquestador. |
| **W17** [O] | Profundidad calculada desde filas persistidas: investigar qué diverge entre el cálculo en memoria y el de filas guardadas; proponer fix. | por definir | Primero diagnóstico. |
| **W18** [U] | Medición y revisión visual con datos reales (Word < 1,5 MB y < 6 s con 109 filas; verificación C1 de bandas). Requiere sesión real del usuario en este PC. | — | Usuario provee archivos. |
| **D1** [U] | Decisión: ¿excluir del top de berma los casos cuyo propio diseño está bajo el mínimo (23 bermas con real 0,00 m en banco 1)? | — | Decisión del usuario. |

Paralelo: W10 ∥ W11 ∥ W12. Luego W13 (comparte archivo con W12). W14 → W15 secuenciales, en paralelo con W12/W13.

### Tanda 2 — Deuda E2E (Playwright; CI no la corre)

| ID | Tarea | Archivos | Aceptación |
|---|---|---|---|
| **W20** | Actualizar `app.spec.ts`: los dos tests con textos antiguos («Cargar Superficies», «Cargar archivo») contra los textos reales de `es.json`. Sin borrar aserciones. | `web/e2e/app.spec.ts` | Spec pasa en local. |
| **W21** | `compliance-plan.spec.ts`: casing de `data-status`. Tomar como verdad lo que emite producción (`CUMPLE`) y ajustar el spec. | `web/e2e/compliance-plan.spec.ts` | Spec pasa. |
| **W22** | Triage de solo lectura de `horizontal-deviation.spec.ts` (timeout esperando `#profile-section-select`): ¿selector cambiado, mock incompleto o defecto real? | solo lectura | Diagnóstico con evidencia; el fix será otra tarea. |
| **W23** | Correr la suite E2E completa con API y Vite en datos aislados (`CONCILIACION_DATA_DIR=data/qa-e2e-20261029`) y reportar. | solo ejecución | El orquestador levanta y cierra los servidores. |
| **W24** [O] | PWA: ¿la regla `StaleWhileRevalidate` de `/api/v1/**` puede servir a la sesión B la respuesta cacheada de la sesión A? Revisión de config Workbox; propuesta recomendada: `NetworkOnly` para `/api/` (los datos son por sesión). | `web/vite.config.ts` | Decisión del orquestador + confirmación del usuario. |

Paralelo: W20 ∥ W21 ∥ W22. W23 después.

### Tanda 3 — Selección de curvas y visor (según W02)

Solo las que W02 confirme vigentes; cada una es una tarea Haiku independiente.

| ID | Tarea | Archivos |
|---|---|---|
| **W30** | Declarar `previewRef` antes de su primer uso en `Mesh3DViewer.tsx`. | `web/src/components/mesh/Mesh3DViewer.tsx` |
| **W31** | Handlers/colores recreados por render → `useCallback`/`useMemo` donde no cambie comportamiento. | `Mesh3DViewer.tsx` (secuencial con W30) |
| **W32** | Marcador de ancla en Float32 frente al payload double: el marcador se dibuja relativo al centro de render (verificar test de precisión). | `curveSelectionVisuals.ts` + test |
| **W33** | Sincronizar el borrador de tolerancias del sidebar cuando cambian los settings del servidor y el usuario no está editando. | `LeftSidebar.tsx`/`TolerancesForm.tsx` + test |

Excluido: índice espacial del topo (pospuesto por el usuario el 18-oct).

### Tanda 4 — Despliegue (según W02)

| ID | Tarea | Archivos |
|---|---|---|
| **W40** | Prefijos de variables en `render.yaml` (`CONCILIATION_*` → `CONCILIACION_*`) si siguen mal. | `render.yaml` |
| **W41** | `VITE_API_URL` en `deploy-frontend.yml`: confirmar que `resolveApiBaseUrl` añade `/api/v1`; si no, corregir el workflow y añadir test unitario de `resolveApiBaseUrl`. | `.github/workflows/deploy-frontend.yml`, `web/src/api/client.ts` + test |
| **W42** | `release.yml`: ruta de los AppImage coherente con `electron/builder.config.js` (solo la ruta, sin tocar Electron). | `.github/workflows/release.yml` |

### Tanda 5 — Cierre (orquestador)

- Gates completos frontend y backend; E2E completa.
- Actualizar `README.md` (badge y conteo de tests), `docs/UI_PARITY_AUDIT.md` (estado G01–G18 según W01) y `docs/HANDOFF.md`.
- Push solo si el usuario lo pide.

## 4. Plantilla de brief para cada ejecutor Haiku

```
Proyecto: <ruta>. Tarea <ID>: <título>.
Contexto: <2–4 líneas con el porqué y el estado actual, archivo:línea>.
Archivos que PUEDES modificar: <lista cerrada>. Cualquier otro: solo lectura.
Prohibido: app.py, ui/, electron/, cli.py, commits, push, git checkout/reset/stash, instalar paquetes, comentarios en código.
Pasos: 1) escribir test que falle (RED) y mostrar el fallo; 2) implementar; 3) correr <comando focalizado> (GREEN).
Entrega: lista de archivos tocados, salida del test RED y GREEN, dudas abiertas. No declares éxito sin la salida del comando.
```

## 5. Decisiones pendientes del usuario

1. D1 — top de berma con diseño bajo el mínimo.
2. W24 — estrategia de caché PWA para `/api/` (recomendado `NetworkOnly`).
3. W18 — disponibilidad de archivos/sesión real en este PC.
4. Push al cierre de cada tanda o solo al final.
