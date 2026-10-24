# Plan — Informes exportados (Word y PDF): coherencia, contenido, legibilidad y tronadura

Fecha: 18 de octubre de 2026. Base: `73e443c` (main limpio). Usuario aprobó paquetes **A, B, C, D, E, F, G** y la decisión de criterio: **un perfil cumple según el peor estado de sus bancos (igual que el dashboard web); el puntaje ponderado se muestra aparte como dato**.

Actualización del 24 de octubre de 2026: el usuario autorizó consolidar y publicar todos los cambios existentes en GitHub. Esta autorización sustituye la restricción histórica de no hacer push, pero no amplía el alcance de implementación ni da por cerrada la validación visual y de rendimiento de V; estado y verificaciones actuales en `docs/HANDOFF.md`.

Evidencia de partida: `data/report-review/` (Word 17 pp. / 3,4 MB / 6 s y PDF 3 pp. generados de la sesión real del usuario `2db4a029…`, 109 comparaciones). Inventario de código: filtros sector/sección/nivel no enviados ni aplicados; `plot_options`/`df_pozos` ignorados; plano con `score>=70`; conteos Word/PDF distintos; `design_achievement` ausente; duplicación de donuts/profundidad/breakdown; plots a 200 dpi.

## 1. Alcance y restricciones

- Ruta **web** (`/api/v1/export/word` y `/export/pdf`). Streamlit (`app.py`, `ui/`) queda fuera: sus funciones `generate_word_report`, `generate_pdf_report`, `generate_section_images_zip` y `create_*` **no se modifican** y sus tests deben seguir verdes. Los nuevos módulos pueden importar helpers existentes, pero no cambiar su comportamiento.
- Sin dependencias nuevas, sin cambios de cálculos científicos (`core/section_cutter.py`, extracción, `compute_section_scores`, `design_achievement`), sin push. Español en todo el texto del informe; términos técnicos consistentes ("as-built" → "real/topografía" salvo nombre propio).
- Criterio de perfil = peor estado de banco con la misma semántica del dashboard (`web/src/components/results/ProfileView/domain/status.ts`: `parseBenchStatus`, `worstOfThree`, severidad UNKNOWN<CUMPLE<FUERA<NO_CUMPLE; `mapping.ts::toComparisonBenchStatuses` filtra `type ∈ {MATCH, MISSING, EXTRA}`). Desglose por parámetro = `Dashboard.tsx::computeParameterBreakdown` (ignora estado vacío o `-`; FUERA y NO CUMPLE se agrupan como no cumple). Puntaje ponderado = `compute_section_scores` existente.

## 2. Contrato central (F) — `core/report_data.py`

```python
@dataclass(frozen=True)
class ReportFilters:  # vacío = todos
    sectors: tuple[str, ...]; sections: tuple[str, ...]; levels: tuple[str, ...]; benches: tuple[int, ...]

def filter_comparisons(rows, filters) -> list[dict]  # misma semántica que web resultFilters.filterResults

@dataclass(frozen=True)
class BenchRow:
    section: str; sector: str; level: str; bench_num: int | None; type: str  # MATCH|MISSING|EXTRA
    height_design/real/dev, angle_design/real/dev, berm_design/real/dev: float | None
    height_status/angle_status/berm_status: str | None      # texto backend original
    spill_width: float | None; effective_berm: float | None
    worst_status: str            # CUMPLE|FUERA|NO_CUMPLE|UNKNOWN (worstOfThree)
    status_label: str            # etiqueta legible en español: CUMPLE, FUERA DE TOLERANCIA, NO CUMPLE, NO CONSTRUIDO, BANCO ADICIONAL, SIN EVALUAR

@dataclass(frozen=True)
class ProfileSummary: section, sector, worst_status, weighted_score (float|None), n_match, n_missing, n_extra
@dataclass(frozen=True)
class ParameterSummary: parameter ('height'|'angle'|'berm'), label, unit, cumple, no_cumple, pct_cumple, mean_real
@dataclass(frozen=True)
class ReportData:
    meta: dict             # project, author, operation, phase, generated_at, design/topo filenames, process settings (spacing, etc.)
    tolerances: dict       # las tolerancias efectivas de la sesión (con signo neg/pos donde existan)
    filters: ReportFilters
    rows: tuple[BenchRow, ...]
    profiles: tuple[ProfileSummary, ...]
    profile_counts: dict   # {'CUMPLE','FUERA','NO_CUMPLE'}
    global_weighted_score: float | None
    parameters: tuple[ParameterSummary, ...]
    design_achievement: dict | None   # global + por sector, desde core.design_achievement
    top_deviations: tuple[dict, ...]  # mayores |desv| relativas a la tolerancia aplicable, con estado real
    depth: dict | None                # None ⇒ la sección no se imprime
    counts: dict                      # n_rows, n_match, n_missing, n_extra, n_sections
    section_geometry: tuple           # passthrough de `all_data` que ya arma export.py (para perfiles)
    plan_inputs: dict | None          # comparaciones + secciones + malla topo para el plano
    blast: dict | None                # pozos (settings['blast_holes']) + tolerancia, o None
    conclusions: tuple[str, ...]      # reglas deterministas en español
    warnings: tuple[str, ...]

def build_report_data(comparisons, settings, filters, meta, section_geometry=None, plan_inputs=None, blast=None) -> ReportData
```

