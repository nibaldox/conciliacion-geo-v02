# Revisión de tronadura: Streamlit frente a web

Fecha: 4 de noviembre de 2026. Alcance: inspección del código local de Streamlit, la web y sus rutas de API. No se modificaron las sesiones ni se ejecutaron ambos flujos completos con los mismos datos durante esta revisión. «Parcial» significa que existe una función relacionada, no que todos sus controles y resultados sean equivalentes.

## Hallazgos prioritarios

1. **Fecha de corte para la correlación — falta en web.** Streamlit ofrece fecha de levantamiento y advierte cuando no se usa; la pasa a la proyección para excluir pozos posteriores. La correlación web revisada no incluye esa fecha en su solicitud. Los filtros de fecha de la vista 3D no demuestran que se filtre también la correlación. Esto puede cambiar la población analizada y producir asociaciones temporales equivocadas. Referencias: `ui/modulo_tronadura/tabular.py:121`, `ui/tabs/blast_correlation/renderers.py:41`, `web/src/api/hooks.ts:740`, `api/routers/process.py:1152`.
2. **Asignación general de columnas — parcial.** Streamlit dispone de vista previa y mapeador para confirmar campos de origen; la web deja seleccionar inclinación y azimut y resuelve otras columnas mediante alias. Un nombre no reconocido puede dejar datos faltantes o impedir indicadores, aunque Streamlit permita mapearlo. Referencias: `ui/modulo_tronadura/column_mapper.py:190`, `ui/modulo_tronadura/upload.py:118`, `web/src/components/results/BlastUploader.tsx:318`, `api/routers/blast.py:303`.
3. **Datos de perforación y cumplimiento de diseño — faltan en el flujo web revisado.** Streamlit acepta archivos adicionales de diseño de perforación y del equipo de perforación, enriquece dureza y muestra cumplimiento por malla. El cargador web revisado recibe un CSV principal y no presenta ese flujo. Referencias: `ui/modulo_tronadura/upload.py:88`, `ui/modulo_tronadura/upload.py:532`, `ui/modulo_tronadura/enrichment.py:53`, `web/src/components/results/BlastUploader.tsx:248`.

## Matriz funcional

| Área | Streamlit | Web local | Estado |
|---|---|---|---|
| Formato de pozos | CSV, XLSX y XLS | CSV | Parcial: Excel requiere conversión para la web. |
| Configuración geométrica | Convenciones de inclinación, signo, azimut, unidades y confirmación. | Contrato geométrico con convenciones y confirmación, más estimación opcional de cota sobre diseño con confirmación espacial. | Ambas; los flujos y fuentes de cota no son idénticos. |
| Diagnóstico de carga | Filas recibidas/aceptadas/rechazadas, avisos y procedencia. | Resumen, rechazos, avisos, configuración y diagnóstico espacial. | Ambas, con presentación distinta. |
| Filtros de pozos en 3D | Malla, polígono, banco, fase, longitud y carga. | Esos filtros en el visor principal, más identificación, estado, fecha/evento y relación con sección. | Cubiertos en el visor principal; no implica filtrar todos los análisis. |
| Paletas y colores 3D | Atributos, categorías y escalas Plotly. | Selección de variable/categoría, 19 escalas y leyenda en el visor principal. | Parcial: validar visualmente con datos reales y valores faltantes. |
| Pozos, superficies y perfiles | Pozos y trayectorias con capas de malla; proyección en secciones. | Capa de pozos sobre el visor principal y proyecciones/cruces en perfiles; visor independiente bajo demanda. | Ambas, con diferencias de representación e interacción. |
| Campo energético IDW y halos de factor de carga | Capas 3D y vista 2D de halos, según datos; descarga de grilla IDW. | No se encontró equivalente de esas capas ni de esa descarga en el visor revisado. | Falta. No confundir con el simulador energético de vóxeles. |
| Tabla detallada de pozos filtrados | Tabla de datos procesados y calidad de explosivos. | Conteos y detalle de pozo seleccionado en 3D; no se encontró tabla completa equivalente con los mismos filtros. | Parcial. |
| Correlación geotécnica | Análisis por sección, banco y malla/polígono; filtros espaciales y temporales. | Tabla por sección y panel PF/daño; no se encontraron las vistas equivalentes por banco y malla/polígono ni el corte temporal. | Parcial. |
| Modelos y análisis complementarios | Recomendación de carga, modelo multivariado, predictor de back-break, pasadura/piso, stemming/cresta, atribución y temporal/pre-post. | Dispersión PF–sobreexcavación y ajuste OLS; no se encontraron interfaces equivalentes para los demás análisis enumerados. | Parcial. La existencia de funciones en `core` no equivale a una interfaz disponible. |
| Simulador energético 3D | Configuración del dominio, modos físicos, cortes, perfiles y procedencia. | Editor, ejecución, resultados, cortes, perfiles y procedencia. | Ambas; paridad detallada de parámetros y resultados pendiente de prueba comparativa. |
| Exportación específica | Descarga de grilla IDW si fue calculada. | API de simulación con exportación, pero no se encontró botón correspondiente en el panel revisado; exportaciones generales de conciliación aparte. | Parcial; verificar UX y contenido final por formato. |

## Cálculos y cautelas

Ambos flujos llaman al procesador de pozos y al motor de correlación compartidos en `core`; en esta inspección no se comprobó una diferencia de fórmula para PF o Voronoi. Eso no garantiza resultados idénticos: la asignación de columnas, las convenciones, los filtros, la altura y la fecha de corte pueden cambiar las entradas. La cota obtenida desde la superficie de diseño en la web es una estimación, no una medición real; no extrapola fuera de la malla ni resuelve puntos ambiguos. Las convenciones y el marco espacial del archivo real siguen pendientes de confirmación operacional.

## Orden recomendado

1. Fecha de levantamiento y filtro temporal coherente en correlaciones, con tratamiento explícito de fechas ausentes y aviso cuando no se aplique.
2. Mapeador general y vista previa de columnas; soporte Excel o conversión clara.
3. Importación opcional de diseño de perforación y reporte rig, con procedencia y cumplimiento de diseño.
4. Análisis por banco y malla/polígono, tabla de pozos y filtros coherentes entre vistas.
5. Capas IDW/halos y descarga, seguidas de modelos complementarios y análisis temporales, con advertencias sobre alcance y calibración.
6. Comparación de simulador y resultados con un mismo conjunto de datos y validación visual de la vista 3D con los 20.939 pozos.
