# Plan de soporte DXF para diseño y topografía real

Fecha: 2026-10-03. Estado: primera implementación en validación. Guía de uso: [superficies DXF](../DXF_SUPERFICIES.md). Pendiente comprobar archivos reales del usuario.

## Objetivo

Cargar superficies DXF en ambos espacios de la aplicación —Diseño y Topografía real— y utilizarlas en vista 3D, cortes, extracción de bancos, conciliación, mapa de calor y exportaciones. También debe funcionar mezclar DXF con STL, OBJ o PLY.

La primera entrega se centrará en superficies con caras explícitas. La reconstrucción de terreno desde curvas de nivel o puntos requiere otro alcance, porque implica decidir una triangulación nueva y puede modificar la geometría de comparación.

## Situación verificada

- `web/src/components/mesh/MeshUpload.tsx` ya admite `.dxf` en ambos espacios.
- `api/routers/meshes.py` utiliza el mismo cargador para diseño y topografía.
- `core/mesh_handler.py::_load_dxf` solo extrae `3DFACE` directamente de modelspace. Divide cuadriláteros y combina vértices; no interpreta otras representaciones de superficie, bloques ni selección de capas.
- Existen tres pruebas básicas de carga DXF en `tests/test_mesh_handler.py`; falta validar el circuito completo de importación y procesamiento para ambos roles.
- La base de datos conserva el archivo original y lo vuelve a interpretar al reconstruir la malla. Las futuras opciones de importación deberán persistirse y reaplicarse también en esas rutas.
- `ezdxf` ya es una dependencia y está incluida en el empaquetado portable.
- El límite específico de STL es 200 MiB; el límite HTTP configurado es 500 MiB. DXF actualmente pasa por el segundo. Este trabajo no aumentará ni unificará esos límites y no incluye archivos de 800 MB.

## Alcance de compatibilidad

| Contenido DXF | Primera entrega propuesta |
|---|---|
| `3DFACE`, triangular o cuadrilateral | Mantener y reforzar la lectura existente |
| `POLYLINE` de tipo POLYFACE | Incorporar caras y sus índices |
| `MESH` | Incorporar vértices y caras; triangulación validada |
| Las superficies anteriores dentro de `INSERT`/`BLOCK` | Aplicar transformaciones y resolver bloques anidados con límites de expansión |
| Capas con varias superficies | Permitir escoger las capas destinadas al rol seleccionado |
| Líneas, textos, cotas y curvas de nivel | Informar su presencia; no convertirlos automáticamente en una superficie |
| POLYMESH, sólidos, superficies propietarias/proxy o referencias externas | Detectar cuando sea posible y dar un diagnóstico; compatibilidad adicional según los archivos reales |

El soporte se declarará por entidades verificadas, no por el nombre del programa exportador. Si un archivo solo contiene un objeto de superficie propietario, se indicará que debe exportarse con caras o malla compatibles.

## Flujo previsto para el usuario

1. Elegir un DXF en Diseño o Topografía real.
2. Mostrar un resumen: capas con superficies, tipos de entidad, caras, extensión XYZ y unidades declaradas.
3. Seleccionar las capas y revisar las unidades. Una capa compatible podrá venir preseleccionada; varias capas requerirán elección explícita.
4. Mostrar la superficie seleccionada y confirmar la importación. Si las unidades no están declaradas, pedir su definición; si requieren conversión, mostrar el factor antes de aplicarlo.
5. Presentar el resultado y advertencias de importación, y habilitar el procesamiento habitual.

Los errores deben explicar la causa: archivo sin caras, capa vacía, solo curvas, geometría inválida, transformación no soportada o archivo ilegible. Cancelar o fallar la nueva importación conservará la superficie anterior.

## Secuencia de implementación

### 1. Inventario y archivos de referencia

- Confirmar el programa y la opción de exportación utilizados para diseño y topografía. Esta información está pendiente de respuesta.
- Examinar un DXF representativo de cada rol cuando estén disponibles: versión, entidades, capas, bloques y unidades.
- Preparar ejemplos sintéticos pequeños para cada entidad admitida, más una superficie equivalente en STL.
- Documentar los casos compatibles y las instrucciones de exportación verificadas. No atribuir compatibilidad con un exportador antes de comprobar sus archivos.

Resultado: matriz de compatibilidad y ejemplos reproducibles para iniciar el desarrollo, incluso mientras se esperan archivos reales.

### 2. Lectura y validación en `core/`

- Separar inspección del documento, extracción de caras y construcción de la malla en un módulo de importación DXF.
- Conservar `load_mesh(filepath) -> trimesh.Trimesh` y la API estable de `core`; añadir una interfaz explícita para opciones y diagnóstico de importación sin cambiar llamadas existentes.
- Leer `3DFACE`, POLYFACE y `MESH`. Resolver bloques con ubicación, rotación, escala y sistema de coordenadas de la entidad; conservar la procedencia de cada superficie y la política de capa efectiva.
- Validar índices, coordenadas finitas, caras degeneradas y duplicadas. Definir y probar la triangulación de cuadriláteros y polígonos; rechazar casos ambiguos antes de producir caras incorrectas.
- Mantener coordenadas de cálculo en precisión doble. No desplazar a un origen local, suavizar, rellenar huecos ni simplificar automáticamente la superficie analítica.
- Admitir terrenos abiertos: no exigir que la malla sea un sólido cerrado.
- Registrar unidades declaradas, unidades confirmadas, factor aplicado, capas elegidas, entidades importadas/omitidas, advertencias y versión del importador.
- Detectar bloques cíclicos, expansión excesiva, referencias faltantes y recortes de bloque no resueltos. No admitir silenciosamente una superficie distinta de la representada en el dibujo.