Paridad web↔Python: fixture compartido `tests/fixtures/report_parity.json` (filas MATCH/MISSING/EXTRA, estados mixtos, sectores, niveles) con valores esperados; test Python y test Vitest (`web/src/components/results/__tests__/reportParity.test.ts`) verifican **los mismos números** con las funciones reales del dashboard.

## 3. Entregas

| ID | Paquete | Archivos propios | Depende |
|---|---|---|---|
| **T1** | F + A (semántica) | NUEVO `core/report_data.py`, `tests/test_report_data.py`, `tests/fixtures/report_parity.json`, `web/src/components/results/__tests__/reportParity.test.ts` | — |
| **T5** | F + C + E (gráficos) | NUEVO `core/report_charts.py`, `tests/test_report_charts.py` | contrato §2 |
| **T2** | A + G (API/web) | `api/schemas.py` (ExportFilters: sectors/sections/levels), `api/routers/export.py` (rutas word/pdf: construir `ReportData`, aplicar todos los filtros, pasar `blast_holes` y `plot_options`, cabecera de filtros aplicados, nombres de archivo), `web/src/components/export/ExportPanel.tsx`, `web/src/api/hooks.ts`, tests `tests/test_export_with_filters.py` (+casos) y tests web del panel | T1 |
| **T3** | B + C + D + G (Word) | NUEVO `core/web_word_report.py` (`build_word_report(data: ReportData) -> BytesIO`), `tests/test_web_word_report.py`; puede AÑADIR helpers nuevos al final de `core/word_report_layout.py` sin cambiar los existentes | T1, T5 |
| **T4** | B + D (PDF) | NUEVO `core/web_pdf_report.py` (`build_pdf_report(data: ReportData) -> BytesIO`), `tests/test_web_pdf_report.py` | T1, T5 |
| **V** | cierre | coordinador | todo |

### T1 — Modelo de datos y paridad
RED primero con el fixture. Puerto exacto de `parseBenchStatus/worstOfThree/computeProfileStatuses/computeProfileComplianceCounts/computeParameterBreakdown` y de `filterResults`. `status_label` en español sin "✗ 0" para filas sin medición. Conclusiones deterministas (p. ej. % perfiles NO CUMPLE, parámetro con menor % de cumplimiento, sector con menor logro de diseño, nº de bancos no construidos/adicionales). Top desviaciones relativas a la tolerancia efectiva (no umbral fijo de 1,0 m). Profundidad: reutilizar la lógica existente; `None` si no hay datos.

