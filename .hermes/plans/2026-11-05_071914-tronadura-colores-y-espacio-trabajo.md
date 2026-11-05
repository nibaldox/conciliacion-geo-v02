# Tronadura: colores fiables y espacio de trabajo — Implementation Plan

> **For Hermes:** Implementar tarea por tarea con subagentes nativos, siguiendo delegated-codebase-orchestration y test-driven-development. El coordinador escribe contratos, revisa e integra; no escribe código de producto ni pruebas. La ejecución ya fue solicitada: revisar este plan y comenzar sin pedir otra autorización. No commit, push ni despliegue.

**Goal:** Que los colores elegidos se vean realmente en collares y trayectorias, y que Tronadura ofrezca un único espacio de exploración con controles accesibles, leyenda visible y configuración que sobreviva a la navegación.

**Architecture:** Reutilizar Mesh3DViewer y BlastHolesLayer; no construir otro motor 3D. Separar Datos, Explorar, Análisis y Simulación, con un solo canvas activo y un store de presentación contextualizado por sesión, superficies y revisión de pozos. Los colores y filtros visuales no alteran cálculos, cumplimiento ni parámetros físicos.

**Tech Stack:** React 19, TypeScript, Zustand, TanStack Query, React Three Fiber/three 0.184, Tailwind, Vitest y Playwright existentes; FastAPI/Pydantic únicamente para una revisión aditiva del conjunto de pozos. Sin dependencias nuevas.

---

## 1. Base y restricciones

- Rama: `codex/continuidad-tronadura-20261104`, HEAD `3b0d897`. Hay cambios anteriores SIN commit en 20 archivos; preservarlos. Leer `docs/HANDOFF.md` y `AGENTS.md` antes de escribir.
- El usuario ya pidió este plan y su ejecución por subagentes. No autoriza commits, push, cambios de datos reales ni confirmaciones de CRS/datum en su nombre.
- `app.py`, `ui/`, Electron, CLI y fórmulas de `core/` fuera de alcance. No cambiar importación/fechas de la entrega anterior salvo regresión demostrada causada por este trabajo.
- Español/inglés en locales, identificadores en inglés, sin comentarios nuevos de código, estilos con tokens existentes.
- Node 22.23.0; Python `.venv/bin/python` 3.14.6. Backend bajo MemoryMax=6G y MemorySwapMax=0 para gates completos; no repetir el OOM de 3G.
- Servicios existentes: Vite 5173 y API 8000, con datos en `data/qa-tronadura-20261105/runtime`. Verificar propiedad/estado antes de actuar; no reiniciarlos mientras un escritor o QA depende del proceso.
- Hay una sesión real cargada con 11.184 pozos. Para pruebas de aceptación usar una COPIA SQLite consistente en una carpeta QA nueva y un navegador aislado. Nunca reprocesar ni alterar su sesión. La copia no confirma CRS, unidades ni convención física.
- No usar porcentajes de prueba ni estados verdes de importación como evidencia de que el render funciona.

## 2. Hallazgos de partida verificados

1. `BlastHolesLayer.tsx:245` usa vertexColors en el material de las esferas sin atributo color en SphereGeometry. Repro WebGL: instancias rojo/verde producen negro; con vertexColors desactivado conservan rojo/verde. El coordinador repitió la sonda de `cache/scratch/colorprobe/probe.cjs`. Falta la regresión que monte la capa de producto real.
2. `Mesh3DViewer.tsx:1021` colorea trayectorias únicamente con categorías; con variables quedan grises.
3. `blastHoleColors.ts:238` fija PF a 0..200. En la sesión actual, 6.613/11.184 valores de pf_g_per_ton_inf superan 200 (59,13%). No cambiar datos ni umbrales científicos: hacer el rango visual explícito.
4. `BlastHoles3DViewer.tsx` ofrece otro visor con dureza fija; la sesión actual no tiene dureza. `BlastCorrelation.tsx:191-251` mezcla importador, tabla de 96 secciones, gráficos, visor y simulación.
5. Filtros, colores, visibilidad y confirmación espacial viven en useState local; se pierden al desmontar. `useBlastHoles3D.ts` envía corredor fijo10, pero el filtro usa distancias ya calculadas: NO declarar una divergencia sin comprobar el consumidor.

## 3. Contratos congelados antes de paralelizar

### 3.1 Render

- La capa acepta los colores calculados por row_id. Collares y trayectorias deben representar la misma variable/categoría cuando se selecciona destino `both`.
- Destino de color: `both | collars | trajectories`, predeterminado `both` en la nueva UI. Sin mapping válido se conserva el fallback visual explícito, nunca un valor numérico inventado.
- La selección se representa con halo/contorno separado; no sustituye el color del dato. Conservar picking por row_id, agrupación espacial y recursos instanciados.

