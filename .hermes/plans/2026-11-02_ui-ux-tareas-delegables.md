# Plan UI/UX web — tareas pequeñas y delegables

Fecha: 2 de noviembre de 2026. Origen: revisión visual del modo demo a 1280 × 720. No es una auditoría completa de accesibilidad ni una validación con datos reales o en móvil.

## Tanda 0 — resultados de preparación

- **U00:** árbol `main` con cambios locales previos en API, informes, frontend, pruebas y documentación, más planes y pruebas nuevas sin seguimiento; no se descartó nada. Node 22.23.1 y Python 3.12.14. Al momento de revisar, API y web tenían listeners en 127.0.0.1:8000/5173. El estado y los identificadores de proceso son temporales; volver a verificar antes de cualquier acción.
- **U01 (AGY, estático):** `ProfileView.tsx` asigna 380 px al panel lateral desde `xl`; propone desplazarlo debajo del gráfico hasta `2xl` o hacerlo plegable, y explorar menor altura en pantallas pequeñas. Su sugerencia de dejar la navegación de 1280 px solo con iconos contradice el objetivo de descubribilidad y no se adopta. Ninguna propuesta se ha probado en móvil ni medido visualmente; no reducir el gráfico sin verificar legibilidad, selección y proporción. Un primer intento agotó el tiempo sin respuesta; el segundo, acotado, terminó.
- **U02 (Luna, estático):** la demo usa mallas virtuales y datos sintéticos. Los hooks de exportación no tienen rama demo y pueden llamar a la API si el panel queda accesible; el uploader de tronadura también puede llamar a la API. La pantalla observada previamente mostró «Conciliación pendiente» en demo: el acceso efectivo depende del estado y debe reproducirse. No se demostró modificación de datos. Para U11 considerar el modo demo **y** la malla virtual, no solo el indicador `demoMode`, y preservar sesiones reales; agregar una tarea separada para el estado/carga de tronadura si se confirma su accesibilidad.
- **U03 (Luna, estático):** pruebas disponibles de barra de vistas, demo, dashboard, filtros, perfiles y selección de curvas bajo `web/src/components/**/__tests__/`. Playwright estándar puede reutilizar API/Vite existentes; la validación debe usar procesos, puertos, base y capturas propios, sin sobrescribir `docs/design`. Edge está instalado, pero el intento anterior se cerró antes de ejecutar pruebas; no afirmar que la validación visual funciona hasta comprobarlo. No se ejecutaron pruebas en U03.

## Alcance y reglas

- Repartir tareas entre Antigravity (AGY) y GPT-6 Luna. El coordinador asigna, revisa cada diff y verifica la integración. Una asignación en este documento es propuesta, no evidencia de ejecución.
- El árbol ya tiene cambios locales sin commit. Preservarlos; no revertir, reescribir ni mezclar trabajo ajeno. Cada agente recibe una lista cerrada de archivos y no hace commits, push, instalaciones ni cambios en datos, sesiones o procesos ajenos.
- Trabajar en `web/`; no modificar `app.py`, `ui/`, `core/`, API, Electron ni criterios de cálculo o cumplimiento. Textos de interfaz en español e inglés, sin comentarios nuevos en código, colores mediante tokens existentes.
- Evitar conflictos en el checkout compartido: los agentes proponen claves ES/EN en su entrega; el coordinador incorpora ambas traducciones de cada tanda en `web/src/locales/es.json` y `en.json` de forma secuencial antes de la validación de integración. Ningún agente de una tanda paralela modifica esos dos archivos.
- Las pruebas visuales usan demo o datos sintéticos en una sesión y puertos propios, sin reiniciar la aplicación abierta del usuario. No usar la configuración Playwright con reutilización de servidores sin aislamiento; no sobrescribir capturas versionadas. Si el navegador no arranca, registrar el bloqueo, no afirmar validación visual.
- Las pruebas focalizadas son proporcionales al cambio y comprueban comportamiento observable; no borrar ni relajar aserciones para obtener un resultado verde. Los agentes no ejecutan suites completas simultáneamente.

## Tanda 0 — Preparación

| ID | Agente | Tarea | Entrega y aceptación |
|---|---|---|---|
| U00 | Coordinador | Congelar inventario de cambios existentes y verificar los procesos y datos de prueba sin modificarlos. | Registrar `git status`, versiones y límites; ningún cambio de producción. |
| U01 | AGY | Revisar diseño y anchos actuales de navegación, perfil y dashboard. Solo lectura. | Propuesta de tamaños y distribución para 1280 × 720, escritorio amplio y móvil; localizar archivos y riesgos de regresión. |
| U02 | Luna | Revisar estados de demo y condiciones de acceso a Exportar/Tronadura. Solo lectura. | Identificar condición real y mensaje correcto; distinguir funcionalidad demo de producción. |
| U03 | Luna | Inventariar pruebas existentes y opciones seguras de navegador. Solo lectura. | Comandos focalizados, disponibilidad de navegador y estrategia aislada para capturas y datos. |

U01, U02 y U03 pueden ejecutarse en paralelo después de U00.

## Tanda 1 — Orientación y estados claros

