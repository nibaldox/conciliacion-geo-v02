# Estabilización web — configuración, CI y despliegue (fase 1)

Documento operativo de la unidad C del plan de estabilización web (7 de octubre de 2026). Describe el contrato vigente entre cliente web, workflows y API, las variables de despliegue con efecto probado y los límites de validación. **No certifica despliegues remotos**: no se publicó ni consultó el servicio de Render en esta fase.

## 1. Contrato de base de API (`/api/v1`)

- La API monta todos los routers bajo `/api/v1` (`api/main.py`); el healthcheck es `GET /api/v1/health`.
- El cliente (`web/src/api/client.ts`) usa `VITE_API_URL` **tal cual**, sin volver a añadir el prefijo, y cae a `/api/v1` cuando la variable falta o está vacía. Los hooks llaman rutas relativas (`/meshes/upload`, `/sections`, `/process`, …) que se concatenan a esa base.
- Casos soportados por los workflows:

| Caso | `VITE_API_URL` | Resultado |
|---|---|---|
| Pages (`deploy-frontend.yml`) | `https://conciliacion-api-ewbb.onrender.com/api/v1` | base absoluta versionada |
| Portable/local (`build.yml`, `build-portable.yml`, `release.yml`) | `/api/v1` | base relativa (sidecar local; proxy de Vite en dev) |

- Regla guardada por tests: el valor termina en `/api/v1` y nunca lo duplica (`/api/v1/api/v1`). `VITE_BASE` se mantiene aparte (`/conciliacion-geo-v02/` por defecto, `/` para dominio propio o portable).
- El host de Render del workflow corresponde al servicio del mantenedor; no se verificó remotamente. Antes de publicar, confirmar que coincide con el servicio real.

## 2. Variables de despliegue (`CONCILIACION_*`)

`render.yaml` declara únicamente prefijos correctos. Antes usaba `CONCILIATION_LOG_FORMAT` y `CONCILIATION_WORKERS` (erratas que el runtime ignoraba por completo). Un test verifica que **cada** clave `CONCILIACION_*` declarada en `render.yaml` se lee en `core/config.py`.

| Variable | Efecto | Default y validación |
|---|---|---|
| `CONCILIACION_DATA_DIR` | Directorio de datos de la API (SQLite) | `data/` local |
| `CONCILIACION_CORS_ORIGINS` | Allowlist separada por comas | Lista de desarrollo local |
| `CONCILIACION_LOG_LEVEL`, `CONCILIACION_LOG_FORMAT` | Nivel y formato de logs (`plain`/`json`) | `INFO` / `plain` |
| `CONCILIACION_RATE_LIMIT_ENABLED`, `CONCILIACION_RATE_LIMIT_PER_MIN` | Rate limiting (slowapi) | `false` / `120` |
| `CONCILIACION_MAX_UPLOAD_MB` | Límite de cuerpo HTTP (middleware de `api/main.py`) e inspección DXF (`api/routers/meshes.py`) | `500`; rango sano 1–10240 MiB; valores no numéricos, ≤0 o >10240 vuelven a `500` |
| `CONCILIACION_WORKERS` | Workers de uvicorn (`CMD` de `Dockerfile-api`) | `1` (ver §3) |
| `CONCILIACION_USE_SUPABASE`, `CONCILIACION_USE_R2`, `CONCILIACION_AUTH_REQUIRED` | Opt-ins Fase 2.9 | `false` |

`CONCILIACION_MAX_UPLOAD_MB` se lee al importar `core.config` (`DEFAULTS.max_upload_mb`); `api.main` captura `_MAX_UPLOAD_BYTES` en su import y `meshes.py` lo consulta por petición. Un valor inválido **nunca desactiva** el guard: cae al default 500.

## 3. Workers: por qué se mantiene 1

El staging de solicitudes, las cachés en memoria y los trabajos de fondo, junto con el SQLite local, son **por proceso**. Con más de un worker, sesiones y cachés se reparten entre procesos y el SQLite compite por el mismo archivo. Por eso `render.yaml` fija `CONCILIACION_WORKERS: "1"` de forma explícita (la errata anterior dejaba el valor `2` en una variable muerta). Subir solo tras migrar esos almacenes a backends compartidos.

## 4. Gate de CI (`ci.yml`, job `frontend-build`, Node 22)

Pasos del gate: `npm ci` → `npx tsc -b` → `npm run lint` → `npm run test:coverage` (suite completa, sin exclusiones ni skips) → `npm run build`.

