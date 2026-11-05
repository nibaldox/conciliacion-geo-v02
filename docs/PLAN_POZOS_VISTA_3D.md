# Plan: pozos de tronadura en la vista 3D y perfiles

Fecha: 3 de noviembre de 2026. Estado: implementación inicial en curso; resultados y verificaciones en `docs/HANDOFF.md`.

## Objetivo

Integrar los pozos cargados en la misma escena que las superficies de diseño y topografía real, y relacionarlos de forma verificable con las secciones y perfiles. La visualización debe seguir siendo legible con el volumen de datos disponible y distinguir geometría observada de geometría estimada.

## Situación actual

- `Mesh3DViewer` ya muestra las mallas y las secciones. Existe un visor independiente de tronadura que dibuja collares, pero no los integra con las superficies; crea una esfera y una etiqueta HTML por pozo, por lo que requiere una estrategia diferente para miles de registros.
- El perfil ya puede mostrar pozos proyectados mediante el endpoint de sección. La consulta usa un radio de inclusión y marca por separado la tolerancia solicitada; no debe presentarse automáticamente como un cruce exacto.
- El parámetro `section_name` de la consulta de pozos por sesión está reservado y actualmente no filtra. No se debe reutilizar como si fuera un filtro operativo.
- Las cotas de collar obtenidas de la superficie de diseño son estimaciones con procedencia, no levantamientos reales. Los registros rechazados por falta de cota o geometría no deben representarse inventando coordenadas.
- Los archivos facilitados contienen 20.939 registros de pozos. El sondeo exploratorio encontró 18.470 ubicaciones sobre el diseño y 2.469 fuera; no confirma sistema de coordenadas, datum ni unidades.

## Decisiones de diseño propuestas

1. Añadir una capa «Pozos de tronadura» en la vista 3D principal, inicialmente apagada. Mostrar el collar y el trayecto completo collar–pata si ambos extremos son válidos. Si solo existe un collar válido, mostrar únicamente un marcador diferenciado; contar y explicar los pozos sin geometría dibujable. Nunca sustituir cotas ausentes por cero.
2. Usar el mismo origen local, ejes, escala y transformaciones que las mallas y secciones. Asegurar que el sistema de referencia del archivo y la superficie fue confirmado. Identificar visualmente y en la ficha el collar estimado desde diseño, la procedencia de la malla y cualquier advertencia geométrica.
3. Ofrecer filtros independientes y combinables: sección activa y corredor en metros; banco o rango de cota cuando el atributo sea fiable; fecha o evento de tronadura cuando exista; y estado de geometría/procedencia. Ofrecer búsqueda de ID. Usar «Sin dato» cuando corresponda y no inferir sector o banco a partir de campos ambiguos.
4. Mantener una leyenda y conteos visibles de total cargado, aptos para representar, visibles con los filtros y excluidos por geometría; explicar que filas rechazadas no son pozos representados. Permitir limpiar filtros. Los filtros de pozos tendrán alcance explícito y no cambiarán silenciosamente los filtros de bancos ni la geometría del perfil.
5. Al elegir una sección, resaltar su traza y un corredor configurable, sugerido inicialmente de 10 m a cada lado. Es una distancia de búsqueda, no una tolerancia de cumplimiento; mostrarla como tal. Permitir activar el contexto de pozos exteriores atenuados sin sobrecargar la escena.
6. Separar dos resultados: «intersecta el plano de la sección» para el cruce geométrico del segmento finito, y «próximo a la sección» para un pozo dentro del corredor. La intersección debe calcularse con distancias con signo y considerar los límites longitudinales reales de la sección, tolerancias numéricas, trayectos paralelos, extremos sobre el plano y segmentos incompletos. Verificar la convención de origen y longitud antes de fijar el algoritmo. No calificar un collar proyectado como intersección ni atribuir causalidad por cercanía espacial.
7. Al seleccionar un pozo, mostrar ID, collar, pata, longitud, distancia a la sección, tipo de relación y procedencia disponible. La sección activa se sincroniza con el perfil y el pozo seleccionado se destaca allí cuando corresponda; dejar clara la diferencia entre geometría 3D y proyección 2D. Detectar IDs duplicados sin fusionar ni descartar registros automáticamente.
8. La fecha de tronadura y la fecha de topografía solo se compararán si ambas tienen fuente fiable. Sin ellas, indicar que el orden temporal es desconocido; no filtrar ni atribuir efecto a una tronadura por defecto.