Avance local: U10 implementada por Luna tras timeout de AGY; etiquetas visibles a 1280 × 720 y vista activa accesible. U11/U11b muestran mensajes específicos y bloquean exportación, IA y carga de pozos con mallas virtuales, manteniendo las sesiones de mallas reales; la consulta de pozos no se activa con una malla virtual. U12 entregada como propuesta: usar estado real de superficies, secciones y procesamiento, distinguir carga/error y no reutilizar `WizardProgress` como indicador de datos. U13 incorporó textos ES/EN. Validación: 89 pruebas dirigidas y suite completa 759/759 en 84 archivos, cobertura del dominio 100 %, TypeScript, ESLint y build con PWA aprobados. Inspección visual con demo en 1280 × 720 de navegación y mensajes; móvil, datos reales y Playwright pendientes.

| ID | Agente | Tarea pequeña | Archivos previstos | Aceptación |
|---|---|---|---|---|
| U10 | AGY | Hacer identificable la navegación de análisis en el ancho habitual. | `web/src/components/layout/ViewsToolbar.tsx` y sus pruebas; revisar uso en `LeftSidebar.tsx` sin editarlo salvo asignación explícita. | En 1280 × 720, nombres visibles o alternativa accesible y descubrible sin depender exclusivamente de iconos; foco de teclado y vista activa claros; no desbordar en móvil. |
| U11 | Luna | Corregir mensaje contradictorio de Exportar en demo. | `web/src/App.tsx` y prueba focalizada del estado de demo, o componente de estado identificado por U02. | Si demo no permite exportar, explicarlo sin pedir procesar datos; no cambiar las condiciones ni mensajes de sesiones reales sin evidencia. Si demo sí permite exportar, preservar esa función y aclarar alcance. |
| U11b | Luna | Revisar y proteger el acceso de carga de tronadura en demo. | `BlastCorrelation.tsx`/`BlastUploader.tsx` y pruebas focalizadas; determinar el punto mínimo antes de editar. | Reproducir accesibilidad; si está accesible con mallas virtuales, evitar acciones que envíen datos a la sesión real y explicar que no hay datos de tronadura en la demo. Mantener carga y mensajes de sesiones reales. |
| U12 | Luna | Diseñar guía breve de etapas y requisitos. | Solo diagnóstico y propuesta de ubicación/estado; sin editar archivos compartidos. | Definir estados derivados de datos existentes, sin convertir una recomendación visual en requisito nuevo ni duplicar estados inconsistentes. |
| U13 | Coordinador | Integrar traducciones de U10/U11 en ES/EN. | Archivos de locales. | Claves idénticas en ambos idiomas; textos revisados en contexto. |

U10, U11 y U12 se ejecutan en paralelo si U02 aclara U11. U13 sucede a U10/U11. Evitar que U10 y tareas posteriores editen `LeftSidebar.tsx` a la vez.

## Tanda 2 — Lectura de perfiles

Avance local: U20, U21 y corrección de selección y distribución de la grilla implementadas por Luna. U22 diagnosticó que los datos de las tarjetas no sustentan un indicador de cumplimiento sin obtener resultados comparativos; resumen diferido. Tras autorización expresa, Antigravity revisó en solo lectura ProfileView, ProfileChart y documentos acordados; se corrigió el muestreo global entre grupos de estado y el plano plegable. Integración final: 48 pruebas focalizadas, TypeScript y ESLint dirigido aprobados. Revisión visual en escritorio, móvil y datos reales pendiente; anotaciones de pata/dH no se redujeron por densidad.

| ID | Agente | Tarea pequeña | Archivos previstos | Aceptación |
|---|---|---|---|---|
| U20 | AGY | Dar más espacio al gráfico de detalle y hacer plegable el plano de ubicación. | `web/src/components/results/ProfileView/presentation/ProfileView.tsx` y pruebas de presentación; confirmar ruta real antes de asignar. | En 1280 × 720 el gráfico gana espacio; el plano sigue disponible y conserva sección activa. Sin alterar geometría, proporciones ni cálculos. Comprobar escritorio y móvil. |
| U21 | Luna | Reducir superposición de etiquetas en el gráfico. | `ProfileChart.tsx` y pruebas de presentación correspondientes. | Mantener datos y selección accesibles; etiquetas relevantes visibles por selección/zoom o con una estrategia clara. No ocultar advertencias ni estados sin alternativa. |
| U22 | Luna | Revisar tarjetas de grilla y proponer un resumen útil. | `ProfilesGrid.tsx` y pruebas; solo diagnóstico inicial de datos disponibles. | Si los datos y semántica están disponibles sin peticiones costosas, mostrar estado y/o bancos evaluados; si no, entregar propuesta sin inventar resultados. |
| U23 | Coordinador | Integrar traducciones y revisar U20–U22. | Locales ES/EN; pruebas de integración. | Verificar que interacción gráfico ↔ tabla y navegación por sección siguen funcionando; inspección visual con demo y, cuando sea posible, datos reales sobre copias. |

U20, U21 y U22 pueden paralelizarse con archivos disjuntos; revisar imports y pruebas compartidas antes de asignar. U23 va después de las tres entregas.

