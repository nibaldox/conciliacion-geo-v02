# Propuesta de rediseño UX — frontend web

Rama: `feat/ux-redesign` · Alcance: rediseño visual + flujo guiado.

## Diagnóstico del frontend actual

| # | Problema | Dónde |
|---|----------|-------|
| 1 | El panel lateral muestra 4 botones en grilla 2×2 (Superficies, Secciones, Parámetros, Procesar) sin orden visible ni estado; no se sabe qué está hecho ni qué sigue. | `LeftSidebar.tsx` |
| 2 | Las vistas de análisis (Perfiles, 3D, Resumen, Tronadura, Exportar) están al pie del panel lateral, compitiendo con los controles del proyecto; no indican si están disponibles. | `ViewsToolbar.tsx` |
| 3 | Los estados vacíos usan emojis, jerga ("Protocol Alpha/Omega") y solo dicen "vaya al panel lateral": no ofrecen una acción directa. | `App.tsx › WarningState` |
| 4 | La cabecera tiene un logotipo de texto "CG" y no refleja el estado del proyecto. | `Header.tsx` |
| 5 | Estética plana: encabezados en monoespaciada mayúscula, estilos en línea repetidos, poca jerarquía (sombras/radios), textos sin traducir ("Tabla Detallada de Comparación"). | `globals.css`, `App.tsx` |

## Propuesta

### A. Sistema visual (tokens)
- Escala de elevación (`--shadow-sm/md/lg`) y radios (`--radius-sm/md/lg`) consistentes.
- Superficies con más contraste entre niveles; acento azul acero conservado; colores de estado/datos intactos (no cambian semántica CUMPLE / FUERA / NO CUMPLE).
- Encabezados en sans-serif con peso, la monoespaciada solo para datos técnicos.
- Clases utilitarias `.ui-card`, `.ui-section-title`, `.ui-chip` para dejar de repetir estilos en línea.

### B. Flujo guiado en el panel lateral (stepper vertical)
Reemplaza la grilla 2×2 por un **stepper vertical de 4 pasos**:

1. **Superficies** — resumen: "Diseño ✓ · Topografía ✓"
2. **Secciones** — resumen: "12 secciones definidas"
3. **Parámetros** — resumen: "Tolerancias de referencia"
4. **Procesar** — resumen: "Listo para procesar" / "Análisis completo"

Cada paso muestra su estado (completado ✓, actual, bloqueado 🔒) y un resumen de una línea; solo uno se expande a la vez y, al completar uno, se abre automáticamente el siguiente pendiente.

### C. Barra de vistas superior
Las vistas pasan a **pestañas horizontales sobre el área de trabajo** (3D, Perfiles, Resumen, Tronadura, Exportar), en el orden natural del flujo, con estado bloqueado cuando faltan prerrequisitos y el atajo de teclado visible (1–5).

### D. Estados vacíos accionables
Nuevo componente `EmptyState` (icono SVG, título claro, descripción y **botón de acción**):
- Sin mallas → "Cargar superficies" (abre paso 1) + "Probar con datos demo".
- Sin secciones → "Definir secciones" (abre paso 2).
- Sin procesar → "Iniciar análisis" (abre paso 4).

### E. Cabecera
Marca gráfica SVG, nombre de la app y un **chip de estado del proyecto** (Sin datos / Superficies cargadas / Listo para procesar / Procesando / Análisis completo).

### F. Pulido de vistas
Encabezados de tarjeta unificados en Resumen y Exportar; todos los textos visibles en `es.json` y `en.json`.

### G. Paletas
- **Deep dark** (tema por defecto): casi negro con leve tinte azul (`#07090c` / `#0e1217`), bordes discretos, sombras profundas.
- **Claro suave**: gris perla en lugar de blanco puro (`#eceef1` / `#f6f7f9`), texto carbón (`#1f2933`), estados en pastel apagado.
- Contraste WCAG ≥ 4.5 para texto, ≥ 3 para texto atenuado.

### H. Guía minimalista (todas las pestañas)
1. **Un solo nivel de superficie por vista.** El contenido va sobre el fondo de la página; las tarjetas solo agrupan gráficos o tablas. Nada de tarjetas dentro de tarjetas. Bordes de 1 px sutiles y sin sombras, salvo en elementos flotantes.
2. **Tipografía.** Títulos de sección con `.ui-section-title` en formato de oración. Se eliminan las etiquetas en MAYÚSCULAS con `tracking-wider` y la monoespaciada en títulos (solo se mantiene en IDs y coordenadas). Las etiquetas pequeñas van en `text-xs text-text-muted`.
3. **El color solo comunica significado.** Los colores de estado aparecen únicamente en indicadores (punto, pill, número), nunca en fondos completos. No se usan hex fijos (`#10b981`, `#ef4444`, …), sino los tokens `--status-*` y `--color-*`.
4. **Menos texto.** Sin emojis ni iconos decorativos en títulos. Los párrafos explicativos pasan a un tooltip (ⓘ) o a un `<details>` "¿Cómo se calcula?".
5. **Ritmo.** `gap-6` entre secciones y `gap-3` dentro de cada una. Tablas sin cebra, con divisores finos, encabezados `text-xs text-text-muted` sin mayúsculas y números `tabular-nums` alineados a la derecha.
6. **Filtros.** Una sola barra compacta de selects. Los filtros avanzados van plegados, con un chip que muestra cuántos hay activos.
7. **Layouts estables.** Seleccionar algo nunca cambia la altura de otros bloques: se reserva el espacio (alturas fijas, "—" como marcador).
8. **Gráficos.** Fondo transparente, rejilla mínima, sin títulos internos que repitan el título de la sección y leyenda horizontal compacta.

### I. Detalle de perfil
- Gráfico a ancho completo con altura fija. El inspector de banco pasa a ser una **franja fija de altura constante** bajo el gráfico, dentro de la misma tarjeta (Banco · Altura · Ángulo · Berma · Estado, real vs diseño), con "—" cuando no hay banco seleccionado. Así seleccionar un banco no hace crecer nada.
- La planta en miniatura pasa a ser un panel lateral plegable de tamaño fijo (o un popover), sin estirar el gráfico.
- La cabecera de sección y los filtros se compactan en una sola fila.

### J. Resumen
- Encabezado con una sola línea de KPIs: score global grande + 3 contadores (Cumple / Fuera / No cumple) con punto de color, sin barras ni iconos. La explicación del score va en un tooltip.
- Filtros en una barra compacta.
- Desglose por parámetro: una tabla limpia con una mini barra de % cumple en línea. Se elimina el gráfico redundante o se deja plegado.
- Cumplimiento por sector y plano de cumplimiento en dos columnas en pantallas anchas.
- Histogramas agrupados en una sola sección "Distribución de desviaciones" con un selector (Altura / Ángulo / Cresta / Pata / Berma), en lugar de 5 cajas.

## Fuera de alcance
- Lógica de dominio, API y cálculos.
- Streamlit (`app.py`, `ui/`).
- Rediseño interno de `ProfileView`, `Mesh3DViewer` y gráficos Plotly.

## Plan de implementación (oleadas)
1. Tokens + primitivas (`EmptyState`, `StepperItem`) + claves i18n.
2. En paralelo: (a) stepper del panel lateral; (b) pestañas superiores, estados vacíos, cabecera y layout.
3. Verificación: `tsc`, lint, vitest, build y revisión visual con capturas.
