# Continuación web — handoff portátil (rama `wip/web-stabilization-2026-10-07`)

Documento autónomo para continuar la estabilización web en otro equipo. Fecha: **7 de octubre de 2026** (America/Santiago, UTC-03:00). Resume lo ejecutado en la fase `web-stabilization` con sus límites y no certifica una release: **la validación de navegador quedó parcial** (§3) y el CI remoto no se ejecutó en esa fase.

---

## 1. Rama, repositorio y alcance

- Repositorio: `https://github.com/nibaldox/conciliacion-geo-v02` (público).
- Rama de continuación: **`wip/web-stabilization-2026-10-07`** — creada desde `main` local en `cc8b95c` con el árbol de la fase de estabilización, commit por unidad de trabajo. Incluye los commits locales previos (`aed2988`, `22496f3`, `cc8b95c`) tal cual; no se reescribió historial.
- `main` no se publicó. La publicación de esta rama fue autorizada puntualmente por el usuario para continuar en otro PC; **no es un permiso permanente de push ni de despliegue**, y no reactiva el «no push» histórica de fases anteriores.
- **Alcance vigente: solo web.** Trabajo nuevo en `web/` y `api/`; `core/` solo como soporte de la web (p. ej. `core/config.py` de despliegue). **No** modificar `app.py`, `ui/` (salvo la excepción documentada `ui/modulo_tronadura/`), Electron/portable ni `cli.py`.
- El asistente principal **orquesta** (divide, delega, evalúa evidencias); los ejecutores implementan. Commits locales por unidad, con rutas explícitas y los tests de cada unidad en su propio commit.

## 2. Puesta en marcha en un PC nuevo

Prerrequisitos (de `pyproject.toml`, `web/package.json` y CI):

| Componente | Requisito |
|---|---|
| Python | 3.12 (el que usa CI); `pyproject.toml` exige >= 3.10 |
| Node.js | >= 22 (`engines` en `web/package.json`; CI usa Node 22) |
| npm | incluido con Node (`npm ci` en `web/`) |
| uv | para el harness de integración fullstack de vitest (CI usa `uv sync --locked --extra test --python 3.12`) |
| libspatialindex | requerido por `rtree`: Linux `apt-get install libspatialindex-dev`, macOS `brew install spatialindex`; en Windows los wheels de rtree suelen incluir la DLL |

```bash
# 1) Clonar la rama de continuación
git clone -b wip/web-stabilization-2026-10-07 https://github.com/nibaldox/conciliacion-geo-v02.git
cd conciliacion-geo-v02

# 2) Entorno Python (Windows: .venv\Scripts\... en lugar de source)
python -m venv .venv
source .venv/bin/activate              # Linux/macOS

# 3) Dependencias (comandos de README + CI)
python -m pip install -r requirements-api.txt
python -m pip install -e ".[test]"     # extra test = pytest, pytest-asyncio, httpx

# 4) uv para el harness del frontend
uv sync --locked --extra test --python 3.12

# 5) Frontend
cd web
npm ci
```

Notas de entorno:

- El typecheck real del proyecto es `npx tsc -b` (no `tsc --noEmit`: ese no analizaba ningún archivo). Para paridad con CI, exportar `UV_NO_SYNC=1` antes de `npm run test:coverage`.
- **Aislar datos antes de importar la API**: exportar `CONCILIACION_DATA_DIR` a un directorio nuevo (p. ej. `data/qa-localfecha/`) en la misma shell que lance `uvicorn`; el SQLite se crea ahí. No apuntar a `data/` compartido ni a directorios de logs históricos.
- **No reutilizar** IDs de sesión, puertos ni PIDs que aparezcan en bitácoras o logs históricos: crear sesión, puerto y procesos nuevos y verificar que el puerto esté libre. Los PID registrados en cualquier bitácora son históricos y no acreditan propiedad.
- **No repetir búsquedas amplias** por el home o el disco completo (fueron lentas y consumieron presupuesto en la fase previa); en otro PC las rutas difieren. Trabajar siempre dentro del clon.
- Cifras de tests en `AGENTS.md`/`README.md` están desactualizadas frente a la suite actual (ver §4); no usarlas como meta.