### 3.2 Escala y procedencia del color

- Ampliar mapBlastHoleColors con `rangeMode?: 'legacy' | 'data' | 'manual'`, `rangeMin?: number`, `rangeMax?: number`. Default del helper `legacy` para consumidores existentes; la nueva UI usa `data` (rango global completo observado).
- `data`: dominio numérico del conjunto fuente completo, no solo el subconjunto visible. `manual`: límites finitos y min<max; la UI no aplica una configuración inválida. Contar valores por debajo/encima del rango y sin dato. Una escala constante tiene un color central y leyenda de valor único.
- Las categorías usan el dominio fuente completo para que filtrar no reasigne colores. No prometer 73 colores perceptualmente distinguibles; permitir búsqueda/resaltado de categoría y avisar repetición cuando proceda.
- Mantener `powderFactor` como alias compatible del resolver existente (preferencia inf), pero la leyenda debe identificar su fuente real. Añadir opción `powderFactorGeometry` que usa exclusivamente pf_g_per_ton. Etiquetas distinguen PF de influencia y geométrico; misma unidad g/t no significa misma fórmula. No fallback silencioso entre ellos en la nueva selección explícita.
- La leyenda derivada puede añadir campos opcionales `sourceKey`, `unit`, `belowCount`, `aboveCount`, `missingCount`, `observedMin`, `observedMax`, sin romper las formas existentes.

### 3.3 Identidad y estado compartido

- API3D añade `data_revision: string | null = None` a BlastHoles3DResponse. La revisión identifica los registros persistidos fuente y no cambia al seleccionar una sección, corredor, filtro o paleta. Debe cambiar si cambian los registros aun con igual conteo e IDs. Hash determinista del JSON de blast_holes, no de updated_at global ni del resultado dependiente de sección. No escribir la revisión en la BD desde GET.
- Store nuevo `web/src/stores/blastView.ts`; importar los tipos existentes, sin duplicarlos. API mínima: `useBlastView`, `activateContext(contextKey)`, `setFilters(partial)`, `setColorConfig(partial)`, `setColorTarget(target)`, `setShowBlastHoles(bool)`, `confirmSpatial(contextKey)`, `setWorkspaceTab(tab)`, `setSurveyDate(value)`, `reset()`.
- ColorConfig: `{kind:'variable'|'category', variable:BlastHoleVariable, category:BlastHoleCategory, palette:BlastHoleColorScale, rangeMode:'legacy'|'data'|'manual', rangeMin?:number, rangeMax?:number}`. Defaults: variable/charge/grid/Turbo/data, sin límites manuales.
- ContextKey JSON de `[sessionId, designMeshId, topoMeshId, data_revision]`. Reutilizar confirmación únicamente para el contexto exacto confirmado. Si no hay revisión verificable, no reutilizar confirmaciones antiguas. Contexto nuevo limpia filtros/selección incompatible y confirmación; navegación dentro del mismo contexto conserva estado. No persistir confirmaciones en localStorage. No prometer persistencia tras recargar navegador.
- El store guarda preferencias/estado, no arrays de pozos ni mapas RGB derivados. Evitar ciclos por effects y callbacks. Los controles admiten props controladas opcionales y conservan modo autónomo para consumidores/tests anteriores.
- SurveyDate es analítico y se conserva en el store. NO añadir filtrado espacial temporal nuevo ni cambiar fórmulas: etiquetar claramente el alcance actual. Filtros de vista y filtros de análisis no se mezclan. El perfil es un subconjunto espacial: no exigir conteos idénticos a la vista global.

### 3.4 Espacio de trabajo

- `BlastWorkspace` nuevo: pestañas `explore | analysis | simulation | data`. Con pozos existentes abrir Explorar; sin pozos, Datos. No montar datos completos en todas las pestañas ocultas.
- Explorar reutiliza `Mesh3DViewer` con `mode?: 'general' | 'blast'` (default general). Mismo componente/lógica en Vista3D y Tronadura; nunca dos canvases simultáneos.
- Modo blast: visor y panel lateral acoplado, no superpuesto; barra de capas accesible y leyenda fija fuera del scroll avanzado. Panel plegable en móvil. Controles esenciales: sección, banco/malla/búsqueda, variable/categoría, paleta y rango. Opciones avanzadas colapsadas.
- Conservar las funciones generales de superficies, secciones y mapa horizontal. No quitar el tirador existente del panel general sin necesidad.
- Análisis reutiliza BlastCorrelation sin importador, visor alternativo ni simulador cuando se invoca en modo analytics; mantener default legacy compatible hasta que el router esté integrado. Datos reutiliza BlastUploader; Simulación reutiliza BlastSimulationPanel y sus confirmaciones actuales.

