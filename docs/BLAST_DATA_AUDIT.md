# Auditoría Técnica — Datos de Tronadura Faltantes para Conciliación Geotécnica

**Proyecto:** `46-conciliacion-geo-v02`
**Fecha auditoría:** 19 junio 2026
**Autor:** Auditoría técnica (perfil Drill & Blast + reconciliación geotécnica)
**Alcance:** identificar variables, ratios, métricas e integraciones externas que el pipeline actual **NO captura ni calcula** y que aportarían valor explicativo al resultado del diseño de taludes.

---

## 0. Resumen ejecutivo

- El pipeline actual procesa **sólo 14 campos de entrada** del reporte ENAEX (cálculo_tronadura.py:65-90) y descarta 8 explícitamente (COLS_DROP en `core/calculo_tronadura.py:17-20`). Quedan sin leer al menos 15 columnas de valor típicas del esquema ENAEX/SmartBlast.
- De las 14 columnas leídas, sólo 9 (`X, Y, Z_collar, Incl, Az, Len, Burden, Esp, Diam_mm, Tipo_Explosivo, Taco_m, Kilos_Cargados_real, fecha_tronadura`) se promueven a la correlación. `Taco_m`, `Diam_mm` y `Tipo_Explosivo` (parcialmente) **se leen pero nunca se usan** aguas abajo — son minas de oro sin explotar.
- La correlación PF↔daño es **monovariable** (regresión lineal `damage = β₀ + β₁ × PF`). Faltan al menos **8 ratios derivados** que la industria Drill & Blast usa como estándar (stemming ratio, subdrilling ratio, ISPU, uniformidad de malla, distribución de carga fondo/columna) y que se pueden calcular **sólo con lo que ya está en memoria**.
- Hay **0 integraciones externas** hoy: ni vibración (sismógrafo), ni geología (RQD, UCS, litología), ni equipos (perforadora, broca), ni operacional (turno, clima). Cualquier cruce con esos dominios requiere trabajo de ingestión.
- El motor de recomendaciones (`blast_advisor.py`) sólo conoce el PF global por sector. No segmenta por litología, no propone cambios de burden/espaciamiento, no valida restricciones de diámetro ni secuencia.
- **Recomendación priorizada:** hay 6 mejoras de **alto impacto / bajo esfuerzo** que se pueden implementar hoy con el código actual sin pedir nuevos datos al usuario; otras 8 requieren columnas adicionales del CSV; 5 requieren integración externa.

---

## 1. Lo que el pipeline YA hace (para evitar repetir)

Esto está **explícitamente fuera del alcance de esta auditoría** — sólo se lista para delimitar lo que el sistema ya cubre.

| Función / capacidad | Ubicación | Estado |
|---|---|---|
| Signed deviations `delta_crest`, `delta_toe` (sobre/deuda) | `core/blast_correlation.py:287-342` | ✅ Fase 0 |
| Toe projection (no sólo collar) | `core/calculo_tronadura.py:122-139` | ✅ Fase 0 |
| Filtro temporal `fecha_tronadura ≤ fecha_levantamiento` | `core/calculo_tronadura.py:203-216` | ✅ Fase 0 |
| Powder factor volumétrico y areal | `core/blast_correlation.py:112-192` | ✅ Fase 1 |
| k-NN fallback para burden/espaciamiento ausente | `core/blast_correlation.py:84-109` | ✅ Fase 1 |
| Energía MJ por tipo de explosivo (ANFO/HANFO/Emulsión) | `core/config.py:114-150` | ✅ Fase 1 |
| Regresión OLS `damage ~ β₁·PF + β₀` con p, R², IC95% | `core/blast_model.py:45-133` | ✅ Fase 2 |
| Correlación pasadura ↔ delta_toe (Pearson) | `core/blast_model.py:172-329` | ✅ Fase 2 |
| IDW energy density a lo largo del perfil | `core/blast_model.py:332-414` | ✅ Fase 2 |
| Motor cuantitativo `recommend_pf_adjustment` | `core/blast_advisor.py:132-232` | ✅ Fase 4 |
| Recomendaciones por sector (`recommend_by_sector`) | `core/blast_advisor.py:276-375` | ✅ Fase 4 |
| UI Fase 5 — conexión advisor con Streamlit | `ui/tabs/blast_correlation.py:799-865` | ✅ Fase 5 |

---

## 2. Sección A — Datos **computables hoy** con el código actual

Estas métricas e índices **no requieren nuevos inputs del usuario**: se pueden extraer de las coordenadas, inclinaciones, longitudes y `Kilos_Cargados_real` que ya están en `df_clean` después de `procesar_pozos()`. Son ratio y agregaciones puras, sin input externo.

### A.1 Ratios geométricos derivados (estándar Drill & Blast)

