# Selección continua de puntos sobre el diseño — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. En este perfil, aplicar el flujo disponible `parallel-coding-workflows`: subagentes nuevos por entrega, propiedad de archivos, TDD, integración y dos revisiones independientes. No instalar habilidades ni cambiar la configuración para ejecutar este plan.

**Goal:** Seleccionar el inicio y el final de un tramo exactamente sobre la línea de diseño señalada por el ratón, sin cuantizar a vértices ni capturar silenciosamente líneas vecinas, y generar perfiles únicamente a lo largo del tramo confirmado.

**Architecture:** Separar geometría continua, decisión de picking en pantalla y estado de interacción en funciones pequeñas y comprobables. El visor, el formulario y el payload consumirán una misma representación del punto seleccionado. Conservar `POST /api/v1/sections/curve` y el generador existente: enviar una polilínea XY recortada con extremos interpolados y vértices intermedios originales.

**Tech Stack:** React 19, TypeScript, Zustand, Three.js r184, React Three Fiber/Drei, Vitest/Testing Library, Playwright; FastAPI y core Python existentes para comprobar el contrato de generación.

---

## 1. Alcance y supuestos

- La solicitud inicial autorizó **un plan**, no implementar código. Posteriormente el usuario autorizó T01, T02 y finalmente continuar con T03–T14 en orden; el registro de ejecución se encuentra al final de este documento.
- La mejora parte del modo existente **sobre una línea del diseño**. No añade selección libre sobre cualquier triángulo, ni un nuevo modo de perfiles entre dos puntos arbitrarios de la superficie.
- Mantener el paso de elegir la línea y después sus extremos. El primer clic no se reinterpretará silenciosamente como inicio si actualmente solo selecciona la línea.
- Después de elegir la línea, inicio y final quedan restringidos a esa misma curva/ramal. Para cambiar de línea habrá una acción explícita de restablecimiento.
- El campo «Sector» del formulario es una etiqueta de las secciones generadas, **no una restricción espacial**. Cambiar esa etiqueta no corrige este problema.
- No modificar Streamlit, Electron, CLI, matching, tolerancias de cumplimiento ni geometría de conciliación.
- No hacer commit, push ni despliegue sin una autorización posterior específica.
- Preservar todos los cambios locales del bloque 1 y los de dH. HEAD inspeccionado: `7348b8cb55a6484ed8971f46c1130a566b87b798`, rama `main`, con cambios sin confirmar. Antes de ejecutar, volver a leer `AGENTS.md`, `docs/HANDOFF.md`, `git status` y los diffs actuales.

## 2. Diagnóstico que sustenta el plan

### Evidencia directa

1. `web/src/components/mesh/Mesh3DViewer.tsx:125-128` fija `raycaster.params.Line.threshold = 5`. Es una tolerancia en unidades de la escena, no una distancia constante en píxeles; con el mapeo actual, la geometría está expresada en metros.
2. `Mesh3DViewer.tsx:394-402` transmite `e.point` y `e.index`, pero llama `vertexIndex` al índice recibido.
3. `Mesh3DViewer.tsx:309-326` reconstruye el marcador con `segment[pt.pointIndex]`, descartando la posición continua del clic.
4. `web/src/components/sections/SectionCurveForm.tsx:76-81` genera el tramo con `segment.slice(...)`. Las coordenadas seleccionadas `x/y` no se usan como extremos efectivos.
5. `SectionCurveForm.tsx:103` exige índices diferentes: dos puntos distintos dentro del mismo segmento pueden resultar no seleccionables como tramo.
6. El formulario ya bloquea otra curva (`SectionCurveForm.tsx:36-39`), pero el visor detiene propagación antes de esa comprobación (`Mesh3DViewer.tsx:395`). La restricción debe actuar al elegir candidatos, no solo descartando el resultado después.
7. El endpoint ya acepta una lista de puntos (`api/routers/sections.py:483-510`). El generador documenta puntos Nx2 y calcula longitudes con todas las columnas que recibe (`core/section_cutter.py:322-359`): enviar explícitamente XY y conservar Z solo para visualización/identidad del ancla.

### Reproducción ejecutada

Con la dependencia Three.js instalada, una línea sintética entre X=0 y X=100 y dos rayos en X=20 y X=80 producen:

| Clic | `event.point.x` | `event.index` | Marcador con el código actual |
|---|---:|---:|---:|
| Inicio | 20 | 0 | 0 |
| Final | 80 | 0 | 0 |

La comprobación actual de índices diferentes rechaza ese tramo. Esto demuestra la cuantización errónea; no demuestra que sea la única causa de cada selección de otro sector del caso real del usuario.

## 3. Resultado esperado para el usuario

1. Elegir la línea de diseño.
2. Ver un candidato que sigue de forma continua el tramo de línea bajo el cursor.
3. Confirmar inicio y final sin saltos a vértices.
4. Ver resaltado **el recorrido exacto** que se utilizará, con los extremos diferenciados.
5. Generar perfiles solo dentro de ese recorrido; cambiar el zoom no debe convertir un clic alejado en una selección válida.
6. Si no hay candidato válido, no modificar la selección ni buscar otra línea en silencio.

No se promete que un clic fuera de una línea se guarde como un punto libre: el ajuste se hará sobre el segmento visible, dentro del radio de captura permitido.

## 4. Contratos que debe congelar el coordinador antes de delegar implementación

### 4.1 Ancla continua propuesta — archivo NUEVO

`web/src/components/sections/curveSelectionTypes.ts`

Representación propuesta `CurveAnchor`:

- `curveId`: identidad de la polilínea/ramal actualmente cargado.
- `segmentIndex`: índice del par consecutivo de vértices que contiene el punto; no llamarlo índice del punto seleccionado.
- `t`: fracción en ese segmento, entre 0 y 1, con normalización determinista de extremos compartidos.
- `position`: tupla XYZ en coordenadas mineras originales: Este, Norte, Elevación.
- `chainage`: distancia acumulada **XY** desde el inicio de esa polilínea.

Contrato congelado para T01:

- `MiningPoint3D`: tupla readonly `[east: number, north: number, elevation: number]`.
- `CurveSelectionContext`: `designMeshId: string` y `geometryKey: string`, ambos readonly.
- `CurveAnchor`: `context: CurveSelectionContext`, `curveId: string`, `segmentIndex: number`, `t: number`, `position: MiningPoint3D`, `chainage: number`; todos readonly.
- `geometryKey` es una identidad opaca local de los datos de curvas vigentes, no un campo/revisión que se afirme disponible en la API. El adaptador de T06 deberá producirla y cambiarla cuando se sustituya la geometría; la igualdad del contexto compara `designMeshId` y `geometryKey` por valor, no la referencia del objeto.
- No conservar `pointIndex` como alias del punto continuo ni duplicar `x/y` junto a `position`. El callback legado no se modifica en T01: la migración de consumidores corresponde a T06.

Una recarga/reemplazo de esa geometría invalida anclas antiguas; no reutilizar un índice sobre otra versión de la curva. Los tipos de T01 son estructurales: no garantizan en ejecución finitud, integralidad, rango de `t` ni pertenencia geométrica. Esas validaciones pertenecen a T02–T05.

Reglas:

- Derivar `position` de la geometría original y `t`, no de un vértice cercano ni de coordenadas globales convertidas a Float32.
- Mantener las transformaciones actuales: render X=Este−centroX, Y=Elevación−centroZ, Z=−(Norte−centroY).
- Rechazar valores no finitos, índices fuera de rango y segmentos de longitud nula. No convertir errores a `(0, 0, 0)`.
- Usar una única convención para normalizar `t=0/1`, estaciones y puntos repetidos.
- En un vértice compartido, preferir el segmento inmediatamente siguiente con `t=0` si ese segmento es válido; en el extremo final abierto, conservar el último segmento válido con `t=1`. No saltar sobre segmentos degenerados inventando una continuidad ni renumerar la geometría original. En curvas cerradas, no identificar automáticamente la estación final con la inicial.
- `chainage` se mide desde el inicio de la curva original en XY, no desde el primer clic, sin redondearlo antes de generar. Las anclas coincidentes en la misma estación no forman un tramo válido; dos estaciones diferentes en un mismo segmento sí pueden formarlo.
- No incorporar este DTO al endpoint: es un contrato interno de la interacción web.

### 4.2 Recorte de la polilínea

Archivo NUEVO propuesto: `web/src/components/sections/curveRange.ts`.

Entrada: curva original y dos anclas válidas de la misma identidad/contexto.

Salida: puntos ordenados desde el inicio elegido hasta el final, compuestos por:

1. Inicio interpolado.
2. Solo los vértices originales estrictamente interiores al tramo.
3. Final interpolado.

