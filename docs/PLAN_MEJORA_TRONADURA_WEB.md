# Plan de mejora de tronadura y traslado a la web

Fecha: 4 de noviembre de 2026. Referencia: `REVISION_TRONADURA_STREAMLIT_WEB.md` y el módulo de Streamlit vigente. Objetivo: convertir la experiencia de tronadura en un flujo verificable, con filtros coherentes y rendimiento adecuado para el archivo de 20.939 pozos. La implementación se organiza por entregas completas, con su validación; la disponibilidad en el motor de cálculo no cuenta como una función terminada en pantalla.

## Diseño del módulo

Flujo propuesto: Datos → Calidad y geometría → Análisis → Vista 3D y perfiles → Simulación → Exportación. Los filtros del análisis deben indicar su alcance; modificar colores o capas no debe cambiar indicadores. La fecha de levantamiento, las convenciones angulares y la procedencia de las cotas deben aparecer junto a resultados dependientes. La estimación de collar en la superficie no equivale a medirlo ni determina por sí sola una altura de banco.

En Streamlit la propuesta es agrupar controles en formularios, aislar cálculos mediante fragments cuando corresponda y limitar cachés por datos/configuración, con grillas y simulaciones bajo demanda. Mantener lógica en core y usar UI solo como adaptador. Para la web aplicar los mismos principios con peticiones explícitas, resultados paginados, render instanciado y consultas con claves que incluyan filtros. Se preserva el módulo Streamlit operativo durante el traslado.

## Entregas y criterios de cierre

| Entrega | Funciones web | Verificación exigida | Estado inicial |
|---|---|---|---|
| 1. Entrada y contexto temporal | CSV/XLSX, selección de hoja, vista previa limitada, 20 campos mapeables con confirmación; fecha de levantamiento para correlación y modelo de daño, con margen temporal del motor visible. | Campos obligatorios/mapeos inválidos, hojas, convenciones, fechas ausentes/posteriores, igualdad con criterio del motor; no persistir preview. | Cierre técnico (5 nov. 2026) con datos sintéticos y aislados: backend 2.795 aprobadas, frontend 962 aprobadas, ESLint y build PWA aprobados, browser QA sintético 22/22 en escritorio y móvil. **Validación operacional pendiente**: sin archivos reales confirmados, CRS/datum no validados, rendimiento con 20.939 pozos no medido, Playwright completa y apertura 3D con datos reales no realizadas. La suite frontend, build y lint se repitieron tras el último ajuste CSS y aprobaron. Entregas 2 a 6 no iniciadas. |
| 2. Datos operacionales | Archivo opcional de diseño de perforación y reporte rig; unión por identidad comprobable, diagnósticos de coincidencias y cumplimiento por malla. | Sin asignación silenciosa por IDs duplicados; unidades/procedencia; indicadores no calculables explícitos. | Pendiente. |
| 3. Exploración coherente | Tabla paginada de pozos, filtros de análisis por banco/malla/polígono; análisis por sección, banco y malla. | Conteos y exportación usan el mismo conjunto; identidad sección+sector; agregados contra referencia. | Pendiente. |
| 4. Capas espaciales | Campo IDW, halos PF 2D/3D, leyendas y descarga de grillas; parámetros y procedencia visibles. | Reusar core; validar unidades, dominio y datos faltantes; carga bajo demanda y sin etiquetas masivas. | Pendiente. |
| 5. Herramientas de ingeniería | Recomendaciones, back-break, modelo multivariado, pasadura/piso, taco/cresta, atribución y temporal/pre-post. | Muestras mínimas, incertidumbre, fuentes y límites del modelo; resultados no presentados como causalidad o calibración comprobada. | Pendiente. |
| 6. Simulación y salidas | Comparación de parámetros del simulador con Streamlit, exportaciones visibles de simulación y análisis, metadatos de filtros/configuración. | Mismos datos y configuración → mismos resultados; archivos válidos y comprobación visual. | Pendiente. |

## Decisiones para la primera entrega