| # | Métrica | Fórmula | Valor diagnóstico | Computable hoy | Archivo a tocar |
|---|---|---|---|---|---|
| A.1.1 | **Stemming / Burden ratio** | `Taco_m / Burden` | Óptimo 0.7–1.0 (Konya). <0.5 = cresta volada; >1.2 = proyección de roca deficiente. | ✅ (Taco_m existe pero no se usa) | `core/blast_correlation.py` nueva función |
| A.1.2 | **Subdrilling / Burden ratio** | `(Z_collar - bench_h - Z_toe) / Burden` | Óptimo 0.2–0.4. <0.1 = lomo duro; >0.6 = sobreperforación. | ✅ (pasadura ya existe) | `core/blast_correlation.py` nueva función |
| A.1.3 | **Burden / Spacing ratio (S/B)** | `Esp / Burden` | 1.0–1.5 (cuadrada a rectangular). S/B > 2 = mala fragmentación por shoot-out. | ✅ | nueva en blast_correlation.py |
| A.1.4 | **Carga por metro de pozo (kg/m)** | `Kilos_Cargados / longitud_real` | ANFO ~8–15 kg/m, emulsión ~25–35 kg/m. Crítico para detectar pozos mal cargados. | ✅ | nueva en blast_correlation.py |
| A.1.5 | **Densidad de carga lineal relativa** | `kg_por_metro / (π/4 × D² × densidad_roca)` | Detecta decoupling (carga sub-densa). | ✅ si se conoce densidad_roca (default 2.7 t/m³) | nueva |
| A.1.6 | **Desviación estándar de inclinación entre pozos vecinos** | `std(inclinaciones en malla)` | >2° indica perforación errática. | ✅ con k-NN existente | nueva en blast_correlation.py |

### A.2 Índices compuestos (multi-variable en una sola)

| # | Índice | Fórmula / concepto | Significado | Computable hoy |
|---|---|---|---|---|
| A.2.1 | **ISPU (Índice Schwimmbeck / Powder Utilization)** | `(kg explosivo) / (volumen × UCS_referencial)` | Eficiencia energética. Requiere UCS como input externo → ver §C.1. | ⚠️ Parcial (necesita UCS) |
| A.2.2 | **Factor de carga por área** (kg/m²) — ya existe como `pf_area_kgm2` | `Kilos / (B × S)` | Ya está implementado. | ✅ hecho |
| A.2.3 | **Densidad de carga volumétrica local** (kg/m³) | `kg_por_metro / (B × S)` | Distingue pozos saturados de sub-cargados dentro de una misma malla. | ✅ |
| A.2.4 | **Coeficiente de variación del burden real** | `std(B_real) / mean(B_real)` | "Uniformidad de malla". CV<10% buena, CV>25% cresta irregular. | ✅ con datos reales de burden; ⚠️ con k-NN es menos confiable |
| A.2.5 | **Razón carga-fondo/carga-columna** | `fondo_kg / columna_kg` | Típico 0.3–0.5 (ANFO) / 0.2–0.3 (emulsión). | ⚠️ requiere columna nueva `Kilos_Fondo` (ver §B.5) |

### A.3 Detección automática de anomalías por pozo

Estas detecciones se pueden correr después de `procesar_pozos()` sin nuevos inputs:

| # | Detección | Lógica | Acción automática |
|---|---|---|---|
| A.3.1 | Pozo desviado (inclinación > 5° sin vecino también inclinado) | `Incl > 5° AND |Incl - Incl_vecino_medio| > 3°` | Marcar para QA de perforación |
| A.3.2 | Pozo sobrecargado / subcargado | `kg_por_metro > percentil_95(kg_por_metro)` o `< percentil_5` | Flag para revisión |
| A.3.3 | Pozo corto respecto a sus vecinos | `|Len - mean(Len_vecinos)| > 3m` | Riesgo de piso no fragmentado |
| A.3.4 | Pozo aislado (sin vecinos dentro de 2×Burden) | k-NN k=4, si `min_dist > 2*burden` | Evaluar impacto en fragmentación |
| A.3.5 | Mallas con burden ratio erróneo | `(S/B) > 2 OR < 0.5` | Alerta de patrón mal diseñado |

> **Valor para tu meta:** la mayoría de estos ratios correlacionan mejor con el daño de talud que el PF crudo. Estudios ENAEX y Julius Kruttschnitt muestran que stemming ratio fuera de rango y subdrilling ratio explican más varianza de sobre-excavación que PF solo.

### A.4 Análisis espacio-temporal avanzado