Conservar la curvatura y el sentido de selección. No sustituir el recorrido por la recta inicio–final. Evitar duplicados consecutivos en extremos que ya son vértices. Dos anclas distintas dentro del mismo segmento son un caso válido.

El payload de generación usará exclusivamente las componentes XY de ese resultado. No cambiar el criterio actual del generador de empezar a media separación ni su orientación/asimetría.

### 4.3 Selección en pantalla

Archivo NUEVO propuesto: `web/src/components/mesh/curvePicking.ts`.

- Candidatos vinculados a la geometría visible y al contexto actual.
- Si ya hay curva elegida, filtrar por ella **antes** de decidir qué intersección consume el evento.
- Comparar distancia al cursor en **píxeles CSS**, usando la proyección y la cámara actuales. No multiplicar dos veces por `devicePixelRatio`.
- Radio inicial propuesto: 8 píxeles CSS con ratón. Es un parámetro de interfaz por validar en QA, no una tolerancia geotécnica ni un valor calibrado.
- Para táctil, considerar un radio separado solo si se valida; no ampliar automáticamente la captura de escritorio.
- El radio mundial de búsqueda del raycaster puede ser conservador y dependiente de cámara/profundidad, pero la aceptación final debe cumplir el límite en pantalla.
- Resolver empates de manera estable. No aceptar detrás de cámara ni elegir líneas ocultas/vecinas solo por estar dentro de una tolerancia mundial grande.

## 5. Descomposición en entregas pequeñas

Cada tarea de implementación ejecutará un ciclo vertical: **una prueba relevante → fallo observado por la conducta ausente → implementación mínima → prueba focalizada aprobada → detenerse**. Los errores de mocks/importación no cuentan como RED de comportamiento.

Los archivos marcados NUEVOS son propuestas del plan, no archivos que ya existan. El coordinador confirmará rutas y convenciones antes de crearlos.

### T01 — Congelar tipos y reglas de selección

**Responsable:** coordinador, con revisión breve de un subagente.

**Archivos:** NUEVO `web/src/components/sections/curveSelectionTypes.ts`; lectura de `session.ts`, visor y formulario.

**Objetivo:** fijar el contrato anterior y las reglas de normalización, sentido y cancelación, sin añadir lógica de picking.

**Aceptación:** no quedan ambiguos `segmentIndex`, `t`, XYZ frente a XY ni el caso de dos puntos en una misma arista. Identificar todos los lectores/escritores afectados antes de migrarlos.

**Dependencias:** ninguna. **Salida:** contrato escrito que se entrega íntegro a los siguientes agentes.

### T02 — Resolver un ancla continua sobre un segmento

**Responsable:** subagente de geometría A.

**Archivos propios:** NUEVO `web/src/components/sections/curveAnchorGeometry.ts`; NUEVO `web/src/components/sections/__tests__/curveAnchorGeometry.test.ts`.

**Objetivo:** convertir una posición/intersección válida en segmento, fracción, XYZ y estación XY coherentes.

**Primer RED:** sobre la arista sintética 0–100, anclas en 20 y 80 conservan sus posiciones y son diferentes aunque compartan segmento.

**Otros casos, en ciclos separados si hacen falta:** extremos exactos, vértices repetidos, coordenadas grandes con diferencias pequeñas, no finitos y segmentos degenerados.

**Aceptación:** anclas numéricas correctas sin mutar la curva ni inferir datos; precisión calculada sobre datos originales.

**Dependencia:** T01. **Paralelizable:** T04 y T05.

### T03 — Recortar un recorrido con extremos interpolados

**Responsable:** subagente de geometría B.

**Archivos propios:** NUEVO `web/src/components/sections/curveRange.ts`; NUEVO `web/src/components/sections/__tests__/curveRange.test.ts`.

**Objetivo:** construir la polilínea exacta entre dos anclas.

**Primer RED:** inicio y final dentro del mismo segmento generan dos extremos distintos, no un tramo vacío ni los dos vértices completos.

**Ciclos siguientes:** varios segmentos conservando esquinas; selección inversa; extremo sobre un vértice sin duplicarlo; rechazo de anclas de curvas/contextos diferentes y de longitud nula.

**Aceptación:** ningún punto generado para el recorrido queda antes/después del tramo elegido en estación; invertir extremos invierte el mismo recorrido.

**Dependencias:** T01 y T02. No duplicar la función de estaciones de T02.

### T04 — Seleccionar candidatos con un límite en píxeles

**Responsable:** subagente de picking C.

**Archivos propios:** NUEVO `web/src/components/mesh/curvePicking.ts`; NUEVO `web/src/components/mesh/__tests__/curvePicking.test.ts`.

**Objetivo:** elegir o rechazar candidatos según distancia en pantalla, línea activa y visibilidad.

**Primer RED:** una curva vecina no puede ganar si ya existe una curva seleccionada; fuera del radio no hay selección.

**Ciclos siguientes:** cámaras/profundidades diferentes, zoom, DPR distinto, empate estable y candidatos detrás de cámara.

**Aceptación:** resultado determinista; las unidades de captura son píxeles CSS. Separar radio mundial de búsqueda y radio final de aceptación.

**Dependencia:** T01. **Paralelizable:** T02 y T05. No editar aún `Mesh3DViewer.tsx`.

### T05 — Estado de selección como función pura

**Responsable:** subagente de interacción D.

**Archivos propios:** NUEVO `web/src/components/sections/curveSelectionState.ts`; NUEVO `web/src/components/sections/__tests__/curveSelectionState.test.ts`.

**Objetivo:** definir transiciones sin depender del render 3D.

**Primer RED:** tras elegir una curva y un inicio, un clic en otra curva no cambia el inicio ni confirma un final allí.

**Casos:** elegir línea; elegir inicio; elegir final distinto en el mismo segmento; tercer clic según comportamiento explícito de reinicio; cancelar; cambio de malla/curvas; éxito de generación; geometría inválida.

**Aceptación:** no confundir elegir línea con elegir inicio; no conservar anclas obsoletas; el formulario puede explicar por qué una selección se rechaza.

**Dependencia:** T01. **Paralelizable:** T02 y T04.

### T06 — Conectar el contrato continuo de extremo a extremo

**Responsable:** un único subagente integrador; no dividir estos archivos entre escritores simultáneos.

**Archivos propios:** preparación compartida NUEVA `web/src/components/sections/curveGeometryAdapter.ts` y `__tests__/curveGeometryAdapter.test.ts`; después, un único escritor sobre `web/src/stores/session.ts`, `web/src/components/mesh/Mesh3DViewer.tsx`, `web/src/components/sections/SectionCurveForm.tsx` y NUEVO `web/src/components/sections/__tests__/SectionCurveForm.selection.test.tsx`. Regresión adicional de integración: NUEVO `web/src/stores/__tests__/session.curve-selection.test.ts` para identidad de raíz y suscripciones en no-ops.

**Objetivo:** que el mismo punto continuo sea recibido, almacenado, dibujado y enviado al generador.

**Trabajo acotado:** consumir T02–T05, sustituir el uso semánticamente incorrecto de `pointIndex`, dibujar desde `position` y obtener el payload con T03. `LeftSidebar.tsx:307` pasa el setter como callback; verificar compatibilidad sin modificar su guardado de tolerancias.

**Primer RED de integración:** dos clics distintos en una sola arista habilitan generación y la mutación recibe esos extremos XY, no los vértices de la arista.

**Aceptación:** marker/formulario/payload coinciden; la firma del callback y todos sus lectores compilan juntos; se conserva el recorrido inverso, separación, longitudes arriba/abajo y sector.

**Dependencias:** T02, T03, T04, T05. Esta es la única entrega atómica que puede tocar los tres adaptadores compartidos: los cálculos ya deben estar terminados y probados. Si descubre una nueva regla, detener y devolverla al coordinador, no ampliar el trabajo.

**Preparación T06a fijada por el coordinador:** compartir una instantánea de las curvas originales y su contexto entre formulario y visor, en vez de duplicar conversión e inventar dos tokens distintos. `getCurveGeometrySnapshot(designMeshId, contourData)` devolverá un contexto local estable y un mapa readonly de curvas con ID original, tipo y puntos XYZ válidos. Cache débil por objeto de datos inmutable e ID de malla: sustituir los datos o la malla cambia contexto; conservarlos mantiene la instantánea. Convertir puntos XY a XYZ usando únicamente la elevación finita declarada por la línea; una Z explícita inválida no se sustituye por cero ni por otra cota. Rechazar la polilínea inválida sin reindexar las restantes. T06b consume este adaptador y migra los tres consumidores atómicamente. No se modifica API/core ni T01–T05 para crear la identidad compartida.

