# Inventario REST — Ola 2 del agente (§5.5)

Metodología: conteo verificado contra los decorators `@router.*` de `api/routers/*.py` el 9-nov-2026 — **64 endpoints exactos**. `GET /api/v1/health` vive en `api/main.py`, fuera de los routers, y queda fuera del alcance. Clasificaciones:

- **CUBIERTO** — herramienta actual del catálogo v1 (14 ToolSpec; `query_results` añade lectura filtrada de resultados por cota/banco/sector/sección/parámetro/estado).
- **OLA-2** — candidato; `PENDING_USER_DECISION`: no se implementa ni se excluye sin la decisión explícita del usuario.
- **DESTRUCTIVO** — OLA-2 con confirmación nivel 3 obligatoria (irreversible o de alcance total).
- **FRONTEND** — acción del frontend (payload de visualización/transporte); excluido como herramienta.
- **EXCLUIDO** — infraestructura o transporte propio; sin valor como herramienta.

## /api/v1/ai (8)

| Método | Ruta | Clasificación | Detalle |
|---|---|---|---|
| GET | /ai/health | EXCLUIDO | Infra: estado del chat para la UI |
| GET | /ai/providers | EXCLUIDO | Infra: estado de proveedores para la UI del chat |
| POST | /ai/generate | EXCLUIDO | Transporte legacy del módulo de informes (lo consume la UI de informes) |
| POST | /ai/generate/stream | EXCLUIDO | Ídem (SSE) |
| POST | /ai/chat | EXCLUIDO | Transporte propio del agente — como herramienta sería circular |
| POST | /ai/chat/confirm | EXCLUIDO | Ídem |
| GET | /ai/chat/conversation/{conversation_id} | OLA-2 | Gestión de sesión del chat (historial saneado) |
| DELETE | /ai/chat/conversation/{conversation_id} | DESTRUCTIVO | Borrado real de conversación — nivel 3 |

## /api/v1/blast (7)

| Método | Ruta | Clasificación | Detalle |
|---|---|---|---|
| POST | /blast/preview | OLA-2 | Tronadura: preview rápido de diseño; revisar coste antes de toolizar |
| POST | /blast/upload | OLA-2 | Tronadura: carga de CSV de pozos |
| GET | /blast/definitions | OLA-2 | Tronadura: catálogos READ |
| GET | /blast/{session_id}/summary | OLA-2 ⚠️ | READ; `{session_id}` en path → requiere revisión de aislamiento de sesión antes de toolizar (vector anti-spoof que la política prohíbe) |
| GET | /blast/{session_id}/holes | OLA-2 ⚠️ | Ídem |
| GET | /blast/{session_id}/holes/{hole_id} | OLA-2 ⚠️ | Ídem |
| GET | /blast/holes/3d | FRONTEND | Payload de visualización Cesium |

## /api/v1/export (7)

| Método | Ruta | Clasificación | Detalle |
|---|---|---|---|
| GET | /export/excel | CUBIERTO | export_report |
| GET | /export/word | CUBIERTO | export_report |
| GET | /export/dxf | CUBIERTO | export_report |
| GET | /export/images | CUBIERTO | export_report |
| GET | /export/pdf | CUBIERTO | export_report |
| GET | /export/blast-diagnostics | OLA-2 | READ de diagnósticos de tronadura |
| GET | /export/blast-rejections | OLA-2 | READ de rechazos de importación |

## /api/v1/mapping (2)

| Método | Ruta | Clasificación | Detalle |
|---|---|---|---|
| GET | /mapping/schema | OLA-2 | Mapeos: catálogo de columnas; útil cuando el agente cargue CSV por cuenta propia |
| POST | /mapping/detect | OLA-2 | Mapeos: detección automática; verificar que no muta sesión |

## /api/v1/meshes (11)

| Método | Ruta | Clasificación | Detalle |
|---|---|---|---|
| POST | /meshes/upload | OLA-2 | Carga de mallas por el agente (hoy acción del frontend); REEMPLAZA la malla del mismo rol → confirmación si hay trabajo previo |
| POST | /meshes/dxf/inspect | OLA-2 | Paso 1 del flujo DXF |
| POST | /meshes/dxf/confirm | OLA-2 | Paso 2 del flujo DXF (REPLACE) → confirmación |
| DELETE | /meshes/dxf/{upload_id} | DESTRUCTIVO | Nivel 3 |
| GET | /meshes/{mesh_id}/info | CUBIERTO | get_mesh_info |
| GET | /meshes/{mesh_id}/vertices | FRONTEND | Payload three.js |
| GET | /meshes/{mesh_id}/vertices/roi | FRONTEND | Payload three.js (ROI) |
| GET | /meshes/{topo_id}/horizontal-deviation | OLA-2 | READ analítico diseño-vs-topo |
| DELETE | /meshes/{mesh_id} | DESTRUCTIVO | Nivel 3 |
| GET | /meshes/{mesh_id}/contours | FRONTEND | Payload Cesium |
| GET | /meshes/{mesh_id}/breaklines | FRONTEND | Payload Cesium |