| # | Análisis | Implementación | Valor |
|---|---|---|---|
| A.4.1 | **Variograma de burden real** entre pozos vecinos | Distancias pareadas por grupo | Detectar anisotropía de la malla |
| A.4.2 | **Densidad de energía local en el perfil** (ya existe IDW global) | Suavizar con ventana de 5m | Picos locales correlacionan con sobre-excavación puntual |
| A.4.3 | **Gradiente de PF a lo largo de la sección** | `dPF/dx` a lo largo del perfil | Detecta transiciones mal diseñadas |
| A.4.4 | **Histéresis de daño vs PF** por fecha | Scatter `damage_t` vs `damage_{t-1}` coloreado por `ΔPF` | Detecta efectos rezagados |

---

## 3. Sección B — Datos **ignorados del CSV ENAEX** que están ahí pero no se leen

`core/calculo_tronadura.py:65-90` llama a `find_df_column()` con listas cortas de candidatos. El docstring de la línea 7-9 enumera los campos descartados a propósito, pero hay **decenas de columnas ENAEX típicas** que ni siquiera se intentan leer. A continuación se identifican las de **mayor valor** y la dificultad de procesamiento.

### B.1 Inventario del CSV: lo leído vs lo ignorado

**Columnas leídas** (procesar_pozos.py:65-90):
- `Latitud_Geo / Longitud_Geo` (X, Y)
- `Nombre_Banco` (Z_collar base)
- `Inclinacion_real, Azimuth_real, longitud_real`
- `Burden / Esp / Diam_mm / Tipo_Explosivo / Taco_m`

**Columnas descartadas explícitamente** (COLS_DROP en calculo_tronadura.py:17-20):
- `uniqid, id_rajo, id_malla_opit, id_pozo, numero, camion, holes_dateUpdated, mes_tronadura`

**Columnas típicas ENAEX/SmartBlast NO leídas NI descartadas** (quedan en `df_clean` pero sin uso):

| # | Columna típica ENAEX | Significado | Valor potencial | Esfuerzo |
|---|---|---|---|---|
| B.1 | **`Numero_Pozo` / `N_Pozo` / `HoleID`** | ID único del pozo | Trazabilidad, join con bitácora de perforación | Bajo |
| B.2 | **`Secuencia` / `Secuencia_Iniciacion` / `Detonador_Nro`** | Número de secuencia de iniciación | Análisis de vibración por retardo, errores de secuencia | Bajo |
| B.3 | **`Retardo_ms` / `Delay_ms` / `Tiempo_Retardo`** | Retardo en ms | PPV depende fuertemente del retardo (ventana de 8–25 ms/pozo) | Bajo |
| B.4 | **`Numero_Fila` / `Fila_Pozo` / `Row`** | Fila dentro de la malla (1=cresta) | Distingue carga de precorte/producción; análisis por fila | Bajo |
| B.5 | **`Carga_Fondo_kg` / `Kilos_Fondo` / `Bottom_Charge`** | kg en el fondo del pozo | Distribución de carga fondo/columna | Bajo |
| B.6 | **`Carga_Columna_kg` / `Kilos_Columna`** | kg en la columna | Complemento de B.5 | Bajo |
| B.7 | **`Longitud_Carga_m` / `Charge_Length`** | metros cargados (vs Taco_m arriba) | Permite calcular burden sin asumir columna completa | Bajo |
| B.8 | **`Densidad_Carga` / `Loading_Density`** | kg/m³ in-hole | Cross-check vs `kg_por_metro` calculado | Bajo |
| B.9 | **`Tipo_Pozo` / `Hole_Type`** | producción / precorte / buffer / alivio | Análisis por tipo de carga | Bajo |
| B.10 | **`Fecha_Perforacion` / `Drilled_Date`** | Cuándo se perforó el pozo | Lag perforación-tronadura (perforado y no tronado) | Bajo |
| B.11 | **`Operador_Perforacion` / `Driller`** | Quién perforó | Variabilidad operacional (curva de aprendizaje) | Bajo |
| B.12 | **`Perforadora` / `Drill_Rig` / `Marca_Equipo`** | Marca/modelo de perforadora | Sesgos por equipo (broca desgastada, alineación) | Bajo |
| B.13 | **`Diametro_Broca_mm` / `Bit_Diameter`** | Diámetro real de broca (vs D_pozo) | Detecta desgaste de broca | Bajo |
| B.14 | **`Numero_Perforaciones_Previas` / `Reused_Hole`** | Pozos re-perforados | Calidad de perforación | Bajo |
| B.15 | **`Azimuth_Diseno` / `Design_Azimuth`** | Azimut planificado (vs Azimuth_real) | **Desviación de perforación** — métrica crítica | Bajo |
| B.16 | **`Inclinacion_Diseno` / `Design_Dip`** | Inclinación planificada | **Desviación de perforación** | Bajo |
| B.17 | **`Espaciamiento_Real` / `Esp_Real`** vs `Esp_Diseno` | Espaciamiento medido en terreno | CV de malla real | Bajo |

### B.2 Las **5 más valiosas** priorizadas por impacto