### T07 — Integrar captura adaptativa y no consumir clics equivocados

**Responsable:** subagente del visor E.

**Archivos propios:** preparación NUEVA `web/src/components/mesh/curveScenePicking.ts` y `web/src/components/mesh/__tests__/curveScenePicking.test.ts`; después `web/src/components/mesh/Mesh3DViewer.tsx` y su prueba focalizada de picking/interacción.

**Objetivo:** sustituir la tolerancia fija de 5 unidades por búsqueda adaptativa más validación final de T04.

**Primer RED:** una línea ajena que recibe antes una intersección no bloquea la selección válida de la línea activa; un clic fuera del radio no mueve los extremos.

**Aceptación:** no ejecutar `stopPropagation` para un candidato descartado antes de permitir resolver el válido; selección estable con zoom y líneas cercanas; no disparar una selección al arrastrar la cámara.

**Dependencias:** T04 y T06. **No paralelizar:** T08/T09, porque editan el mismo visor.

### T08 — Vista previa del candidato bajo el cursor

**Responsable:** subagente del visor E, en una entrega nueva.

**Archivos propios:** `Mesh3DViewer.tsx` y prueba de interacción focalizada.

**Objetivo:** mostrar antes del clic dónde se fijará realmente el punto.

**Primer RED:** el candidato se mueve dentro de una arista sin saltar a sus vértices y desaparece cuando se abandona el radio válido.

**Aceptación:** estilo diferente de los puntos confirmados; no modificar el estado confirmado en cada movimiento; no recorrer toda la geometría ni crear arrays grandes en cada frame sin necesidad.

**Dependencias:** T07. La vista previa debe usar la misma función de aceptación que el clic, no otro algoritmo aproximado.

### T09 — Resaltar el tramo exacto y distinguir sus extremos

**Responsable:** subagente del visor E, en una entrega nueva.

**Archivos propios:** `Mesh3DViewer.tsx`; NUEVOS `web/src/components/mesh/curveSelectionVisuals.ts` y `web/src/components/mesh/__tests__/curveSelectionVisuals.test.ts` para probar el mismo dato de render sin mocks frágiles de WebGL.

**Objetivo:** mostrar el recorrido que se enviará, con inicio/final distinguibles por algo más que color.

**Primer RED:** la geometría resaltada contiene los extremos interpolados y las esquinas originales, no toda la línea ni una diagonal entre extremos.

**Aceptación:** visor y payload comparten el resultado de T03; no reutilizar un índice de vértice para el marcador. Una curva cerrada no elige silenciosamente otro arco.

**Dependencias:** T06 y T08. **Paralelizable:** T10 y T11.

### T10 — Mensajes y controles de confirmación

**Responsable:** subagente de formulario F.

**Archivos propios:** `SectionCurveForm.tsx`; `web/src/locales/es.json`; `web/src/locales/en.json`; NUEVO `web/src/components/sections/__tests__/SectionCurveForm.feedback.test.tsx`; la regresión existente `SectionCurveForm.selection.test.tsx` se preserva salvo una adaptación imprescindible y revisada.

**Objetivo:** hacer comprensible la selección sin exponer `P0/P1` como si fueran los puntos exactos.

**Trabajo:** mostrar XY y distancia del tramo/estación según el contrato; explicar la línea activa, rechazos y cancelación; actualizar la ayuda; restablecer claramente para escoger otra línea.

**Primer RED:** dos extremos del mismo segmento se presentan como posiciones distintas y el botón responde a la longitud real, no a la diferencia de índices.

**Aceptación:** todas las cadenas en ES/EN; cero es válido; ausencia/error no se convierte en coordenada cero; accesibilidad por etiquetas, foco y Escape. No añadir un modo libre nuevo.

**Dependencia:** T06. **Paralelizable:** T09 y T11, con propiedad de archivos estricta.

### T11 — Verificar el contrato existente con la API

**Responsable:** subagente de regresión API G.

**Archivos propios:** NUEVO `tests/api/test_curve_selection.py`; lectura de `api/routers/sections.py` y `core/section_cutter.py`.

**Objetivo:** proteger el envío de una polilínea XY con extremos interiores sin rediseñar el endpoint.

**Casos:** dos extremos interiores; recorrido con una esquina; selección inversa; tramo más corto que spacing; longitudes asimétricas; aislamiento de sesión.

**Aceptación:** los orígenes de las secciones permanecen dentro del recorrido enviado; separación y azimut siguen el comportamiento documentado del generador. No exigir perfiles exactamente en ambos extremos: hoy se sitúan a media separación.

**Dependencia:** T03 para fijar casos y payload. Usar la fixture raíz `api_test_client` y datos aislados. Esta es una tarea de regresión del contrato existente: puede pasar antes de cambiar producción; no inventar un RED ni modificar API/core para forzarlo. Si revela un defecto real, reportarlo y abrir una tarea mínima separada autorizada por el coordinador.

### T12 — Prueba de navegador con clics reales

**CERRADA — 18 de octubre.** Causa del `database is locked` demostrada con pilas nativas (`fsync` del commit WAL y del checkpoint al cerrar la última conexión, en btrfs). Fix aprobado por el usuario: `synchronous=NORMAL` + conexión centinela en lifespan; TDD 4 casos, suite Python 2537/12 skip. Estrés 0/24 000; probe de arranque real 1200/1200; **smoke combinado 11/11 dos veces**, cero retries/flaky (`data/qa-curve-selection/t12-dbfix-smoke/`). T13 y T14 habilitadas.

**PAUSADA por el usuario — 17 de octubre, 23:02 −03:00.** No continuar hasta nueva solicitud. Snapshot `data/qa-curve-selection/pause-20261017-230219/`, 457 hashes iguales al último freeze. Interrupción de diagnóstico `deleg_cdb8d944` solicitada, sin resultado final todavía; conservar parciales y registrar resultados tardíos sin reanudar. API/Vite propios cerrados, puertos 8000/5181/5173 libres y PID propios ausentes. T12 incompleta por bloqueo SQLite real tras restart, no por layout/fuentes ya aprobados; T13/T14 siguen pendientes. Gates actuales frontend704/77 + dominio100/tsc/lint/PWA, API aislada58, fuentes32/32; no nuevo smoke completo después del probe de boot fallido.

**Resultado tardío de interrupción registrado, sin reanudar:** `deleg_cdb8d944` finaliza `interrupted`, cuatro llamadas, esperando respuesta del modelo. Sin diagnóstico concluido ni GREEN verificable en la entrega. No se ejecutaron ni inspeccionaron parciales; la pausa sigue vigente.

**Reanudación autorizada — 17 de octubre, 21:57 −03:00:** el usuario pidió retomar y continuar. Snapshot de pausa idéntico en 450 fuentes; baseline nueva `t12-resume-20261017-215744/`. Node 22.23.3 restaurado en scratch con SHA256 oficial, sin tocar dependencias. Replay central del legado **2 PASS / 1 FAIL**: clipping derecho de una acción (266,46875 > 259), no selector de Reset, que ya es correcto. Vite propio 5181 `proc_b58731c8c7cb`, sin API para este fixture interceptado. Reparación acotada `deleg_cb0fd64b` solo CSS/legado, con las aserciones previas intactas y comprobaciones de texto/bounds/altura mínima/1001. Sin cobertura/build ni QA simultáneos durante escritura. T12 sigue abierta y T13/T14 esperan su cierre.

**Resultado posterior de esa reparación:** worker 3/3, CSS/legado únicos archivos cambiados; captura 640 revisada. Gates centrales actuales **704/77 + dominio 100% + tsc/lint/PWA**, **53 API** aprobados. Smoke central combinado **9 PASS / 2 FAIL**, cero retries: tres legado ampliados pasan; dos nativos fallan solo al exigir consola vacía tras superar geometría/generación/readback. Preservar intento en `t12-resumed-attempt-01-failed/`, no sobrescribirlo con un eventual verde.

**Bloqueos y nuevas entregas acotadas:** trazas relacionan 500 con `get_or_create_session:135` y fuentes WOFF2 externas con `ERR_ADDRESS_UNREACHABLE`. `deleg_fbccb7ef` reproduce concurrencia del MISMO ID nuevo en SQLite aislado; solo si hay RED demuestra y repara inserción/cierre de esa función, sin aumentar timeout ni tocar esquema/cálculos. `deleg_c5f5772c` prepara fuentes de prueba idénticas con licencias, desde bytes capturados verificados y helper de rutas solo de fuentes; no filtrar errores ni simular API. Ambos archivos propios disjuntos; sin smoke App/API mientras hay escritores. Revisiones CSS/legado `deleg_61b2746d` pendientes de integrar; T12 no cerrada y T13/T14 sin empezar.

