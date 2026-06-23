# UI Parity Audit: Streamlit vs Web

> Auditoría de paridad de features entre la UI Streamlit (`app.py` + `ui/`, legacy, off‑limits) y la web React/Vite (`web/`, en construcción activa).
> Fecha: 2026‑06‑22. Solo lectura: no se modificó código.

## Resumen ejecutivo

La web cubre **el flujo principal end‑to‑end** (carga de mallas → definición de secciones → procesamiento → visualización de perfil, dashboard, tabla y exportación) con una arquitectura de calidad claramente superior al Streamlit (ProfileView con arquitectura hexagonal `domain/application/presentation/infrastructure`, Zustand, TanStack Query, i18n, modo demo sin backend). Sin embargo **la capa de visualización del perfil es notoriamente más pobre** que la de Streamlit: faltan capas enteras (áreas de derrame, áreas por sector con sobre‑excavación/deuda, pozos de tronadura proyectados, anotaciones de pata, indicadores de ancho de berma y análisis de estabilidad FS) y, lo más grave, **el gráfico web nunca dibuja la polilínea `reconciled_design`** y **construye el perfil reconciliado con `build_reconciled_profile_v2`** mientras Streamlit usa la función legada. Estas dos diferencias explican directamente la divergencia que reportó el usuario. El próximo sprint debería enfocarse exclusivamente en cerrar los gaps P0 del área Profile (estimado 24–32 h) antes de seguir agregando features nuevas.

**Conteos aproximados (LOC):**
- Streamlit auditado: `app.py` 86 + `ui/modulo_conciliacion.py` 58 + `ui/step1..4` 961 + `ui/tabs/*` 2 890 + `ui/{sidebar,ref_lines,plots,labels}.py` 374 + `ui/modulo_tronadura.py` (~1 300 no leído en detalle) ≈ **5 670 LOC**.
- Web auditado: `App.tsx` 281 + `api/hooks.ts` 484 + `stores/session.ts` 213 + `components/results/ProfileView/**` ~1 600 + `components/{mesh,sections,analysis,results,export,layout}/**` ~3 800 ≈ **6 400 LOC**.

---

## Mapa de features por área

Leyenda de Status: **OK** = paridad funcional razonable · **PARCIAL** = existe pero le faltan piezas · **NO** = no existe en web · **DIV** = existe pero con divergencia funcional.

### 1. Upload (step1)

| Feature Streamlit | Streamlit file | Web equivalent | Web file | Status | Notas |
|---|---|---|---|---|---|
| Carga Diseño (STL/OBJ/PLY/DXF) | `ui/step1_upload.py:32-39` | `DropZone type="design"` | `web/src/components/mesh/MeshUpload.tsx:21-218` | OK | Web usa drag&drop + click; mismas extensiones. |
| Carga Topografía | `ui/step1_upload.py:36-39` | `DropZone type="topo"` | `MeshUpload.tsx` | OK | idem. |
| Botón "Limpiar superficies" | `ui/step1_upload.py:45-57` | Botón "delete" por zona | `MeshUpload.tsx:76-81,145-153` | OK | Web elimina por malla; Streamlit limpia ambas. |
| Info de malla (caras, vértices, bounds) | `ui/step1_upload.py:91-108` | `meshInfo` summary (n_vertices, n_faces, extensión) | `MeshUpload.tsx:122-135` | OK | |
| Decimación previa para visualización | `ui/step1_upload.py:135-136` (`_cached_decimate`) | No (el viewer usa vertices directamente) | — | PARCIAL | La web pide `useMeshVertices(step=150000)` (`hooks.ts:85-100`) — sampling en servidor. No hay decimación de visualización client‑side. |
| Vista 3D (Plotly) de ambas superficies | `ui/step1_upload.py:155-199` | `Mesh3DViewer` (three.js) | `web/src/components/mesh/Mesh3DViewer.tsx:385-501` | DIV | Ver detalle abajo. |
| Vista en planta con curvas de nivel | `ui/step1_upload.py:202-285` | `ContourChart` (Chart.js) | `web/src/components/mesh/ContourChart.tsx:47-255` | DIV | Ver detalle abajo. |
| Control superficie a mostrar (Diseño/Topo/Ambas) | `ui/step1_upload.py:274-275` | Solo capa de diseño (`useMeshContours(designMeshId)`) | `ContourChart.tsx:48` | PARCIAL | Web solo dibuja curvas del diseño. No hay "Topo/Ambas". |
| Intervalo de curvas configurable | `ui/step1_upload.py:277-278` | `interval` fijo a 15.0 | `hooks.ts:110-116`, `ContourChart.tsx:49` | PARCIAL | Web recibe `interval=15` por defecto, no expone UI. |
| Resolución de grilla | `ui/step1_upload.py:279-280` | No | — | NO | |
| Cargar líneas de referencia (mallas, CSV) | `ui/ref_lines.py:25-91`, `app.py:66-67` | No | — | NO | Ver P2‑03. |
| Botón "Try demo" | (no existe) | `TryDemoButton` | `web/src/components/demo/TryDemoButton.tsx` | OK (extra) | Exclusivo web. Streamlit no tiene demo. |

