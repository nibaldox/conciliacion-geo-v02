# Plan de implementación y cierre de la versión web

Fecha: 2 de noviembre de 2026. Base de referencia: `main` en `fedbbef`.
Este plan organiza trabajo futuro; no acredita su ejecución ni autoriza publicación.
Complementa el plan del 29 de octubre y prioriza los hallazgos comprobados en Windows.

## Reparto Antigravity y GPT-6 Luna — continuación

El usuario pidió dividir la delegación entre Antigravity (AGY) y GPT-6 Luna. Cada entrega se revisa antes de integrarse; diagnósticos paralelos son de solo lectura y los cambios paralelos deben usar listas de archivos disjuntas. El árbol ya contiene cambios locales sin commit: preservarlos.

Estado de despacho: Luna recibió 1B y 1C. Tras el rechazo inicial de la revisión automática por posible transmisión de código a un servicio externo, el usuario autorizó expresamente esa transmisión; 1A fue despachada a AGY en modo de solo lectura.

Resultados iniciales de Luna: 1B confirma una regla Workbox `StaleWhileRevalidate` para GET de API sin clave explícita por sesión; el cruce de datos es un riesgo inferido, no una fuga reproducida. Probar dos sesiones sintéticas y revisar CacheStorage. 1C identifica que Playwright puede reutilizar servidores ajenos, que Edge está disponible pero no el Chromium descargado, y que el spec horizontal navega a `/` pese al prefijo configurado; la causa del timeout no está confirmada. Usar puertos y datos aislados, `reuseExistingServer: false` y redirigir capturas para no sobrescribir `docs/design`. Una revisión estática adicional del diff de informes no encontró defectos concretos; no sustituye pruebas ni inspección visual.

| Orden | Responsable | Tarea | Entrega y dependencia |
|---|---|---|---|
| 1A | Antigravity | Diagnosticar profundidad de informes desde resultados persistidos, selección por filtros y fuentes de cotas. | Propuesta y casos de regresión; sin cambiar criterios ni datos. |
| 1B | Luna | Auditar caché PWA de API y aislamiento entre sesiones. | Evidencia, riesgos e hipótesis claramente identificadas; definir prueba A/B. En paralelo con 1A. |
| 1C | Luna | Diagnosticar ejecución aislada de Playwright y bloqueo de pruebas en Windows. | Protocolo seguro, requisitos y limitaciones; sin utilizar servicios ni datos ajenos. En paralelo con 1A/1B. |
| 1D | Coordinador | Revisar el diff local previo y preparar el diseño verificable de perfiles Word. | Riesgos, propuesta de paginación y prueba visual; sin reinterpretar criterios de cumplimiento. |
| 2A | Antigravity | Implementar profundidad si el diagnóstico demuestra una fuente y semántica inequívocas. | Pruebas comparan datos en memoria y persistidos, filtros y ausencia de medición. Después de 1A y revisión del coordinador. |
| 2B | Luna | Implementar la corrección de caché si el diagnóstico lo justifica. | Prueba de aislamiento y efecto offline; después de 1B. Archivos distintos de 2A. |
| 2C | Luna | Resolver pruebas E2E obsoletas y preparar ejecución aislada. | Reproducción y pruebas focalizadas; después de 1C. |
| 3 | Coordinador + agentes | Verificación y cierre. | Revisar informes reales sobre copias, suites frontend/backend, Playwright, PDF y documentación; registrar omisiones. No publicar sin solicitud. |

La decisión sobre bermas con diseño bajo mínimo sigue pendiente del usuario. No ejecutar en paralelo tareas que editen el mismo archivo, ni gates completos pesados. Si AGY no está disponible, conservar la asignación y continuar las tareas independientes con Luna.

## Alcance y coordinación

- Prioridad: versión web y API. `core/` solo como soporte de la web, sin cambiar criterios científicos ni la API legacy estable. No modificar `app.py`, `ui/`, `electron/` ni `cli.py`.
- Un coordinador conserva el plan, asigna tareas pequeñas a subagentes **GPT-6 Luna**, revisa sus diferencias y repite la validación. Los subagentes no crean commits, no publican, no instalan dependencias ni alteran datos o procesos del usuario.
- Los agentes comparten el checkout. Ejecutar en paralelo solo tareas con archivos de escritura disjuntos; el coordinador asignará listas concretas de archivos tras cada diagnóstico. No ejecutar gates pesados simultáneamente.
- Trabajar con datos y puertos aislados. Comprobar los puertos antes de levantar servicios; Playwright tiene `reuseExistingServer: true`, por lo que no debe conectarse accidentalmente a una instancia existente. Cerrar solo procesos propios identificados.
- Cada tarea entrega archivos modificados, evidencia de pruebas, riesgos y pendientes. Mantener todas las aserciones útiles, textos ES/EN y convenciones del repositorio. Para defectos reproducibles, preferir una regresión que falle antes del arreglo.
- No tratar los conteos, PIDs ni permisos históricos como estado actual. No cambiar criterios de cumplimiento sin decisión explícita.