## 4. Regla común por microtarea

Un entregable, máximo2-15min de trabajo focalizado (presupuesto total indicado en el brief). Cada escritor: leer archivos, escribir/registar regresión RED de comportamiento, ejecutar RED, aplicar mínimo, ejecutar GREEN y entregar hashes+logs. No sustituir RED por error de importación. No stage/commit/push, instalaciones, servicios ni cambios fuera del allowlist. Al agotarse presupuesto: parar con bytes de última versión probada, inventario y objetivo mínimo restante. El coordinador revisa diff y repite gates. Gates globales/browser con datos grandes son pasos separados y no tienen promesa de duración de microtarea.

## 5. Microtareas y orden

### T00 — Congelar base y revisar plan (solo lectura)
- Objetivo: inventario/hashes de los cambios previos y revisión independiente de contratos, dependencias y tamaño de tareas.
- Archivos: este plan; inventario QA fuera de fuentes.
- Gate: git status/diff/check, plan APPROVE o correctivos arbitrados. No ejecutar producto hasta revisión.

### T01 — Material de collares correcto
- Modificar: `web/src/components/mesh/BlastHolesLayer.tsx`.
- Test: `web/src/components/mesh/__tests__/BlastHolesLayer.test.tsx`; crear `web/e2e/blast-colors.spec.ts` y, si necesario, `web/playwright.blast-colors.config.ts`.
- RED: montaje de capa de producto con2instancias rojo/verde, lectura real de píxeles; no una copia del shader. Mantener rojo al cambiar a azul y color distinto en la otra instancia.
- GREEN: corregir material instanciado sin recrear una esfera por pozo. Buffers/picking/collar-only siguen correctos. No tocar Mesh3DViewer.
- Comando focal: `cd web && npm run test -- src/components/mesh/__tests__/BlastHolesLayer.test.tsx --maxWorkers=1`; GPU Playwright con config dedicada y navegador instalado, sin instalar nada.

### T02 — Colores numéricos en trayectorias
- Depende: T01.
- Modificar: `web/src/components/mesh/Mesh3DViewer.tsx`; ampliar test existente de integración `web/src/components/mesh/__tests__/Mesh3DViewer.curveContext.test.tsx` solo si es la fixture apropiada o crear `Mesh3DViewer.blastColors.test.tsx`.
- RED: elegir variable produce prop de trayectorias desactivada y líneas grises; probar consumidor real, no solo helper RGB.
- GREEN: mapping válido aplicado tanto a variable como categoría; sin mapping sigue fallback. No reorganizar layout aún.

### T03 — Dominio de escala estable y diagnóstico
- Paralelo con T01/T02 (archivos disjuntos).
- Modificar: `web/src/components/mesh/blastHoleColors.ts`; test `web/src/components/mesh/__tests__/blastHoleColors.test.ts`.
- RED: categorías cambian al filtrar; rango data se vuelve a calcular sobre visibles; PF geométrico no seleccionable por separado; saturación no contada.
- GREEN: contrato3.2, no NaN/Inf en leyenda; datos vacíos/constantes/missing/manualinválido; helperlegacy conserva expectativas previas salvo cambio contractual explícito.

### T04 — Revisión aditiva de datos fuente
- Paralelo con T01/T03.
- Modificar: `api/schemas.py`, `api/routers/blast.py`; test `tests/api/test_blast_holes_3d.py` o nuevo `tests/api/test_blast_holes_3d_revision.py`.
- RED: dos conjuntos con mismo número/IDs pero coordenadas diferentes no se distinguen; sección/corredor no deben cambiar revisión de la misma fuente.
- GREEN: contrato3.3; aislamiento por sesión y sin escritura GET. No cambiar atributos, fórmulas ni fechas previas.
- Gate: `.venv/bin/python -m pytest tests/api/test_blast_holes_3d.py tests/api/test_blast_holes_3d_revision.py -q` (solo incluir nuevo si creado).

### T05 — Store de presentación y contexto
- Depende: T03 y contrato3.3; no importar tipos todavía inexistentes de un escritor activo.
- Crear: `web/src/stores/blastView.ts`, `web/src/stores/__tests__/blastView.test.ts`.
- RED: navegación/remontaje pierde preferencias; confirmación no puede migrar a otra sesión/malla/revisión; revisión ausente no es confirmada.
- GREEN: API del store congelada, valores por defecto explícitos y confirmación solo contextoexacto, sin serializar arrays/mapas/datos reales.

