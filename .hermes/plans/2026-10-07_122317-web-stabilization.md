# Plan de estabilización web — fase 1

## Objetivo

Dejar la versión web compilable, con pruebas reproducibles, configuración de API coherente y aislamiento de sesiones protegido. Ejecutar el plan en esta tarea, mediante subagentes; el asistente principal solo planifica, coordina y revisa evidencias.

Base: `main`, HEAD `cc8b95c`, árbol limpio al comenzar. Todos los subagentes Hermes usarán explícitamente `deepseek/deepseek-v4.1-flash`, proveedor `openrouter`, razonamiento `max`, con rol EJECUTOR y sin delegación recursiva.

## Alcance y límites

- Frontend `web/`, su API `api/`, workflows web y configuración de despliegue.
- `core/config.py` solo para ajustes de configuración de la API; no cambiar cálculos geotécnicos, matching, escala de gráficos ni formatos de resultados.
- No modificar `app.py`, `ui/`, Electron, portable ni CLI.
- No push, publicación, cambios remotos, reescritura de historial ni lectura de secretos/.env.
- No reinstalar ni mezclar gestores sobre los node_modules existentes. Descubrir runtimes y herramientas antes de cambiar el entorno. Pedir autorización si hace falta una instalación que modifique el entorno del proyecto.
- QA con datos sintéticos, SQLite y puertos aislados. Nunca reutilizar ni cerrar sesiones/servidores del usuario.
- Ediciones y scripts por ejecutores; pruebas RED–GREEN y revisión independiente antes de commits locales por unidad.

## Unidad A — Build y pruebas frontend

**Responsable:** ejecutor frontend.
**Propiedad exclusiva:** `web/src/components/results/ProfileView/domain/compliance.ts`, sus tests; `web/src/test/**`; `web/vite.config.ts` solo para entorno de pruebas si resulta necesario. Puede añadir pruebas de configuración/harness bajo `web/tests/`; no editar workflows ni archivos API.

1. Descubrir ejecutables Node/npm reales, versión y dependencias presentes. El preflight del coordinador encontró `stdin is not a tty` al invocar el wrapper `node`; no confundirlo con un defecto de la app y usar el ejecutable nativo cuando proceda.
2. Reproducir TS2550 con el typecheck real del proyecto app/build. Conservar ES2020 y corregir la comprobación de propiedad propia sin perder la protección contra claves heredadas ni los estados UNKNOWN.
3. Reproducir los fallos de localStorage del entorno Vitest/jsdom. Resolver el entorno, no ocultar pruebas, borrar aserciones o modificar el comportamiento de producción para satisfacer mocks.
4. Registrar RED–GREEN con regresiones focalizadas.
5. Ejecutar frontend completo con cobertura, typecheck del proyecto referenciado, ESLint y build de producción con PWA habilitada. Exigir 100% en el dominio de ProfileView conforme a la configuración actual.

**Aceptación:** build y lint pasan; no fallos frontend; cobertura obligatoria satisfecha; mismas reglas de cumplimiento/ausencia; runtime y limitaciones registrados.
**Rollback:** revertir solo esta unidad (código de compatibilidad y entorno de pruebas, con sus tests).

## Unidad B — Autenticación y aislamiento de mallas

**Responsable:** ejecutor API.
**Propiedad exclusiva:** `api/middleware_auth.py`, `api/main.py` si hace falta wiring; `api/routers/meshes.py`; tests de auth/ownership relacionados bajo `tests/` y `tests/api/`. No editar configuración core ni workflows.

1. Reproducir preflight CORS con API key activa y origen permitido. Permitir que CORS gestione el preflight sin abrir las peticiones reales: claves faltantes/incorrectas deben seguir siendo rechazadas.
2. Hacer efectivo `CONCILIACION_AUTH_REQUIRED`: si se exige autenticación y falta su configuración, fallar de forma cerrada con un diagnóstico explícito. Preservar el modo local abierto cuando el flag está desactivado. Definir y probar la semántica de arranque/configuración y la de health públicos.
3. Trazar todas las rutas que reciben mesh_id: info, vertices, contours, breaklines, borrado y rutas nuevas. Comprobar pertenencia a la sesión antes de consultar cachés o devolver/modificar datos. No basta un UUID difícil de adivinar.
4. Pruebas A/B con dos sesiones: el propietario conserva acceso; la otra sesión recibe 404 sin nombres, geometría o efectos de borrado. Probar peticiones sin sesión y casos inexistentes.
5. Ejecutar regresiones focalizadas de auth, uploads, meshes, DXF y endpoints de perfiles/mapas relevantes.

**Aceptación:** preflight permitido funciona; auth real no se evade; flag no produce un falso acceso protegido; ninguna ruta de malla filtra o modifica datos ajenos; flujo legítimo permanece operativo.
**Rollback:** revertir middleware/guards y tests de esta unidad; no migraciones ni datos reales.

## Unidad C — Configuración web, despliegue y CI