## Tandas de implementación

### 1. Contrato geométrico y datos

- Auditar las coordenadas, unidades, convención de sección y datos de fecha con los archivos de referencia sin modificar la sesión activa. Definir un identificador estable por registro incluso ante IDs repetidos.
- Añadir una respuesta de pozos 3D acotada a la sesión con collar, pata, atributos filtrables disponibles, estado de geometría y procedencia. Mantener compatibilidad de las respuestas existentes y evitar cargar campos pesados innecesarios. Definir semántica de nulos y recuentos, incluido el origen de registros rechazados.
- Implementar o adaptar una única operación geométrica compartida para la relación segmento–sección/corredor. Revisar el proyector existente, que evalúa puntos representativos y utiliza un radio de inclusión separado de la tolerancia; no asumir que equivale a una intersección exacta. Alinear identificadores de sección y sector sin confiar solo en nombres.

### 2. Capa 3D y rendimiento

- Integrar una capa propia en `Mesh3DViewer`, con buffers o geometrías compartidas y representación por instancias/líneas agrupadas. Aplicar filtros antes de preparar la geometría; sin nodos ni etiquetas HTML por cada pozo. Mostrar etiquetas solo en selección o hover y liberar recursos al cambiar de sesión o datos.
- Medir primero transferencia, tiempo de preparación, interacción, memoria y estabilidad con datos sintéticos y la muestra real autorizada. Evaluar filtrado espacial en servidor o carga acotada si el traslado de todos los registros resulta costoso. Cualquier agregación o nivel de detalle debe indicar cuántos pozos representa y conservar acceso a los datos completos.

### 3. Filtros y cruce con perfiles

- Incorporar controles accesibles, estados vacíos, contador y leyenda; sincronizar selección de sección y pozo entre 3D y perfil sin alterar los filtros existentes. La vista y los resultados deben indicar si se trata de intersección o proximidad y qué ancho de corredor se aplicó.
- Conservar las convenciones y advertencias para cotas estimadas, fechas desconocidas y pozos sin geometría completa. Revisar el visor independiente para compartir componentes o mantenerlo coherente, evitando repetir un render por cada pozo.

### 4. Verificación y entrega

- Pruebas geométricas con intersección real, cercanía sin cruce, extremos en el plano, segmento paralelo, extremos fuera del tramo de sección, datos incompletos, IDs duplicados, sectores con nombres repetidos y valores numéricos límite.
- Pruebas de API para aislamiento por sesión, procedencia, conteos, filtros, nulos y compatibilidad; pruebas de interfaz para selección, sincronización, filtros combinados, límites de fecha y representación de estados vacíos. Mantener la cobertura requerida del dominio de perfiles.
- Prueba visual en escritorio y móvil, temas claro y oscuro, con mallas y una sesión aislada. Comparar rendimiento con la vista actual y registrar resultados reproducibles para una carga de al menos 20.939 registros. No fijar un número máximo de pozos mostrado de forma silenciosa.
- Validar después con los archivos reales y una referencia espacial confirmada; registrar limitaciones y no presentar la estimación de collar como medición de terreno.

## Dependencias y precauciones

- La API activa previamente fue iniciada sin recarga automática; comprobar su propiedad y configuración antes de reiniciarla para probar cambios de backend.
- Mantener el árbol de trabajo existente y la sesión del usuario; las pruebas de carga deben usar una sesión o base aislada.
- No modificar la interfaz Streamlit heredada. Los cambios de dominio compartido deben conservar su API estable y no alterar el significado de tolerancias o cumplimiento de bancos.
- Revisión de desempeño y comprobación geotécnica con datos reales pendientes. Un cruce o proximidad visual no demuestra por sí solo una relación causal entre tronadura y resultado topográfico.