Resultado: malla utilizable por el pipeline existente y un informe de importación comprobable.

### 3. API y persistencia

- Añadir un flujo DXF de inspección y confirmación, conservando los contratos de carga de otros formatos. La inspección no sustituirá la malla activa.
- Asociar el archivo temporal de inspección a su sesión; limpiar archivos al confirmar, cancelar o vencer el plazo de retención.
- Ejecutar lectura y construcción fuera del bucle asíncrono, con concurrencia acotada y límites de recursos definidos después de medir ejemplos reales. Evitar copias completas innecesarias durante la inspección.
- Guardar el original junto con las opciones y el informe de importación mediante una migración aditiva de SQLite.
- Reaplicar capas, unidades y transformaciones al recuperar una malla después de reiniciar o vaciar la caché. Revisar tanto `api/database.py` como los cargadores auxiliares del router.
- Mantener lectura de sesiones anteriores; no reinterpretarlas silenciosamente con nuevas opciones.
- Advertir si diseño y topografía presentan extensiones incompatibles. El usuario debe usar el mismo sistema de coordenadas; no se inferirá ni reproyectará un CRS automáticamente.

Resultado: importación consistente durante la sesión y después de reiniciar el portable.

### 4. Interfaz web

- Integrar el flujo en `MeshUpload.tsx` para ambos roles, con selección de capas y unidades, resumen y errores específicos.
- Ampliar tipos, hooks y metadatos de manera aditiva; incluir todos los textos nuevos en español e inglés.
- Mostrar advertencias relevantes para decidir la importación, sin presentar detalles internos innecesarios.
- Verificar cargas DXF/DXF, DXF/STL y STL/DXF, sustitución de superficies y cancelación.

Resultado: el usuario puede seleccionar qué superficie del DXF utilizar y comprobar su escala antes de procesar.

### 5. Validación y portable Windows

- Pruebas del importador: triángulos, cuadriláteros, POLYFACE, MESH, capas mezcladas, bloques anidados, transformaciones, unidades, coordenadas mineras grandes y archivos inválidos.
- Pruebas API para diseño y topografía, conservación de la malla anterior ante error, aislamiento de sesiones y recuperación tras reinicio/caché vacía.
- Pruebas de equivalencia: para la misma superficie con la misma triangulación en DXF y STL, comparar extensión, cortes y parámetros de bancos con tolerancias numéricas documentadas. Para ejemplos sintéticos exactamente representables, objetivo inicial de diferencia de coordenadas/perfiles ≤ 1e-6 m.
- Pruebas del pipeline: procesamiento de ambos roles, mapa de calor con sector y sin sector, y exportaciones Excel, Word, PDF y DXF sin regresiones.
- Comprobar TypeScript, ESLint y las pruebas frontend afectadas; si se modifica el dominio de perfiles, mantener su cobertura exigida del 100%.
- Medir tiempo de carga y memoria con los archivos representativos, dentro de los límites actuales; fijar objetivos de rendimiento a partir de esas mediciones.
- Construir el frontend con `VITE_PWA=false`, regenerar el sidecar PyInstaller y empaquetar un nuevo EXE portable. Probar el EXE final en una sesión aislada, sin servicios de desarrollo, incluida recuperación de la importación después de cerrar y abrir.

Resultado: portable verificable con soporte DXF documentado y evidencia de pruebas.

## Criterios para considerar terminada la primera entrega

- Los tipos de superficie declarados en la matriz se importan tanto como diseño como topografía.
- Las capas seleccionadas y la escala se conservan después de reiniciar.
- Los ejemplos equivalentes DXF/STL producen perfiles y resultados compatibles dentro de las tolerancias fijadas.
- El mapa de calor y las exportaciones funcionan con superficies DXF procesadas.
- Un archivo sin superficie compatible recibe un mensaje útil y conserva la carga anterior.
- Se valida al menos un archivo real de diseño y uno de topografía antes de declarar compatibilidad con el flujo de exportación del usuario. Sin ellos, la entrega solo podrá declararse validada con ejemplos sintéticos.
- El EXE final funciona de forma autónoma y los límites de carga actuales se mantienen.

## Referencias técnicas

Las alternativas de superficie se basan en la documentación oficial de [POLYFACE](https://ezdxf.readthedocs.io/en/stable/tutorials/polyface.html) y [MESH](https://ezdxf.readthedocs.io/en/stable/dxfentities/mesh.html). POLYFACE utiliza una estructura POLYLINE con caras; MESH puede incluir polígonos de más de cuatro vértices, por lo que requiere una política de triangulación comprobada.

La revisión de escala sigue la documentación de [unidades DXF](https://ezdxf.readthedocs.io/en/stable/concepts/units.html): las coordenadas dependen del contexto de unidades y los bloques pueden tener unidades propias. El manejo de bloques debe contemplar las limitaciones documentadas de [INSERT](https://ezdxf.readthedocs.io/en/stable/blocks/insert.html), incluidas inserciones múltiples y recortes XCLIP.