**Revisiones del delta responsive integradas:** especificación y calidad PASS (`deleg_61b2746d`), sin bloqueantes; goldens geométricos/paramétricos intactos, acciones dentro de panel∩controls y texto completo. Subentrega de layout cerrada con gates y tres casos centrales aprobados; no se confunde con el estado global **9/11** del smoke. Sugerencias menores registradas sin ampliar alcance. T12 continúa esperando DB/fuentes y posterior replay estricto.

**DB: RED determinista y fix acotado entregados; central 58 PASS.** La barrera tras SELECT ausente de dos conexiones reales al mismo ID provoca UNIQUE en la fuente anterior, además de dos RED de cierre en error. Solo `get_or_create_session` cambia: conflicto específico `ON CONFLICT(id) DO NOTHING`, fastpath intacto y cierre garantizado. Nuevo módulo con cinco casos; padre quitó un comentario nuevo y volvió a ejecutar combinación final 58 PASS y cero tokens COMMENT. No se generaliza esa reproducción a todos los locks históricos sin replay. Revisión doble DB `deleg_891f3a3e` pendiente; API viva todavía con código anterior. Font fixture continúa independiente, sin App/API; no repetir smoke completo hasta finalizar escritores y reiniciar el servicio propio verificado.

**Integración de fuentes y nuevo gate real:** padre repitió probe real 32/32 y verificó hashes/ambas OFL oficiales; dos líneas aplican helper al legado. Gates estables **704/77 + dominio100 + tsc/lint/PWA + ESLint E2E PASS**. Dos revisores de fuente `deleg_c8d19700` activos. Manifiesto nuevo **457** y config `t12-session-font-final-evidence/` preparados. API propia reiniciada con DB nueva (`proc_6d9f00932e48`); direct/proxy health200, pero lotes concurrentes iniciales volvieron a producir `database is locked` tras varios lotes 200, con timeout del cliente. No hay nuevo resultado 11/11: smoke nuevo todavía no ejecutado. Conservar `parallel-boot-failed-summary.json` y log por handle. `deleg_cdb8d944` diagnostica solamente, con factory real y rutas reales en DBs aisladas; no más fixes por conjetura. T12 sigue abierta, T13/T14 pendientes.

**Revisión de fuentes integrada:** `deleg_c8d19700` entrega dos PASS estáticos, sin cambios requeridos. Confirma aislamiento de hosts/GET, familias/pesos/CORS, licencias, import independiente de cwd y conservación de asserts. No acredita App montada ni resuelve el bloqueo SQLite; se mantienen separados probe 32/32 y smoke montado pendiente. Sugerencias de generalización no amplían la reparación.

**Revisión DB integrada:** `deleg_891f3a3e` entrega dos PASS de especificación/calidad para conflicto específico, cierre, fastpath, delegación y pruebas aisladas. El comentario de los revisores sobre API vieja es histórico al despacho; la API ya se reinició y el probe real posterior falló, de modo que esos PASS no cierran T12. Observabilidad de no-sobreescritura del ganador y rollback son sugerencias no bloqueantes, no motivo de refactor en paralelo al diagnóstico `deleg_cdb8d944`.

**Pausa histórica — 17 de octubre, 19:04 −03:00:** el usuario pidió detenerse y continuar luego. Interrupción del writer de layout2 (`deleg_0b53d55b`) confirmada posteriormente: `interrupted`, 31 llamadas, sin GREEN final. Última salida sobre selector `/RESET SELECCI/` incorrecto frente al nombre real «RESTABLECER SELECCIÓN»; una intención de corregir/repetir no acredita su ejecución. Conservar parciales CSS y legado; snapshot durante interrupción en `data/qa-curve-selection/pause-20261017-190446/` (450 fuentes). Último GREEN central anterior a esos parciales: 704 frontend, 53 API, 11 navegador, compiler/lint/PWA; no certifica layout2. La reanudación explícita posterior del usuario prevalece sobre esta pausa.

Servicios QA propios cerrados al pausar: API y Vite; comprobados libres 8000/5181/5173. El cierre inicial de Vite fue incompleto y se completó con TERM a sus dos PID verificados, luego ausentes. Los identificadores/PID registrados son históricos, no autorización de acciones sobre procesos futuros.

**Responsable:** subagente QA H.

**Archivos propios:** NUEVO `web/e2e/curve-selection.spec.ts`; adaptación del consumidor legado en `web/e2e/project-entry.spec.ts` al callback `CurveAnchor` sin debilitar sus aserciones de geometría/tolerancias; artefactos bajo un directorio de QA aislado e ignorado por Git.

**Objetivo:** demostrar que el puntero, el marcador y el payload coinciden en el visor real.

**Fixture:** geometría sintética con una arista larga y otra curva cercana, cámara conocida y coordenadas de pantalla calculadas explícitamente. Usar las dependencias instaladas y la transformación real del visor; no inferir coordenadas de pantalla a ojo.

**Pasos:** elegir línea; hacer dos clics reales en interiores de la misma arista; comprobar marcadores, texto, payload y secciones. Repetir con zoom y con un candidato vecino; clic fuera de radio; arrastre de cámara sin selección; inversión de extremos; cancelar.

**Aceptación:** no inyectar los anclajes ni los filtros de selección directamente en Zustand para acreditar picking. Si se programa la preparación de mallas/cámara/navegación, declararlo y mantener reales los eventos de puntero que se están certificando. Cuando el cursor está centrado sobre el trazo, el marcador no presenta un salto visible; comprobar un objetivo inicial de error de proyección ≤1 píxel CSS. Fuera del trazo y dentro del radio, es correcto que el punto se ajuste al segmento, no al espacio vacío.

**Dependencias:** T07–T11 terminadas y sin escritores activos. No ejecutar cobertura HTML mientras Vite atiende el smoke, porque puede provocar recargas ajenas al picking.

### T13 — Comprobar bordes y coste de interacción

**Responsable:** subagente QA/geometría I.

**Archivos propios:** nuevas pruebas focalizadas de T02–T05 y un probe aislado; no refactorizar producción sin un fallo observado.

**Objetivo:** comprobar densidades y coordenadas representativas antes de declarar precisión suficiente.

**Casos:** curvas con pocos vértices, muchos vértices, puntos repetidos, escalas grandes, curvas próximas, vista oblicua, cambio de malla, selección cerrada y geometría sin elevación válida.

**Aceptación:** no selección cruzada ni anclas viejas; no incremento no acotado de trabajo por frame. Registrar entorno, tamaño del fixture y medición real; no asignar una cifra de rendimiento inventada ni añadir índices espaciales sin demostrar que hacen falta.

**Dependencias:** T12 y fuentes estables. Los defectos encontrados se convierten en nuevas tareas pequeñas, no en un refactor general de este agente.

### T14 — Revisión independiente, integración y continuidad

**CERRADA — 18 de octubre.** Revisores de especificación y calidad PASS sin bloqueantes; gates del coordinador: frontend 721/79, dominio 100%, tsc/ESLint/build+PWA, Python 2537/12 skip, smoke 11/11 ×2. T13 cerrada con 17 pruebas de bordes y medición de coste, sin defectos. Pendientes no bloqueantes registrados en `docs/HANDOFF.md`. Sin commit/push/despliegue.

**Responsable:** coordinador y dos revisores de solo lectura, en paralelo y con contextos nuevos.

**Objetivo:** cerrar el alcance con evidencia real.

**Revisor de especificación:** continuidad de puntos, mismo tramo en UI/payload, mismo segmento válido, límites de selección, sentido y ausencia de cambios científicos.

**Revisor de calidad:** unidades, transformaciones, precisión, rendimiento, nulabilidad, eventos, cancelación y conservación de cambios locales ajenos.

**Aceptación:** coordinador inspecciona diff y propiedad; repite suites combinadas y build; verifica lectura posterior de las secciones creadas en la sesión QA; conserva scripts/capturas/JSON y hashes en datos ignorados, fuera del scratch efímero; actualiza continuidad solo al ejecutar la implementación. No cerrar con los reportes de los agentes sin comprobarlos.

## 6. Orden y paralelización

| Tanda | Entregas | Regla |
|---|---|---|
| Preparación | T01 | Contrato aprobado antes de consumidores |
| Funciones independientes | T02 + T04 + T05 | Tres agentes, archivos nuevos distintos |
| Recorrido/API | T03; después T11 | La API no cambia si el contrato existente basta |
| Integración continua | T06 | Un solo escritor sobre store/formulario/visor |
| Precisión del visor | T07 → T08 → T09 | Secuenciales: comparten `Mesh3DViewer.tsx` |
| Formulario | T10 | Puede ir junto a T08/T09 tras T06; no comparte sus archivos |
| QA | T12 → T13 | Sin escritores ni generación de cobertura en paralelo |
| Cierre | T14 | Dos revisiones de solo lectura en paralelo; integración central |