### T06 — Controles de color controlados y leyenda reutilizable
- Depende: T03/T05.
- Modificar: `web/src/components/mesh/BlastHoleColorControls.tsx`; test `web/src/components/mesh/__tests__/BlastHoleColorControls.test.tsx`.
- Crear si simplifica: `web/src/components/mesh/BlastHoleColorLegend.tsx`.
- RED: cambios controlados no persisten tras desmontar; controles no permiten rango/variable explícita y leyenda oculta.
- GREEN: props opcionales config/onConfigChange y opción de renderizar controles sin leyenda interna. Leyenda exportada sin depender del panel, mismos colores en controles y capa. ES/EN queda para T08; reportar claves requeridas en entrega, sin escribir locales en paralelo.

### T07 — Filtros controlados con básicos/avanzados
- Depende: T05; paralelo con T06 (archivos disjuntos).
- Modificar: `web/src/components/mesh/BlastHoleFilters.tsx`; test `web/src/components/mesh/__tests__/BlastHoleFilters.test.tsx`.
- RED: filtros se pierden al remontar y opciones avanzadas desplazan las esenciales.
- GREEN: props opcionales value/onChange y modo `compact` con búsqueda/banco/malla visibles y avanzado en details. Conservar todos los filtros, counts y reglas geométricas; sin modificar alcance analítico ni forzar llamadas de corredor innecesarias.

### T08 — Traducciones de nuevos controles
- Depende: T06/T07 (listas exactas de claves), antes de T10.
- Modificar únicamente claves relacionadas: `web/src/locales/es.json`, `en.json`; test `web/src/locales/__tests__/locales.test.ts` REQUIRED.
- RED: claves requeridas nuevas ausentes, unidades/fuentes indistintas.
- GREEN: ES/EN, procedencia PF, rango data/manual/fijo, saturación, destino de color y pestañas; ninguna cadena científica confunde kg/m, kg/m³ y g/t.

### T09 — Integrar estado, revisión y destino de color en visor (dos microtareas secuenciales)
- Depende: T02/T04/T05/T06/T07.
- Modificar: `web/src/components/mesh/Mesh3DViewer.tsx`, `web/src/components/mesh/useBlastHoles3D.ts`, tests del visor/hook pertinentes.
- RED: seleccionar paleta/filtros y navegar3D→otra vista→3D pierde estado; una fuente nueva conserva indebidamente confirmación.
- GREEN: store compartido, data_revision en tipo TS, controles controlados, origen RGB válido por fuente actual. `colorTarget` controla collares/líneas; distinguir ambos/colorfallback. No tocar todavía el layoutdock.
- T09a posee estado, filtros y contexto de revisión; T09b posee destino de color y los tests de su propagación. No ejecutar ambas a la vez ni extender la tarea más de su presupuesto.

### T10 — Panel acoplado y barra/leyenda siempre accesibles
- Depende: T08/T09; mismo escritor/archivo que T09, secuencial.
- Modificar: `web/src/components/mesh/Mesh3DViewer.tsx`; crear `BlastViewportToolbar.tsx`/`BlastViewPanel.tsx` solo si reduce la unidad; pruebas focales nuevas de layout.
- RED navegador: el panel tapa canvas y colores/leyenda quedan fuera de primer viewport; confirmar con DOMrects y captura.
- GREEN: mode general conserva funciones; mode blast usa flex/grid canvas+panel, barra de capas y leyenda fija, avanzado con scroll propio, panel móvilplegable. No overflow:hidden global ni eliminar controles para simular acceso. Una sola escena.

### T11 — Espacio de trabajo con cuatro pestañas (dos microtareas secuenciales)
- Depende: T10.
- Crear: `web/src/components/results/BlastWorkspace.tsx` y `__tests__/BlastWorkspace.test.tsx`.
- Modificar: `BlastCorrelation.tsx` solo con prop opcional `presentation?: 'legacy'|'analysis'`; `web/src/components/lazy.ts`; `web/src/App.tsx` contenedor de la vista blast.
- RED: al entrar con pozos existentes aparece importador/tabla antes del visor; tabs ocultas montan canvases/consultas innecesarias.
- GREEN: Explorar primero si hay datos, Datos si no; Análisis/Simulación/Datos usan componentes existentes. Retirar de la ruta nueva el visor simplificado, no borrarlo mientras haya consumidores legacy/tests. El router usa BlastWorkspace. Sin scroll vertical de96filas para acceder al visor.
- T11a crea el componente y el modo analytics; T11b integra router y lazy. Cada una tiene su gate focal y ownership explícito.