## /api/v1/process (10)

| Método | Ruta | Clasificación | Detalle |
|---|---|---|---|
| POST | /process | CUBIERTO | run_reconciliation (claim atómico compartido, T7-bis) |
| GET | /process/status | CUBIERTO | Nota de cobertura: alcanzado vía get_workflow_state / get_results_summary — sin herramienta dedicada |
| GET | /process/results | CUBIERTO | get_results_summary; query_results (nuevo): lectura filtrada de resultados por cota/banco/sector/sección/parámetro/estado |
| GET | /process/profiles/{section_id} | CUBIERTO | get_profile |
| PUT | /process/results/{section_id}/reconciled | OLA-2 | Bench drag&drop (REPLACE del estado reconciliado) → confirmación |
| GET | /process/profiles/{section_id}/blast-holes | OLA-2 | READ tronadura↔geotecnia |
| GET | /process/blast-correlation | OLA-2 | READ |
| GET | /process/blast-correlation/damage-model | OLA-2 | READ |
| GET | /process/design-achievement | CUBIERTO | get_design_achievement (acepta filtros por sector/sección/cota/banco) |
| GET | /process/proposed-compliance | CUBIERTO | get_proposed_compliance (acepta filtros por sector/sección/cota/banco) |

## /api/v1/sections (9)

| Método | Ruta | Clasificación | Detalle |
|---|---|---|---|
| GET | /sections | CUBIERTO | list_sections |
| POST | /sections/auto | CUBIERTO | generate_sections_auto |
| POST | /sections/manual | CUBIERTO | generate_sections_manual |
| POST | /sections/click | CUBIERTO | add_section_click (AÑADE) |
| POST | /sections/from-file | OLA-2 | REPLACE → confirmación; requiere mecanismo file_ref (frontend sube el archivo y pasa la observación) |
| PUT | /sections/{section_id} | OLA-2 | REPLACE parcial → confirmación |
| DELETE | /sections/{section_id} | DESTRUCTIVO | Nivel 3 |
| DELETE | /sections | DESTRUCTIVO | Borra TODAS las secciones — nivel 3 con confirmación que nombre el alcance total |
| POST | /sections/curve | OLA-2 | Autoría de secciones (REPLACE) → confirmación |

## /api/v1/session (1)

| Método | Ruta | Clasificación | Detalle |
|---|---|---|---|
| GET | /session/recovery | EXCLUIDO | Bootstrap del frontend; el estado de flujo ya está cubierto por get_workflow_state |

## /api/v1/settings (2)

| Método | Ruta | Clasificación | Detalle |
|---|---|---|---|
| GET | /settings | OLA-2 | Settings READ |
| PUT | /settings | OLA-2 (CONFIG) | REPLACE de settings/tolerancias → confirmación obligatoria (nivel CONFIG) |

## /api/v1/simulations (7)

| Método | Ruta | Clasificación | Detalle |
|---|---|---|---|
| POST | /blast/simulations | OLA-2 (heavy) | Simulación completa; coste alto → confirmación |
| GET | /blast/simulations/{id} | OLA-2 | READ |
| GET | /blast/simulations/{id}/summary | OLA-2 | READ |
| GET | /blast/simulations/{id}/profile | OLA-2 | READ |
| GET | /blast/simulations/{id}/export | EXCLUIDO* | Duplica la familia export_report cuando simulaciones READ aterrice; re-clasificar a OLA-2 si el usuario quiere exportes de simulación |
| GET | /blast/simulations/{id}/plan | FRONTEND | Matriz 2D de visualización |
| GET | /blast/simulations/{id}/section | FRONTEND | Sección 2D de visualización |

## Conteo exacto

| Clasificación | Endpoints |
|---|---|
| CUBIERTO | 16 |
| OLA-2 (incl. 5 DESTRUCTIVOS nivel 3 + PUT /settings CONFIG) | 33 |
| FRONTEND | 7 |
| EXCLUIDO | 8 |
| **Total** | **64** |

Los 33 OLA-2 quedan como `PENDING_USER_DECISION` (§5.5 del plan): el pedido original fue "todas las herramientas de la app", así que el alcance — completo, núcleo (tronadura + settings + sesión) o reducido — lo decide el usuario, no el asistente.