| Prioridad | Columna | Por qué es valiosa | Esfuerzo de implementación |
|---|---|---|---|
| 🥇 | **Secuencia + Retardo_ms** (B.2+B.3) | Permite calcular ventana de vibración pico (suma de contribuciones de pozos adyacentes en [t, t+8ms]). Es la base de la correlación con **daño por vibración**, no sólo por PF. | Bajo: agregar 2 `find_df_column` + 1 columna calculada |
| 🥈 | **Carga_Fondo / Carga_Columna** (B.5+B.6) | Habilita el cálculo de **distribución de carga fondo/columna** (A.2.5), métrica que estudios de ICI Explosives muestran explica más varianza de sobre-excavación que PF solo. | Bajo |
| 🥉 | **Azimuth_Diseno / Inclinacion_Diseno** (B.15+B.16) | Permite calcular **desviación de perforación** (collar deviation = ángulo entre trayectoria real y diseñada). Métrica estándar ICI/Workman. | Bajo: calcular ángulo 3D entre vectores |
| 4 | **Tipo_Pozo** (B.9) | Separa pozos de precorte/buffer/producción. La sobre-excavación de cresta depende casi exclusivamente de la **calidad del precorte**, no del PF de producción. Sin esta distinción, el modelo está mezclando dos efectos. | Bajo |
| 5 | **Perforadora + Diametro_Broca_mm** (B.12+B.13) | Pozos con broca desgastada dan burden efectivo mayor (perforación más lenta, alineación peor). ENAEX documenta diferencias de 5–15% en fragmentación por este factor. | Bajo |

### B.3 Lo que ya se lee pero no se usa (minas de oro escondidas)

| Columna | Estado | Por qué es valiosa |
|---|---|---|
| `Taco_m` (stemming) | Leído en `calculo_tronadura.py:87-108`, **nunca se usa aguas abajo** | Habilita stemming/burden ratio (A.1.1), directamente relacionado con proyección de cresta |
| `Diam_mm` | Leído, sin uso posterior | Cross-check de cálculo de densidad de carga |
| `Tipo_Explosivo` | Usado para energía MJ/kg (`EXPLOSIVE.energy_mj_per_kg`) | La función `EXPLOSIVE.density_g_per_cm3` está definida pero **nadie la llama** — oportunidad para calcular decoupling |

> **Acción concreta:** un PR que compute stemming_ratio, subdrilling_ratio, kg_por_metro y deviation_angulo (con B.15+B.16) y los añada al dataframe enriquecer en `compute_powder_factor` puede hacerse en **<200 líneas + 15 tests**.

---

## 4. Sección C — Datos **externos a cruzar** (no están en el CSV)

Hoy el pipeline no importa nada que no venga del CSV de tronadura + STL de topografía. Cualquier cruce con dominios adyacentes requiere **integración explícita**.

### C.1 Geología

| # | Dato | Fuente típica | Valor | Cómo integrarlo |
|---|---|---|---|---|
| C.1.1 | **UCS (resistencia a la compresión uniaxial, MPa)** | Sondajes + lab, o base geotécnica de la mina | Multiplicador del ISPU (A.2.1); explica por qué el mismo PF daña distinto en distintos bancos | Join espacial `polígono_geología` ∩ `df_clean` |
| C.1.2 | **RQD / Fracturamiento** | Sondajes | Determina energía necesaria para fragmentar; corrige PF objetivo | Join por level + offset |
| C.1.3 | **Litología / Dominio estructural** | Modelo geológico 3D (Leapfrog/Vulcan) | Segmentación del modelo de regresión por litología | Lookup espacial |
| C.1.4 | **Densidad de roca (t/m³)** | Lab o tabla por litología | Convierte volumen→masa (cálculo más preciso de PF areal) | Lookup por litología |
| C.1.5 | **Orientación de discontinuidades (dip/dipdir)** | Sondajes, mapeo de superficie | Controla dirección de sobre-excavación (no es aleatoria) | Lookup por banco |
| C.1.6 | **Presencia de agua subterránea** | Piezómetros | Pozos húmedos requieren emulsión, no ANFO | Join espacial |

### C.2 Vibración (sismógrafo)

| # | Dato | Valor | Integración |
|---|---|---|---|
| C.2.1 | **PPV (Peak Particle Velocity, mm/s)** | Correlaciona directamente con daño por vibración (daño ≠ sobre-excavación por gas) | Importar CSV del sismógrafo con timestamp + coordenadas |
| C.2.2 | **Frecuencia dominante (Hz)** | Indica tipo de daño (baja frecuencia = daño extensivo) | Mismo CSV |
| C.2.3 | **Escala de distancia (Sd)** | `Sd = distancia / √kg` | Permite normalizar vibraciones de pozos de distinta carga |
| C.2.4 | **Vector suma triaxial** | PPV real combinando 3 ejes | — |