**Vista 3D — divergencia (Mesh3DViewer.tsx vs step1_upload `_render_3d_view`)**: Streamlit dibuja **dos mallas trianguladas** (Diseño azul + Topografía verde) con `mesh_to_plotly`. La web dibuja **la topografía como sólido** (si hay caras) o nube de puntos, y el diseño como **líneas de curvas/breaklines** (`useMeshBreaklines`), no como malla. Las secciones se "drapean" sampleando la elevación de la topografía (`Mesh3DViewer.tsx:194-252`), mientras que en Streamlit son líneas planas a `zref`. La web además permite **hacer clic en curvas para colocar secciones** (`mapClickHandler`, `SectionCurveForm`) — un feature que Streamlit no tiene.

**Vista curvas de nivel — divergencia (ContourChart.tsx vs `_render_contour_view`)**: Streamlit usa `go.Contour` con interpolación `scipy.griddata` sobre los vértices. La web pide al backend `GET /meshes/{id}/contours` (curvas precomputadas) y las dibuja con Chart.js. Web **no permite elegir Topo/Ambas ni ajustar intervalo en vivo**.

### 2. Sections (step2)

| Feature Streamlit | Streamlit file | Web equivalent | Web file | Status | Notas |
|---|---|---|---|---|---|
| Pestaña "Archivo" (CSV/DXF) | `ui/step2_sections.py:62-134` | `SectionFileUpload` | `web/src/components/sections/SectionFileUpload.tsx:10-226` | OK | Mismos params (spacing, len_up/down, sector, az_mode). Web: `POST /sections/from-file`. |
| Pestaña "Interactivo (clic en planta)" | `ui/step2_sections.py:208-293` | Clic en curva breakline en vista 3D | `web/src/components/sections/SectionCurveForm.tsx` | DIV | Mecánica distinta: Streamlit usa `st.plotly_chart(on_select)`, la web usa clic en curvas de breakline del diseño 3D. Ambos producen secciones con azimut local. |
| Pestaña "Manual" (form N secciones) | `ui/step2_sections.py:300-342` | Edición inline por fila | `web/src/components/sections/SectionList.tsx:45-77` | PARCIAL | Web no tiene wizard "N secciones de una"; en su lugar edita/crea vía `SectionList` + `SectionSelector`. |
| Pestaña "Automático" (equispaciadas sobre cresta) | `ui/step2_sections.py:349-395` | `useAutoSections` (hook expuesto, sin UI dedicada) | `web/src/api/hooks.ts:152-159` | PARCIAL | El endpoint existe (`POST /sections/auto`) pero no se encontró formulario dedicado equivalente; la generación automática se hace vía clic en curva. |
| Tabla de secciones definidas | `ui/step2_sections.py:416-434` | `SectionList` (tabla editable) | `SectionList.tsx:133-374` | OK | Web permite editar inline; Streamlit no. |
| Botón "Limpiar pendientes"/"Limpiar todas" | `ui/step2_sections.py:423-433` | `useClearSections` + confirm | `SectionList.tsx:98-106,146-160` | OK | Web añade confirmación de 5 s con cancelación por inactividad/Esc. |
| Auto‑azimut por pendiente local (`compute_local_azimuth`) | `ui/step2_sections.py:30-31,259,324,389` | Server‑side en `/sections/click` y `/sections/auto` | `api/routers/sections.py` (vía `compute_local_azimuth`) | OK | |

### 3. Analysis (step3)

| Feature Streamlit | Streamlit file | Web equivalent | Web file | Status | Notas |
|---|---|---|---|---|---|
| Multiselect de secciones a procesar | `ui/step3_analysis.py:27-29` | Implícito (procesa todas las cargadas) | `web/src/components/analysis/ProcessButton.tsx:18-26` | PARCIAL | La web no deja elegir subconjunto; corre todo. |
| Botón "Ejecutar análisis" | `ui/step3_analysis.py:31-48` | `ProcessButton` | `web/src/components/analysis/ProcessButton.tsx:7-84` | OK | |
| Procesamiento paralelo + barra de progreso | `ui/step3_analysis.py:111-146` | `useProcessStatus` con `refetchInterval=1s` | `web/src/api/hooks.ts:235-244`, `web/src/components/analysis/ProcessProgress.tsx` | OK | Web polling server‑side status. |
| Métricas resumen (procesadas, bancos, evaluaciones, cumplimiento) | `ui/step3_analysis.py:159-180` | `Dashboard` KPIs | `web/src/components/results/Dashboard.tsx:57-96` | OK | |
| Precomputo de artefactos (area_fill, reconciled) en `session_state` | `ui/step3_analysis.py:51-87` | Server‑side en `/process` + cacheado en DB + query cache | `api/routers/process.py`, `useResults`, `useProfile` | DIV | **Clave**: Streamlit precalcula `reconciled_design`/`reconciled_topo` con **`build_reconciled_profile` (legacy, tuple)**; el API usa **`build_reconciled_profile_v2` (rich, con berm_top y face sampling)**. Geometrías diferentes. Ver §"Hallazgos". |
| Editor manual de bancos (drag crest/toe → recalc) | (no existe) | `BenchEditor` + `PUT /process/results/{id}/reconciled` | `web/src/components/analysis/BenchEditor.tsx:51-259`, `api/routers/process.py:455-560` | OK (extra) | Exclusivo de la web. |

