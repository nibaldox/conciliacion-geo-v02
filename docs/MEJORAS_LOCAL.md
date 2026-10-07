# Mejoras de la revisión local — 30 de septiembre de 2026

Implementación posterior a la preparación del entorno y la corrección de
dependencias. Los cambios se guardaron localmente, sin commit ni push.

## Plan completado

- [x] Reducir la descarga de Plotly manteniendo los gráficos existentes.
- [x] Eliminar los avisos de módulos Node externalizados en la compilación web.
- [x] Mantener la carga de gráficos bajo demanda y la exclusión del precache PWA.
- [x] Corregir referencias antiguas de la arquitectura y textos de carga.
- [x] Verificar pruebas, compilación y comportamiento en un navegador real.

## Implementación

`web/src/components/charts/Plot.tsx` crea un único componente React con
`react-plotly.js/factory` y el bundle precompilado
`plotly.js/dist/plotly-cartesian.min.js`. Dashboard, perfiles y correlación de
tronadura lo comparten. Los gráficos actuales usan scatter, barras e
histogramas, incluidos en ese bundle. La visualización 3D continúa en sus
componentes de three.js/Cesium.

La configuración de Vite apunta al bundle cartesiano y a la factoría. Antes,
la lista manual de chunks incluía el punto de entrada completo de `plotly.js`
además de la dependencia del componente React, incorporando módulos que la
web no necesita. Se conservó el nombre `vendor-plotly` para las reglas PWA.

Las declaraciones del bundle se encuentran en
`web/src/types/plotly-cartesian.d.ts`; los tipos de gráficos siguen procediendo
de `plotly.js`. Si se incorpora en el futuro un tipo de gráfico no incluido
en el bundle cartesiano, habrá que ampliar el runtime compartido.

Los textos de carga en español e inglés ahora dicen «Cargando gráficos…» /
«Loading charts…», sin una estimación fija de descarga.

`ARCHITECTURE.md` documenta el módulo `core.ai_v2`, los routers actuales,
las rutas de perfiles bajo `/api/v1/process`, los límites de importación
del API público y el bloqueo de escrituras de SQLite. La cota del collar
usa la altura de banco confirmada por el usuario cuando corresponde; se
eliminó la referencia a una suma automática de 15 m. No se modificaron
los cálculos geotécnicos ni la interfaz Streamlit.

## Medición de la compilación de producción

| Bundle Plotly | Antes | Después | Reducción |
|---|---:|---:|---:|
| JavaScript | 4.808.478 bytes | 1.514.584 bytes | 68,5% |
| Gzip | 1.481.743 bytes | 502.752 bytes | 66,1% |

La medición usa el archivo `vendor-plotly` generado por Vite y gzip de Node,
con la misma configuración de compresión para ambos archivos. No es una
medición de latencia de red ni de tiempo de renderizado.

## Validación

- `npm run build`: TypeScript, Vite y PWA correctos, sin avisos de bundle grande
  ni módulos Node externalizados. El bundle Plotly no aparece en el precache.
- `npm run test -- --coverage`: 397 pruebas aprobadas en 45 archivos;
  dominio de perfiles al 100% en líneas, sentencias, ramas y funciones.
- ESLint y `git diff --check`: correctos.
- Edge sin ventana sobre la compilación de producción, en modo demo: barras
  e histogramas del dashboard, grilla y detalle de perfil renderizados con
  datos. Esta comprobación visual no prueba una carga real de mallas vía API.
- Perfil verificado con cuatro trazas scatter de 95, 95, 95 y 8 puntos;
  zoom y generación de PNG correctos, sin errores de JavaScript.
- Ninguna descarga de Plotly antes de abrir gráficos; un único bundle
  compartido entre dashboard y perfiles.

Las pruebas de backend de la etapa anterior siguen registradas en
`CONTINUAR_LOCAL.md`: 2.199 aprobadas y 7 omitidas, excluyendo el archivo
opcional de openblast. Esta etapa no cambió código Python.

La vista previa y el navegador usados para validar se cerraron al terminar.