## 3. Pendiente primero: validación de navegador (NO completada)

La suite e2e vive en `web/e2e/` (9 specs) con `web/playwright.config.ts` (baseURL `http://localhost:5173`, `webServer` levanta API en 8000 y Vite; `reuseExistingServer: true`). CI **no** ejecuta Playwright: correrlo localmente.

Corrida histórica seleccionada (12 de 15 tests completados; 8 pass / 4 fail; sin JSON final — estado reconstruido por artefactos por-test; consola con 0 errores en los 12):

- 3 fallos por **expectativas desactualizadas del spec** (no defectos de la web; actualizar el spec contra la UI/contratos reales, sin borrar aserciones):
  - `app.spec.ts` «side panel lists current navigation…»: busca el botón «Cargar Superficies»; la UI actual usa «Superficies / Secciones / Parámetros / Procesar» y nav «Análisis».
  - `app.spec.ts` «design and topography upload zones…»: busca «Cargar archivo»; la UI usa «Cargar superficie de Diseño / Topografía».
  - `compliance-plan.spec.ts` «canonical compliance colors»: espera `data-status="cumple"` (minúscula); el DOM emite `CUMPLE`. Decidir el casing desde la fuente de producción, no al revés.
- 1 fallo **sin clasificar**: `horizontal-deviation.spec.ts` «…keeps B2 inspector selection» — timeout de 120 s esperando `#profile-section-select` tras «Perfiles → Detalle». Requiere triaje (¿precondición de mock/estado sembrado vs render real?) antes de tocar nada.
- **No ejecutados**: `project-entry.spec.ts` (3 tests).
- **PWA NO ejecutado** (sin hallazgo y sin descarte):
  - Escenario A/B pendiente: verificar si la regla `StaleWhileRevalidate` de `api-cache` para `/api/v1/**` (solo GET) puede devolver a una sesión B la respuesta cacheada de una sesión A con la misma URL y `X-Session-ID` distinto (los settings del API son por sesión; la config Workbox no declara partición por `X-Session-ID`). **No está confirmado ni descartado.** Un probe previo quedó sin ejecutar y tenía defectos propios de arnés (p. ej. `Object.fromEntries` construido sobre promesas, `serviceWorker.ready` sin timeout); no está en el repo — rehacerlo limpio si se retoma.
  - Verificación de shell offline: también pendiente; no declarar la API cacheada como «offline segura».
- Estado del intento de seguimiento de esa fase (histórico): el triaje E2E y la prueba PWA A/B quedaron **bloqueados antes de ejecutar** por presupuesto del ejecutor — **no se editó ningún spec E2E** y **no hay veredicto PWA** (ni fuga ni descarte). Los servidores QA de esa fase se cerraron con verificación de puertos libres; los PID de las bitácoras son históricos y **no acreditan propiedad actual**: no asumir procesos, sesiones ni puertos por ellos.

Al retomar E2E: `npx playwright test` desde `web/` (API + web corriendo o dejando que Playwright los levante — en ese caso exportar `CONCILIACION_DATA_DIR` aislado antes; atención al `reuseExistingServer: true`, que puede enganchar servidores ya existentes). Navegador: instalar Chromium fresco (`npx playwright install chromium`) o usar el Edge del sistema como respaldo (channel `msedge`) si la revisión de Chromium no está disponible.

## 4. Estado verificado de esa fase (histórico — no re-ejecutado en este PC)

Resultados del PC del mantenedor el 7 de octubre de 2026, sobre el árbol exacto que publica esta rama. Etiquetas: cifras **históricas**; cualquier cambio posterior en `api/` o `core/` invalida la evidencia backend.