### 4. Results Dashboard

| Feature Streamlit | Streamlit file | Web equivalent | Web file | Status | Notas |
|---|---|---|---|---|---|
| Filtros Excel‑style (sector/nivel/sección/banco) | `ui/tabs/dashboard.py:18-39` | `useSession.filters` (sector/section/level) | `web/src/stores/session.ts:82-86,153`, `web/src/components/results/ResultsTable.tsx:42-57` | PARCIAL | La web expone 3 de los 4 filtros (falta `bench`) y solo aplican a `ResultsTable`, no al Dashboard (KPIs se computan sobre `useResults()` global). |
| KPIs por parámetro (H, Á, B) | `ui/tabs/dashboard.py:55-65` | `KPICard × 4` (Global, H, Á, B) | `Dashboard.tsx:57-179` | OK | Web añade "Cumplimiento Global". |
| Barras apiladas CUMPLE/FUERA/NO_CUMPLE | `ui/tabs/dashboard.py:68-92` | Barras horizontales con glow | `Dashboard.tsx:182-217` | PARCIAL | Web no apila los 3 estados; muestra solo el % acumulado. Streamlit separa CUMPLE/FUERA/NO_CUMPLE. |
| Histograma desviación altura + líneas de tolerancia | `ui/tabs/dashboard.py:99-106` | No | — | NO | |
| Histograma desviación ángulo + líneas de tolerancia | `ui/tabs/dashboard.py:108-115` | No | — | NO | |
| Histograma ancho berma + línea mínimo | `ui/tabs/dashboard.py:117-126` | No | — | NO | |

### 5. Profile View (focus area — diff con el usuario)