- CSV sigue disponible con su flujo anterior. XLSX se procesa en el servidor con el lector instalado; las hojas se eligen explícitamente. No anunciar XLS sin lector compatible.
- Las sugerencias de columnas muestran su origen/confianza y se confirman. No se convierten supuestos geométricos en convenciones automáticas.
- La vista previa muestra como máximo 20 filas. Cambiar archivo u hoja invalida la confirmación previa.
- Sin fecha de levantamiento se mantiene el cálculo histórico, acompañado de aviso de que no hay corte temporal. Con fecha, aplicar el criterio temporal del motor, mostrar la fecha efectiva y excluir fechas desconocidas con conteo separado.
- Tabla de correlación y modelo de daño deben usar el mismo contexto temporal; los filtros visuales del visor se mantienen identificados como tales.
- Para el archivo real se hará validación aislada, sin cambiar la sesión de trabajo. La interpretación operacional de CRS, datum y ceros de inclinación requiere datos confirmados, no se deduce de una prueba de software.

## Pruebas y despliegue local

Usar pruebas focalizadas de API/importación/fechas y de interfaz; compilar TypeScript, ejecutar lint de los archivos tocados y comprobar regresiones existentes. Medir antes de ampliar pruebas de desempeño; no reconstruir toda la geometría con cada cambio visual. Registrar en HANDOFF qué entrega está implementada, cuál está verificada con datos reales y qué sigue pendiente. El plan no implica publicar ni cambiar la instalación de Streamlit.

## Ajustes tras revisión independiente

- La comparación con el mismo lote y configuración es un criterio de cada entrega que cambie entradas, geometría o agregados; no se posterga hasta el simulador. Para fuentes de cota distintas, comparar cada fuente por separado y conservar sus etiquetas en tabla y exportación.
- Los filtros analíticos deben viajar en la petición y su clave de consulta; se deben identificar por separado los controles visuales de cámara/color. La exportación declarará el conjunto aplicado.
- La vista previa leerá un máximo de 20 filas y no reprocesará el conjunto completo por cada cambio de campo. Las capas futuras usarán límites de celdas/memoria explícitos derivados de la configuración y de mediciones previas, con rechazo o reducción anunciada al superar el presupuesto.
- Durante el traslado las adaptaciones se implementan en core/API/web. Las propuestas de formularios/fragments/cachés para Streamlit quedan documentadas para una intervención independiente; su interfaz operativa sirve de referencia.

## Avance — 5 de noviembre de 2026: colores de pozos y espacio de trabajo

Cierre técnico de la entrega de presentación de Tronadura (colores fiables y un único espacio de exploración). No es validación operacional: CRS/datum siguen sin confirmar.

- **Render**: el material de collares ya no usa `vertexColors` sin atributo de color (causaba render negro); trayectorias y collares comparten variable o categoría; el destino del color es explícito (ambos, collares o trayectorias) y la selección usa un halo que no sustituye el color del dato.
- **Escalas legibles**: rango observado, fijo heredado y manual validado; se cuentan los valores bajo/sobre el rango y sin dato; PF de influencia y PF geométrico quedan separados sin fallback silencioso; las categorías no cambian al filtrar y la leyenda avisa cuando los colores se repiten.
- **Estado coherente**: store `web/src/stores/blastView.ts` con contexto de sesión, mallas y `data_revision` (campo aditivo de `GET /api/v1/blast/holes/3d`); la confirmación espacial no se hereda entre contextos y se restaura al volver a la misma clave.
- **Espacio de trabajo**: pestañas Explorar, Análisis, Simulación y Datos; panel acoplado, barra de capas y leyenda fija; Análisis reutiliza el componente existente sin importador ni visor alternativo. La Vista 3D general no cambia de comportamiento.
- **Gates**: backend 2.807 aprobadas, 10 omitidas y 12 advertencias (`MemoryMax=6G` sin swap); frontend 1.178/1.178 en 100 archivos con dominio 100 %; ESLint, build PWA (30 entradas) y Playwright GPU 4/4. En navegador, con una copia de 11.184 pozos: 10/12 escenarios PASS y los 2 fallos (aviso con placeholder y `key` de React) corregidos y revalidados.
- **Incidente**: un subagente publicó sin autorización el commit `370c76f` (`blastView.ts` y su test) en la rama remota; no se revirtió y el resto del trabajo sigue sin commit, a la espera de decisión del usuario.
- **Límites**: la confirmación espacial de QA es una hipótesis y no valida CRS/datum; la leyenda ocupa ~49 px del visor en escritorio; la copia no tiene columna de banco; un surrogate suelto en `hole_id` persistido todavía da 500 (solo con BD manipulada); la validación operacional de la entrega 1 sigue pendiente.