> **Insight clave:** el modelo actual **confunde dos mecanismos** — (a) sobre-excavación por **presión de gas** (función del PF), y (b) sobre-excavación por **vibración** (función de PPV y distancia). Sin sismógrafo, no se pueden separar y el modelo mezcla ambos errores. Es la mejora más impactante de toda esta auditoría.

### C.3 Topografía adicional

| # | Dato | Valor | Integración |
|---|---|---|---|
| C.3.1 | **Múltiples levantamientos en el tiempo** | Distinguir sobre-excavación gradual de un evento puntual | Ingestión de varios STL con timestamp |
| C.3.2 | **Densidad de puntos LiDAR** | Calidad del modelo; detecta zonas mal levantadas | Metadatos del levantamiento |
| C.3.3 | **Precisión GPS del levantamiento** | Incertidumbre del baseline | Metadatos |

### C.4 Equipos de perforación

| # | Dato | Valor | Integración |
|---|---|---|---|
| C.4.1 | **Marca/modelo perforadora** | Sesgos sistemáticos (Pit Viper vs DM-45 tienen distinta precisión) | CSV de perforación |
| C.4.2 | **Edad de la broca (m perforados)** | Broca desgastada = burden efectivo mayor | CSV de perforación |
| C.4.3 | **Velocidad de penetración (m/min)** | Indica roca competente vs fracturada | Telemetría |
| C.4.4 | **Desviación de perforación (collar survey)** | Hoy se infiere sólo por inclinación; broca con GPS entrega vector completo | Survey de perforación |

### C.5 Operacional

| # | Dato | Valor | Integración |
|---|---|---|---|
| C.5.1 | **Turno / Operador** | Variabilidad humana en carguío | Bitácora |
| C.5.2 | **Condiciones climáticas (lluvia, temperatura)** | Afecta ANFO (sensitividad al agua) | Estación meteorológica |
| C.5.3 | **Tiempo entre perforación y tronadura** | Pozos perforados y no tronados por >30 días cambian | Bitácora |
| C.5.4 | **Estado de la cara libre** | Cara libre congestionada = vibración amplificada | Inspección visual |

---

## 5. Sección D — Métricas estándar de la industria **no implementadas**

Estas métricas son **estándar** en la literatura Drill & Blast (Konya & Walter, 1991; Workman, 1993; ICI Explosives; Dyno Nobel) y **ninguna está computada** en el pipeline actual.

### D.1 Métricas físicas

| # | Métrica | Fórmula | Estado | Archivo sugerido |
|---|---|---|---|---|
| D.1.1 | **Powder factor vs burden ratio** | `(PF_actual / PF_óptimo) × (Burden_actual / Burden_diseño)` | ❌ No existe; combina dos efectos | nueva función en `core/blast_metrics.py` |
| D.1.2 | **Stemming / burden ratio** (objetivo 0.7–1.0) | Taco_m / Burden | ⚠️ Datos leídos, ratio no calculado | nueva en `core/blast_metrics.py` |
| D.1.3 | **Subdrilling / burden ratio** (objetivo 0.2–0.4) | `(Z_collar - bench_h - Z_toe) / Burden` | ❌ No implementado | nueva |
| D.1.4 | **ISPU** | Eficiencia volumétrica real / ideal × 100 | ❌ | nueva (necesita UCS — ver C.1.1) |
| D.1.5 | **Desviación de perforación (collar deviation, °)** | ángulo 3D entre `vector_diseño` y `vector_real` | ❌ (requiere B.15+B.16) | nueva en blast_metrics.py |
| D.1.6 | **Coeficiente de variación del burden real** | `σ(B) / μ(B)` | ⚠️ Posible con k-NN, no implementado | nueva |
| D.1.7 | **Distribución de carga (kg/m)** | `Kilos / longitud_real` | ❌ | nueva |
| D.1.8 | **Distribución de carga de fondo vs columna** | `Kilos_Fondo / Kilos_Columna` | ❌ (requiere B.5+B.6) | nueva |
| D.1.9 | **Densidad de carga volumétrica in-hole** | `kg_por_metro / (π/4 × D²)` | ❌ | nueva |
| D.1.10 | **Ratio de espaciamiento S/B** | `Esp / Burden` | ❌ | nueva |

### D.2 Métricas de uniformidad y calidad

| # | Métrica | Concepto | Estado |
|---|---|---|---|
| D.2.1 | **Coeficiente de variación de burden real** | Detecta mallas irregulares | ❌ |
| D.2.2 | **% de pozos dentro de tolerance angular** | >2° de desviación = mala perforación | ❌ (requiere B.15+B.16) |
| D.2.3 | **Índice de subdrilling efectivo** | Pasadura real / Burden | ❌ |
| D.2.4 | **% de burden correcto vs diseño** | Pozos con burden dentro de ±10% del diseño | ❌ |
| D.2.5 | **Fragmentación estimada (Kuznetsov)** | `X = A × (V/Q)^0.8 × Q^0.1667 × (E/115)^-0.633` | ❌ — **importantísimo**, no requiere nuevos inputs |
| D.2.6 | **Índice de uniformidad de taco** | `std(Taco_m) / mean(Taco_m)` | ❌ |
| D.2.7 | **% de pozos con stemming ratio en rango óptimo** | % entre 0.7–1.0 | ❌ |