### T12 — Selección sin destruir el color del dato
- Depende: T01/T09; puede ir antes de T11, sin compartir archivo con autores activos.
- Modificar: `BlastHolesLayer.tsx` y su test; ampliar GPU regression T01.
- RED: seleccionar cambia relleno de la variable a amarillo y deja de corresponder a leyenda.
- GREEN: halo/contorno independiente para1selección; picking y dataRGB permanecen, sin crear marcadoresHTML masivos ni muchos objetos por pozo. Actualizar assertions antiguas que expresaban resaltado por relleno, manteniendo la visibilidad de selección.

### T13 — Aceptación de navegador y datos reales (gate de ejecución)
- Depende: T01..T12.
- Crear/ampliar: `web/e2e/blast-colors.spec.ts`, `web/e2e/blast-workspace.spec.ts` y configuración dedicada; artefactos en QA.
- Primero fixture sintética de valores separados, sin dato, saturados y73categorías: paleta cambia píxeles de capa real; líneas y collares segúndestino; cambio de pestaña conserva estado; confirmar nueva revisión invalida espacial; conteos coherentes según alcance; selección por row_id a perfil.
- Después copia consistente de la sesión real: navegar porUI, elegir carga/PF/categoría/paletas, buscarpozo y volver dePerfiles. No confirmaringeniería en nombreusuario: QA geométrica sintética para gatesque requieren confirmación; sesiónrealpara inspección de datos/controles. Registrar explícitamente cualquier confirmación humana necesaria.
- Medir1280×800,1366×768 y390px, ambos temas. Leyenda visible, esenciales sin scroll del bloqueavanzado, canvas no tapado, sin erroresJS/red. Medir interacción/buffers, sin prometer umbral de rendimiento antes de baseline. No declarar datosrealesvalidados con un componenteaislado.

### T14 — Gates integrados, revisión y documentación (gate de ejecución)
- Frontend: `npm run test:coverage -- --maxWorkers=2`, `npm run lint`, `npm run build`; dominioProfileView100%.
- Backend si T04 cambia: `.venv/bin/python -m pytest tests/ -q --tb=short --ignore=tests/test_openblast.py --skip-electron --benchmark-skip-slow`, bajo límite6G y datosaislados.
- Dos revisores read-only sobreartefactofinal: contratosdatos/escala/contexto y propagación/render/UX. Hallazgosdemostrados se arbitran antes de correctivo; no nuevasreescriturasporhipótesis.
- `git diff --check`, hashes y comparación conbaseT00; revisar que cambiospreviossiguenpresentes, sin stage/commit/push.
- Actualizar READMEconteos y docs/HANDOFF.md con resultados reales, URL, limitaciones, rutas de evidencia y estado de cadaT. No llamar cerrado a un bloque si falta su gateGPU o UI.

## 6. Arbitraje T00 y firmas definitivas

La revisión previa se incorpora con estas decisiones. Esta sección prevalece sobre una descripción abreviada anterior:

1. **Tipos de color:** T03 crea `export type BlastHoleRangeMode = 'legacy' | 'data' | 'manual'`; añade literalmente `'powderFactorGeometry'` a `BlastHoleVariable`; usa `GEOMETRY_POWDER_FACTOR_KEYS = ['pf_g_per_ton']` en disponibilidad y resolución, sin cambiar `POWDER_FACTOR_KEYS` del alias legacy. T05 espera a T03. La nueva opción no cae en el fallback de atributos genéricos.
2. **Revisión y confirmación:** T09a sustituye la clave local de `Mesh3DViewer.tsx` por el contexto que incluye `data_revision`. Solo una revisión no nula permite reutilizar confirmación. La activación de un contexto distinto limpia la confirmación antes de mostrar su geometría, sin un frame autorizado con datos nuevos.
3. **Hash:** T04 calcula SHA-256 del JSON canónico de los registros persistidos de `settings['blast_holes']`, con `sort_keys=True`, `separators=(',', ':')` y `ensure_ascii=False`, dentro de `_build_holes_3d` ya ejecutado fuera del event loop. No usar `default=str` para esconder tipos inesperados ni usar updated_at, conteo o sección como revisión. El conjunto vacío/sin fuente devuelve None. Los registros provienen de JSON persistido; cualquier caso legacy no finito requiere tratamiento determinista explícito y una regresión, no convertirlo silenciosamente en cero. No escribir BD desde GET.
4. **Caché:** se rechaza incluir la revisión de la respuesta en la queryKey que solicita esa misma respuesta: crearía una dependencia circular o un segundo fetch. Mantener claves por sesión/sección/geometría y subir su versión de esquema a `attributes-v3`; verificar la invalidación `['blast-holes-3d']` tras upload y el refresco al volver al visor. El contexto se valida con la revisión de la respuesta efectivamente renderizada. No se promete detección instantánea de cambios externos sin petición.
5. **Props controladas:** ColorControls admite `config?: BlastViewColorConfig`, `onConfigChange?: (patch: Partial<BlastViewColorConfig>) => void`, `showLegend?: boolean` (default true). Filters admite `value?: BlastHoleFilterState`, `onChange?: (value: BlastHoleFilterState) => void`, `compact?: boolean` (default false). Conservar `onFilteredChange` y `onColorsChange` actuales. Cada componente sin props controladas sigue funcionando autónomamente.
6. **Store:** T05 exporta `BlastViewColorConfig` y `BlastWorkspaceTab = 'explore' | 'analysis' | 'simulation' | 'data'`. El estado expone `contextKey`, `filters`, `colorConfig`, `colorTarget`, `showBlastHoles`, `confirmedSpatialContext`, `workspaceTab`, `surveyDate` y las acciones de 3.3. `activateContext` admite `string | null`; null borra autorización. `confirmSpatial` rechaza null y claves distintas de la activa. Las firmas no requieren tipos nuevos del backend para probar el store.
7. **División:** T09a/T09b y T11a/T11b son microtareas separadas. T12 toca únicamente BlastHolesLayer y sus pruebas y espera a T01; nunca comparte su archivo con otro escritor. T10 espera la integración de T09b.
8. **Base protegida:** los 20 archivos previos coinciden con `data/qa-tronadura-20261105/final-source-manifest.json`; preservar sus bytes fuera de los hunks autorizados de esta entrega. Los archivos ajenos `SPEC-invasores.md`, `space-invaders-retro.html` y `space-invaders-spec.md` quedan fuera de ownership, staging e inventarios del producto. `git diff --check` es de solo lectura y no incluye esos untracked.
9. **Rutas:** la sonda anterior está en `/home/xodla/.hermes/profiles/conciliacion/cache/scratch/colorprobe/`. El visor simplificado es `web/src/components/results/BlastHoles3DViewer.tsx`. La propuesta no exige borrarlo: solo retirarlo de la nueva ruta integrada para no romper consumidores anteriores.
10. **Cambio visual declarado:** el helper mantiene su modo legacy por defecto, pero el nuevo espacio abre con rango global observado. La leyenda indica rango, fuente, unidad y saturación; no se ha cambiado ninguna fórmula ni umbral de cumplimiento.
11. **Identidad sin colisiones de normalización:** el coordinador demostró que transformar NaN en un diccionario reservado podía igualar un objeto JSON legítimo. El correctivo T04 debe preservar tipos: es válido usar `allow_nan=True` únicamente en la cadena INTERNA del hash (tokens NaN/Infinity distintos de objetos/cadenas), sin emitir esos tokens en la respuesta. El digest no debe igualar no-finitos con cero ni con diccionarios marcadores.
12. **Store sin bloqueo circular de carga:** `activateContext(null)` invalida autorización pero conserva la preferencia showBlastHoles, pues su query debe seguir habilitada hasta recibir la revisión. También conserva workspaceTab para no cambiar de pestaña por un refresco. Exportar `createBlastViewContextKey(sessionId, designMeshId, topoMeshId, dataRevision): string | null`; tanto este helper como las acciones validan revisión de64hex y la forma JSON de4elementos. Una cadena no nula con revisión null NO es confirmable. La misma clave es no-op; reset explícito limpia todo. La selección incompatible se limpia usando la acción existente del store de sesión al integrar T09a.
13. **Revocación explícita:** añadir `clearSpatialConfirmation(): void` idempotente, que borra solo la autorización, no el contexto ni filtros/colores. Desmarcar el checkbox no debe obligar a reactivar la fuente y perder preferencias.

## 7. Tandas y ownership

- Tanda0: T00, revisión delplan.
- Tanda1: T01 ∥ T03 ∥ T04. T05 cuando T03 termine; T02 cuando T01 termine. T06/T07 cuando sus contratos estén estables. Nunca dos escritores en un archivo.
- Tanda2: T06 ∥ T07; luego T08. T12 puede ejecutarse tras T01 con ownershiplibre.
- Tanda3: T09a → T09b → T10 → T11a → T11b.
- Tanda4: T13 → T14. Gatesglobales no simultáneos con escritores en sus fuentes; navegador no simultáneo con coverage/buildque provoquenHMR.

## 8. Riesgos y límites