## Tanda 3 — Dashboard, flujo y legibilidad

Avance local: Luna implementó U30–U32 en archivos separados; se integraron textos ES/EN y se comprobó el cálculo del score (berma 60, ángulo 10, altura 30; promedio de bancos MATCH por perfil y luego de perfiles). El panel de filtros describe sus selecciones y el alcance del restablecimiento; el aviso de curvas explica el cambio a 3D. U33 midió pares de tokens: texto atenuado sobre surface en claro 4,34:1 y sobre surface-muted 4,07:1; las ayudas nuevas usan texto secundario y la explicación del KPI aumenta a 14 px. Contraste de paneles translúcidos y revisión visual en ambos temas siguen pendientes. Revisión independiente Luna PASS. Integración focal 32/32, TypeScript, ESLint dirigido y build PWA aprobados; dominio 124/124 con cobertura 100 %. Suite frontend completa no repetida tras timeout anterior.

| ID | Agente | Tarea pequeña | Archivos previstos | Aceptación |
|---|---|---|---|---|
| U30 | AGY | Aclarar la escala del puntaje global y distinguirlo de los conteos de perfiles. | `Dashboard.tsx` y prueba focalizada. | Explicar escala 0–100 solo si se confirma en el cálculo; conservar valores, denominadores y clasificación. |
| U31 | Luna | Mejorar comprensión del alcance de los filtros. | Componente de filtros de resultados identificado al iniciar y pruebas; no editar `Dashboard.tsx` mientras U30 esté activo. | Identificar filtros activos y alcance de cada restablecimiento; conservar selecciones y resultados actuales. Si requiere `Dashboard.tsx`, reprogramar tras U30. |
| U32 | Luna | Hacer explícito el cambio automático a vista 3D al definir secciones. | `LeftSidebar.tsx`, formulario de secciones y pruebas correspondientes. | El usuario sabe que debe elegir una curva y comprende el cambio de vista; preservar selección y navegación previas. No introducir cambios de geometría. |
| U33 | AGY | Revisar tamaños y contraste de texto secundario. | Solo lectura y mediciones iniciales de tokens/componentes. | Lista de fallos medidos o sospechas etiquetadas como tales; proponer ajustes sin afirmar conformidad WCAG sin medición. |
| U34 | Coordinador | Integrar traducciones y decidir ajustes U33. | Locales y componentes acordados. | ES/EN coherentes; sin raw hex nuevos, contraste y legibilidad verificados en temas claro/oscuro cuando el navegador funcione. |

U30, U32 y U33 pueden comenzar en paralelo. U31 solo en paralelo si no comparte archivos con U30. U34 integra al final.

## Tanda 4 — Validación y cierre

Avance parcial: tras revisión AGY y Luna se corrigieron mensaje vacío de filtros, traducciones, semántica de checkboxes y acordeones, se aclaró alcance del filtro de banco y se mejoró legibilidad. Revisión independiente Luna PASS. Última suite: **780/780 en 85 archivos** con `--maxWorkers=2` y cobertura de dominio 100 %; el intento anterior con concurrencia por defecto tuvo 778 aprobadas y 2 timeouts fullstack. TypeScript, ESLint dirigido y build PWA aprobados. Anotaciones densas dH y muestras no medidas requieren revisión visual antes de alterar su presentación; no se identificó copia de datos reales con procedencia comprobada. Sin publicación.

| ID | Responsable | Tarea | Aceptación |
|---|---|---|---|
| U40 | Coordinador | Ejecutar TypeScript, lint, pruebas focalizadas y suite frontend con cobertura. | Registrar comando, resultado y fallos de entorno; dominio de ProfileView conserva la cobertura requerida. |
| U41 | AGY o Luna | Recorrer demo y estados vacíos con navegador aislado. | Revisar 1280 × 720, escritorio amplio y móvil; teclado, foco, estados, controles sin solapamiento y capturas guardadas fuera de rutas versionadas. No declarar accesibilidad completa. |
| U42 | Coordinador | Validar con datos reales sobre copias cuando estén disponibles. | Revisar gráfico, plano, filtros y exportación sin alterar sesiones de trabajo; dejar limitaciones registradas. |
| U43 | Coordinador | Revisar diff y actualizar continuidad y estado del plan. | Resultados y pruebas reales claros; no hacer commit, push ni despliegue salvo solicitud. |

Las suites completas y la inspección visual se hacen después de integrar cada tanda, sin paralelizar procesos pesados. Si Playwright o el sistema bloquean el navegador, documentar el error y completar las verificaciones independientes.

## Plantilla de encargo

```text
Tarea UXX — objetivo y comportamiento esperado.
Archivos permitidos: <lista exacta>. Archivos de locales: solo lectura;
entregar claves y traducciones propuestas al coordinador.
Preservar el diff previo. No modificar datos/sesiones, procesos ajenos,
dominio, API, app.py, ui/ o Electron; no instalar, commit ni push.
Ejecutar <pruebas focalizadas> y entregar archivos, comandos, resultados,
capturas o limitaciones. No declarar verificación visual si no se hizo.
```