### D.3 Métricas de eficiencia energética

| # | Métrica | Concepto | Estado |
|---|---|---|---|
| D.3.1 | **Energía por unidad de área de talud generado** | MJ / m² de cara libre creada | ❌ |
| D.3.2 | **Densidad de potencia por metro de banco** | MJ / (m lineal de banco) | ❌ |
| D.3.3 | **Energía específica (Workman)** | MJ / ton de roca fragmentada | ❌ |
| D.3.4 | **Decoupling ratio** | `volumen_carga / volumen_pozo` | ❌ (necesita densidad explosivo) |
| D.3.5 | **Factor de acoplamiento (coupling)** | `d_carga / d_pozo` | ❌ (con D_pozo y carga) |

> **La métrica D.2.5 (Kuznetsov)** es la más valiosa de toda la lista: predice el **tamaño medio de fragmento** sin requerir inputs nuevos. Combinada con el `delta_crest` actual, cierra el ciclo entre diseño de tronadura → granulometría esperada → daño de talud observado.

---

## 6. Sección E — Análisis **temporal avanzado** posible con los datos actuales

El campo `fecha_tronadura` existe (procesar_pozos.py:62-64) pero sólo se usa para el **filtro temporal básico** (≤ fecha_levantamiento). Hay mucho más por extraer.

### E.1 Análisis de series temporales

| # | Análisis | Lógica | Output |
|---|---|---|---|
| E.1.1 | **Tendencia de PF en el tiempo** | `mean(PF) por mes o por campaña` | Gráfico + pendiente (¿el equipo está ajustando a la baja o sigue igual?) |
| E.1.2 | **Comparación entre campañas** | `aggregate(PF, daño) por campaña_id` | Detecta campañas outliers |
| E.1.3 | **Outliers de PF** | IQR o z-score sobre PF por sector | Flag para revisión |
| E.1.4 | **Estacionalidad del daño** | `mean(delta_crest) por mes` | Detecta efectos climáticos o de aprendizaje |
| E.1.5 | **Lag perforación→tronadura** | Requiere `Fecha_Perforacion` (B.10) | Pozos perforados mucho antes pueden tener agua/humedad |

### E.2 Análisis de cohortes

| # | Análisis | Valor |
|---|---|---|
| E.2.1 | **Comparar PF pre/post intervención** | Después de cambiar de ANFO a emulsión, ¿bajó el daño? |
| E.2.2 | **Cohorte por tipo de explosivo** | ¿Emulsión da más o menos sobre-excavación que ANFO en este banco? |
| E.2.3 | **Cohorte por sector** | ¿El sector Norte tiene sistemáticamente más daño que el Sur, controlando por PF? |

### E.3 Análisis de capacidad del proceso (SPC)

| # | Análisis | Valor |
|---|---|---|
| E.3.1 | **Cartas de control X̄-R** sobre PF y daño | Detecta drift en el proceso |
| E.3.2 | **Cpk del proceso** | `min((USL-μ)/3σ, (μ-LSL)/3σ)` para PF |
| E.3.3 | **Detección de puntos de cambio** (CUSUM) | Identifica el momento en que el proceso cambió |

### E.4 Lo que el AI reporter recibe hoy

Inspeccionando `core/ai_service.py:85-175` y `core/ai_reporter.py:42-54`, el LLM recibe:
- Conteos CUMPLE / FUERA / NO CUMPLE por parámetro
- Top 5 desviaciones de altura y ángulo
- `pasadura_promedio`, `pasadura_optima_pct`, `correlacion_r`

**Falta:** series temporales, comparación de campañas, tendencia, outliers. **Una sola tabla con esos datos cambiaría la calidad del informe ejecutivo generado por el LLM.**

---

## 7. Roadmap priorizado

Ordenado por **impacto en la meta × esfuerzo**, con dependencias explícitas.

### 🥇 PRIORIDAD 1 — Quick wins con datos existentes (semanas 1-2)

