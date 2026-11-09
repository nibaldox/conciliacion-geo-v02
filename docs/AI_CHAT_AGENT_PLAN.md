# Plan — Agente de IA con herramientas para la webapp (chat flotante)

**Rama**: `feat/ai-agent-chat` — base `origin/main` (`ce84f86`, incluye PR #38; `fix/mobile-view` ya fusionada vía PRs #35/#36/#37).
**Fecha**: 9 de noviembre de 2026 · v3
**Estado**: **APROBADO por el usuario** (9-nov-2026). Política de escritura definida por el asistente por delegación explícita. Implementación iniciada (T0).

---

## 1. Pedido y alcance

> Chat que se despliega desde un ícono en la esquina inferior derecha de la pantalla, con todas las herramientas de la app, capaz de cargar las topos (topografías STL/OBJ/DXF) y hacer todo el flujo por su cuenta.

**Aclaraciones del usuario**: exclusivamente para la **webapp** — NO toca `app.py`, `ui/` ni ningún componente Streamlit; solo `web/`, `api/` y `core/ai_v2/`. La validación es con pytest + vitest y prueba funcional en la web con STL reales (T6). La costumbre registrada "validar primero en Streamlit" queda suspendida para este feature.

Interpretación funcional: agente conversacional con function calling que, dentro de la sesión activa de la webapp, puede subir malla de diseño/topografía → generar secciones → procesar la conciliación → consultar resultados/cumplimiento → exportar informes, narrando y ejecutando el flujo en lenguaje natural.

---

## 2. Qué ya existe (se reutiliza, no se reescribe)

| Pieza | Ubicación | Rol en el agente |
|---|---|---|
| Agente IA v2 (async, provider-agnóstico) | `core/ai_v2/` | Base: proveedores, config, caché, streaming, sanitización. Hoy solo genera informes — sin tools. |
| Router IA HTTP | `api/routers/ai.py` (`/api/v1/ai/*`) | Se **extiende** con chat + confirmación. El `/ai/generate` actual no se toca. |
| Presets de proveedores | `core/ai_v2/providers/registry.py` | ollama, lmstudio, openai, openrouter, minimax, glm, grok. |
| Flujo completo como REST | `api/routers/{meshes,sections,process,blast,export,settings,mapping,simulations,session}.py` | Cada herramienta es un **wrapper fino** sobre servicios/funciones de dominio existentes. |
| Selector de IA en el front | `useAIConfig` + `AIReporter.tsx` | El chat reutiliza el selector provider/model del usuario. |
| Sesión por `X-Session-ID` | `api/database.py` + middleware | Las herramientas operan la sesión activa. |

**Decisión central**: el agente NO reimplementa lógica minera. Herramientas = adaptadores de servicios existentes → preserva la API legacy, el contrato de procedencia (`value+unit+status+source+assumptions+warnings`) y las invariantes de auditoría.

### Proveedores — regla por capacidad (no por formato)

- Cada preset declara `supports_tool_calls`; la v1 habilita herramientas **solo** para proveedores con tool-calling verificado.
- No se asume que "endpoint OpenAI-compatible" implique function calling funcional: son propiedades distintas.
- Proveedor sin soporte → la UI deshabilita las herramientas y lo explica claramente (sin fallo silencioso).

### "Todas las herramientas de la app" — obligación de inventario

La v1 cubre el flujo geotécnico núcleo. El feature **no se declara terminado** hasta que cada router relevante (`meshes`, `sections`, `process`, `blast`, `export`, `settings`, `mapping`, `simulations`, `session`) tenga sus endpoints mapeados a herramientas o **excluidos explícitamente con motivo** (ola 2 documentada en §5.5).

### Independencia de capas

- `core/ai_v2/agent/` **no importa de `api/`**: `ToolSpec`, clases de riesgo y modelos de argumentos viven en `core` (puros, testeables con pytest sin HTTP).
- La capa `api/` implementa los **handlers** (traducción catálogo → `api.database`/funciones de dominio) y los endpoints HTTP.
- Los handlers **nunca se llaman a sí mismos por HTTP**: importan funciones de `api.database` y `core` directamente (un self-call añadiría middleware doble, rate limit y riesgo de deadlock con un worker).

---

## 3. Restricciones

- Solo `web/` + `api/` + `core/ai_v2/`. Prohibido `app.py` y `ui/` (incluido `ui/modulo_tronadura/`).
- API legacy de `core/__init__.py` intacta; imports estables desde `core`.
- Código/docstrings en inglés; UI y textos del agente en español; i18n en `es.json` **y** `en.json`.
- API keys solo en backend; `_sanitize_error` para errores hacia el cliente.
- **Invariantes de memoria**: herramientas devuelven resúmenes/IDs y conteos SQL agregados, nunca vértices ni blobs (topo real de 41 MB → pico ~795 MB; el chat no retiene el blob).
- Archivos ajenos del árbol (`SPEC-invasores.md`, `motion/`, `space-invaders-*`, `web/wave4-suite.log`) y el stash preexistente de otra rama: **no tocar, no commitear**; `git add` con rutas explícitas.
- Commits convencionales (en inglés), sin `Co-Authored-By` ni atribución IA.

---

## 4. Arquitectura

```
web/ (la UI del chat vive solo aquí)
  FloatingChatButton (fixed, esquina inferior derecha)
    └─ ChatPanel (desplegable)
          ├─ historial + indicador "ejecutando «herramienta»…"
          ├─ ToolCallCard (estado por paso; Confirmar/Cancelar)
          └─ stores/aiChat.ts (Zustand) + useAgentChat (lector NDJSON tipado)
                    │ eventos tipados (NDJSON)
                    ▼
api/routers/ai.py   POST /ai/chat · POST /ai/chat/confirm
    └─ core.ai_v2.agent.loop  (bucle acotado, máx ~8 iteraciones)
          └─ catálogo (core) + handlers (api) → funciones de dominio (sesión activa)
                └─ policy.py + confirmations.py (PendingRun, TTL)
```

### 4.1 Motor — `core/ai_v2/agent/` (nuevo) + handlers en `api/`

- `models.py`: `ToolRisk` (str Enum: READ, ADDITIVE, EXPORT, REPLACE, EXPENSIVE_REPLACE, DESTRUCTIVE, CONFIG), `ToolSpec` (nombre, descripción, modelo Pydantic de args, riesgo, `state_keys` que vigilan el estado previo, `timeout_s` propio, `idempotent`, resumen de impacto), `ToolState` (n_sections, n_results, process_status, has_design_mesh, has_topo_mesh), `PolicyDecision`.
- `events.py`: unión discriminada de eventos NDJSON por `type`: `text`, `tool_call` (lleva `invocation_id`), `tool_result`, `confirmation_required`, `error`, `done`; `finish_reason: "stop" | "error" | "confirmation_required"`.
- `policy.py`: función **pura** `decide(spec, state) -> PolicyDecision` — la decisión depende solo de la clase de riesgo y del estado previo (los argumentos no la afectan); tabla de verdad testeada (§5).
- `catalog.py`: catálogo v1 de `ToolSpec` con schemas derivados de los parámetros reales de los routers; modelos de args con `extra="forbid"` y límites de longitud/tamaño; sin imports dinámicos de nombres de herramienta.
- `confirmations.py`: interfaz congelada de `PendingRunStore` (`create` / `claim` atómico / `invalidate`); implementación en T3.
- `loop.py` (T2) + `handlers` (T1/T3, en `api/`): traducción catálogo → `api.database`/dominio; `/process` se envuelve importando `_run_pipeline_sync` tal cual y ejecutándolo en executor — **sin refactor de `process.py`** en esta fase.

### 4.2 Contrato de eventos (NDJSON; espejo TS en `web/src/api/agentChat.ts`)

```jsonc
{"type":"text","content":"Voy a generar 78 secciones…"}
{"type":"tool_call","invocation_id":"inv_…","name":"generate_sections_auto","args":{...},"requires_confirmation":false}
{"type":"tool_result","invocation_id":"inv_…","name":"generate_sections_auto","ok":true,"summary":"78 secciones creadas","duration_ms":1200}
{"type":"confirmation_required","invocation_id":"inv_…","name":"run_reconciliation","args_summary":"Procesar 78 secciones (sobrescribe 78 resultados existentes)"}
{"type":"error","content":"…"}
{"type":"done","finish_reason":"stop","usage":{...}}
```

Los eventos `tool_call` llevan `invocation_id` también (no solo las confirmaciones) para correlacionar logs con lo que ve el usuario. El stream original termina en `confirmation_required`; `POST /ai/chat/confirm` devuelve **su propio stream NDJSON** que reanuda la misma conversación. El chat tiene **lector propio** de eventos tipados (el de `useAIReport.ts` asume chunks de texto), con tests sobre NDJSON simulado.

### 4.3 Protocolo de confirmación — `PendingRun` (anti-spoofing)

El store pendiente guarda **todo el estado para reanudar el bucle**, no solo tool+args:

- `session_id`, `run_id`, lista completa de mensajes (incluidos los `assistant.tool_calls` crudos del proveedor), `tool_call_id`, **hash SHA-256 de los argumentos canónicos**, provider/model, **fingerprint del estado** (`ToolState` al momento de pedir confirmación), TTL (~15 min), contador de confirmaciones y consumo **single-use** (claim atómico).
- Al aprobar: se reclama atómicamente el pending, se añade el mensaje `role: tool` correspondiente y se reanuda **el mismo bucle**.
- `invocation_id` queda ligado a sesión + herramienta + hash de args + `tool_call_id` + fingerprint: **el frontend no puede autoaprobar**; solo aprueba/deniega con el ID.
- Si el estado cambió desde la solicitud (p. ej. nuevas secciones entre aprobación y ejecución), la aprobación se **invalida y se reevalúa** la política.
- Continuidad: la fuente de verdad de la continuación es el `PendingRun` server-side; el historial en localStorage es solo presentación.

### 4.4 Idempotencia, sesión, timeouts y cancelación

- Sesión siempre del middleware (`X-Session-ID`); nunca del cuerpo.
- **Concurrencia de proceso**: antes de `run_reconciliation`, si `process_status == "running"` se rechaza con observación al modelo (la protección real es no lanzarlo dos veces; la "idempotencia" de un cálculo pesado no existe).
- **Timeouts separados**: el del proveedor (120 s) no es el de la herramienta; `run_reconciliation` tiene presupuesto propio (~300 s; HANDOFF mide ~42 s en 1c-2g) o el loop lo abortaría a mitad.
- `export_report` devuelve metadatos/URL de descarga — **nunca el binario** en el contexto del modelo.
- `get_workflow_state` cuenta con consultas SQL agregadas (`db.get_results_count`), nunca cargando resultados completos.
- Cancelación: cerrar el stream aborta el loop; comportamiento por herramienta documentado en T0.
- El 413 de `CONCILIACION_MAX_UPLOAD_MB` se traduce a error de herramienta legible, no excepción cruda.

### 4.5 Carga de topos (dos vías)

- **(a) Drag & drop en el chat**: el frontend sube por multipart a `/meshes/upload` (o `/dxf/inspect` + `/dxf/confirm`) y pasa el `mesh_id` al agente como observación. La subida **siempre es iniciada por el usuario** (el modelo nunca sube archivos ni acepta rutas del servidor) → sin segunda confirmación. Si reemplaza una malla del mismo rol, la UI advierte en línea antes de subir y la tarjeta del resultado lo informa ("reemplazó el diseño previo"). En T0 se verifica la semántica de reemplazo por rol de `save_mesh` y los nombres exactos de los campos del formulario.
- **(b) Usar ya cargada**: herramientas `list_meshes` + selección por `mesh_id`.

### 4.6 Frontend

- `FloatingChatButton.tsx`: `fixed bottom-right`, tokens del tema, `safe-area-inset`, z-index sobre el contenido.
- `ChatPanel.tsx`: ~380 px escritorio / full-width móvil; historial, auto-scroll, indicador de herramienta en uso.
- `ToolCallCard.tsx`: estado ok/error + Confirmar/Cancelar.
- `useAgentChat.ts`: lector NDJSON tipado + confirmaciones + cancelación.
- `stores/aiChat.ts` (Zustand): historial, streaming, pendientes; contexto ligado a `[sesión, mallas]`.
- i18n: claves nuevas en `es.json` + `en.json` (plurales ICU).

### 4.7 Persistencia del historial

localStorage vía Zustand persist, indexado por sesión (se limpia al cambiar de sesión), botón "limpiar chat". **Solo presentación**: sin invocations, claves ni estado de confirmación en localStorage — la continuación tras confirmación usa el `PendingRun` server-side.

---

## 5. Política de escritura (definitiva) y matriz de herramientas

### 5.1 Semántica verificada en el código (9-nov-2026)

- `db.save_sections` — **"Replace all sections for a session"** (`api/database.py:445`) → `/sections/auto`, `/sections/manual` y **`/sections/from-file`** (termina en `_save_sections`, `sections.py:403`) **REEMPLAZAN** todas las secciones.
- `/sections/click` — **AÑADE** a las existentes (`sections.py:309`).
- `db.save_results` — **"Replace all results for a session"**: `DELETE FROM results WHERE session_id = ?` + `INSERT` por resultado (`api/database.py:634-637`) → cada `/process` **sobrescribe todos** los resultados oficiales de la sesión.
- Detección de "hay trabajo previo": conteos SQL (`db.get_results_count`, ya usada por `/process/status`), nunca cargando datasets.
- Pendiente de verificar en T0 (lectura, no suposición): semántica de reemplazo por rol de `/meshes/upload` + campos del formulario; colisión de nombre de archivo en exportaciones repetidas; forma del soporte de tool-calls en `providers/base.py` / `openai_compat.py` / `config.py`; asignación de `session_id` en el middleware.

### 5.2 Niveles de riesgo

| Clase (`ToolRisk`) | Confirmación |
|---|---|
| READ, ADDITIVE, EXPORT | **Nunca** |
| REPLACE (secciones) | **Solo si ya existen secciones** (sus `state_keys` ≠ cero) |
| EXPENSIVE_REPLACE (conciliación) | **Solo si ya existen resultados** |
| DESTRUCTIVE, CONFIG | **Siempre** (fuera de la v1) |
| Herramienta desconocida | **Fail-closed**: nunca se ejecuta sin confirmación |

Consecuencia práctica: en una **sesión limpia**, el flujo completo `subir → secciones → procesar → exportar` corre **sin ninguna confirmación**. Con trabajo previo, pisarlo exige un clic explícito que muestra qué se reemplaza ("sobrescribe 78 resultados, ~42 s"). No hay excepción por "el usuario lo pidió explícitamente": el modelo no puede auto-autorizarse (anti-spoof); el coste de protección es un clic.

### 5.3 Matriz v1 (flujo geotécnico núcleo)

| Herramienta | Fuente | Clase | Confirmación |
|---|---|---|---|
| `get_workflow_state` | agregador con conteos SQL | READ | nunca |
| `list_meshes` | `db.list_meshes` | READ | nunca |
| `get_mesh_info` | `GET /meshes/{id}/info` | READ | nunca |
| `list_sections` | `GET /sections` | READ | nunca |
| `add_section_click` | `POST /sections/click` | ADDITIVE | nunca |
| `generate_sections_auto` | `POST /sections/auto` | REPLACE | sí si existen secciones |
| `generate_sections_manual` | `POST /sections/manual` | REPLACE | sí si existen secciones |
| `run_reconciliation` | `POST /process` (`_run_pipeline_sync`) | EXPENSIVE_REPLACE | sí si existen resultados |
| `get_results_summary` | `GET /process/results` + `/status` | READ | nunca |
| `get_profile` | `GET /process/profiles/{id}` (una sección, campos resumidos) | READ | nunca |
| `get_design_achievement` | `GET /process/design-achievement` | READ | nunca |
| `get_proposed_compliance` | `GET /process/proposed-compliance` | READ | nunca |
| `export_report` | `GET /export/{excel,word,pdf,dxf,images}` | EXPORT | nunca |

`upload_mesh` no es herramienta del modelo: es acción del frontend (drag&drop) que pasa el `mesh_id` como observación (§4.5). `get_profile` devuelve una sola sección con campos resumidos, nunca el dataset completo.

### 5.4 Guardarraíles transversales

1. `get_workflow_state` antes de cualquier escritura (estado real, no memoria del modelo).
2. Confirmación server-side con `PendingRun`; el modelo no puede auto-aprobarse; el front solo aprueba/deniega con el ID.
3. Una aprobación = una ejecución exacta (hash de args + fingerprint + sesión); claim atómico single-use; revalidación si el estado cambió.
4. Tope: máx **2 confirmaciones REPLACE/EXPENSIVE_REPLACE por turno** del usuario; más allá, el agente lo solicita en lenguaje natural.
5. Denegación → observación y sin reintento de la misma llamada en el turno.
6. Handlers sin auto-HTTP (§2); sesión del middleware; `extra="forbid"` en todos los modelos de args; sin imports dinámicos de herramientas.
7. Guard de concurrencia en `/process` (`process_status == "running"` → rechazo limpio).
8. Timeout por herramienta, separado del timeout del proveedor.
9. Log de auditoría por `tool_call` (args saneados, duración, resultado, `invocation_id`).
10. Proveedor sin `supports_tool_calls` → mensaje claro en la UI, sin fallo silencioso.

### 5.5 Ola 2 (mapeo o exclusión explícita de cada endpoint restante)

Tronadura (upload de pozos, resumen, holes/3d, correlation, damage-model), simulaciones, mapeos, settings/tolerancias (CONFIG — siempre confirmación), `delete_sections` / `delete_mesh` (DESTRUCTIVE — siempre confirmación), session, y generación de secciones desde archivo (`/sections/from-file`): acción del frontend — sube el CSV/DXF y pasa el resultado al agente como observación, igual que la subida de mallas — sin mecanismo backend para un `file_ref`. Cada endpoint queda mapeado a herramienta o excluido con motivo antes de declarar el feature completo (T7).

---

## 6. Seguridad y límites

- API keys solo backend; sanitización de errores existente.
- Tope de iteraciones (~8) + timeout global del chat + timeout por herramienta.
- Rate limit reutiliza `middleware_ratelimit.py`.
- Feature flags: `VITE_AI_CHAT=true` + `CONCILIACION_AI_CHAT_ENABLED` — la demo pública Render free (512 MB) puede mantenerlo apagado.
- Toda escritura de settings (ola 2) pasa por `save_settings` (incrementa `settings_version`).
- Las herramientas nunca mutan registros de pozos in situ ni devuelven blobs.

---

## 7. Matriz de pruebas

- **Tabla de verdad de `policy.py`**: cada clase × estado (vacío/con trabajo); herramienta desconocida → fail-closed.
- Selección correcta de herramienta; argumentos inválidos rechazados por schema (`extra="forbid"`).
- Sesión inexistente o ajena; timeout por herramienta; cancelación de stream.
- Confirmación: aprobada ejecuta **una vez** y el claim se consume; **claim concurrente → el segundo falla**; denegada continúa sin ejecutar y sin reintento; ID desconocido/expirado/de otra sesión rechazado; **args modificados tras aprobación → inválida**; **fingerprint de estado distinto → inválida y reevalúa**.
- Guard de `/process` en marcha (rechazo limpio).
- Reintentos de export sin colisión problemática de nombres.
- Sanitización de claves y errores; 413 legible en upload.
- Proveedor sin herramientas → evento de error claro.
- Front: lector NDJSON con mock, `ToolCallCard`, i18n ES/EN, móvil 390 px, ambos temas.

---

## 8. Entregas

- **T0 — Congelar contrato** *(completada — contrato congelado y validado: pytest/vitest/tsc dirigidos en verde)*: `core/ai_v2/agent/` — `models.py` (ToolRisk, ToolSpec, ToolState, PolicyDecision), `events.py` (unión discriminada + helpers NDJSON), `policy.py` (tabla de verdad pura), `catalog.py` (13 ToolSpec con schemas de los parámetros reales), `confirmations.py` (interfaz `PendingRunStore` + dataclass `PendingRun`, implementación T3); espejo TS `web/src/api/agentChat.ts` + fixture; tests de contrato y de tabla de verdad. Verificaciones por lectura: `/meshes/upload` (campos + reemplazo por rol), colisión de nombre en export, soporte de tool-calls en `providers/base.py`/`openai_compat.py`/`config.py`, asignación de sesión en middleware. **Sin HTTP, sin loop, sin handlers, sin llamadas a proveedores.**
- **T1 — Handlers de lectura** *(completada — handlers de solo lectura validados: 127 pytest dirigidos en verde)*: en `api/`, sobre `api.database`/dominio; conteos SQL. pytest con sesión fixture.
- **T2 — Bucle de tool-calling + eventos** *(completada — extensión aditiva de proveedores + bucle validados: 332 pytest del barrido ai_v2 en verde)*: con proveedor fake; extender provider sin romper `/ai/generate`.
- **T3 — `PendingRun` completo** (claim atómico, TTL, invalidación) + herramientas REPLACE + guards de concurrencia e idempotencia.
- **T4 — Endpoints `/ai/chat` y `/ai/chat/confirm`** (NDJSON, timeouts separados, flags, auditoría).
- **T5 — UI web del chat** (botón, panel, tarjetas, store, lector, i18n; vitest + build).
- **T6 — Integración visual**: instancia funcional con URL, probada con STL reales del usuario; dashboard refleja lo que el agente genera; móvil + ambos temas.
- **T7 — Gates finales**: pytest (`--ignore=tests/test_openblast.py`), vitest, `npx tsc -b`, `npm run build`, ESLint + revisión adversarial del delta (contratos/datos + anti-spoof/propagación) + HANDOFF + cierre del inventario §5.5.

---

## 9. Decisiones cerradas

1. **Proveedor/modelo**: selector existente (`useAIConfig`); herramientas v1 solo con proveedores con `supports_tool_calls` verificado.
2. **Política de escrituras**: clases de riesgo por estado (§5) — definida por el asistente por delegación del usuario.
3. **Carga de topos**: doble vía — drag&drop en el chat (siempre iniciada por el usuario, autónoma, con advertencia en línea y informe de reemplazo) + mallas ya cargadas.
4. **Alcance v1**: flujo geotécnico completo (subir → secciones → procesar → exportar), entregas incrementales T1–T5; inventario completo de routers como cierre (§5.5).
5. **Historial**: persistente en localStorage por sesión, solo presentación; la continuación confirmatoria vive en el `PendingRun` server-side.
6. **Destructivas y settings**: fuera de la v1; clase siempre-confirmación cuando entren.
7. **`core` sin dependencias de `api`**: catálogo puro en core; handlers/traducción en la capa API.

---

## 10. Riesgos

- Encadenamiento multi-paso erróneo → `get_workflow_state` previo, tope de iteraciones, confirmaciones.
- Costo/latencia por múltiples llamadas al modelo → caché de `ai_v2`, proveedor local como opción.
- Memoria de la API → resúmenes y conteos SQL, nunca blobs; la subida grande no pasa por el semáforo de blast (limitación conocida: no empeorarla).
- Store de `PendingRun` en memoria → válido en el despliegue single-process actual (SQLite, instancia única); migrar a BD si hay multi-worker.
- Demo pública Render free (512 MB) → feature flags permiten mantener el chat apagado.