**Responsable:** ejecutor de configuración.
**Propiedad exclusiva:** `.github/workflows/ci.yml`, `.github/workflows/deploy-frontend.yml`, `render.yaml`, `core/config.py` solo variables de despliegue; nueva documentación `docs/WEB_STABILIZATION.md`; tests nuevos de contratos de configuración. No editar frontend del ejecutor A ni API del B.

1. Configurar la base absoluta de Pages con `/api/v1`; mantener el caso portable/local `/api/v1` sin duplicación del prefijo. Validar conjuntamente workflow, cliente y rutas API, sin tocar el servicio remoto.
2. Unificar prefijos CONCILIACION_* en Render y conectar el límite de carga a la configuración efectiva, con validación segura de valores. No alterar defaults científicos.
3. No activar dos workers por corregir una errata: mantener explícitamente un worker mientras existan staging/cachés/trabajos en memoria y SQLite local; documentar el motivo.
4. Añadir Vitest con cobertura al gate frontend de CI y typecheck real de proyectos TS; conservar Node 22 y el build existente. No incorporar tokens/API keys a artefactos frontend.
5. Tests de contratos + documento operativo conciso con variables, comandos y límites de validación. Los resultados publicados siguen sin verificarse.

**Aceptación:** rutas cliente/workflow/API coherentes; variables anunciadas tienen efecto probado; CI no omite las pruebas frontend; no cambia la arquitectura efectiva de workers accidentalmente.
**Rollback:** configuración y tests/documentación de esta unidad, sin acciones remotas.

## Unidad D — Validación integrada, navegador y revisión

**Responsable:** ejecutor QA después de completar A/B/C; revisor independiente de solo lectura. Un único ejecutor corre la suite global.

1. Revisar diffs y evidencias de las tres unidades. Corregir bloqueos a través del ejecutor propietario, nunca por el coordinador.
2. Ejecutar frontend con cobertura, typecheck, lint y build sobre el árbol final; backend completo excluyendo OpenBlast, sidecar y benchmark más pesado como en la validación anterior. Registrar counts reales, skips y warnings.
3. Levantar API y web QA en puertos libres, con base y CORS aislados y directorio de datos nuevo. Verificar readiness por HTTP, no reutilizar servidores existentes. Adaptaciones de harness solo en scratch salvo que una regresión demostrada justifique un test reusable.
4. Playwright en navegador disponible: smoke de entrada/navegación y casos relevantes de perfiles/escala, filtros, DXF y dH. Revisar consola, errores/reintentos y capturas reales. No certificar los casos históricos de datos reales sin autorización ni volver a importar sus sesiones.
5. Si browser/dependencias impiden una comprobación, reportar el bloqueo y las alternativas; no inventar resultados ni eliminar tests.
6. Evaluar la caché PWA de API como riesgo pendiente: no declarar aislamiento offline probado sin un escenario de navegador que lo demuestre. No ampliar esta fase a un rediseño completo del service worker sin reproducir el defecto.
7. Dictamen independiente, persistido antes de agotar iteraciones; defectos de seguridad/lógica deben resolverse antes de commits. Anotar riesgos no bloqueantes por separado.

## Unidad E — Commits locales y entrega

Solo tras aprobar pruebas y revisión, un ejecutor Git confirma rutas explícitas por unidad con sus tests/documentación; nunca `git add -A` indiscriminado. Mensajes convencionales, identidad existente, sin atribución IA. El plan acompaña documentación/CI o un commit documental propio. Verificar cada SHA, parent, contenido, autor y árbol final. No push.

La entrega incluye: qué se corrigió, comandos y resultados reales, commits locales, capturas si se obtuvieron y límites aún pendientes. Guardar logs/evidencias en `C:/Users/nibal/AppData/Local/hermes/cache/scratch/web-stabilization/`; no tratarlos como artefactos publicados ni permanentes.

## Estado de publicación — 7 de octubre de 2026 (autorización explícita del usuario)

- El usuario autorizó explícitamente publicar todo el progreso a GitHub para continuar en otro equipo. La autorización es **para esta publicación**; no constituye permiso permanente de push ni de despliegue. El «No push» de la fase original aplicaba a esa fase sin push, no a esta publicación autorizada.
- Rama de continuación: **`wip/web-stabilization-2026-10-07`** en `https://github.com/nibaldox/conciliacion-geo-v02` (pública), creada desde `main` @ `cc8b95c` con los 20 paths pendientes preservados. `main` no se publicó.
- Unidad E ejecutada con commits locales por unidad (rutas explícitas, tests de cada unidad en su commit) y verificación de hashes de fuentes contra el snapshot certificado antes de confirmar: `3c2ea21` (web), `db94136` (api), `668b6e6` (ci/config) + commit documental con este handoff.
- Límites vigentes (no release-ready): QA de navegador parcial (12/15 E2E seleccionados; 3 specs con expectativas desactualizadas; 1 timeout por triajar; `project-entry` sin correr), PWA A/B y verificación offline sin ejecutar, CI remoto sin correr. Punto de reanudación portátil: `docs/CONTINUAR_WEB.md`.