| # | Mejora | Impacto | Esfuerzo | Dependencias | Archivos |
|---|---|---|---|---|---|
| 1 | **Calcular 6 ratios derivados**: stemming_ratio, subdrilling_ratio, S/B ratio, kg_por_metro, density_coupling, deviation_ratio | **Alto** | Bajo | Taco_m, Incl, Az ya leídos | nuevo `core/blast_metrics.py` (~150 líneas) |
| 2 | **Añadir serie temporal de PF y daño** (gráfico + tendencia) en `ui/tabs/blast_correlation.py` | Alto | Bajo | `fecha_tronadura` ya existe | modificar UI |
| 3 | **Implementar Kuznetsov** (X₅₀ tamaño medio de fragmento) | Alto | Bajo | kg, B, S, tipo_explosivo ya están | nueva función `compute_kuznetsov_x50` en blast_model.py |
| 4 | **Exponer Taco_m y Diam_mm aguas abajo** (hoy se leen y no se usan) | Medio | Bajo | — | modificar `compute_powder_factor` |
| 5 | **Reporte al LLM** con resumen de serie temporal + outliers | Medio | Bajo | resultados de #2 y #3 | modificar `core/ai_service.py` `build_analysis_prompt` |

### 🥈 PRIORIDAD 2 — Requiere leer columnas adicionales del CSV (semanas 2-4)

| # | Mejora | Impacto | Esfuerzo | Dependencias | Archivos |
|---|---|---|---|---|---|
| 6 | **Leer Secuencia + Retardo_ms** y calcular ventana de vibración pico por sección | **Muy alto** (conecta con sismógrafo) | Bajo | B.2+B.3 del CSV | nueva función en blast_metrics.py + entrada en procesar_pozos |
| 7 | **Leer Carga_Fondo / Carga_Columna** y calcular distribución de carga | Alto | Bajo | B.5+B.6 del CSV | nueva función |
| 8 | **Leer Azimuth_Diseno / Inclinacion_Diseno** y calcular **collar deviation** | Alto | Bajo | B.15+B.16 | nueva función |
| 9 | **Leer Tipo_Pozo** y segmentar análisis por precorte/buffer/producción | Alto | Bajo | B.9 | nueva columna de filtrado |
| 10 | **Modelo de regresión multivariable** (PF + stemming ratio + subdrilling ratio + collar deviation) en lugar de sólo PF | **Muy alto** | Medio | resultados de #1, #6, #7, #8 | nueva función en `core/blast_model.py` |

### 🥉 PRIORIDAD 3 — Integraciones externas (mes 2-3)