## Tanda 0 — Línea base y bloqueo de Windows

| ID | Tarea para Luna | Alcance | Aceptación y dependencia |
|---|---|---|---|
| W00 | Inventariar versiones y dependencias locales; reproducir el error TypeScript que involucra `ResultFilters.tsx` y `resultFilters.ts`. | Solo lectura. | Registrar comando, errores y archivos afectados. No instalar dependencias. |
| W01 | Eliminar la ambigüedad de nombres entre el componente y el módulo de filtros; actualizar imports y pruebas afectadas. | `web/src/components/results/` y consumidores directos. | TypeScript `tsc -b --force` pasa en Windows; tests de filtros y dashboard pasan; confirmar que Linux también resuelve los imports. Después de W00. |
| W02 | Diagnosticar el `EPERM` del temporal de Vitest y buscar una ejecución aislada en una ruta escribible del proyecto. | Configuración de ejecución y directorio temporal aislado; sin cambios de producción inicialmente. | Un test focalizado se ejecuta o se registra la causa exacta y limitación; no concluir que los tests funcionales fallaron por un error de entorno. |
| W03 | Ejecutar línea base frontend: TypeScript, lint, cobertura y build; anotar versiones y resultados. | Solo ejecución; artefactos generados ignorados. | Resultados completos o fallos concretos clasificados; después de W01 y W02. Si un gate falla, crear una tarea pequeña antes de continuar con cambios relacionados. |
| W04 | Revisar el estado actual de los gaps G01–G18 de `docs/UI_PARITY_AUDIT.md`. | Solo lectura. | Matriz implementado/parcial/pendiente con rutas y evidencia; distinguir presencia de código de validación funcional. |

W00, W02 y W04 pueden comenzar en paralelo. W01 sigue a W00; W03 es secuencial y no se ejecuta junto a suites pesadas.

## Tanda 1 — Exportación y experiencia de informes

| ID | Tarea para Luna | Archivos previstos | Aceptación |
|---|---|---|---|
| W10 | Exponer al navegador `Content-Disposition` y `X-Export-Filters-Applied` para orígenes permitidos. | `api/main.py`, pruebas CORS. | Regresión con `Origin` permitido y cabecera de exposición; pruebas CORS existentes pasan. |
| W11 | Traducir el aviso de filtros aplicados del panel de exportación. | `ExportPanel.tsx`, locales ES/EN y test del panel. | Cambio de idioma comprobado y sin cadena visible fija del aviso. |
| W12 | Representar en gris las secciones excluidas por filtros en el plano del informe. | `core/report_charts.py` y pruebas de gráficos. | Caso con secciones incluidas y excluidas; leyenda clara y sin cambio de generadores legacy. |
| W13 | Revisar robustez del render de gráficos, sin retirar la guarda de tamaño. | `core/report_charts.py` y pruebas de gráficos. | Diagnóstico y, si procede, figuras independientes y limpieza garantizada; pruebas de renders repetidos y concurrentes. Después de W12. |
| W14 | Evitar títulos huérfanos en Word y marcar el índice para actualizar al abrir. | `core/web_word_report.py` y pruebas Word. | XML del documento comprueba ambas propiedades. |
| W15 | Mejorar tamaño y paginación de perfiles Word. | `core/web_word_report.py` y pruebas Word. | Un perfil no conforme por página a ancho completo; anexo de dos por página sin bajar de 16 cm; comprobar visualmente. Después de W14. |
| W16 | Investigar la estación de la punta en pozos inclinados y la profundidad desde filas persistidas. | Solo lectura de geometría, informes y pruebas. | Dos diagnósticos separados con ejemplos, impacto y propuesta; cambios de dominio a cargo del coordinador con revisión de dominio. |

W10, W11, W12, W14 y W16 son candidatos paralelos con listas de archivos cerradas. W13 sigue a W12 y W15 a W14. Las dimensiones y criterios de W15 se revisarán con datos reales antes de declarar el diseño terminado.

## Tanda 2 — Navegador y aislamiento de sesiones