### T5 — Gráficos comunes
Funciones puras que devuelven PNG en memoria con DPI configurable (por defecto 130 para perfiles, 150 para plano/donuts) y tamaño controlado: donuts por parámetro (valores coherentes con `ParameterSummary`, sin redondeos contradictorios), plano con estado por **peor banco** y etiquetas de sección legibles + leyenda en español, perfil de sección grande (C): diseño, topografía y conciliado; banda de tolerancia en cotas de banco cuando aplique; desviaciones anotadas por banco; título "Sección S-01 · Sector X · Estado"; rango vertical ajustado a los datos; opción de pozos de tronadura (G) cuando `blast` existe. Reutilizar `create_section_plot`/`create_plan_view_image` solo si sirven sin modificarlos; si no, implementar en el módulo nuevo.

### T2 — Filtros, tronadura y cableado
`ExportFilters` acepta `sectors/sections/levels/selectedBenchNumbers` (alias camelCase). `ExportPanel` envía los filtros de sesión completos (no solo banco) y las opciones de gráfico; `hooks.ts` usa el nombre de archivo del `Content-Disposition` y expone `X-Export-Filters-Applied` (mostrar un aviso breve en el panel si hubo filtros). Word y PDF de la web pasan a `build_word_report/build_pdf_report(ReportData)`; Excel/DXF/imágenes no cambian. Pozos desde `settings['blast_holes']`; tolerancia desde filtros. Tests: filtros por cada dimensión, combinación, vacío = todo, cabecera, compatibilidad de la query actual.

### T3 — Informe Word
Orden: portada (proyecto, operación, fase, autor, fecha, bloque de revisión/aprobación) → índice (campo TOC) → 1 Resumen ejecutivo (estado de perfiles por peor banco, puntaje ponderado como dato, logro de diseño global, conclusiones) → 2 Parámetros y criterios (tolerancias con signo, espaciado, filtros aplicados, archivos/fechas) → 3 Cumplimiento por parámetro (tabla + donuts) → 4 Logro de diseño por sector → 5 Plano de cumplimiento (con título) → 6 Tabla por perfil (estado legible, desviaciones con signo, derrame y berma efectiva; columnas sin datos omitidas, p. ej. "Cota Piso" si todo es N/A) → 7 Detalle por sección: 1 perfil por página para perfiles no conformes y anexo compacto (2 por página) con el resto → 8 Tronadura (solo si hay pozos; reutiliza la semántica del bloque existente) → secciones sin datos omitidas con nota. Decimales y unidades uniformes, español, colores accesibles (texto oscuro sobre fondo de estado).
**Meta de tamaño/tiempo** con la sesión real de 109 filas: < 1,5 MB y < 6 s (medir y reportar).

### T4 — PDF ejecutivo
Mismo modelo y mismos números que el Word. A4 vertical: portada, resumen ejecutivo con conclusiones, criterios, cumplimiento por parámetro, logro por sector, top desviaciones relativas a tolerancia con encabezados completos ("Desviación (m)"), plano, resumen de tronadura si existe. Encabezado (proyecto) y pie "Página X de Y" en todas las páginas salvo portada. Ocultar secciones sin datos.

## 4. Orden y paralelismo

| Tanda | Entregas | Regla |
|---|---|---|
| 1 | T1 ∥ T5 | Contrato §2 congelado; archivos nuevos disjuntos |
| 2 | T2 ∥ T3 ∥ T4 | Consumen T1/T5; archivos disjuntos |
| 3 | V | Sin escritores |

## 5. Verificación (V)

- Suites: Python completa (base 2539/12), frontend `test:coverage` (base 739/81, dominio 100%), `tsc -b`, lint, build.
- Tests de Streamlit de informes (`test_report_generator.py`, `test_word_report_*.py`, `test_export_*`) siguen verdes sin modificar.
- Generar Word y PDF desde la sesión real del usuario (`data/manual-20261018`, 109 filas) y desde la sesión de 449 filas (`data/qa-real-file/runtime-r2`) con y sin filtros (sector/sección/nivel/banco); convertir a imágenes y revisión visual del coordinador; comprobar que los números coinciden con el dashboard para los mismos filtros (perfiles por estado, desglose por parámetro, logro de diseño).
- Tronadura: generar con pozos sintéticos o un CSV de ejemplo existente del repo, declarado como tal.
- Dos revisores de solo lectura (especificación y calidad). Actualizar HANDOFF. Commit solo si el usuario lo pide.