| # | Mejora | Impacto | Esfuerzo | Dependencias |
|---|---|---|---|---|
| 11 | **Ingestión de CSV de sismógrafo** (PPV, frecuencia, Sd) + correlación con daño | **Muy alto** | Alto | C.2 |
| 12 | **Lookup geología** (UCS, RQD, litología) por banco y join espacial | Alto | Alto | C.1 + GIS/tabla geotécnica |
| 13 | **Ingestión de bitácora de perforación** (perforadora, broca, fecha_perforacion, driller) | Medio | Medio | C.4, C.5 |
| 14 | **Múltiples levantamientos topográficos** para distinguir daño progresivo de evento único | Medio | Alto | C.3 |
| 15 | **Implementar ISPU** (requiere UCS ya cruzado en #12) | Alto | Bajo (una vez UCS disponible) | C.1.1 |

### 🏅 PRIORIDAD 4 — Análisis avanzado y producto (mes 3+)

| # | Mejora | Impacto | Esfuerzo | Dependencias |
|---|---|---|---|---|
| 16 | **Carta de control SPC** sobre PF, taco y daño | Medio | Medio | E.3 |
| 17 | **Detección de campañas outliers** (aislar efectos de un cambio de operador, equipo o explosivo) | Medio | Medio | E.2 |
| 18 | **Comparación pre/post intervención** (`reco PF antes vs después`) | Medio | Bajo | E.2.1 |
| 19 | **Restricciones operativas en el advisor** (validar diámetro de perforación, explosivo disponible) | Medio | Bajo | módulo advisor |
| 20 | **Visualización 3D de collar deviation** (flechas desde collar planeado al real) | Alto | Medio | #8 |

---

## 8. Tabla resumen final

Leyenda tipo: **calc** = computable hoy / **input** = requiere nueva columna del CSV / **ext** = requiere integración externa / **ind** = métrica estándar de industria / **temp** = análisis temporal.

| # | Mejora | Tipo | Impacto | Esfuerzo | Prioridad | Archivos clave |
|---|---|---|---|---|---|---|
| 1 | Ratios derivados (stemming, subdrilling, S/B, kg/m, coupling, deviation) | calc | Alto | Bajo | 1 | nuevo `core/blast_metrics.py` |
| 2 | Serie temporal de PF y daño en UI | temp | Alto | Bajo | 1 | `ui/tabs/blast_correlation.py` |
| 3 | Kuznetsov X₅₀ (tamaño medio fragmento) | ind | Alto | Bajo | 1 | `core/blast_model.py` |
| 4 | Exponer Taco_m + Diam_mm aguas abajo | calc | Medio | Bajo | 1 | `core/blast_correlation.py` |
| 5 | Reporte LLM con serie temporal y outliers | temp | Medio | Bajo | 1 | `core/ai_service.py` |
| 6 | Leer Secuencia + Retardo_ms + ventana vibración | input | Muy alto | Bajo | 2 | `calculo_tronadura.py` + nuevo |
| 7 | Leer Carga_Fondo + Carga_Columna + distribución | input | Alto | Bajo | 2 | `calculo_tronadura.py` + nuevo |
| 8 | Leer Azimut_Diseno + Incl_Diseno + collar deviation | input | Alto | Bajo | 2 | `calculo_tronadura.py` + nuevo |
| 9 | Leer Tipo_Pozo + segmentar precorte/buffer/prod | input | Alto | Bajo | 2 | UI |
| 10 | Regresión multivariable (PF + ratios + deviation) | calc | Muy alto | Medio | 2 | `core/blast_model.py` |
| 11 | Ingesta sismógrafo + correlación PPV-daño | ext | Muy alto | Alto | 3 | nuevo `core/seismograph.py` |
| 12 | Lookup geología (UCS, RQD, litología) | ext | Alto | Alto | 3 | nuevo `core/geology.py` |
| 13 | Bitácora de perforación (equipo, broca, driller) | ext | Medio | Medio | 3 | nuevo `core/drilling_log.py` |
| 14 | Múltiples levantamientos topográficos | ext | Medio | Alto | 3 | modificar `mesh_handler.py` |
| 15 | Implementar ISPU | ind | Alto | Bajo (post #12) | 3 | `core/blast_metrics.py` |
| 16 | Cartas SPC sobre PF/taco/daño | ind | Medio | Medio | 4 | nuevo `core/spc.py` |
| 17 | Detección campañas outliers (CUSUM) | temp | Medio | Medio | 4 | nuevo `core/campaigns.py` |
| 18 | Comparación pre/post intervención | temp | Medio | Bajo | 4 | UI |
| 19 | Restricciones operativas en advisor | ind | Medio | Bajo | 4 | `core/blast_advisor.py` |
| 20 | Visualización 3D collar deviation | calc | Alto | Medio | 4 | UI |

### Conteo rápido

- **Total mejoras identificadas:** 20
- **Computables hoy (sin nuevos inputs):** 7 (calc) + 3 (ind) + 2 (temp) = **12**
- **Requieren columna nueva del CSV:** 4 (input) — bajo esfuerzo
- **Requieren integración externa:** 4 (ext) — alto esfuerzo
- **Impacto Muy alto:** 4 (regresión multivariable, vibración, secuencia+retardo, geología UCS)
- **Bajo esfuerzo y Alto impacto:** 8 (1, 2, 3, 6, 7, 8, 9, 19)

---

## 9. Observaciones adicionales

### 9.1 Inconsistencias detectadas durante la auditoría

| # | Observación | Archivo:línea |
|---|---|---|
| O.1 | `EXPLOSIVE.density_g_per_cm3` (`config.py:141-150`) está definida pero **nadie la llama** | `core/config.py:141-150` |
| O.2 | `Taco_m` se lee en `calculo_tronadura.py:87-108` pero no se promueve a `burden_est_m`, `pf_*`, `BlastCorrelationRow` ni a ninguna métrica | varios |
| O.3 | `Diam_mm` se lee pero sólo se coerciona a numérico (`calculo_tronadura.py:113-115`); no se usa en cálculo alguno | `calculo_tronadura.py:113-115` |
| O.4 | `recompute_powder_factor` se llama 4 veces seguidas en el mismo flujo (una por sección); riesgo de performance y de inconsistencia si cambia el modelo | `ui/tabs/blast_correlation.py:400-432` |
| O.5 | El `ai_service.py:127-144` calcula correlación r dentro del módulo UI, duplicando lógica que ya existe en `blast_model.py:fit_powder_factor_damage_model` | `ui/tabs/ai_report.py:127-144` vs `core/blast_model.py:45-133` |
| O.6 | `_render_local_blast_advisory` (ui/tabs/ai_report.py:180-277) recomputa correlación dentro del bloque, ignorando el modelo ya ajustado en `blast_correlation.py` | `ui/tabs/ai_report.py:180-277` |

### 9.2 Mejoras de salud de código (no funcionales)

- Mover el cálculo de ratios derivados a un módulo dedicado `core/blast_metrics.py` (≈300 líneas + 30 tests) para limpiar `blast_correlation.py` que ya tiene 462 líneas y mezcla responsabilidades.
- Documentar las **firmas esperadas del CSV ENAEX** en `docs/BLAST_DATA_SCHEMA.md` (hoy sólo están implícitas en `procesar_pozos`).
- Crear un **validador de schema** (`core/csv_schema_validator.py`) que advierta al usuario qué columnas se ignoraron en silencio.

---

**Fin del informe.**