**Backend:** Python 3.12.14 + pytest 9.1.1 → **2447 passed, 8 skipped, 11 warnings** (~7:22 min)
`python -m pytest tests/ -q --tb=short --ignore=tests/test_openblast.py --skip-electron --benchmark-skip-slow`
(`--skip-electron` y `--benchmark-skip-slow` son flags reales de `tests/conftest.py`). Skips: 1 benchmark pesado, 5 de sidecar Electron y 2 módulos legacy pre-existentes — por diseño, no fallos. Warnings: deprecaciones pre-existentes de librerías/legacy, ninguna del código estabilizado. Verificación por hash de 29 archivos fuente (incl. workflows, tests y config): 29/29 OK sin deriva durante la validación.

**Frontend (Node 22.23.1):** `tsc -b` exit 0 · eslint exit 0 · vitest **480/480 en 56 archivos** exit 0 · cobertura obligatoria del dominio ProfileView **100%** (statements 194/194, branches 220/220, functions 49/49, lines 171/171) · `npm run build` con PWA exit 0. (Node 26 no es paridad: ese runtime presentaba el problema de binding de storage que el setup de test resuelve; usar Node 22.)

**Revisión estática independiente:** **PASS** para ese árbol exacto (verificado por hash), solo lectura. Riesgos no bloqueantes anotados: CI remoto sin ejecutar; notas stale en `README.md`/`docs/HANDOFF.md`; errores de auth llevan CORS solo para orígenes allow-listed (por diseño). No es revisión visual ni corrida remota.

**API (auth y ownership):** preflight estricto `OPTIONS + Origin + Access-Control-Request-Method`; CORS envuelve 401/403/503 para orígenes permitidos; fail-closed 503 si `CONCILIACION_AUTH_REQUIRED` está activo sin key; ownership de mallas verificado antes de caché/lectura/borrado (404 uniforme para ajenas). Corridas focalizadas: 34 auth + 23 ownership + 191 foco + 33 adyacentes, todas pass (incluidas en la suite global).

**CI/configuración:** gate frontend **sin exclusiones** (suite completa + cobertura), provisionado en el mismo job (Python 3.12 + uv + `uv sync --locked --extra test`); `UV_NO_SYNC=1` congela el entorno del harness. Base API `/api/v1` sin duplicación; `render.yaml` con prefijos `CONCILIACION_*` corregidos, un worker documentado y límite de carga 500. **El CI remoto NO se ejecutó** en esa fase (no hubo push): la validez es local (tests de contrato + parseo YAML + `uv lock --check`). Al abrir esta rama, revisar el estado real de los workflows en GitHub si se disparan.

**Cambios científicos:** ninguno. Lo tocado es auth/ownership (API), configuración de despliegue y build/tests web; `core/` solo `core/config.py` (lectura validada de `CONCILIACION_MAX_UPLOAD_MB`).

## 5. Comandos de verificación (reproducibles)

```bash
# Backend, desde la raíz (como CI)
python -m pytest tests/ -v --tb=short --ignore=tests/test_openblast.py
python test_pipeline.py

# Frontend, desde web/
npx tsc -b
npm run lint
UV_NO_SYNC=1 npm run test:coverage     # paridad con CI
npm run build

# E2E (no corre en CI; requiere API+web — ver §3)
npx playwright test
```

## 6. Qué no hacer

- No tocar `app.py`, `ui/`, Electron, portable ni `cli.py`; el foco es solo la web.
- No publicar `main`, tags ni releases; esta rama es de continuación, no una release. No declararla «lista para release» con la validación de navegador parcial.
- No reescribir historial (force/reset/amend/rebase); no borrar tests ni aserciones para conseguir verdes.
- No reutilizar sesiones/puertos/PIDs históricos; no cerrar procesos del usuario.
- No leer `.env` ni credenciales; el repo es público — revisar que nada sensible se agregue.

---

Procedencia: resumen elaborado desde la evidencia local de la fase (logs y verificaciones por hash del PC del mantenedor, 2026-10-07), condensado aquí para que sea autónomo; los archivos crudos no viajan con el repo. Los resultados llevan la etiqueta de históricos y sus límites explícitos.