| ID | Tarea para Luna | Alcance | Aceptación |
|---|---|---|---|
| W20 | Verificar los fallos históricos de textos de `app.spec.ts` y corregir expectativas obsoletas si siguen vigentes. | Spec correspondiente. | Especificación alineada con la interfaz real, sin eliminar aserciones; ejecución focalizada. |
| W21 | Verificar casing del estado de cumplimiento en `compliance-plan.spec.ts`. | Spec correspondiente. | Alineado con el contrato real y prueba focalizada verde. |
| W22 | Diagnosticar el timeout de `horizontal-deviation.spec.ts`. | Solo lectura y reproducción aislada. | Identificar selector, fixture o defecto real con evidencia; proponer fix específico. |
| W23 | Revisar caché PWA de respuestas API por sesión. | `web/vite.config.ts` y pruebas aisladas. | Reproducir o descartar el escenario A/B con igual URL y distinto `X-Session-ID`; evaluar también datos obsoletos. No afirmar fuga sin evidencia. |
| W24 | Implementar la política de caché de API que resulte del diagnóstico W23. | Configuración PWA y pruebas asociadas. | Prueba de aislamiento A/B y comportamiento de actualización; documentar el efecto offline. `NetworkOnly` es una opción a evaluar, no un resultado predeterminado. |
| W25 | Ejecutar Playwright completo con datos y servicios propios aislados. | Solo ejecución. | Registrar aprobadas, fallos, omitidas y artefactos; sin reutilizar servidores del usuario. Después de W20–W24 y sus correcciones. |

W20, W21, W22 y W23 pueden trabajar en paralelo. W24 depende de W23; el coordinador revisa cualquier cambio de comportamiento offline antes de aplicarlo.

## Tanda 3 — Revisión y estabilización del visor

| ID | Tarea para Luna | Alcance | Aceptación |
|---|---|---|---|
| W30 | Auditar los pendientes históricos de selección de curvas y visor. | Solo lectura. | Marcar cada pendiente vigente, resuelto o no verificable con evidencia actual. |
| W31 | Corregir únicamente el orden de declaración de `previewRef` si W30 confirma el problema. | `Mesh3DViewer.tsx` y test pertinente. | Sin cambio funcional; pruebas focalizadas y TypeScript pasan. |
| W32 | Verificar precisión del marcador respecto al payload y centro de render. | Visuales de selección y pruebas. | Caso con coordenadas grandes; fix solo si se reproduce una diferencia relevante. |
| W33 | Verificar sincronización de tolerancias del panel con settings del servidor. | Sidebar/formulario y pruebas. | Los cambios externos se reflejan cuando no se edita y no sobrescriben una edición en curso; implementar solo si el diagnóstico demuestra el problema. |

El índice espacial del topo permanece pospuesto por decisión previa. No introducir optimizaciones especulativas de handlers o render sin medición y justificación.

## Tanda 4 — Validación real y cierre

| ID | Responsable | Tarea | Aceptación |
|---|---|---|---|
| W40 | Coordinador | Revisar disponibilidad y procedencia de datos reales; trabajar sobre copias y sin reprocesar la sesión del usuario sin autorización. | Identificar datos utilizables o solicitar los que falten. |
| W41 | Coordinador | Verificar C1, regenerar e inspeccionar Word/PDF y medir tiempo y tamaño con el mismo conjunto real. | Evidencia visual y tiempos; meta histórica Word < 6 s y < 1,5 MB para 109 filas, o registrar desviaciones y condiciones del equipo. |
| W42 | Usuario + coordinador | Decidir si excluir del ranking las bermas cuyo diseño es inferior al mínimo. | Decisión explícita antes de cambiar la selección; conservar clasificación actual hasta entonces. |
| W43 | Luna | Auditar configuración web de despliegue y contratos reales. | Verificar `render.yaml`, URL de API y workflow contra el código; corregir solo discrepancias demostradas en tarea separada. No ampliar a empaquetado portable. |
| W44 | Coordinador | Correr gates completos frontend/backend, Playwright y revisión de diferencias. | Registrar comandos, versiones, conteos y límites; no equiparar suites verdes con validación visual o despliegue. |
| W45 | Coordinador | Actualizar `docs/HANDOFF.md`, auditoría de paridad y conteos aplicables del README. | Estado comprobado, pendientes y evidencias claros. No hacer push ni desplegar sin solicitud vigente. |

## Plantilla de asignación

```text
Tarea: WXX — título.
Objetivo y comportamiento esperado: ...
Archivos permitidos para escritura: ...
Contexto y evidencia: ...
Restricciones: no modificar app.py, ui/, electron/ o cli.py; no commit,
push, instalación de dependencias ni cambios de datos/procesos ajenos.
Validación: reproducir el defecto cuando corresponda, añadir regresión útil,
ejecutar pruebas focalizadas y entregar comandos, resultados y limitaciones.
```

El coordinador revisa cada entrega antes de integrarla y resuelve conflictos de alcance. Una tarea bloqueada no detiene los diagnósticos independientes.