El mecanismo de factoría sigue la [documentación de React Plotly](https://github.com/plotly/react-plotly.js#customizing-the-plotlyjs-bundle).
Los tipos incluidos en el bundle cartesiano se describen en la
[documentación de bundles de Plotly](https://github.com/plotly/plotly.js/blob/main/dist/README.md#plotlyjs-cartesian).

## Frontend oscuro implementado — 30 de septiembre

- Navegación de vistas integrada en el lateral izquierdo; acceso a todas las vistas también con el panel contraído.
- Tema de grafito con acentos azules, encabezados más legibles y controles de carga compactos.
- Perfil amplio, inspector de banco con valores reales y de diseño, y tabla completa debajo del gráfico. Se conservan las columnas de cota, piso y puntaje.
- Selección por clic y teclado. Se corrigió un efecto que borraba la selección en cada render; ahora se limpia al cambiar de sección.
- Zoom, restablecer ejes y descargar PNG mediante la barra del gráfico; etiquetas y controles en español e inglés.
- Adaptación móvil con navegación contraíble y tabla desplazable.
- Validación: 403 pruebas web en 48 archivos aprobadas; cobertura del dominio al 100%; TypeScript, ESLint y build PWA correctos.
- Edge verificó grilla, detalle, navegación entre secciones, inspector, filtros y distribución de escritorio/móvil sin errores de JavaScript.
- Capturas: `docs/design/frontend-options-2026-09-30/implementacion-oscura.png` e `implementacion-movil.png`.
- Servidores de prueba conservados: web http://127.0.0.1:5174/conciliacion-geo-v02/ y API http://127.0.0.1:8000.
- Cambios guardados localmente, sin commit ni push. No se modificó Streamlit ni el cálculo geotécnico en esta fase.

## Ajuste de carga inicial compacta

- A solicitud del usuario se redujeron las tarjetas de diseño y topografía a filas de 54 px en el lateral, conservando selector de archivos, arrastre, progreso, errores, reemplazo y eliminación.
- El demo ocupa un botón pequeño y los formatos aceptados se muestran una sola vez.
- Se eliminó el límite fijo del 55% para los controles del proyecto. En ventanas de hasta 850 px de altura, la navegación de resultados usa dos columnas.
- Edge comprobó que todos los controles iniciales caben sin desplazamiento interno a 1366×768, 1280×720 y 1024×640. También verificó el selector por teclado y la carga del demo, sin errores de JavaScript.
- Validación final: 403 pruebas web aprobadas, TypeScript/build PWA y ESLint correctos.
- Captura del lateral: `docs/design/frontend-options-2026-09-30/carga-compacta.png`.
- Los cambios siguen guardados localmente, sin commit ni push.

## Corrección de tamaño de la vista 3D

- Se reprodujo el fallo con datos demo: el panel tenía 402 px de altura y el canvas WebGL solo 150 px.
- La vista 3D ahora recibe una altura definida desde el layout y el canvas ocupa el panel completo mediante posicionamiento absoluto. Las otras vistas mantienen su desplazamiento.
- En una ventana de 1920×1080 el panel mide 899 px y el canvas 897 px; también se comprobó su ajuste a 1366×768, 1024×640 y 390×844, sin desbordamiento ni errores JavaScript.
- Build/TypeScript y ESLint correctos. La revisión de perfiles confirmó filtros, selección, zoom, PNG y navegación de escritorio/móvil. No se repitieron pruebas unitarias para este cambio de distribución visual.
- Captura: `docs/design/frontend-options-2026-09-30/vista-3d-ampliada.png`.
- Cambios locales guardados, sin commit ni push.

## Tema claro y selector visible — 30 de septiembre

- Se añadió un botón de sol/luna con las acciones «Claro» y «Oscuro» en el encabezado, visible también en móvil y accesible por teclado.
- La preferencia se guarda en el navegador y se aplica antes de mostrar la página. El tema claro adapta fondos, textos, tablas, gráficos Plotly, miniaturas y escena 3D.
- Cambiar de tema conserva la sección y el banco seleccionados. La vista 3D mantiene el tamaño ampliado del ajuste anterior.
- Validación: 405 pruebas web en 49 archivos aprobadas; las 110 pruebas del dominio de perfiles mantienen cobertura del 100%; TypeScript/build PWA y ESLint correctos.
- Edge verificó persistencia, selección, colores de gráficos y botón móvil sin desbordamiento. La escena 3D se comprobó renderizada con WebGL por software en un contexto nuevo, sin errores de JavaScript. Se usaron datos demo; la carga de mallas reales queda para la prueba del usuario.
- Capturas reales: modo-claro-perfiles.png, modo-claro-resumen.png y modo-claro-3d.png en docs/design/frontend-options-2026-09-30/.
- Servidores de prueba conservados: http://127.0.0.1:5174/conciliacion-geo-v02/ y API en el puerto 8000.
- Cambios guardados localmente, sin commit ni push.

## Corrección de escala de perfiles — 30 de septiembre

- Se reprodujo la deformación al pasar de la grilla al detalle: el gráfico demo usaba 1,77 píxeles por metro horizontal y 5,35 vertical, una exageración de aproximadamente 3×.
- Se eliminó la exageración calculada a partir del contenedor. El detalle ahora mantiene una escala 1:1 entre distancia y elevación, igual que las miniaturas; Plotly amplía el rango visible para conservar la geometría completa.
- Se actualizan explícitamente las dimensiones del gráfico cuando cambia su contenedor, incluido el panel lateral. Los datos y cálculos geotécnicos se conservan.
- La prueba de regresión web/e2e/profile-scale.spec.ts verifica la escala realmente renderizada al abrir, ampliar, restablecer, cambiar sección/tema y ajustar a escritorio/móvil. Aprobada en Edge con datos demo; medición final: 2,01 píxeles por metro en ambos ejes.
- Validación: 100 pruebas de presentación de perfiles aprobadas, build/TypeScript y ESLint correctos; git diff --check correcto.
- Captura: docs/design/frontend-options-2026-09-30/perfil-escala-corregida.png.
- Referencia de escala Plotly: https://plotly.com/javascript/reference/layout/yaxis/#layout-yaxis-scaleratio.
- Cambios guardados localmente, sin commit ni push. Servidores conservados en los puertos 5174 y 8000.

## Cumplimiento y planos de evaluación — 30 de septiembre

- [x] Alinear el resumen web con el motor que usa Streamlit: berma 60, altura 30 y ángulo 10. Se toma el puntaje calculado por el motor cuando está disponible; los perfiles cumplen desde 70/100.
- [x] Promediar los bancos MATCH de cada perfil y luego los perfiles con igual peso. Los bancos ausentes o adicionales no distorsionan ese puntaje; los indicadores de sector cuentan los parámetros evaluados, como Streamlit.
- [x] Agregar al resumen la topografía real y las líneas de los perfiles procesados, con colores de cumplimiento y coordenadas Este/Norte a la misma escala.
- [x] Incluir el plano en los informes Word y PDF pasando las secciones y la topografía de la sesión. Se corrigieron dos fallos que impedían insertar las imágenes en PDF y el puntaje global del informe ahora representa todos los perfiles.
- [x] Respetar también los filtros actuales al exportar el PDF.
- Validación: 2.210 pruebas Python aprobadas y 7 omitidas, excluyendo openblast; Word generado con siete imágenes y PDF real de tres páginas con el plano visible. No se modificaron app.py ni ui/.

## Ingreso de datos con un diseño uniforme

- [x] Usar controles compartidos de 32 px, etiquetas legibles, colores del tema y espaciado coherente en Secciones y Parámetros; Procesamiento usa botones del mismo tamaño.
- [x] Organizar Superficies, Secciones, Parámetros y Procesar en un selector de dos filas, dejando más espacio para completar los formularios.
- [x] Reducir la carga CSV/TXT/DXF a una fila compacta, con selector por teclado, arrastre y eliminación del archivo seleccionado.
- [x] Agrupar sector, separación y longitudes en dos columnas. Las instrucciones de selección del tramo y las secciones existentes se pueden desplegar cuando se necesitan.
- [x] Mostrar la lista lateral con tarjetas compactas que conservan edición de coordenadas, azimut, longitudes, sector y eliminación. Los ángulos globales de tolerancia permanecen accesibles en un desplegable.
- [x] Adaptar la navegación a una fila de iconos con etiquetas emergentes en ventanas de hasta 700 px de altura.
- Edge verificó que los formularios básicos caben sin desplazamiento a 1366×768, 1280×720 y 1024×640. La ayuda, los parámetros adicionales y las listas desplegadas pueden necesitar scroll.
- Tres pruebas e2e verifican selección de archivo por teclado, envío de la geometría completa, selección del tramo, edición de secciones y guardado de parámetros/tolerancias con API simulada, sin alterar la sesión del usuario.

## Mejoras de ubicación solicitadas y completadas

- [x] Abrir el plano del resumen con zoom sobre la zona evaluada, calculada con los cortes reales de los perfiles visibles. Se mantiene la escala métrica y un margen de contexto.
- [x] Separar los nombres de los perfiles a ambos lados del plano y conectarlos a sus líneas. Se comprobó que los 32 nombres de una evaluación concentrada no se superponen.
- [x] Permitir alternar entre «Zona evaluada» y «Superficie completa».
- [x] Agregar al detalle de perfiles una miniatura de ubicación en planta: topografía real, perfil activo en azul, hasta siete perfiles cercanos del mismo sector en gris y flecha Norte. La miniatura sigue la navegación sin cambiar el banco seleccionado.
- Se reutilizan las consultas y la caché de perfiles; no se agregan cálculos al motor geotécnico.
- Validación web: 415 pruebas unitarias aprobadas (suite de 413 más las dos pruebas nuevas de encuadre), siete pruebas e2e aprobadas, TypeScript/build PWA, ESLint y git diff --check correctos.
- Capturas en docs/design/frontend-options-2026-09-30/: perfil-con-miniatura.png, plano-zona-evaluada-32-perfiles.png, ingreso-archivo-compacto.png, ingreso-parametros-compacto.png e ingreso-curvas-claro.png.
- Servidores conservados: frontend en http://127.0.0.1:5174/conciliacion-geo-v02/ y API en http://127.0.0.1:8000. La API fue reiniciada para cargar las correcciones de informes.
- Cambios guardados localmente; sin commit ni push. La prueba pendiente del usuario es revisar sus mallas reales, el encuadre y la legibilidad de los nombres con su número habitual de perfiles.


## Filtro por banco, carga de Tronadura y plano ampliado — 30 de septiembre

- [x] Resumen: selector visible «Filtrar por banco», con búsqueda, selección múltiple y «Restablecer». Sin bancos seleccionados se muestran todos, como en Streamlit. Los indicadores, gráficos, perfiles contados y colores del plano se recalculan con los bancos elegidos.
- [x] Informes: al filtrar por banco se recalcula el puntaje por perfil para evitar que el plano conserve el puntaje de todos los bancos. Las comparaciones originales de la sesión permanecen intactas.
- [x] Tronadura: «Seleccionar CSV» abre el selector desde el inicio, por ratón o teclado. Elegir el archivo abre la configuración geométrica; tras revisarla y confirmarla, «Cargar pozos» envía el archivo. Volver a elegir un archivo o editar la configuración invalida la confirmación. Se conservan las convenciones, unidades independientes y diagnósticos 400/422; no se asume altura de banco.
- [x] Detalle del perfil: columna del plano ampliada de 260 a 380–420 px. La vista en planta tiene proporción 10:9 y mantiene la escala de la geometría, el perfil activo azul, sus vecinos y la flecha Norte. Medida en escritorio 1600 px: 394 × 355 px frente a los 160 px de altura anteriores. En móvil se adapta al ancho disponible.
- Validación: 419 pruebas unitarias web aprobadas; 16 pruebas Python de resumen/exportación aprobadas. ESLint, TypeScript/build PWA correctos. Navegador Edge: filtro por banco, selector CSV por teclado, envío FormData de geometría confirmada, cambio de perfil/tema y adaptación móvil verificados en sesiones aisladas.
- Capturas: docs/design/frontend-options-2026-09-30/perfil-planta-ampliada.png y resumen-filtro-banco.png.
- API reiniciada para aplicar los puntajes de exportación filtrados (puerto 8000, PID 14416). Frontend conservado en http://127.0.0.1:5174/conciliacion-geo-v02/.
- Cambios guardados localmente, sin commit ni push. Prueba con datos reales: seleccionar los bancos del resumen; cargar un CSV de pozos confirmando sus convenciones; verificar la ubicación del perfil en el plano ampliado.

- Cierre: seis pruebas e2e afectadas aprobadas; la escala 1:1 del gráfico se mantiene tras ampliar el plano. Captura adicional tronadura-carga-csv.png revisada. API responde 200 y git diff --check correcto.
