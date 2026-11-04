# Propuesta de informe de conciliación geotécnica

**Estado:** primera implementación local de Word/PDF realizada; queda pendiente la revisión visual de Word y la validación con datos reales. Los ejemplos entre corchetes son marcadores, no resultados medidos.

## Objetivo

Permitir que jefatura identifique rápidamente el alcance, los resultados y los puntos que requieren atención; permitir que ingeniería rastree cada conclusión hasta sus mediciones, criterios y perfiles. Mantener los criterios de cumplimiento existentes y diferenciar datos medidos, estimaciones y datos no disponibles.

## Formatos

- **Word técnico:** documento completo, editable, con tablas por banco y perfiles. A4 apaisado con dos perfiles más pequeños por página, conforme a la elección del usuario.
- **PDF:** lectura más breve, con el mismo resumen, criterios, plano y hallazgos prioritarios; detalle técnico condensado cuando esté disponible. El PDF actual no incluye todos los perfiles ni la tabla completa por banco: su ampliación debe revisarse como parte del diseño, no suponerse existente.

## Estructura propuesta

1. **Portada y control documental.** Proyecto, sector o fase, fecha, superficies comparadas y espacio para revisión y aprobación, usando solo datos disponibles. Estado y filtros visibles desde el comienzo.
2. **Resumen ejecutivo.** Resultado por perfil según el peor estado de banco; conteos y denominador; puntaje ponderado y logro de diseño como indicadores separados. Una síntesis breve de desviaciones prioritarias y advertencias, sin presentar recomendaciones automáticas como decisiones de ingeniería.
3. **Alcance y criterios.** Fuentes, fecha de análisis, filtros aplicados, tolerancias efectivas, ajustes relevantes del proceso, unidades, cobertura y límites. Explicar claramente qué resultados quedan fuera del alcance y qué no pudo evaluarse.
4. **Resultados por parámetro.** Tabla compacta de altura, ángulo y berma con criterio, resultados, conteos y unidad, acompañada de gráficos legibles. Identificar si un desglose combina estados fuera de tolerancia y no conformes; no llamar evaluados a registros sin medición válida.
5. **Plano y sectores.** Plano con nombres de sección, sector, orientación y leyenda. Señalar el peor estado por perfil y distinguir las secciones excluidas por filtros y las que no se pueden resolver. Mostrar resultados por sector solo cuando el dato esté disponible y su definición sea inequívoca.
6. **Desviaciones prioritarias.** Para cada parámetro: sección, banco, valor de diseño, valor real, diferencia, unidad y estado, cuando existan. Explicar el criterio de orden: tolerancias para altura y ángulo y déficit respecto al mínimo para berma. No convertir una ausencia de medición en cero.
7. **Detalle por banco y perfil.** En Word, tabla trazable seguida de perfiles no conformes primero y anexo de conformes, dos por página en A4. Cada perfil debe identificar sección y sector, fuentes, unidades, tolerancias y advertencias aplicables. Mantener explícitos bancos faltantes o adicionales.
8. **Tronadura, cuando corresponda.** Resumen de pozos y variables disponibles, con procedencia y advertencias. No inferir alturas de banco, convenciones geométricas ni explosivos faltantes.
9. **Anexos y definiciones.** Métodos, definiciones de indicadores, supuestos disponibles, glosario de estados y trazabilidad de filtros y archivos de entrada.

## Criterios de diseño

- Estilo sobrio y técnico: tipografía consistente, espacios suficientes, tablas alineadas por unidad y pocos colores con significado estable.
- Estado mediante texto y símbolo además de color; distinguir **sin evaluar** de **no cumple** cuando la fuente permita calcularlo sin reinterpretar resultados.
- Gráficos con título, unidad, leyenda, alcance y breve explicación del denominador. El puntaje ponderado no sustituye el estado del perfil ni el logro de diseño.
- Jerarquía constante: primero qué ocurrió y dónde; después criterio y evidencia. Mantener las advertencias junto al resultado afectado.
- En Word, evitar encabezados huérfanos, repetir encabezados de tablas y mantener juntos los elementos de cada perfil cuando sea posible. Comprobar la paginación en un procesador de documentos, además de las pruebas estructurales.

## Ejemplo de lectura ejecutiva

> **Alcance:** [sectores y secciones] · [n] perfiles · [fecha] · [filtros aplicados]
>
> **Estado de perfiles:** CUMPLE [n] · FUERA DE TOLERANCIA [n] · NO CUMPLE [n] · SIN EVALUAR [n, si se puede determinar]
>
> **Puntaje ponderado:** [valor]/100, calculado sobre [denominador]. **Logro de diseño:** [valor o no disponible]. Son indicadores distintos del estado por perfil.
>
> **Prioridades de revisión:** [sección / banco / parámetro / diferencia / criterio]. **Advertencias:** [cobertura, datos ausentes o ambigüedades comprobadas].

## Comprobaciones antes de implementar y cerrar

1. Confirmar qué denominadores y estados pueden recuperarse del modelo actual; agregar trazabilidad solo cuando la fuente la aporte.
2. Diseñar primero el resumen y una página de detalle usando datos sintéticos, sin alterar las reglas de cálculo.
3. Generar Word y PDF de prueba y revisar visualmente páginas, tablas, perfiles, plano y leyendas. Mantener el formato A4 y dos perfiles por página elegido.
4. Repetir la revisión con una copia de datos reales cuando el usuario la adjunte; contrastar filtros, conteos, estados y exportaciones con la aplicación.

La primera implementación reorganiza y aclara la información disponible, sin cambiar criterios de cálculo. La presentación visual de Word y los resultados con datos reales aún deben verificarse; las ampliaciones que dependen de datos no disponibles no se consideran validadas.