No mantener a un mismo agente trabajando indefinidamente sobre un área. Nueva entrega, objetivo y condición de parada para cada fila. Si un agente deriva a explorar/releer, el coordinador da una única corrección concreta; si no avanza, lo detiene y reasigna preservando el trabajo útil.

## 7. Contrato de cada delegación

Cada prompt debe llevar:

1. Raíz absoluta `/home/xod/Documentos/Code/conciliacion-geo-v02` y `workdir` explícito; herramientas de archivos con rutas absolutas para evitar ediciones en `web/` por error.
2. Objetivo de una sola entrega y lista exacta de archivos propios.
3. Contrato de entradas/salidas y las decisiones del apartado 4.
4. Archivos de contexto de solo lectura; prohibición de cambiar otros archivos, dependencias o configuración.
5. Primer test de comportamiento a ejecutar y condición de parada tras GREEN focalizado.
6. Sin comentarios nuevos de código, sin atribuciones IA, sin commit/push y sin tocar `app.py`, `ui/`, Electron o CLI.
7. Informe breve: archivos, RED real, GREEN real, comandos, conteos y pendientes. Un error de montaje no se reporta como reproducción del defecto.
8. No ejecutar suite global, build, navegador o publicar desde la tarea de una función pequeña: esas verificaciones pertenecen al coordinador/QA de su tanda.

## 8. Comandos previstos de verificación

Son instrucciones para la futura implementación, **no comandos ya ejecutados para este plan**. Confirmar primero runtimes y dependencias; usar Node 22 para comparación con la evidencia local. No fijar en el repositorio la ruta temporal del runtime descargado.

### Focalizadas frontend

Desde `web/`, tras crear cada archivo de prueba correspondiente:

- `npm run test -- src/components/sections/__tests__/curveAnchorGeometry.test.ts`
- `npm run test -- src/components/sections/__tests__/curveRange.test.ts`
- `npm run test -- src/components/mesh/__tests__/curvePicking.test.ts`
- `npm run test -- src/components/sections/__tests__/curveSelectionState.test.ts`
- `npm run test -- src/components/sections/__tests__/SectionCurveForm.selection.test.tsx`

Ejecutar las nuevas pruebas también juntas: un GREEN aislado no certifica la integración.

### Gates integrados frontend

Desde `web/`:

- `UV_NO_SYNC=1 npm run test:coverage`
- `npx tsc -b --force`
- `npm run lint`
- `npm run build`
- `npx playwright test e2e/curve-selection.spec.ts --workers=1`

La cobertura obligatoria al 100% corresponde al dominio existente `ProfileView/domain`; no afirmar cobertura del 100% de toda la web. Registrar los conteos reales nuevos, no fijar como meta los 585 históricos del bloque anterior.

### API/core

Desde la raíz, con Python/dependencias comprobados y `CONCILIACION_DATA_DIR` definido a un directorio nuevo de QA antes de importar la app:

- `env -u PYTHONPATH -u PYTHONHOME .venv/bin/python -m pytest tests/api/test_curve_selection.py -v --tb=short`
- `env -u PYTHONPATH -u PYTHONHOME .venv/bin/python -m pytest tests/ -q --tb=short --ignore=tests/test_openblast.py --skip-electron --benchmark-skip-slow`

Repetir el pipeline sintético como regresión del comportamiento compartido. Inspeccionar sus rutas de salida; si conserva `/tmp` literales, redirigir únicamente esas constantes a un scratch nuevo mediante el arnés ya documentado, sin alterar el script de producción.

## 9. Criterios de aceptación finales

- Dos clics interiores en una misma arista producen dos puntos válidos y un tramo generable.
- Coordenada seleccionada, marcador, resumen y extremos del payload representan el mismo lugar.
- El recorrido conserva los vértices/esquinas interiores y nunca se extiende a los vértices exteriores por redondeo.
- El sentido inicio→final es explícito; no se invierte por ordenar índices ni se sustituye por una recta.
- Con curva activa, otro ramal no consume la selección. Un clic fuera de radio no modifica nada.
- La captura se mantiene consistente al variar zoom/DPR y no acepta puntos detrás de cámara o geometría inválida.
- La cámara puede orbitar/arrastrarse sin fijar extremos accidentalmente.
- Cambiar de diseño/curvas cancela anclas que ya no corresponden a la geometría.
- Vista previa y resaltado permiten anticipar qué tramo se generará; los dos extremos son distinguibles sin depender solo del color.
- El payload sigue siendo compatible con `/sections/curve`, con puntos XY finitos y los parámetros de spacing/longitudes/sector originales.
- Pruebas focalizadas, integradas, typecheck, lint, build y smoke real aprobados; informes con límites explícitos y sin resultados simulados.
- No hay cambios ajenos ni commit/push/despliegue no autorizado.

## 10. Riesgos y decisiones que no deben ocultarse

### Curvas cerradas

Dos puntos de una curva cerrada pueden definir dos arcos. La primera versión mantendrá la semántica de recorrido directo existente, **pero mostrará el tramo antes de generar**. No introducir una regla automática de «camino más corto». Si la necesidad real exige el otro arco, abrir una tarea adicional para un selector explícito de recorrido/sentido; no mezclarlo con la corrección básica.

### Superposición y oclusión

No basta con reducir el umbral: una línea vecina puede aparecer antes en la lista de intersecciones. La prioridad de curva activa y el momento de consumir el evento son requisitos del arreglo. La visibilidad/oclusión debe comprobarse en vista oblicua; no afirmar solución completa solo con una vista en planta.

### Precisión y densidad

`e.point` ya contiene una posición continua, pero el ancla debe reconstruirse sobre las coordenadas originales para no degradar precisión. No cambiar resolución/decimación global ni remuestrear toda la superficie para ocultar el bug de índices.

### Radio de selección

8 píxeles CSS es una propuesta inicial de interfaz. Ajustarla exige evidencia del smoke y, preferentemente, revisión del usuario con su diseño; no equivale a una tolerancia en metros. Un radio mayor no debe permitir seleccionar otra línea cuando una curva ya está activa.

### Posibles ampliaciones, fuera de esta primera mejora

- Selección libre sobre la superficie sólida del diseño.
- Nueva vista en planta dedicada, si los controles actuales no bastan para revisar casos oblicuos.
- Edición numérica avanzada/arrastre de extremos y elección explícita del arco alternativo de curvas cerradas.
- Rediseño del generador, intervalos de perfiles o criterios geotécnicos.

## Estado de este documento

Durante la planificación solo se creó este documento, basándose en lectura del código y un probe real de Three.js. Posteriormente se completaron T01–T11 con autorización del usuario. La reanudación del 17 de octubre a las 08:18 −03:00 permitió preservar, reparar y verificar el T10a interrumpido; la pausa de las 05:47 es histórica. T12a está delegada; T12b/c–T14 siguen pendientes, con ejecución secuencial autorizada y sin commit/push/despliegue. La validación con el archivo concreto del usuario sigue siendo necesaria para confirmar que esta causa explica todos sus casos y para ajustar la experiencia de selección.

### Inicio posterior autorizado — T01 únicamente

El usuario pidió comenzar T01. El coordinador fijó el contrato estructural y sus reglas anteriores; se delegó exclusivamente la creación de `curveSelectionTypes.ts` y su prueba contractual. El subagente reportó RED de compilación con TS2307 al crear primero la prueba e importar el módulo todavía ausente; después creó el contrato. El coordinador comprobó personalmente `tsc -b --force`, las 4 pruebas nuevas y la suite completa: **589/589 en 67 archivos**, cobertura obligatoria 100%, ESLint sin advertencias y build con PWA aprobados. Se corrigió una advertencia de lint usando un alias de tipo en vez de una variable utilizada solo como tipo. Dos revisiones independientes: PASS, sin bloqueantes.

**Estado: T01 terminado y verificado.** No se comenzó T02 ni se modificaron visor, formulario, store, API o core. Los 32 archivos fuente/pruebas del manifiesto previo conservan sus hashes. Las limitaciones runtime de los tipos están explícitas en §4.1; no se certifica todavía una mejora visible de la selección. Sin commit ni push.

### Continuación autorizada — T02 únicamente

Se divide en dos entregas sobre los mismos dos archivos nuevos, con escritores serializados:

- **T02a:** `createCurveAnchor(input: CurveAnchorInput): CurveAnchor | null`, con entrada readonly `context`, `curveId`, `points: readonly MiningPoint3D[]`, `segmentIndex` y `t`. Interpola XYZ original y acumula distancia XY, sin redondeo. Se rechaza el segmento solicitado si su longitud XY es cero, incluso cuando `t=1`; solo se normaliza al segmento siguiente inmediato si este es válido. Si el siguiente es degenerado, se conserva el segmento válido actual con `t=1`.
- **T02b:** `projectCurveAnchor(input: CurveAnchorProjectionInput): CurveAnchor | null`, con los mismos campos salvo `position: MiningPoint3D` en lugar de `t`. Proyección euclídea **3D** sobre el segmento original indicado, fracción limitada a `[0,1]` y reconstrucción mediante T02a. No se ajustan índices inválidos, no se deduplican puntos ni se interpretan identificadores. Se conserva la elevación original de cada punto, que puede variar. Los resultados no finitos se rechazan antes de limitar la fracción; no hay umbral geométrico arbitrario. La aceptación por distancia de pantalla pertenece a T04, no a esta función pura.

La primera entrega T02a pasó sus pruebas, pero solo reportó un fallo de importación y tenía dos errores en extremos adyacentes a segmentos degenerados. Se retiró esa implementación, se dejó un stub y el coordinador observó personalmente el RED de comportamiento (`expected null not to be null` en la selección 20/80). Un nuevo agente reimplementó el contrato y añadió las dos regresiones: **9/9 de geometría y 13/13 junto a T01**, comprobadas por el coordinador. T02b añadió proyección 3D y reportó RED de aserción con un stub antes del GREEN; cubre extremos, coordenadas grandes, no finitos, índices, entradas congeladas y desbordamiento.

**Estado: T02 terminada y verificada.** El coordinador ejecutó **20/20 pruebas focalizadas** (16 de geometría + 4 de T01), la suite completa **605/605 en 68 archivos**, cobertura obligatoria del dominio de perfiles **100%**, `tsc -b --force`, ESLint completo y build con PWA, todos aprobados con Node 22.23.3. Tres avisos JSDOM de navegación no implementada, sin fallos. Dos revisiones independientes: **PASS**, sin bloqueantes. Los **434 archivos fuente/pruebas preexistentes** conservan sus hashes. La cobertura obligatoria no incluye el helper nuevo; no se afirma cobertura del 100% para este.

Límites conservados: operaciones extremas que desbordan y segmentos de longitud XY nula retornan `null`; el cálculo recorre la curva sin caché. No se implementó elegibilidad en píxeles ni se conectaron consumidores. Sin cambios en visor, formulario, store, API o core; backend, pipeline y navegador no se repitieron para esta entrega pura. Sin commit ni push. **No se inició T03.**

### Continuación autorizada — T03 a T14, en orden

El usuario pidió continuar con las demás tareas en orden. Se ejecutarán T03 → T04 → T05 → T06 → T07 → T08 → T09 → T10 → T11 → T12 → T13 → T14, sin nueva autorización entre entregas. Se mantienen los límites de alcance, preservación de cambios anteriores y prohibición de commit, push y despliegue. La preparación de contexto de solo lectura puede hacerse en paralelo; la implementación de las entregas es secuencial.

**T03 cerrada:** `buildCurveRange(input: CurveRangeInput): readonly MiningPoint3D[] | null`, con entrada readonly `context`, `curveId`, `points`, `start` y `end`. Identidades comparadas por valor; anclas recalculadas con T02 y verificadas contra la geometría actual. Resultado XYZ con extremos interpolados, vértices interiores y sentido elegido, sin duplicados consecutivos ni arco alternativo automático. Se corrigieron mediante regresiones la ausencia de readonly en cuatro campos y la validación errónea de longitud sobre la curva completa en vez del tramo recortado. Coordinador: **32/32 pruebas combinadas T01–T03**, `tsc -b --force` y ESLint dirigido aprobados. Revisión independiente: PASS, con repetición propia de 12/12 de T03, compilador y lint. Sin consumidores integrados. Los 436 archivos fuente/pruebas preexistentes conservan sus hashes.

**T04 cerrada:** `pickCurveCandidate(input: CurvePickingInput): CurveAnchor | null`. Recibe candidatos `{anchor, visible}`, contexto actual, curva activa o null, cámara Three.js con matrices vigentes, centro XYZ minero, viewport y puntero locales en píxeles CSS y radio opcional (8 px CSS por defecto). Proyecta con la transformación real del visor, filtra contexto/curva/visibilidad/recorte de cámara antes de elegir y desempata de forma estable por distancia, profundidad e identidad. No utiliza DPR ni modifica cámara/estado; la oclusión física y el radio mundial de búsqueda serán responsabilidad del adaptador T07. Coordinador: **44/44 pruebas combinadas**, compilador y lint aprobados; revisión independiente PASS. Sin edición del visor.

**T05 cerrada:** estado readonly con `context`, `curveId`, `start`, `end` y `rejection`; `createCurveSelectionState` y `reduceCurveSelection`. Primer clic elige solo curva; segundo fija inicio; tercero fija final en estación distinta de la misma curva, incluso en el mismo segmento. Otro clic después de dos extremos reinicia el inicio incluso sobre un extremo existente. Otra curva se rechaza sin alterar extremos. Cambiar contexto por valor cancela selección; un contexto igual, incluido null→null, preserva referencia y motivo de rechazo. Cancelar o generar limpia selección conservando contexto. Se corrigieron esos dos casos y el contrato readonly de las acciones con regresiones de comportamiento/compilador. Coordinador: **59/59 combinadas**, suite completa **644/644 en 71 archivos**, cobertura obligatoria de perfiles **100%**, compilador, ESLint completo y build con PWA aprobados. Revisión inicial y revisión del delta: PASS; el coordinador reprodujo y corrigió los bordes omitidos por la primera revisión. Aún sin integración en Zustand.

**T06a cerrada:** adaptador compartido de instantáneas e identidad local definido en T06. Coordinador: **67/67 pruebas combinadas**, compilador y lint aprobados; revisión independiente PASS. La cache depende de datos inmutables de React Query; no detecta mutación en sitio ni afirma una revisión del backend.

**T06 cerrada:** callback, store, formulario y marcadores consumen `CurveAnchor`; `curveSelection` es la fuente única de estado. Readiness y payload comparten el recorte T03, exclusivamente XY al generar. Se corrigió el éxito tardío: solo limpia si contexto, curva y referencias de extremos siguen siendo los enviados; un rechazo de metadatos no impide limpiar la selección original. Dos regresiones reales prueban no-ops de Zustand sin cambiar raíz ni notificar suscriptores. Se eliminaron únicamente los tres comentarios nuevos no permitidos. Coordinador: **663/663 en 74 archivos**, cobertura obligatoria de perfiles **100%**, `tsc -b --force`, lint completo y build con PWA aprobados. Dos revisiones iniciales y revisión del delta: PASS tras corregir el hallazgo asíncrono. Solo cambiaron los tres archivos fuente previstos de la línea base; LeftSidebar, tolerancias, API/core y cambios ajenos se conservaron. Clics reales aún pendientes.

**T07a cerrada:** tras el primer GREEN de 85/85 y una revisión inicial PASS, el coordinador reprodujo errores de oclusión oblicua/ortográfica y desbordamiento del umbral. Se añadieron cuatro regresiones y se corrigió el rayo con `setFromCamera`, la comparación a distancia real del objetivo, el recorte de cámara en profundidad de vista y la finitud del resultado. Se ignoran materiales ocultos. Coordinador: **89/89 combinadas**, compilador aprobado y **3/3 probes independientes** ejecutando el helper de producción; revisión del delta PASS. Script y JSON preservados en `data/qa-curve-selection/occlusion-probe.mjs` y `occlusion_verification.json`, evidencia sintética de helper, no de navegador. Soporte de oclusión acotado a mallas/materiales opacos simples actuales, sin prometer alpha-texturas o multi-material universal.

**T07 cerrada:** `createCurveSceneClickHandler` está conectado a las líneas etiquetadas con su ID; usa todas las intersecciones, clientX/clientY menos el rectángulo real del canvas y dos referencias acotadas a mallas opacas. Solo consume un candidato válido sin arrastre. `useFrame` sustituye el umbral fijo por actualización escalar según cámara/proyección/altura CSS; aceptación final de T04. Coordinador: **677/677 en 75 archivos**, cobertura obligatoria de perfiles **100%**, compilador, lint completo y build con PWA aprobados; **3/3 probes** conservados. Revisión del wiring PASS. Eliminados los comentarios nuevos no permitidos, sin cambios de comportamiento. Log y hashes de 444 archivos de código preservados en `data/qa-curve-selection/t07-frontend-gates.log` y `t07-source-manifest.json`. No se presenta el test del adaptador de evento como prueba de puntero real.