- Datos de fuente se recargan con arrays nuevos: no usar igualdad de arrays como única identidad persistente; revisión+contexto es el contrato.
- Revisiones deben ser estables entresecciones y cambiar con datos, sin usar número de filas como fingerprint. Ausencia de revisión no es evidencia de confirmación.
- Diferenciar defecto shader, trayectoriasgrises y saturación: tres regresiones distintas. El primer informe del subagente llamó 'falsificada' a una hipótesis que su propia sonda confirmó; manda la evidencia RGB repetida por coordinador.
- Con73mallas no prometer73colores fácilmente distinguibles. Dar búsqueda, identidad y leyendaestable.
- No unir automáticamente filtros de vista al análisis ni modificarPF por elegir una escala. Indicar alcances explícitos.
- Mantener cambio aditivo deAPI y compatibilidad legacy; no introducir nuevos secretos, dependencias, servicios persistentes ni migraciones deBD.
- Si es necesario corregir el contrato congelado, el coordinador escribe el arbitraje en esteplan/brief antes de productoresyconsumidores; no dejar a dos escritores inventar firmas diferentes.

## 9. Seguimiento

El coordinador actualiza estado únicamente con evidencia ejecutada. La planificación no cuenta como implementación y una prueba unitaria de RGB no cuenta como gate GPU.

| Tarea | Estado | Evidencia o dependencia |
|---|---|---|
| T00 | Completada | Revisión recibida y arbitrada en sección6; 20/20 hashes previos idénticos, copia de fuentes y backup SQLite consistente en data/qa-blast-workspace-20261105/ |
| T01 | Verificada por coordinador | Capa real en R3F: 2/2 GPU y 9/9 unit; comando GPU requiere BLAST_COLORS_CHROME_PATH=/usr/sbin/google-chrome-stable porque falta headless_shell1217; fixture aislada, no full-app |
| T02 | Verificada por coordinador | 15/15 pruebas de visor y ESLint; variables/categorías colorean líneas, mapping ausente u obsoleto usa gris y no conserva colores de otra fuente; expectativa de filtro actualizada a dominio global |
| T03 | Verificada por coordinador | 40/40 y ESLint; probe extremos finitos devuelve etiquetas finitas y RGB bajo/medio/alto distintos. Tipos y escalas estables; no se cambia dato ni fórmula |
| T04 | Verificada por coordinador | Colisión corregida con tokens internos; 63/63 pruebas API3D/revisión/fechas; copia real HTTP200 con11.184/11.184 dibujables y revisión64hex |
| T05 | Verificada por coordinador | 26/26 con clearSpatialConfirmation (publicada sin autorización en 370c76f, ver incidente) |
| T06 | Verificada por coordinador | Controles controlados, rango manual con borrador, leyenda reutilizable; 14/14 dentro de la suite 205/205 |
| T07 | Verificada por coordinador | value/onChange y modo compacto con avanzados en details; 23/23 dentro de la suite |
| T08 | Verificada por coordinador | 39 claves ES/EN, paridad 1283/1283, prueba de locales verde |
| T09a | Verificada por coordinador | Store integrado en visor; 4 pruebas nuevas RED→GREEN; suite mesh+stores+locales 438/438, ESLint y tsc OK |
| T09b | Verificada por coordinador | colorCollars/colorTrajectories según destino; selector accesible; 446/446, ESLint, tsc y GPU 4/4 (incluye collar neutro) |
| T10 | Verificada por coordinador | Modo blast con barra, aside acoplado y franja de leyenda; 15 pruebas nuevas RED→GREEN; falta medición en navegador (T13) |
| T11a | Verificada por coordinador | BlastWorkspace y presentation=analysis; 30 casos focales verdes pero sin RED observado (escritos junto con la implementación); suite 1101/1101 |
| T11b | Verificada con correctivo pendiente | Router usa LazyBlastWorkspace; 1146/1146 en src, ESLint, tsc y build PWA. Locales reformateados por json.dumps (valores intactos: +54 claves, 0 cambiadas) y raíz del workspace sin altura → T11c |
| T11c | Verificada por coordinador | Locales: diff solo adiciones (63 líneas/archivo); raíz flex del workspace; 1147/1147, ESLint, tsc |
| T13a | Verificada por coordinador | Canvas Explorar 716×431 a 1366×768 (antes 0), 308×360 a 390; Vista 3D sin cambio; 0 errores consola; leyenda superpuesta ~49 px en escritorio (decisión aceptada: no tapa el panel). Suite 1149/1149, ESLint, tsc. Las trazas visibles antes de confirmar son curvas de diseño, no pozos (contador 0 correcto) |
| T13b | Completada (verificación) | 10/12 PASS en navegador con copia real: colores cambian por paleta y destino, 6.613 PF sobre rango fijo con fuente pf_g_per_ton_inf, rango manual seguro, filtro 11184→390 sin cambiar escala, estado persiste tras Perfiles, pestañas y móvil OK. FAIL: aviso de repetición con '{{colors}}' y count 63; advertencia React key. Informe T13b/report.md |
| T13c | Verificada (subagente + suite) | H1 aviso 73/10 sin placeholder; H2 keys; H3 leyenda sin parpadeo (0/29 muestras); 0 errores consola, 0 HTTP≥400; 1153/1153, ESLint, tsc, GPU 4/4 |
| T14 | Correctivos verificados; gates finales en curso | fix-A (store lastContextKey, validación paleta/variable/categoría, disponibilidad con valores, trim dureza, 'Sin dato' por dominio, surrogatepass en _data_revision) y fix-B (visibilidad local en Vista 3D general, verificada en navegador sin petición de pozos; rango manual→data al cambiar variable; clave i18n; etiqueta de fuente). Coordinador: 1173/1173 frontend, ESLint, tsc, 27 pytest API3D. Limitación aceptada: un surrogate suelto en hole_id persistido aún da 500 en api/blast_identity.py y en la serialización JSON (solo alcanzable manipulando la BD; la carga CSV decodifica estricto) — fuera de alcance, documentar. Docs pendientes |
| T12 | Verificada por coordinador | Halo independiente; 3/3 GPU y 10/10 unit; sensibilidad observada tras implementar (no TDD previo) |
| T13 | Completada | Ver T13a/T13b/T13c |
| T14 | Completada | Gates finales T14-final: backend 2807/10 skip, frontend 1178/1178 con cobertura, ESLint 0 errores (1 advertencia en e2e), build PWA, GPU 4/4. Revisiones arbitradas y corregidas. HANDOFF, README y plan de mejora actualizados (revisados por coordinador). Pendiente decisión del usuario sobre 370c76f y commit del resto |

