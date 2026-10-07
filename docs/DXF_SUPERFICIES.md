# Superficies DXF en diseño y topografía real

La interfaz web y el portable Windows pueden importar superficies DXF en ambos roles. También se pueden combinar un DXF de diseño con una topografía STL, o viceversa.

## Cómo cargar un archivo

1. Seleccionar el DXF en Diseño o Topografía.
2. Revisar las capas que contienen caras de superficie. Si hay varias, elegir explícitamente las que corresponden al terreno o al diseño.
3. Revisar las unidades. Si el archivo no las declara, seleccionarlas antes de confirmar. La interfaz muestra el factor de conversión a metros y la extensión XYZ seleccionada.
4. Confirmar la importación y revisar las advertencias. La superficie puede utilizarse en vista 3D, perfiles, conciliación, mapa de calor y exportaciones.

Cancelar la revisión o recibir un error no sustituye la superficie que estaba cargada. Las inspecciones pendientes caducan después de 15 minutos; si una inspección vence, debe seleccionarse nuevamente el archivo.

## Formatos de superficie admitidos

| Entidad del DXF | Compatibilidad |
|---|---|
| `3DFACE` | Triángulos y cuadriláteros planos |
| `POLYLINE` de tipo POLYFACE | Caras indexadas triangulares o cuadrilaterales planas |
| `MESH` | Caras triangulares y polígonos planos con triangulación validada |
| `INSERT` / `BLOCK` | Superficies anteriores con traslación, rotación, escala y bloques anidados |
| `MINSERT` | Instancias múltiples dentro de los límites de expansión |

Se admite una superficie abierta: no necesita representar un sólido cerrado. El importador conserva coordenadas de cálculo en doble precisión y no suaviza, rellena huecos ni simplifica la superficie analítica automáticamente.

Las caras duplicadas o degeneradas que se descarten quedan registradas en el informe. Los polígonos autointersectados o no planos se rechazan; en ese caso debe exportarse la superficie triangulada.

## Unidades y coordenadas

La interfaz permite confirmar metros, milímetros, centímetros, pies, pulgadas y pies topográficos US. El importador lee las unidades declaradas mediante `$INSUNITS`; su confirmación explícita determina la conversión a metros.

Diseño y topografía deben utilizar el mismo sistema de coordenadas: X Este, Y Norte y Z Elevación. La aplicación no infiere ni reproyecta el sistema de referencia. Si las extensiones horizontales no se cruzan, muestra una advertencia para revisar las capas y unidades.

El archivo original, las capas elegidas, las unidades y el informe se guardan en la base de datos. Al reconstruir la malla después de un reinicio o de vaciar la caché se reaplican esas opciones. Esto no incorpora una función nueva para abrir proyectos automáticamente en la interfaz.

## Casos que requieren otra exportación

- Un DXF con solo curvas de nivel, puntos, líneas o contornos no contiene caras de terreno. Debe exportarse una superficie triangulada desde el programa de origen.
- Objetos propietarios, entidades proxy, POLYMESH, sólidos y superficies CAD no tienen conversión automática en esta entrega.
- Las mallas con subdivisión/suavizado requieren exportar su superficie resultante, no su malla de control.
- Los bloques con recortes XCLIP, referencias cíclicas, definiciones faltantes o transformaciones no resueltas producen un diagnóstico en lugar de una geometría aproximada.

La compatibilidad se define por las entidades presentes, no por el nombre del programa exportador. Aún debe verificarse el flujo concreto del usuario con un archivo real de diseño y otro de topografía.

## Límites y compatibilidad anterior

El límite STL se amplió a 250 MiB (262.144.000 bytes) el 3 de octubre, por petición del usuario para cargar una superficie de 220 MB. La API utiliza el límite HTTP configurado, por defecto 500 MiB. El portable actualizado se identifica con el sufijo `dxf-stl250`; las versiones anteriores conservan 200 MiB. No se habilitan archivos de 800 MB.

La expansión DXF está acotada a 16 niveles de bloques y 2 millones de entidades/caras de origen. Una carga puede alcanzar esos límites aunque el archivo sea pequeño, por ejemplo si contiene muchas instancias de un bloque. Los archivos temporales de revisión también tienen límites de concurrencia y espacio.

Las llamadas anteriores a `load_mesh(filepath)` y a `/meshes/upload` mantienen la interpretación de coordenadas sin conversión de unidades implícita. El nuevo flujo de la interfaz utiliza inspección y confirmación explícitas.

## Validación

Las pruebas cubren capas, unidades, bloques, caras inválidas, aislamiento de sesiones, recuperación de opciones y equivalencia con STL. La integración comprueba perfiles y parámetros con una tolerancia de 1e-6 m en ejemplos sintéticos exactamente representables, además de mapa de calor y exportaciones Excel, Word, PDF y DXF.

Las pruebas con superficies sintéticas no certifican todavía el contenido de los archivos reales del usuario ni el rendimiento con sus tamaños de trabajo.