**T08 cerrada:** preview comparte `resolveCurveSceneCandidate`, no despacha selección confirmada, usa un buffer fijo y deduplicación por evento nativo. Tras un GREEN inicial de 681, el coordinador detectó que faltaba invalidar cambios de proyección sin movimiento. Una regresión ortográfica zoom=2 falló realmente; `hasCurvePreviewViewChanged` ahora compara también una matriz copiada al snapshot preasignado. La limpieza por frame no asigna memoria ni recorre geometría. Coordinador final: **682/682 en 75 archivos**, cobertura obligatoria de perfiles **100%**, compilador, lint y build aprobados; revisión del delta PASS. Log final en `data/qa-curve-selection/t08-final-frontend-gates.log`. El Fiber instalado limpia hover antes del movimiento; los datos de salida solo limpian. QA de pantalla sigue pendiente.

**T09 cerrada:** `buildCurveSelectionVisuals` convierte el mismo recorrido T03 en posiciones locales de render; el visor dibuja el tramo exacto y extremos etiquetados, sin modificar picking/preview. Tras 689 y dos revisiones iniciales PASS, el coordinador reprodujo y delegó la reparación del inicio parcial de otra curva con geometría idéntica: guard explícito `anchor.curveId`, regresión real y **8/8** del helper. También se corrigieron los spans inline con `inline-block`; coordinador Chrome con JSX extraído y CSS real del build: **−18/+18 px**, sin mover anclas. La observación CSS previa de 0/0 px no fue una aserción RED: el coordinador la etiquetó como diagnóstico y fijó el probe para exigir siempre el resultado correcto. Estado final: **690/690 en 76 archivos**, cobertura obligatoria de perfiles **100%**, compilador, lint, build y revisión del delta PASS. Logs, probe y JSON bajo `data/qa-curve-selection/`, manifiesto `t09-source-manifest.json` con **446 archivos**. Línea base de 436: solo las tres migraciones autorizadas; sin cambios científicos. CSS aislado no certifica picking real.

**T10 reanudada, por entregas cortas:** T10a1 cerrada: consultas de botón ambiguas precisadas sin modificar aserciones (comparación exacta), slot de longitud y tipo DOM de summary corregidos. T10a2 comprobada: **17/17 focalizadas**, subagente compilador/lint aprobados. Dos RED reales corrigieron el resumen de un ancla ajena con igual geometría y Escape robando foco sin curva activa; se reutiliza T02 con memoización y se preservan contexto, campos y generación pendiente al cancelar selección. Casos adicionales de reset, cero/ausencia y edición pasan como cobertura, no como RED inventado. T10b delegada: borradores numéricos sin convertir vacío/no finito en cero, preservando los límites UI existentes (separación 1–100 m, longitudes 1–1000 m), parámetros y cálculos; cero XY/estación sigue válido. Se comprobará además que una discrepancia del contexto global no deje habilitada la generación mientras se ocultan resúmenes. Línea base de traducciones en `$TMPDIR/t10-locales-before.json`: preservadas todas las claves anteriores salvo tres pasos de ayuda, 14 claves nuevas coincidentes ES/EN antes de T10b. Todavía sin suite global ni cierre de T10. T11–T14 pendientes, autorizadas secuencialmente.

**T10 cerrada:** RED reales de discrepancia de contexto y campos vacíos/inválidos; borradores string sin fallback/clamp/snap, parse finito y límites UI existentes, mismo guard en botón/handler. Payload XY original, sector literal y longitudes asimétricas preservados; la validación no anuncia que puede generarse con parámetros inválidos. Focalizadas **23/23**; coordinador global **704/704 en 77 archivos**, dominio obligatorio **100%**, TypeScript/lint/build y dos revisiones independientes aprobados. Log `data/qa-curve-selection/t10-frontend-gates.log`; hashes de **447 archivos** en `t10-source-manifest.json`. Comparación exacta preserva las aserciones originales; delta T09 limitado a formulario, consultas de botón de su test y dos locales, más el nuevo test de feedback. Quince claves nuevas ES/EN coincidentes; solo tres pasos de ayuda previos modificados. La persistencia visual del éxito de una petición anterior se registra como sugerencia no bloqueante, sin cambiar el guard de selección. QA de Canvas/picking sigue pendiente.

**T11 cerrada:** seis regresiones de API existente: extremos interiores, esquina real, sentido inverso, tramo corto, longitudes asimétricas y aislamiento de sesión. Archivo nuevo `tests/api/test_curve_selection.py`; fixture raíz `api_test_client`, datos aislados y GET posterior a POST. GREEN inicial legítimo, sin cambios ni RED fabricado en producción. Tras retirar comentarios nuevos y repetir sobre el archivo final, coordinador: **53 passed / 1 warning** al combinar settings/cutter, log `data/qa-curve-selection/t11-final-api-gates.log`; dos revisiones PASS. Aviso Starlette/httpx, sin instalar dependencias. Manifiesto de **448 archivos** `t11-source-manifest.json`, fuentes T10 intactas. API/core/configuración/frontend no se modificaron.

**T12 por entregas cortas:** T12a delegada: único flujo mínimo de tres clics reales en una arista, inspección de geometría renderizada/posición de pantalla ≤1 px CSS, resumen y payload originales; generación y lectura posterior de API reales. Rutas de mallas interceptadas con fixture sintético explícito para controlar una arista larga y su vecina; IDs/navegación/cámara se preparan programáticamente, nunca las anclas confirmadas. Esta prueba no certifica carga/extracción de STL del usuario. T12b posterior ampliará zoom, vecina/radio, arrastre, inversión, cancelación y DPR; T12c migrará el callback del spec legado manteniendo sus aserciones. Servidores propios y salud directa/proxy comprobados, datos QA aislados; después de la interrupción del proveedor se revalidó su estado a las 12:03 −03:00. Sin escritores de aplicación, cobertura ni builds durante QA. Evidencia en `data/qa-curve-selection/t12-evidence/`; snapshot original del E2E legado preservado.

**T12a verificada centralmente, revisión pendiente:** `sh data/qa-curve-selection/t12-evidence/run-t12a.sh` produjo **1 passed** en navegador instalado y contexto aislado, repetido por el coordinador. Tres clics nativos, anclas interiores distintas del mismo segmento, posiciones a tres decimales y geometrías reales de inicio/fin/rango contrastadas. Error máximo **0,391383528 px CSS**, rango con dos extremos interpolados; POST XY idéntico a las anclas sin Z ni redondeo. GET adicional del coordinador coincide exactamente con la respuesta POST completa: **6 secciones** dentro del tramo. Se inspeccionaron capturas previas/posteriores, con etiquetas separadas y seis líneas. Texto XY parcialmente truncado en panel estrecho, valor crudo preservado en tooltip; no se altera medición/payload. Fixture de mallas mockeado y preparación programática declarados; API de secciones real. Baseline de spec/JSON/capturas en `t12a-baseline/`, manifiesto `t12a-source-manifest.json` de **450 archivos** y fuentes de producción sin cambios. Revisión de evidencia de solo lectura en curso; T12b/c aún pendientes.

**T12a cerrada tras revisión PASS; T12b1 delegada:** dos casos adicionales de eventos nativos para hover/vecina/radio/arrastre y Reset/Escape. Se reforzarán también los checks de consola, método GET del fixture, visibilidad del rango, nombre accesible de Generar e igualdad GET/POST, sin cambiar producción. T12b2 posterior comprobará zoom/DPR e inversión. Precaución para inversión: el generador inicia siempre a media separación desde el extremo elegido; si la longitud no es múltiplo del spacing, invertir el recorrido no conserva exactamente la misma grilla de orígenes en orden contrario. Se verificó con el tramo real de T12a (60,203123698 m): ambas grillas son interiores pero distintas. Mantener el comportamiento existente; no modificar el motor para satisfacer una expectativa incorrecta de QA.

**T12b1 verificada: 3/3 PASS de navegador**, repetidas por el coordinador, sin cambiar producción. Hover de un punto se mueve por la arista sin confirmar (error máximo 0,000029401 px CSS); prioridad de A ante B a 3,333870 px, fuera de radio y arrastre sin alterar selección. Control positivo de cámara y Reset/Escape con conservación de contexto/borrador/foco, sin POST en esos dos casos nuevos. A fortalecida con método GET explícito del fixture, nombre accesible, rango visible/rol, igualdad GET/POST y aserciones de consola vacía.