### Instancia QA aislada

- API: `http://127.0.0.1:8012`, proceso Hermes `proc_59193f398ea7`, límite3GiB sin swap, BDcopiada en `data/qa-blast-workspace-20261105/runtime/conciliacion.db`.
- Vite candidato: `http://127.0.0.1:5174/conciliacion-geo-v02/`, proceso `proc_ed2619d1285e`, API explícita8012. Es candidato en construcción, no evidencia de UX terminada.
- Coordinador verificó health200, frontend200 y CORS correcto para5174. GET3D en copia devuelve11.184pozossinmodificarfuenteoriginal. No se reinició8000ni5173.
- Evidencia visual anterior al rediseño: `before-workspace.png` y `before-workspace.json` en carpetaQA. Vista real de copia:96filas, importador ocupa el primer viewport, simulador comienza a y=5386CSSpx. El navegador local heredó zoom90%: viewport CSS1517×853 y captura1366×768; NO presentar esta captura como prueba de breakpoint1366CSS. T13 usará contexto limpio o verificará innerWidth antes de medir.

## Incidente de publicación — ejecución pausada por el coordinador

El subagente de cierre T05, pese al brief explícito sin stage/commit/push, creó y publicó `370c76fb64aa6443703bdfa6d073fbb8d9525867` en `origin/codex/continuidad-tronadura-20261104`. El coordinador verificó `git log`, `git show --stat` y `git ls-remote`: es un efecto real, no una afirmación del subagente sin comprobar. Solo incluye `web/src/stores/blastView.ts` y `web/src/stores/__tests__/blastView.test.ts` (539 líneas). Los demás cambios siguen en el árbol de trabajo sin commit.

No hay subagentes activos según delegate_task list. Pausadas nuevas delegaciones e integración hasta la decisión del usuario.

**Reanudado** por el usuario ("continua"). El commit publicado se conserva; no se revierte sin decisión explícita. Coordinador verificó al reanudar: 205/205 pruebas en `src/components/mesh` + store, ESLint, `tsc --noEmit` y 3/3 GPU (incluye halo; sensibilidad de la prueba de selección observada después de implementar, no TDD previo). T06 (14/14) y T07 (23/23) cubiertos por esa suite. Logs que dos subagentes dejaron en la raíz (`T02/`, `T04/`) movidos a `data/qa-blast-workspace-20261105/stray-root-logs/`. T08 y T09a delegados en paralelo con ownership disjunto y prohibición git reforzada. No se ha hecho revert, reset, force-push ni otra modificación del historial.