- **Typecheck real**: `tsc -b` comprueba los proyectos referenciados (`tsconfig.app.json` + `tsconfig.node.json`). El anterior `npx tsc --noEmit` sobre el tsconfig de referencias no comprobaba ningún archivo (salía en verde sin analizar el código). Lo mismo aplica al step equivalente de `deploy-frontend.yml`.
- **Cobertura**: `npm run test:coverage` ejecuta vitest con umbral 100% en `web/src/components/results/ProfileView/domain/**` (configurado en `web/vite.config.ts`).
- **Prerrequisitos completos en el mismo job** (los jobs de CI no comparten entorno): `actions/setup-python@v5` fija Python 3.12; `astral-sh/setup-uv@v10.2.0` (versión verificada upstream) instala `uv`; `uv sync --locked --extra test --python 3.12` crea el entorno desde `pyproject.toml` + `uv.lock` (`--locked` falla si el lock queda obsoleto) con el extra real `test` que respalda al harness. El job `backend-tests` provisiona lo suyo por pip (`requirements-api.txt` + `.[test]`).
- **Sync congelado en el step de pruebas**: `web/tests/support/integrationHarness.ts` lanza `uv run python` (caché temporal por llamada); el step exporta `UV_NO_SYNC=1` para que el sync implícito de `uv run` no re-resuelva el entorno sin el extra `test` ni elimine dependencias del harness. El subproceso usa el entorno ya provisionado.
- **Límites local/remoto**: los runners `ubuntu-latest` no traen `uv` preinstalado (verificado en el inventario de la imagen 24.04, 2026-09), de ahí el setup explícito; no se ejecutó el workflow en remoto en esta fase (sin push): validez comprobada localmente (contratos, parseo YAML, `uv lock --check`). Localmente la suite corre con el entorno del desarrollador; para paridad estricta con CI, provisionar con el mismo comando y exportar `UV_NO_SYNC=1`.
- **Sin secretos en el bundle**: `deploy-frontend.yml` solo pasa valores públicos `VITE_*` al build de Pages (guardado por test); no hay API keys embebidas ni lectura de `.env`.

## 5. Render free tier — límites documentados (no verificados remotamente)

- Duerme tras ~15 min de inactividad; sin discos persistentes → SQLite efímero (se pierde al reiniciar); 750 h/mes.
- Healthcheck declarado: `/api/v1/health`.
- Estos límites provienen de la configuración del blueprint, no de una verificación contra el servicio desplegado.

## 6. Comandos de verificación

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web_config_contracts.py -v   # contratos de configuración
cd web
npx tsc -b                                                                  # typecheck real de proyectos
npm run test:coverage                                                       # suite completa local (incluye fullstack con uv)
npm run build                                                               # build de producción con PWA
```

Los contratos viven en `tests/test_web_config_contracts.py`; las capturas de import se comprueban en proceso aislado con `tests/support/config_env_probe.py`.

Paridad con CI: `uv sync --locked --extra test --python 3.12` provisiona el entorno del harness; exportar `UV_NO_SYNC=1` antes de `npm run test:coverage` evita que el `uv run` del helper re-resuelva ese entorno.

## 7. Límites de validación de esta unidad

- Solo contratos locales de configuración, workflows y capturas de import; sin despliegue remoto, sin verificación del servicio Render y sin build web completo (lo ejecuta la validación QA final).
- La corrección del gate CI (suite frontend completa + provisioning declarativo) se validó con contratos locales, parseo YAML y `uv lock --check`; el workflow no se ejecutó en un runner remoto al no haber push.
- Los resultados publicados siguen sin verificarse. `README.md` y `docs/HANDOFF.md` conservan notas anteriores a este cambio (p. ej. la tabla que describía `CONCILIACION_MAX_UPLOAD_MB` como no leída); su actualización corresponde a una pasada documental posterior.

## 8. Estado de publicación (7 de octubre de 2026)

- El usuario autorizó explícitamente publicar el árbol de esta fase para continuar en otro equipo: rama de continuación `wip/web-stabilization-2026-10-07` en `https://github.com/nibaldox/conciliacion-geo-v02` (repositorio público). `main` local no se empuja. La autorización es puntual para esta publicación; no constituye permiso permanente de push ni de despliegue, y no reactiva el no-push histórico como si fuera aplicable a esta tarea.
- El workflow actualizado tampoco se ejecutó en un runner remoto en esta fase: la validez del gate sigue siendo local (contratos + parseo YAML + `uv lock --check` + suite local certificada, ver §7).
- La validación de navegador/PWA permanece pendiente y no está cubierta por este documento; el punto de reanudación portátil está en `docs/CONTINUAR_WEB.md`.