**Pendientes T12 independientes, delegados en paralelo:** B2 posee únicamente `curve-selection.spec.ts` y su carpeta QA: añade zoom nativo e inversión, ejecuta todos los casos con DPR 1/2 y evidencia separada por proyecto. C posee únicamente `project-entry.spec.ts` y su carpeta QA: migra callback con contexto actual y constructor T02, conserva elevación original en aserción de anclas y exige payload de tres puntos XY sin Z. Se preservan todas las aserciones originales de tolerancias, geometría, tamaños y no-scroll; no es prueba de picking, sino contrato del formulario. Configs/resultados/browser contexts separados; ninguna edición de aplicación, build ni cobertura durante estas dos verificaciones. Si aparece un defecto de aplicación, ambos workers reportan y el coordinador asignará su reparación solo tras detener los escritores/QA afectados.

**Resultado central inicial T12b2/c:** matriz nativa **8/8 PASS en 58,4 s**; legado inicialmente **1/3 PASS en 6,8 s**, con `expectNoScroll` fallando por 35 px vacío y 75 px con selección a **1280×720**. Corrección de evidencia: la atribución inicial de 35 px a 1366×768 era incorrecta; los probes registran 0 px vacío en ese tamaño. Se preservan ambos RED reales y todas las aserciones; el fixture de resultados necesitó `[]` en lugar de `{}` para montar Canvas, corrección de setup distinta del fallo de presentación.

**Reparación acotada T12-layout (`deleg_e839f9a9`):** un único escritor sobre `globals.css` y presentación/ARIA del formulario, sin cambios de dominio ni de tests. Hipótesis a medir: espacio fijo de navegación, espaciado vertical y ajuste de botones. No ocultar campos, feedback ni acciones, ni falsear el overflow; reutilizar patrones compactos accesibles. Esperar a fuentes estables antes de repetir matriz nativa/globales.

**Higiene pendiente de evidencia B2:** la separación efectiva B→línea A es 10,180886 px tras zoom. El reporte llamado `abCenterGapPx` compara B-centro con A-20 %, no con A-centro, y produce 347,106547 px; corregir objetivo y añadir coherencia con la medición centrada de settle. También comprobar B explícitamente dentro del Canvas antes del clic negativo. No alterar producción ni las expectativas de media separación del motor. T12 permanece abierta; T13 mantiene su dependencia de T12 y T14 conserva sus gates y dos revisiones.

**Layout entregado y replay central C: 3/3 PASS (8,3 s)**. Solo cambió CSS; hashes de Formulario/LeftSidebar y restantes fuentes T11 intactos. Compactación existente extendida a 720 px, sin cambios de handlers, valores ni tests. Ya se ejecutan completas las aserciones de payload/tolerancias antes bloqueadas. Captura seleccionada a 720 px inspeccionada, acciones y navegación visibles. Los dos JSON de probes del worker son baseline anterior, no métricas finales; el resultado posterior está acreditado por el runner E2E. Compiler/lint y 23 focalizadas del worker quedan pendientes de repetición central.

**Dos entregas acotadas activas (`deleg_c492638b`):** corregir únicamente metrología B2 con RED/assert de coherencia y replay 8 nativos; investigar sin escritura de backend el lock SQLite observado en log real (`get_or_create_session:135`). Cualquier repro usa otra DB nueva, nunca la QA viva. No clasificar el 500 como preexistente solo porque el rerun pasó. Preparación de cobertura T13 exclusivamente de lectura en `deleg_7f69e587`; ejecución y rendimiento siguen pendientes hasta cerrar T12.

**Verificación central posterior, autorizada y ejecutada:** frontend **704/704 en 77 archivos**, dominio obligatorio 100%, compiler/lint/PWA PASS; API combinada **53 PASS**, una deprecación. Logs `t12-integrated-frontend-gates.log` y `t12-integrated-api-gates.log`. Navegador combinado sobre fuentes estables **11/11 PASS** (4 DPR1 + 4 DPR2 + 3 legado), cero reintentos/skip/flaky, reporte y resumen en `t12-final-evidence/`. Manifiesto de 450 fuentes sin cambios entre gates y navegador. Dos GET adicionales del coordinador igualan exactamente las seis `sections` del POST de cada sesión; la comparación correcta excluye el wrapper y las columnas diagnósticas agregadas por QA. Primeros intentos adicionales con representaciones incorrectas fallaron, sin defecto de aplicación ni reparación de producción.

**Métrica corregida acreditada:** distancia centro-centro 10,180886 px CSS, coherente con settle; precondiciones B en pantalla/Canvas/profundidad positiva, error de marcador zoom 0,044647306 px en DPR 1/2. No se modificaron expectativas del motor. El lock SQLite histórico conserva causa concreta sin identificar; ningún cambio de DB y ningún 500 en la corrida central posterior. API QA reiniciada por el coordinador con datos nuevos tras terminar el proceso anterior.

**Revisiones T12 activas (`deleg_04e3d7a8`):** especificación + calidad, solo lectura. Se pide contraejemplo del tramo ya listo justo por encima del breakpoint 720, no solo el formulario vacío o el tramo listo a 720 que acredita el legado. T12 no se cierra hasta resolverlas; T13/T14 permanecen pendientes, con solo preparación de lectura previa para T13.

**Revisión recibida: BLOCK de presentación, selección/payload/calidad PASS.** Probe READY confirma 74 px de overflow a 721, 27 px a 768 y 19 px a 640; el 11/11 anterior no cubría esas combinaciones. El lookup de Reset del probe era incorrecto (caja null) y su visibilidad de Generar solo comparaba el viewport, no el contenedor: conservar los hechos de overflow sin atribuir recorte específico no medido.

**Reparación T12-layout2 (`deleg_0b53d55b`):** únicamente CSS + regresión en el legado. Añadir antes del payload un loop READY 640/719/720/721/768/769/800/801/850/851/900/1000 y bounds de ambas acciones dentro del contenedor; restaurar 720 antes de los valores originales. RED real primero, después ajuste responsive medido, sin física ni cambios semánticos. Investigar márgenes start/end de Tailwind 4 y saltos de reserva de navegación, no trasladar la discontinuidad al siguiente píxel. Repetir gates y smoke tras entrega estable. Preparación del contrato del probe T13 en solo lectura (`deleg_8a6d2811`), sin iniciar esa implementación.

**Preparación técnica T13 recibida y contrastada, no ejecución:** el probe podrá importar el resolver real `resolveCurveSceneCandidate` por ESM de Vite sin montar App ni tocar API y medir broadphase/resolver por separado. Correcciones al resumen del preparador tras leer tipos: `ContourLine.segments` es `number[][][]` (polilínea/punto/coordenada), y `CurveScenePointerEvent` exige `delta` y `stopPropagation`, no son opcionales. `CurveScenePickingInput` requiere snapshot, selectedCurveId, camera, center, viewport, pointer, intersections y occluders; radio opcional. Identidad estable dentro de cada dataset, identidad nueva al cambiar los datos/densidad. Medidas aisladas no acreditan FPS ni la actividad de frame de la App montada. Cualquier complejidad O(N) observada en fuente es riesgo estático hasta medirla, no un defecto de rendimiento demostrado. La dependencia T12 sigue vigente.

**Preparación de QA comprobada, no prueba de aplicación:** Playwright no tiene su Chromium descargado, pero `/usr/bin/google-chrome-stable` lanzó un navegador headless aislado **155.0.8059.79**, con WebGL2 disponible. Usar ese ejecutable mediante configuración aislada de QA, sin perfiles personales. Python del proyecto: 3.11.15; `rtree` no está instalado ni declarado en los manifiestos actuales. No se instalaron paquetes; confirmar si lo requiere alguna prueba API/pipeline antes de intervenir. El Playwright estándar reutiliza puertos 8000/5173: QA deberá comprobar propietarios y usar puertos/datos aislados, sin apropiarse de servidores previos.

**Corrección del reconocimiento QA:** no hay desajuste `crests/toes` frente a `lines`: el coordinador trazó `api/routers/meshes.py:1234–1271`, donde `_get_breaklines_cached` convierte el resultado de core a `ContourData` con `lines` antes de responder. No modificar API/hooks por aquella inferencia del reconocimiento. El spec existente `project-entry.spec.ts:93–98` sí invoca la firma antigua de `mapClickHandler`; deberá migrarse en T12 manteniendo esa prueba como contrato de formulario, no como evidencia de picking. La prueba nueva usará clics reales. `_roots` y `getRootState` están exportados por el Fiber instalado, pero la forma exacta del store/cámara debe verificarse en el navegador antes de usarla; no asumir que `_roots.get(canvas)` ya sea directamente un RootState. El navegador ya existe: no instalarlo ni reutilizar 5173 por seguir una receta histórica.