| Feature Streamlit | Streamlit file | Web equivalent | Web file | Status | Notas |
|---|---|---|---|---|---|
| Polilínea Diseño | `ui/tabs/profiles.py:138-141` | `buildPolyline(design)` | `ProfileChart.tsx:355-357,384-399` | OK | |
| Polilínea Topografía | `ui/tabs/profiles.py:170-173` | `buildPolyline(topo)` + `buildGroundFill` | `ProfileChart.tsx:360-368` | OK | Web añade relleno sutil "tozeroy" (no está en Streamlit). |
| **Perfil Conciliado Diseño (línea azul discontinua)** | `ui/tabs/profiles.py:175-181` (`reconciled_design` dashed royalblue) | **NO se renderiza** | `ProfileChart.tsx:370-376` | **NO / DIV** | **Bug P0**: el comentario del código dice literalmente `"no dashed reconciled design"`. El dato llega a `vm.lines` (`mapping.ts:62-63`) y el filtro `showReconciledDesign` está `true` por defecto (`filters.ts:38`), pero `buildTraces` no lo dibuja. |
| **Perfil Conciliado Topo (línea ámbar sólida)** | `ui/tabs/profiles.py:182-190` (`reconciled_topo` sólido #FF7F0E + berm labels) | `buildPolyline(reconciled_topo)` ámbar | `ProfileChart.tsx:371-376` | **DIV** | Se dibuja, pero **los datos vienen de `build_reconciled_profile_v2`** (API) vs legado en Streamlit → geometría diferente. Web no dibuja los indicadores de ancho de berma como `shape`. |
| Toggle "Mostrar perfil conciliado" | `ui/tabs/profiles.py:23-26` | `FilterBar` toggle "Reconciliado" | `FilterBar.tsx:36-69` | DIV | Web: un solo toggle controla ambos flags a la vez (`setReconciled` setea `showReconciledDesign` y `showReconciledTopo`), pero el chart ignora `showReconciledDesign`. |
| Toggle "Mostrar Áreas" (sobre‑excavación + deuda) | `ui/tabs/profiles.py:29-32` + `_add_area_traces` (316-333) | `FilterBar` toggle "Áreas" + `buildAreaFills` | `ProfileChart.tsx:345-351,424-503` | OK | Diferente implementación (web interpola manualmente, Streamlit usa `calculate_area_between_profiles`). |
| Toggle "Área de Derrame" | `ui/tabs/profiles.py:33-36` + `_add_spill_areas_traces` (623-656) | **Toggle existe** (`FilterBar.tsx:78-85`) **pero `ProfileChart.buildTraces` lo ignora** | `ProfileChart.tsx:336-382` | **NO / DIV** | **Bug P0**: `showSpillAreas` está `true` por defecto, el toggle se muestra, pero `buildTraces` nunca lee ese flag ni genera las trazas de derrame. El backend expone `spill_width/spill_start_*` en `benches_topo` (`api/schemas.py`) — los datos existen. |
| Toggle "Sectores coloreados por desviación" | `ui/tabs/profiles.py:37-40` + `_add_sector_areas_traces` (268-313) | No | — | NO | clasificación overbreak/underbreak/compliant/mixed con hover rico. |
| Toggle "Semáforo" | `ui/tabs/profiles.py:43-46` + `_add_semaphore_traces` (421-451) | `FilterBar` toggle "Semáforo" + `buildBenchMarkers` split por status | `ProfileChart.tsx:571-582` | OK | Implementación distinta: Streamlit colorea puntos de la polilínea topo; web colorea marcadores de banco. Aceptable. |
| Toggle "Mostrar Pozos de Tronadura" + tolerancia | `ui/tabs/profiles.py:49-59` + `_add_blast_holes` (536-620) | **Toggle + input existen** (`FilterBar.tsx:95-116`) **pero `ProfileChart.buildTraces` ignora `showBlastHoles` y `blastTolerance`** | `ProfileChart.tsx:336-382` | **NO / DIV** | **Bug P0**: ni siquiera hay referencia a esos campos en `ProfileChart.tsx` (verificado con grep). El backend NO expone pozos por perfil; habría que llamar a `proyectar_pozos_en_seccion` server‑side. |
| Anotaciones de banco (B1, B2… con flecha) | `ui/tabs/profiles.py:194-198` | `annotations` en layout | `ProfileChart.tsx:90-106` | OK | Solo cuando `showReconciledTopo`. |
| Anotaciones de pata (Pa1, Pa2…) | `ui/tabs/profiles.py:199-204` | No | — | NO | |
| Indicador de ancho de berma (línea discontinua + label "B2=17.3m") | `ui/tabs/profiles.py:465-519` (`_add_berm_width_indicators`) + labels vía `_add_reconciled_trace(..., show_berm_width=True)` | Solo label textual del ancho | `ProfileChart.tsx:108-120` | PARCIAL | Web no dibuja la `shape` (línea discontinua naranja) sobre la berma, solo el texto. |
| Hover rico en bancos (ΔCr/ΔPa coloreados, H.real, Cara, status icon) | `ui/tabs/profiles.py:402-418` | `customdata` + `hovertemplate` | `ProfileChart.tsx:526-567,597-607` | OK | Web con HTML span y colores. |
| Cross‑link chart ↔ tabla (hover/click) | (no existe) | `useCrossLinkState` + `BenchTable` | `ProfileView.tsx`, `BenchTable.tsx` | OK (extra) | Exclusivo web. |
| Grid vertical (altura banco) + cota de referencia | `ui/tabs/profiles.py:225-235` (`dtick=grid_height`, `tick0=grid_ref`) | No | — | NO | Web no dibuja grilla horizontal por banco. Estos valores (`grid_height`, `grid_ref`) vienen de `config` del sidebar Streamlit. |
| Select columnas en pantalla (1/2/3) | `ui/tabs/profiles.py:62-67` (grilla de varios perfiles) | `ProfilesGrid` (modo grilla) | `web/src/components/results/ProfileView/presentation/ProfilesGrid.tsx` | OK (extra) | Web usa vista grilla/detalle en vez de N columnas. |
| **Sugerencia de ángulo de cara (FS objetivo)** | `ui/tabs/profiles.py:116-130` (`suggest_face_angle_for_fs`) | No | — | NO | Análisis de estabilidad por sección. Falta toda la integración con `core.stability_analysis`. |
| Navegador anterior/siguiente sección | (no existe, scroll) | `SectionNavigator` overlay | `ProfileView.tsx:109`, `SectionNavigator.tsx` | OK (extra) | Exclusivo web. |
| Compliance summary card | (parcial, en dashboard) | `ComplianceSummary` | `ProfileView.tsx:129` | OK (extra) | Web muestra resumen debajo del gráfico. |

**Análisis de la divergencia reportada por el usuario (§5):**
La diferencia visual que ve el usuario entre Streamlit y web se explica por **tres causas independientes que se acumulan**:

1. **Falta la polilínea "Conciliado Diseño"** en la web (`ProfileChart.tsx:370-376`). Streamlit siempre la dibuja como línea azul discontinua; la web nunca. Es el gap más visible.
2. **Diferente geometría del "Conciliado Topo"** porque se calcula con funciones distintas: API usa `build_reconciled_profile_v2(benches, source="topo", profile=profile_t)` que inserta puntos `berm_top` y samplea la cara real (`api/routers/process.py:427-439`), mientras Streamlit usa `build_reconciled_profile(ep_t.benches)` legado que solo ordena crest/toe por distancia y dibuja caras rectas (`ui/step3_analysis.py:82`, `core/profile_compliance.py:97-115`). Resultado: misma sección, dos polilíneas reconciliadas distintas.
3. **Toggle "Derrame" y "Pozos" presentes pero no operativos** en la web: el usuario los activa y no pasa nada, lo que refuerza la percepción de "resultados diferentes".

### 6. Export

| Feature Streamlit | Streamlit file | Web equivalent | Web file | Status | Notas |
|---|---|---|---|---|---|
| Excel conciliación | `ui/tabs/export.py:79-111` | `useExportExcel` → `GET /export/excel` | `web/src/components/export/ExportPanel.tsx:114-120`, `api/routers/export.py` | OK | |
| ZIP de imágenes PNG por sección | `ui/tabs/export.py:118-195` | `useExportImages` → `GET /export/images` | `ExportPanel.tsx:135-141` | PARCIAL | La web no pasa `plot_options` desde filtros UI; el backend usa defaults. |
| Informe Word (.docx) | `ui/tabs/export.py:202-292` | `useExportWord` → `GET /export/word` | `ExportPanel.tsx:121-127` | PARCIAL | Mismo: no pasa `plot_options`/filtros. |
| DXF 3D de perfiles (con capas CUMPLE/NO_CUMPLE/FUERA_TOL) | `ui/tabs/export.py:300-359` | `useExportDxf` → `GET /export/dxf` | `ExportPanel.tsx:128-134` | PARCIAL | Web no pasa filtros. |
| Form info de proyecto (proyecto/operación/fase/autor) | `ui/sidebar.py:51-55`, `ui/tabs/export.py:89-95` | Form en `ExportPanel` | `ExportPanel.tsx:26-110` | OK | |
| Respeta filtros activos al exportar | `ui/tabs/export.py:51-72,127,213` (`_get_filtered_comparisons`) | No | — | NO | La web no pasa los filtros del `ResultsTable`/`Dashboard` al backend exportador. |

### 7. AI Report

| Feature Streamlit | Streamlit file | Web equivalent | Web file | Status | Notas |
|---|---|---|---|---|---|
| Selector provider (ollama/lmstudio/openai/openrouter/minimax/glm/grok) | `ui/tabs/ai_report.py:146-156` | Selector desde `/ai/providers` | `web/src/components/export/AIReporter.tsx:359-380` | OK | |
| Input modelo + default por provider | `ui/tabs/ai_report.py:157-160` | Input + `PROVIDER_DEFAULT_MODELS` | `AIReporter.tsx:52-60,382-403` | OK | |
| API key por provider (env o input) | `ui/tabs/ai_report.py:138-182` | Solo server‑side (no UI para key) | — | PARCIAL | Web no pide API key al usuario; asume backend configurado. |
| Avanzado: max_tokens, timeout, cache | `ui/tabs/ai_report.py:184-203` | No | — | NO | |
| Temperature slider | `ui/tabs/ai_report.py:161-163` | No | — | NO | |
| **Streaming** del informe en vivo | `ui/tabs/ai_report.py:433-460` (`stream_report`, async iterator) | **No**: `stream: false` hardcoded | `AIReporter.tsx:215` | DIV | Web hace POST una sola vez y muestra el resultado completo. Streamlit renderiza token a token. |
| Botón copiar + descargar .md | `ui/tabs/ai_report.py:103-135,420-430` | Botón copiar | `AIReporter.tsx:221-230,506-514` | PARCIAL | Web no tiene "descargar .md". |
| Resumen de uso (tokens in/out, tps, costo USD) | `ui/tabs/ai_report.py:65-100,454-459` | Tokens in/out/total + badge "estimado" | `AIReporter.tsx:542-567` | PARCIAL | Web no muestra tps ni costo USD. |
| Aplica filtros de Tabla al prompt | `ui/tabs/ai_report.py:212-246` | No | — | NO | |
| Enriquecimiento blast_trend metadata | `ui/tabs/ai_report.py:249-348` | No | — | NO | |
| Health check del backend IA | (no existe) | `useAIHealth` (cada 30s) + estados | `AIReporter.tsx:65-72,128-132,232-291` | OK (extra) | Exclusivo web. |
| Clasificación de errores (rate_limited/network/server) con countdown | (no existe) | Sí | `AIReporter.tsx:97-122,155-175,443-476` | OK (extra) | Exclusivo web. |

### 8. Blast correlation (Tronadura)

| Feature Streamlit | Streamlit file | Web equivalent | Web file | Status | Notas |
|---|---|---|---|---|---|
| Carga de archivo de pozos (CSV/XLSX) | `ui/modulo_tronadura.py` (~52 KB, no auditado en detalle) | No | — | NO | No hay uploader de pozos en la web. |
| Visualizador 3D de pozos | `ui/modulo_tronadura.py` | No | — | NO | |
| Tolerancia de proyección slider + filtro temporal por fecha | `ui/tabs/blast_correlation.py:69-92` | No | — | NO | |
| Tab "Análisis por Sección" (scatter PF vs sobre‑excavación + OLS trendline) | `ui/tabs/blast_correlation.py:186-244` | No | — | NO | |
| Tab "Análisis por Banco" (bar carga + scatter desv cresta + eje PF) | `ui/tabs/blast_correlation.py:246-336` | No | — | NO | |
| Tab "Análisis por Malla/Polígono" | `ui/tabs/blast_correlation.py:338-382` | No | — | NO | |
| Modelo OLS PF → Sobre‑excavación (β₁, p, R², IC95%, banda) | `ui/tabs/blast_correlation.py:686-808` | No | — | NO | |
| Recomendaciones de ajuste de PF (global + por sector) vía `core.blast_advisor` | `ui/tabs/blast_correlation.py:811-877` | No | — | NO | |
| Pasadura → daño del piso (Pearson r) | `ui/tabs/blast_correlation.py:880-919` | No | — | NO | |
| Densidad de energía IDW a lo largo del perfil | `ui/tabs/blast_correlation.py:922-1003` | No | — | NO | |
| Tendencia temporal mensual + outliers IQR + comparativa pre/post campaña | `ui/tabs/blast_correlation.py:1006-1088` | No | — | NO | |
| Overlay pozos en perfil (ver §5 "Pozos de Tronadura") | `ui/tabs/profiles.py:49-59,536-620` | Toggle existe pero no funcional | `ProfileChart.tsx` | NO/DIV | Ya contabilizado en §5. |

> El módulo completo de Tronadura en la web es **cero**: no hay ni carga de datos ni visualización ni correlación. Es el gap más grande en volumen.

---

## Gaps priorizados

| # | Priority | Effort | Gap | Where | Why it matters |
|---|---|---|---|---|---|
| G01 | P0 | 4 h | `ProfileChart` no dibuja `reconciled_design` | `web/src/components/results/ProfileView/presentation/ProfileChart.tsx:370-376` | Divergencia visual directa reportada por el usuario; el dato ya está en `vm.lines`. |
| G02 | P0 | 6 h | `ProfileChart` ignora `showSpillAreas` (toggle engañoso) | `ProfileChart.tsx:336-382`; datos en `benches_topo.spill_*` | Toggle activo por defecto que no produce nada. |
| G03 | P0 | 12 h | `ProfileChart` ignora `showBlastHoles`/`blastTolerance` (requiere endpoint) | `ProfileChart.tsx`; `api/routers/process.py` (nuevo endpoint) | Toggle engañoso + requiere exponer `proyectar_pozos_en_seccion` por API. |
| G04 | P0 | 4 h | Divergencia `build_reconciled_profile` (legado) vs `_v2` (API) | `ui/step3_analysis.py:80,82` vs `api/routers/process.py:427,436` | Misma sección produce geometría reconciliada distinta en cada UI. |
| G05 | P1 | 6 h | Áreas coloreadas por sector (overbreak/underbreak/compliant) | `ui/tabs/profiles.py:268-313` → no web | `core.profile_compliance.compute_sector_deviations` ya existe, solo falta UI. |
| G06 | P1 | 3 h | Histogramas del dashboard (H, Á, B) con líneas de tolerancia | `ui/tabs/dashboard.py:95-126` → no web | Visualizaciones analíticas clave para ingeniería. |
| G07 | P1 | 3 h | Barras apiladas CUMPLE/FUERA/NO_CUMPLE por parámetro | `ui/tabs/dashboard.py:68-92` vs `Dashboard.tsx:182-217` | La web solo muestra % acumulado, perdiendo la dimensionalidad del cumplimiento. |
| G08 | P1 | 4 h | Anotaciones de pata (Pa1, Pa2) e indicadores de berma (`shape` dashed) | `ui/tabs/profiles.py:199-204,465-519` vs `ProfileChart.tsx:108-120` | Completitud del perfil firmado. |
| G09 | P1 | 5 h | Exportación respeta filtros activos + `plot_options` | `ui/tabs/export.py:51-72` → no web | Los Excel/Word/DXF/PNG de la web se generan sin respetar filtros. |
| G10 | P1 | 4 h | Filtro `bench` + aplicar filtros del store al Dashboard | `ui/tabs/dashboard.py:18-39` vs `Dashboard.tsx` | Los KPIs del Dashboard no reflejan los filtros del usuario. |
| G11 | P2 | 6 h | Módulo Tronadura completo (carga + 3D + correlación) | `ui/modulo_tronadura.py` + `ui/tabs/blast_correlation.py` (1 700 LOC) → no web | Bloque entero de funcionalidad ausente. Sprint propio. |
| G12 | P2 | 4 h | AIReporter: streaming + temperature + advanced + filtros + blast_trend metadata | `ui/tabs/ai_report.py` vs `AIReporter.tsx` | Experiencia IA degradada a "una sola respuesta". |
| G13 | P2 | 3 h | Grilla vertical por banco (`dtick=grid_height`) + cota ref | `ui/tabs/profiles.py:225-235` → no web | Referencia visual de altura de banco. |
| G14 | P2 | 3 h | Líneas de referencia (mallas CSV, multifile) en sidebar | `ui/ref_lines.py:25-91`, `app.py:66-67` → no web | Overlay 2D/3D de mallas. |
| G15 | P2 | 3 h | Vista curvas de nivel: elegir Topo/Ambas + intervalo/resolución UI | `ui/step1_upload.py:272-285` vs `ContourChart.tsx:48-49` | |
| G16 | P3 | 2 h | Botón "Descargar .md" del informe IA | `ai_report.py:424-430` → no web | |
| G17 | P3 | 2 h | Uso de tokens con tps + costo USD | `ai_report.py:81-100` → no web | |
| G18 | P3 | 2 h | Histograma Overlay pozos en curva de carga vs descarga (sin módulo blast) | — | Mejoras cosméticas. |

### P0 (critical, blocks user)
- **G01** Render de `reconciled_design` en `ProfileChart` (`buildTraces` debe agregar `buildPolyline(rt reconciled_design, dashed)`)
- **G02** Render de `showSpillAreas` en `ProfileChart` (polígonos `fill='toself'` naranja desde `bench.spill_start_*` + `spill_width`)
- **G03** Endpoint `GET /process/profiles/{id}/blasts?tol=...` + trazas en `ProfileChart`
- **G04** Unificación del builder reconciliado (decidir: migrar Streamlit a `_v2` o regenerar el dato web con legado). Recomendado: **alinear ambos a `_v2`** porque `_v2` es el "preferred" y ya corrige bugs de berma; dejar legado solo para export legacy.

### P1 (high, visible divergence)
- **G05, G06, G07, G08, G09, G10** (ver tabla).

### P2 (medium, nice to have)
- **G11, G12, G13, G14, G15**.

### P3 (low, polish)
- **G16, G17, G18**.

---

## Recomendación de sprints

**Sprint A — "Paridad de Perfil" (P0, ~26 h)**
Cierra la divergencia reportada por el usuario y los toggles engañosos. Orden sugerido:
1. G01 (4 h) + test de regresión visual.
2. G04 (4 h) — alinear builders reconciliados (decisión + implementación).
3. G02 (6 h) — spill areas.
4. G03 (12 h) — endpoint de blasts + trazas.
Entrega: el perfil web se ve idéntico al de Streamlit en capas, toggles operativos, misma geometría reconciliada.

**Sprint B — "Paridad de Dashboard y Export" (P1, ~25 h)**
1. G05 (6 h) áreas por sector.
2. G06 (3 h) histogramas.
3. G07 (3 h) barras apiladas.
4. G08 (4 h) anotaciones + berm shape.
5. G09 (5 h) export con filtros.
6. G10 (4 h) filtro bench + filtros al Dashboard.
Entrega: visualizaciones analíticas y reportes consistentes con los filtros del usuario.

**Sprint C — "Experiencia IA" (P2, ~4 h)**
1. G12 (4 h) streaming + advanced + filtros + blast_trend.
Entrega: IA con paridad funcional razonable.

**Sprint D — "Módulo Tronadura" (P2, ~6 h fase 1, +40 h fase 2)**
1. Fase 1 (6 h): uploader de pozos + visualización 3D mínima + overlay pozos ya hecho en Sprint A.
2. Fase 2 (40 h): tabs de correlación (sección/banco/malla), modelo OLS, recomendaciones PF, pasadura, IDW, tendencias.
Entrega: cierra el gap más voluminoso, en dos iteraciones.

**Sprint E — "Pulido" (P3, ~10 h)**
1. G13 + G14 + G15 + G16 + G17.
Entrega: paridad cercana al 100%.

**Total estimado a paridad funcional completa: ~110–120 h** (≈ 3 sprints de 2 semanas a ritmo sostenido).

---

## Hallazgos sobre el bug del perfil reconciliado

Se identificaron **tres causas independientes** que juntas explican la divergencia entre Streamlit y web:

### Causa 1 — `ProfileChart` no renderiza `reconciled_design` (bug P0, fix trivial)

- **Dónde**: `web/src/components/results/ProfileView/presentation/ProfileChart.tsx:370-376`
- **Evidencia**: el comentario del código dice literalmente `// 4. Reconciled topo — solid amber line (no dashed reconciled design)`. `buildTraces` solo agrega la traza si `l.kind === 'reconciled_topo'`, ignorando `reconciled_design`.
- **Por qué es bug**: el dato SÍ existe en el view model (`web/src/components/results/ProfileView/domain/mapping.ts:62-63` lo construye), el flag `showReconciledDesign` está `true` por defecto (`filters.ts:38`) y la API lo retorna (`api/routers/process.py:430`). Es una omisión del renderer, no de los datos.
- **Fix propuesto (NO aplicado)**: agregar en `buildTraces` antes del bloque de `reconciled_topo`:
  ```ts
  if (filterState.showReconciledDesign) {
    const rd = vm.lines.find((l) => l.kind === 'reconciled_design');
    if (rd && rd.points.length > 0) {
      traces.push(buildPolyline(rd, 'Diseño (reconciliado)', reconciledDesignLineStyle()));
    }
  }
  ```
  donde `reconciledDesignLineStyle()` devuelve `{ color: '#7693b7', width: 1.5, dash: 'dash' }` (azul discontinuo, replicando `ui/tabs/profiles.py:179`).

### Causa 2 — Builders reconciliados diferentes entre Streamlit y API (bug P0, fix requiere decisión)

- **Streamlit**: `ui/step3_analysis.py:80,82` precomputa el reconciliado con `build_reconciled_profile(ep_d.benches)` → invoca la rama **legacy** (`core/profile_compliance.py:97-115`) que **solo ordena crest/toe por distancia y emite `DeprecationWarning`**. Las caras quedan como líneas rectas crest→toe, sin berm_top.
- **API**: `api/routers/process.py:427,436` usa `build_reconciled_profile_v2(benches, source=..., profile=profile)` → retorna `ReconciledProfile` con **berms como segmentos horizontales explícitos** (`berm_top`), **face sampling** desde el perfil real y **ramp points** que omiten la esquina de la berma (ver `AGENTS.md` "Reconciled profile API split").
- **Resultado**: la misma sección produce **dos polilíneas reconciliadas geométricamente distintas** entre ambas UIs, especialmente visible donde hay berma larga o rampa.
- **Fix propuesto (NO aplicado)**: **alinear ambos a `build_reconciled_profile_v2`**. Concretamente, cambiar `ui/step3_analysis.py:80,82` a:
  ```python
  from core.param_extractor import build_reconciled_profile_v2
  reconciled_design[i] = build_reconciled_profile_v2(
      ep_d.benches, source="design",
      profile=(profiles_d[i].distances, profiles_d[i].elevations) if profiles_d[i] else None,
  )
  ```
  y adaptar `ui/tabs/profiles.py:175-190` y `ui/tabs/export.py:415,422` para leer `.distances`/`.elevations` del `ReconciledProfile`. Esto reduce divergencia y elimina el uso del legado. Como efecto colateral positivo, la generación de imágenes y DXF de exportación también quedarán alineadas.
- **Nota**: el legado se conserva en `core/__init__.py` por compatibilidad con scripts externos; no eliminar, solo dejar de usarlo en la UI.

### Causa 3 — Toggles `showSpillAreas` y `showBlastHoles` operativos en UI pero ignorados por el renderer (bug P0, engaño al usuario)

- **Dónde**:
  - `FilterBar.tsx:78-115` muestra los toggles (Derrame, Pozos + Tol) y actualiza `filterState`.
  - `persistenceAdapter.ts:24-27` los persiste en localStorage.
  - Pero `ProfileChart.tsx:336-382` (`buildTraces`) **nunca lee** `showSpillAreas`, `showBlastHoles` ni `blastTolerance` (verificado con grep: 0 ocurrencias en `ProfileChart.tsx`).
- **Impacto**: el usuario activa "Derrame" y "Pozos" y no ve cambio, lo que se interpreta como "resultados distintos a Streamlit" cuando en realidad son toggles no cableados.
- **Fix propuesto (NO aplicado)**:
  - Para **Derrame**: en `buildTraces`, cuando `filterState.showSpillAreas`, iterar `viewModel.benches` y por cada uno con `spillWidth > 0.05 && spillStartElevation > 0` construir un `Scatter fill='toself'` con `fillcolor='rgba(255,165,0,0.4)'` (replica de `ui/tabs/profiles.py:623-656`). Los campos `spill_width`, `spill_start_distance`, `spill_start_elevation` existen en `BenchParams` (`api/schemas.py`) — habría que propagarlos al dominio `Bench` (`web/src/components/results/ProfileView/domain/types.ts`) y al `mapping.ts`.
  - Para **Pozos**: requiere nuevo endpoint `GET /process/profiles/{id}/blasts?tolerance=N` que llame a `core.calculo_tronadura.proyectar_pozos_en_seccion` (ya usado en `ui/tabs/profiles.py:526-533`); luego agregar trazas `Scatter` líneas collar→toe + marcadores coloreados por kg (replica de `ui/tabs/profiles.py:573-620`). Exige además que el usuario haya cargado pozos — lo que hoy la web no permite (gap G11).

### Causa 4 (menor) — Demo data sin `reconciled_design`

- **Dónde**: `web/src/api/hooks.ts:310-311` hardcodea `reconciled_design: null` en el modo demo.
- **Impacto**: incluso con el fix de Causa 1, el modo demo no mostraría la línea reconciliada de diseño.
- **Fix propuesto (NO aplicado)**: regenerar `web/public/demo/precomputed.json` con `reconciled_design` para cada sección (script `scripts/generate_demo_data.py`), o aceptar que demo solo muestre `reconciled_topo`.

---

*Fin del informe. Documento generado en modo solo lectura; ninguna fuente fue modificada.*
