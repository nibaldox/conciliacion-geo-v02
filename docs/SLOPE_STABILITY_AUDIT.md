# Auditoria Tecnica Geotecnica — Estabilidad del Talud Final

**Proyecto:** `46-conciliacion-geo-v02`
**Fecha auditoria:** 20 junio 2026
**Autor:** Auditoria tecnica (perfil geotecnia de taludes, open pit)
**Alcance:** identificar mejoras que beneficien directamente la **estabilidad geotecnica del talud final** (no la tronadura como objetivo en si).
**Trabajo previo relevante:** `docs/BLAST_DATA_AUDIT.md` (Fases 0-8B, blast-focused, 20 mejoras).

---

## 0. Resumen ejecutivo

- El pipeline actual (`core/param_extractor.py`, `core/breaklines.py`, `core/config.py`) **solo modela la geometria del talud a nivel de bancos individuales**: detecta crest/toe/berm, calcula angulo de cara, berm width, inter-ramp angle y overall angle. **No contiene ni una sola linea de codigo** sobre mecanismos de falla (cunva/wedge, planar, toppling), clasificacion de macizo (RMR, GSI, Q), test cinematico de Markland, factor de seguridad, ni monitoreo temporal de salud del talud. Esto se verifico con busquedas exhaustivas (`grep -i "wedge|toppling|RMR|GSI|Markland|kinematic|discontinuity|rock bridge|catch bench|factor de seguridad"` → 0 matches en `core/`).
- La auditoria previa de tronadura (`docs/BLAST_DATA_AUDIT.md`) ya cubre 20 mejoras orientadas al **control de sobre-excavacion** mediante ajustes de PF, stemming ratio, collar deviation, etc. Esta auditoria **complementa** ese trabajo expandiendo el alcance al sistema geotecnico completo: deteccion de mecanismos, FS simplificado, monitoreo, optimizacion de diseno, e integracion con sistemas externos.
- El proyecto tiene **excelentes cimientos geometricos** (RDP, Hungarian matching, tolerances tripartitas, reconciliacion de perfil) que pueden extenderse con **bajo esfuerzo incremental** para soportar analisis de estabilidad real. La mayoria de las mejoras A y B son **computables hoy** sin nuevos inputs del usuario.
- Se identifican **42 mejoras nuevas** distribuidas en 5 secciones (A deteccion, B estabilidad, C monitoreo, D optimizacion, E integracion externa), con un **roadmap priorizado de 10 mejoras top** que pueden implementarse en orden y validar contra los 251 tests existentes.
- **Hallazgo clave**: el angulo inter-rampa actual (`core/param_extractor.py:373-377`) ya resta la proyeccion horizontal de las rampas, pero **no detecta geometrias anomalas** (overhangs en la cresta, bermas negativas, wedge shape en el perfil). Esto abre la puerta a falsos positivos en el cumplimiento CUMPLE/FUERA/NO_CUMPLE: un banco puede cumplir el angulo de cara pero tener un bloque suelto en la cresta que es el precursor de una falla.
- **Quick win n.1**: anadir deteccion de overhangs / negative berms al extractor (`param_extractor.py`) en ~80 lineas + 10 tests. Es la mejora con mejor relacion impacto/esfuerzo de toda la auditoria: una sola corrida detecta condiciones que **hoy pasan inadvertidas** y son precursores clasicos de falla planar.

---

## 1. Lo que el pipeline YA hace (no repetir)

Inspeccion exhaustiva de `core/param_extractor.py`, `core/breaklines.py`, `core/config.py`, `core/geom_utils.py`, `core/section_cutter.py`, `core/blast_*.py`, `core/calculo_tronadura.py`, `core/report_generator.py`.

| Capacidad | Ubicacion | Estado |
|---|---|---|
| Carga de mallas (STL/OBJ/PLY/DXF) | `core/mesh_handler.py:1-217` | ✅ |
| Corte de mallas por secciones verticales | `core/section_cutter.py:38-100` | ✅ |
| Simplificacion RDP del perfil | `core/param_extractor.py:92-139` | ✅ |
| Clasificacion de segmentos (cara / berma) por angulo | `core/param_extractor.py:227-256` | ✅ |
| Deteccion de bancos (face segments) | `core/param_extractor.py:271-348` | ✅ |
| Calculo de berm width (toe-crest entre bancos) | `core/param_extractor.py:385-426` | ✅ |
| Clasificacion berma-rampa (ancho 15-42 m) | `core/blast_correlation.py:470-472` + `RAMP` en `core/config.py:106-110` | ✅ |
| Toe projection con correccion de spill pile | `core/param_extractor.py:142-177` | ✅ |
| Hungarian matching design vs topo | `core/param_extractor.py:720-944` | ✅ |
| Compliance tripartita (CUMPLE/FUERA/NO_CUMPLE) | `core/param_extractor.py:488-503` | ✅ |
| Calculo de inter-ramp angle y overall angle | `core/param_extractor.py:360-382` | ✅ |
| Breaklines (crests/toes) por diedro convexo/concavo | `core/breaklines.py:1-67` | ✅ |
| Powder factor (vol, area), energy MJ | `core/blast_correlation.py:113-202` | ✅ |
| Regresion PF vs damage + IC95% + p-value | `core/blast_model.py:45-133` | ✅ |
| Correlacion pasadura vs delta_toe | `core/blast_model.py:172-329` | ✅ |
| IDW energy density a lo largo del perfil | `core/blast_model.py:332-414` | ✅ |
| Advisor cuantitativo de ajuste de PF | `core/blast_advisor.py:132-232` | ✅ |
| Ratios D&B (stemming, subdrilling, S/B, kg/m, Kuznetsov) | `core/blast_metrics.py:56-256` | ✅ |
| Reportes Excel / Word / DXF / dashboard | `core/excel_writer.py`, `core/report_generator.py` | ✅ |

**Conclusion**: el proyecto tiene una base geometrica solida pero **es unidimensional**: solo ve el talud como secuencia de bancos. Toda la dimension geotecnica (macizo, discontinuidades, agua, mecanismo de falla, FS, tiempo) **no existe**.

---

## 2. Seccion A — Mejoras en DETECCION / EXTRACCION geotecnica

Estas mejoras dotan al extractor de capacidades que ya son **estandar en consultoria geotecnica de talud** (Hoek & Bray 1981, Read & Stacey 2009) y que la auditoria previa no toco porque estaba enfocada en tronadura.

### A.1 Deteccion de **overhangs / bloques sueltos en la cresta** ⭐ Quick win #1

**Por que es la mejora #1 de toda la auditoria**: un overhang (cresta que se proyecta hacia adelante del toe del banco siguiente) es el precursor mas clasico de **falla planar** segun Hoek & Bray. Hoy el extractor (`core/param_extractor.py:308-315`) usa la mascara `d_min..d_max` entre crest y toe **por banco individual**, pero no chequea si la cresta del banco N+1 esta **detras** (hacia el pit) del toe del banco N. Si esto ocurre, hay un bloque en voladizo.

**Computabilidad**: alta. Requiere solo los `crest_distance` y `toe_distance` que ya estan en cada `BenchParams` (`core/param_extractor.py:65-79`).

**Logica** (sketch, no codigo de produccion):

```python
for i in range(len(benches) - 1):
    bn, bn1 = benches[i], benches[i+1]
    # horizontal_overhang_m > 0 indica overhang
    overhang_m = bn.crest_distance - bn1.toe_distance  # si >0, overhang
    # vertical_separation_m: si es positivo, hay puente de roca
    # si es negativo, el overhang "cuelga" sobre vacio
```

**Archivo a tocar**: `core/param_extractor.py` (nueva funcion `_detect_overhangs_and_bridges`, ~80 lineas) + tests en `tests/test_param_extractor.py`.

**Impacto en estabilidad**: **muy alto**. Un overhang > 0.5 m es flag amarillo; > 1.5 m es flag rojo (ver Lorig & Varona 2004, "Guidelines for Open Pit Slope Design", cap. 8).

**Datos requeridos**: ninguno nuevo. Computable hoy.

### A.2 Deteccion de **rock bridges** (puentes de roca entre bermas)

Un **rock bridge** es la porcion de macizo no removido entre el toe de un banco y la cresta del siguiente. Es **el indicador clave de estabilidad** segun Lorig & Varona (2004): un puente de roca ancho y competente es la diferencia entre un talud estable y uno que falla progresivamente.

**Computabilidad**: alta. Es el complemento del overhang:

```python
for i in range(len(benches) - 1):
    bn, bn1 = benches[i], benches[i+1]
    bridge_width_m = bn1.crest_distance - bn.toe_distance  # positivo = puente existe
    bridge_height_m = bn.toe_elevation - bn1.crest_elevation  # positivo = puente vertical
    # rock_bridge_thickness = min(bridge_width_m, bridge_height_m)
```

**Semantica geotecnica**:
- `bridge_width_m < 0`: overhang (caso A.1)
- `0 <= bridge_width_m < effective_berm_width`: berma erosionada / precorte fallido
- `bridge_width_m >= effective_berm_width`: berma sana

**Archivo a tocar**: misma funcion que A.1; reporte en `core/report_generator.py`.

**Impacto en estabilidad**: alto. Sin rock bridge detection, el sistema no puede distinguir entre "banco con berma de 6 m" y "banco donde la berma de diseno de 6 m quedo reducida a 1 m por erosion de precorte".

### A.3 Deteccion de **wedge failures potenciales** (Markland test, cinematico)

**Estado actual**: cero. No hay analisis de discontinuidades. El pipeline no sabe nada de la **orientacion de las familias de discontinuidades** que controlan la estabilidad del talud.

**Markland test** (Markland 1972, luego Hoek & Bray 1981 cap. 7): para que ocurra una falla por cuña, la interseccion de dos discontinuidades debe "daylight" en la cara del talud, es decir:
- `dip_interseccion < dip_cara` (la linea de interseccion buza menos que la cara, aflora en el talud)
- `dip_direccion_interseccion` cae dentro del rango de buzamiento de la cara

**Computabilidad**: **NO es computable solo con la geometria actual**. Requiere orientacion de familias de discontinuidades (dip/dip-direction), que es dato externo del modelo geologico (Leapfrog/Vulcan) o de mapeo de superficie. Ver Seccion E.

**Sin embargo, el sistema PUEDE** entregar un proxy geometrico: contar intersecciones de segmentos del perfil que forman **angulos diedros agudos** (< 60°) en la cara del banco — esos vertices del RDP son candidatos a wedge shape. Esto es un **proxy debil** pero util como filtro previo: si el perfil no muestra vertices diedros agudos en la cara, no hay wedge.

**Logica** (sketch):

```python
def detect_wedge_shape_in_face(face_pts_sorted_by_elev):
    # calcular angulos diedros entre segmentos consecutivos de la cara
    # flag si hay diedro < 60° dentro de la cara (no en cresta ni toe)
```

**Archivo a tocar**: nueva funcion en `core/param_extractor.py` (~50 lineas). Proxy debil pero computable hoy.

**Impacto**: medio (solo proxy) → alto (cuando se cruce con datos reales de discontinuidades, Seccion E).

### A.4 Deteccion de **toppling** (volcamiento) en caras empinadas

**Toppling** es falla por rotacion de bloques columnares cuando la cara es muy empinada respecto a una familia de discontinuidades que buza hacia el pit (anti-dip). Read & Stacey (2009) lo describen como el segundo mecanismo mas frecuente en open pit despues de planar y cuña.

**Estado actual**: el extractor (`core/param_extractor.py:294-296`) descarta bancos con `bench_height < DETECTION.min_bench_height` (2 m), pero **no chequea la relacion angulo de cara vs angulo de la cara opuesta** que indicaria potencial de toppling.

**Computabilidad**: requiere **dos secciones paralelas** (la cara y la cara opuesta del pit) para calcular la relacion de toppling. **Hoy solo se procesa una seccion por llamada** a `extract_parameters`. Esto requiere extension del modelo de datos: ver Seccion E (integracion con modelo geologico) y Seccion C (monitoreo temporal) para deteccion robusta.

**Proxy debil computable hoy**: si `face_angle > 80°` Y `bench_height > 20 m` (banco alto y muy empinado), flag de "toppling potential" con disclaimer de que requiere validacion con discontinuidades.

**Archivo a tocar**: nueva funcion `_flag_toppling_potential` en `core/param_extractor.py` (~30 lineas).

**Impacto**: medio como proxy. **Alto** cuando se combine con datos estructurales (Seccion E).

### A.5 **Bench face angle vs design vs ramp angle consistency**

**Estado actual**: `param_extractor.py:60-79` calcula `face_angle` por banco. `core/excel_writer.py:122-123,236-242` reporta `inter_ramp_angle` y `overall_angle`. Pero **no hay chequeo de consistencia**: si la cara del banco es 75° pero el angulo inter-rampa es 50°, hay una **inconsistencia** que sugiere deteccion erronea de bermas (falsa rampa) o presencia de bancos no detectados.

**Logica**: comparar `mean(face_angle)` vs `arctan(sum(bench_height) / sum(horizontal_run))`. Si difieren en >5°, flag de inconsistencia geometrica.

**Computable hoy**: si, con los datos en `ExtractionResult`.

**Archivo**: nuevo metodo `ExtractionResult.check_geometry_consistency()` en `core/param_extractor.py` (~40 lineas).

**Impacto**: medio-alto. Detecta errores sistematicos del extractor que **hoy pasan inadvertidos**.

### A.6 Deteccion de **catch bench effectiveness** (ancho efectivo vs teorico)

**Concepto**: Read & Stacey (2009) definen que la **efectividad** de una berma de retencion (catch bench) depende no solo de su ancho teorico sino del **ancho efectivo despues de la sobre-excavacion**. Una berma de diseno de 8 m que despues de tronadura tiene solo 5 m efectivos (por spill pile + sobre-excavacion del pie) **no retiene** una caida de rocas de 2 m de diametro.

**Estado actual**: `core/param_extractor.py:77` ya tiene `effective_berm_width = max(berm_width - spill_width, 0.0)` en el dataclass `BenchParams`. **Esto ya esta computado** pero **no se usa como flag** ni se reporta.

**Mejora propuesta**: agregar `catch_bench_effectiveness_pct = effective_berm_width / berm_design` y un flag binario `catch_bench_adequate` basado en el criterio de Ritchie (1963) modificado por Hoek:

```
required_catch_berm_width = bench_height * (1 - tan(slough_angle)/tan(face_angle))
```

donde `slough_angle` ≈ 35° (angulo de reposo del material de spill).

**Computable hoy**: si, con `BenchParams` y `TOLERANCES.berm_width['min']` como umbral.

**Archivo**: nuevo metodo en `core/param_extractor.py` + reporte en Excel.

**Impacto**: alto. Es el indicador #1 de riesgo de caida de rocas en open pit segun la guia de seguridad de SME.

### A.7 Deteccion de **slope drainage problems** (acumulacion de agua en bermas)

**Concepto**: una berma con pendiente transversal < 2% acumula agua, lo que (a) reduce la resistencia al corte del material de spill y (b) genera presion de poros en el macizo detras de la cara.

**Estado actual**: cero. La geometria se reduce a perfil 2D.

**Computabilidad**: **requiere modelo 3D** del pit o al menos **multiples secciones paralelas** para interpolar la pendiente transversal de cada berma. Esto es **NO computable con una sola seccion**.

**Sin embargo**: se puede computar un **proxy debil** con la variabilidad transversal: si se tienen N secciones paralelas del mismo banco, calcular `std(berm_elevation) / mean(berm_width)` como indicador de irregularidad → mayor irregularidad → mayor probabilidad de "puntos bajos" que acumulen agua.

**Archivo**: nueva funcion en `core/param_extractor.py` que recibe lista de perfiles paralelos (~60 lineas).

**Impacto**: medio (proxy). Alto cuando se tenga modelo 3D.

### A.8 **Anisotropia del talud** (orientacion de caras detectadas vs discontinuidades tipicas)

**Concepto**: si la direccion de buzamiento de las caras detectadas esta alineada con la direccion de buzamiento de una familia de discontinuidades tipica del sector, el riesgo de falla planar aumenta (condicion "daylight" en el talud).

**Estado actual**: cero. No se cruza orientacion de caras con orientacion de discontinuidades.

**Computabilidad**: la **orientacion de cada cara detectada** es computable hoy: el angulo de cara esta en `BenchParams.face_angle` y la orientacion horizontal se puede estimar del `azimuth` de la seccion + el signo del `delta_crest`. **Pero la orientacion de discontinuidades NO esta disponible** → requiere integracion externa (Seccion E).

**Archivo** (proxy debil): nueva funcion `compute_face_orientation(bench, section_azimuth)` (~30 lineas).

**Impacto**: bajo como proxy. **Muy alto** cuando se integre con modelo geologico.

### A.9 Resumen Seccion A

| # | Mejora | Tipo | Computable hoy | Impacto estabilidad | Esfuerzo | Archivos |
|---|---|---|---|---|---|---|
| A.1 | Overhangs / bloques sueltos en cresta | calc | ✅ | Muy alto | Bajo (~80 ldc) | `param_extractor.py` |
| A.2 | Rock bridges (puentes de roca) | calc | ✅ | Alto | Bajo (~50 ldc) | `param_extractor.py` |
| A.3 | Wedge shape (proxy diedros agudos) | calc | ✅ parcial | Medio | Bajo (~50 ldc) | `param_extractor.py` |
| A.4 | Toppling potential (proxy face_angle alto) | calc | ✅ parcial | Medio | Bajo (~30 ldc) | `param_extractor.py` |
| A.5 | Consistencia face_angle vs inter-ramp | calc | ✅ | Medio-alto | Bajo (~40 ldc) | `param_extractor.py` |
| A.6 | Catch bench effectiveness | calc | ✅ | Alto | Bajo (~40 ldc) | `param_extractor.py` + excel_writer |
| A.7 | Slope drainage (proxy) | calc | ⚠️ requiere N secciones | Medio | Medio (~60 ldc) | `param_extractor.py` |
| A.8 | Anisotropia (orientacion de caras) | calc+ext | ⚠️ proxy debil | Bajo→Muy alto | Bajo (~30 ldc) | `param_extractor.py` |

**Total esfuerzo**: ~380 lineas + 30 tests.

---

## 3. Seccion B — Mejoras en ESTABILIDAD / ANALISIS estructural simplificado

### B.1 **Factor de seguridad simplificado por banco** (geometrico + RMR estimado)

**Estado actual**: cero. El pipeline no calcula FS.

**Concepto**: el FS de un talud de banco depende de (Hoek & Bray 1981, cap. 4):
- `FS = (c·A + W·cos(ψ_f)·tan(φ)) / (W·sin(ψ_f))` (falla planar)
- donde `ψ_f` = angulo de la cara, `φ` = friccion del macizo, `c` = cohesion, `W` = peso, `A` = area de la base.

**Sin valores de `c` ni `φ`** no se puede calcular FS directamente. Pero la industria usa **guias empiricas** (Hoek 2006 "Practical Rock Engineering") que estiman `c` y `φ` a partir del **GSI estimado del macizo** + **UCS de la roca intacta**.

**Computabilidad parcial**:
- Si el usuario ingresa **GSI** (lookup por litologia, ver Seccion E) y **UCS** (lookup por banco), el sistema puede estimar `c` y `φ` usando el criterio Hoek-Brown y calcular FS.
- Si no, **devolver un proxy geometrico**: `FS_proxy = tan(φ_typical) / tan(face_angle)` con `φ_typical = 35°` (macizo moderado). Esto da un FS minimo asumido que **siempre subestima el FS real** (lado conservador).

**Archivo**: nuevo modulo `core/stability_analysis.py` (~250 lineas):
- `estimate_rock_strength(gsi, ucs_mpa, mi)` → `(c_kpa, phi_deg)` via Hoek-Brown
- `compute_planar_factor_of_safety(bench, c_kpa, phi_deg, water_pressure_ratio)` → `FS`
- `compute_wedge_factor_of_safety(bench, j1, j2, c_kpa, phi_deg)` → `FS`
- `compute_toppling_factor_of_safety(...)` → `FS_proxy` (toppling es cinematico, no FS puro)

**Impacto**: **muy alto**. El FS es el indicador #1 que solicita cualquier ingeniero de taludes. Hoy el sistema no lo entrega.

**Tests**: ~20 tests (parametrizados sobre GSI, UCS, phi, geometrias).

### B.2 **Probabilidad de falla por sector** (back-analysis historico)

**Concepto**: si en el pasado un sector ha mostrado sobre-excavaciones recurrentes, la probabilidad de que la siguiente campana tenga una falla es mayor. Modelo tipico de "PoF = P(FS<1) en condicion operacional".

**Computabilidad**: alta. El sistema ya tiene `delta_crest` y `delta_toe` por seccion (`core/param_extractor.py:854-855`) y `compute_signed_deviations` (`core/blast_correlation.py:297-352`). Se puede:

1. Acumular `|delta_crest|` historico por `sector` + `level` (banco).
2. Ajustar distribucion lognormal o beta a los datos.
3. Estimar `PoF = P(|delta| > umbral_critico)` donde umbral_critico ≈ 2× tolerancia.

**Estado actual**: **parcial**. Hay serie temporal (`docs/BLAST_DATA_AUDIT.md` Seccion E) pero no se traduce a PoF.

**Archivo**: nueva funcion `estimate_pof_by_sector(history_df, critical_m)` en `core/blast_model.py` o nuevo `core/stability_analysis.py` (~80 lineas).

**Impacto**: alto. Es el complemento cuantitativo del "FS estimado" de B.1.

### B.3 **Pseudo-aceleracion maxima tolerable** (sismic equivalence)

**Concepto**: en zonas sismicas, el talud debe resistir una pseudo-aceleracion `k_h · g` (donde `k_h` es el coeficiente sismico horizontal). Para falla planar:

```
FS_steady = FS_static
FS_seismic = (c·A + W·cos(ψ_f - ψ_p)·tan(φ)) / (W·sin(ψ_f - ψ_p))
```

donde `ψ_p = arctan(k_h / (1 - k_v))` es el angulo sismico equivalente.

**Estado actual**: cero. No hay consideracion sismica.

**Computabilidad**: requiere `c`, `φ` (mismos inputs que B.1) + `k_h` regional (input del usuario o tabla por zona sismica). Con GSI + UCS disponibles, **es 100% automatizable**.

**Archivo**: nueva funcion `compute_seismic_factor_of_safety(bench, kh, kv)` en `core/stability_analysis.py` (~60 lineas).

**Impacto**: alto en zonas sismicas (Chile, Peru). Bajo a medio en zonas asismicas.

### B.4 **Markland test cinematico** (planar, wedge, toppling)

**Estado actual**: cero. No hay implementacion del test de Markland.

**Computabilidad**: requiere **orientacion de discontinuidades** (input externo). Ver Seccion E.

**Sin embargo, computable como "alerta preventiva"**:
- Si `face_angle > 75°` Y `bench_height > 15 m` → alerta de planar potencial.
- Si el perfil muestra diedros agudos < 60° en la cara → alerta wedge.
- Si `face_angle > 80°` Y el banco esta en el upper pit (donde la liberacion es mayor) → alerta toppling.

**Archivo**: nueva funcion `markland_screening(face_angle, bench_height, position)` en `core/stability_analysis.py` (~80 lineas).

**Impacto**: medio-alto como screening automatico. **Muy alto** cuando se cruza con discontinuidades reales.

### B.5 **Back-analysis** (estimar parametros resistentes desde sobre-excavacion observada)

**Concepto**: si el talud **NO ha fallado** pero muestra sobre-excavacion `δ`, se puede inferir que el FS en el punto de operacion esta entre 1.0 (limite de falla) y ~1.3 (operacion normal con dano). De ahi se puede estimar un rango de `(c, φ)` compatibles con la geometria observada.

**Estado actual**: cero.

**Computabilidad**: alta. Requiere geometria del banco (disponible) + asumir `FS_actual` ∈ [1.0, 1.3] y resolver para `(c, φ)`. Es una inversion analitica directa de la ecuacion de FS planar.

**Archivo**: nueva funcion `back_analyze_resistance(face_angle, bench_height, fs_assumed_range)` en `core/stability_analysis.py` (~100 lineas).

**Impacto**: alto. Permite calibrar el modelo con datos reales del pit **sin necesidad de ensayos de laboratorio**.

### B.6 **Sensitivity analysis** (como varia FS con PF, burden, etc.)

**Concepto**: si cambiar PF de 0.35 a 0.50 kg/m³ cambia la sobre-excavacion de 0.3 m a 0.8 m (segun el modelo PF→damage de `core/blast_model.py`), eso cambia el FS aparente del banco:

```
FS_post = f(face_angle + arctan(delta_h / bench_height))
```

**Estado actual**: el modelo PF→damage existe pero **no se conecta al FS**.

**Computabilidad**: alta. Encadenar `predict_damage_for_pf()` (`core/blast_model.py:136-169`) → recalcular `face_angle_post` → recalcular `FS_post`.

**Archivo**: nueva funcion `sensitivity_analysis_fs(model, pf_range)` en `core/stability_analysis.py` (~120 lineas). Salida: tabla `(PF, delta_h, FS, status)` + grafico tornado.

**Impacto**: alto. Cierra el ciclo "tronadura → dano → estabilidad" que el blast_advisor solo deja implícito.

### B.7 Prediccion de **dilucion** (overbreak → dilution en mineria)

**Concepto**: en mineria, la sobre-excavacion del talud lateral se traduce directamente en **dilucion**: roca estéril o de baja ley que entra al flujo de mineral. La dilución tipica es 5-15% del volumen del banco.

**Estado actual**: cero. El sistema mide sobre-excavacion geometrica pero no la traduce a impacto economico.

**Computabilidad**: alta, asumiendo densidad de roca y ley del sector:

```python
dilution_pct = (overbreak_volume / in_situ_volume) * 100
overbreak_value_usd = dilution_pct * tons * (grade_waste - grade_ore) * price
```

**Archivo**: nueva funcion `estimate_dilution_and_cost(overbreak_m, bench_length, density, grade_waste, grade_ore, price_usd_per_ton)` en `core/stability_analysis.py` (~60 lineas).

**Impacto**: medio. Da dimension economica al sobre-excavation, **conecta geotecnia con finanzas**.

### B.8 **Slope stability radar por sector** (resumen visual de salud)

**Concepto**: grafico de radar (araña) por sector con 5-7 ejes: `FS`, `catch_bench_effectiveness`, `overhangs_count`, `toppling_risk`, `wedge_risk`, `PoF`, `drainage_score`. Cada eje es una dimension de salud del talud.

**Estado actual**: `core/report_generator.py:259-266` ya usa pie/donut charts pero no radar.

**Computabilidad**: requiere que las metricas A.1-A.6 + B.1-B.7 existan. Cuando esten, el radar es una capa de visualizacion.

**Archivo**: nuevo metodo en `core/report_generator.py` (~150 lineas con matplotlib radar).

**Impacto**: alto en comunicacion a stakeholders no tecnicos.

### B.9 Resumen Seccion B

| # | Mejora | Tipo | Computable hoy | Impacto | Esfuerzo | Archivos |
|---|---|---|---|---|---|---|
| B.1 | Factor de seguridad simplificado | calc+ext | ⚠️ requiere GSI/UCS | Muy alto | Alto (~250 ldc) | nuevo `stability_analysis.py` |
| B.2 | Probabilidad de falla por sector | calc | ✅ | Alto | Medio (~80 ldc) | `blast_model.py` o nuevo |
| B.3 | Pseudo-aceleracion tolerable (sismic) | calc+ext | ⚠️ requiere GSI/UCS + kh | Alto (Chile) | Medio (~60 ldc) | nuevo `stability_analysis.py` |
| B.4 | Markland screening cinematico | calc+ext | ✅ parcial | Medio-alto | Medio (~80 ldc) | nuevo |
| B.5 | Back-analysis parametros resistentes | calc | ✅ | Alto | Alto (~100 ldc) | nuevo |
| B.6 | Sensitivity FS vs PF | calc | ✅ | Alto | Medio (~120 ldc) | nuevo |
| B.7 | Dilucion + impacto economico | calc | ⚠️ requiere densidad/ley/precio | Medio | Bajo (~60 ldc) | nuevo |
| B.8 | Slope stability radar | calc+UI | ⚠️ requiere A.1-A.6 + B.1-B.7 | Alto (visual) | Medio (~150 ldc) | `report_generator.py` |

---

## 4. Seccion C — Mejoras en MONITOREO / SEGUIMIENTO

### C.1 **Tendencia temporal del angulo de cara por banco**

**Concepto**: el angulo de cara puede variar entre levantamientos topo. Una **tendencia sostenida al aumento** (cara poniendose mas empinada) es indicador de **erosion progresiva** o **deformacion del talud**.

**Computabilidad**: si el usuario carga **multiples STL con timestamps** (hoy no implementado, ver `docs/BLAST_DATA_AUDIT.md` C.3.1), el sistema puede calcular `d(face_angle)/dt` por banco.

**Estado actual**: el sistema procesa **un STL por sesion**. Para tener serie temporal hay que **iterar manualmente** o **guardar resultados en BD** (SQLite ya existe en `core/config.py:86`).

**Archivo**: nuevo modulo `core/temporal_monitor.py` (~200 ldc):
- `MultiSurveyResult` dataclass con resultados por timestamp.
- `compute_face_angle_trend(bench_history)` → `(slope, p_value, alert)`.

**Impacto**: alto. Es la base del monitoreo de salud del talud.

### C.2 **Tendencia temporal del ancho de berma**

**Concepto**: igual que C.1 pero para `effective_berm_width`. La perdida de berma es **el indicador temprano #1** de inestabilidad progresiva (Lorig & Varona 2004).

**Computabilidad**: misma que C.1.

**Archivo**: misma estructura, `compute_berm_width_trend`.

**Impacto**: muy alto.

### C.3 **Deformation rate estimado entre dos levantamientos**

**Concepto**: `deformation_rate = displacement / Δt`. Si el sistema puede comparar dos levantamientos consecutivos y medir el desplazamiento horizontal/vertical de puntos homólogos (crestas, toes), puede dar una **tasa de deformacion** que se compara con umbrales empiricos de Read & Stacey:

- `< 1 mm/dia`: estable
- `1-5 mm/dia`: alerta amarilla
- `5-50 mm/dia`: alerta naranja (instrumentar)
- `> 50 mm/dia`: alerta roja (evacuar)

**Estado actual**: cero. No hay comparacion temporal.

**Computabilidad**: requiere **dos levantamientos**. Hoy hay que correr el pipeline dos veces y comparar resultados manualmente.

**Archivo**: nuevo `core/temporal_monitor.py` con funcion `compute_deformation_rate(survey_t0, survey_t1)`.

**Impacto**: muy alto. Es la metrica que todos los sistemas de monitoreo (radar, prismas) entregan.

### C.4 **Critical bench identification** (banco mas debil)

**Concepto**: aplicar reglas empiricas (Hoek, Read & Stacey) para identificar el banco mas debil del pit. Reglas:

1. Banco con `effective_berm_width < berm_min` → flag.
2. Banco con `overhang > 0` → flag.
3. Banco con `face_angle > 75°` Y `bench_height > 20 m` → flag.
4. Banco con `|delta_crest|` mas alto del sector → flag.
5. Banco con `toppling_risk = TRUE` → flag.

Un puntaje ponderado ordena los bancos por criticidad.

**Estado actual**: cero.

**Computabilidad**: alta con los datos en `BenchParams` + las metricas de Seccion A.

**Archivo**: nuevo `core/critical_bench.py` (~150 ldc).

**Impacto**: alto. Es directamente accionable: "ir a verificar el banco 4270".

### C.5 **Alert system** (notificaciones automaticas por umbral)

**Concepto**: dado un `BenchParams`, evaluar contra umbrales criticos y emitir alertas categorizadas (GREEN/YELLOW/ORANGE/RED).

**Estado actual**: solo `core/param_extractor.py:488-503` emite CUMPLE/FUERA/NO_CUMPLE basado en tolerances. Pero no hay sistema de alertas categoricas (semáforo).

**Computabilidad**: alta, **wrapper** sobre las metricas A.1-A.6 + B.1.

**Archivo**: nuevo `core/alert_system.py` (~120 ldc):
- `evaluate_bench_health(bench)` → `{health: 'GREEN', flags: [...], recommended_action: '...'}`
- Hooks para notificacion (email, Slack) via configuracion.

**Impacto**: alto en operaciones.

### C.6 **Health score por seccion** (0-100, tipo semaforo)

**Concepto**: combinar todas las metricas A+B en un **score unico 0-100** por seccion, donde:
- `90-100`: GREEN (operacion normal)
- `75-89`: YELLOW (revisar)
- `50-74`: ORANGE (investigar)
- `< 50`: RED (parar / instrumentar)

Formula sugerida (referencia, requiere calibracion):
```
health = 0.30*FS_score + 0.20*berm_score + 0.20*overhang_score + 
         0.15*wedge_score + 0.10*toppling_score + 0.05*drainage_score
```

**Estado actual**: `core/param_extractor.py:932-934` ya tiene un `section_score` (promedio de `bench_score`), pero **no es un health score geotecnico**: solo pondera cumplimiento de tolerances geometricas.

**Computabilidad**: requiere metricas A+B. Hoy no se puede computar completamente.

**Archivo**: nueva funcion `compute_health_score(section_metrics)` en `core/stability_analysis.py` (~80 ldc).

**Impacto**: muy alto en dashboards ejecutivos.

### C.7 Resumen Seccion C

| # | Mejora | Tipo | Impacto | Esfuerzo | Archivos |
|---|---|---|---|---|---|
| C.1 | Tendencia face angle | temporal | Alto | Alto (~200 ldc) | nuevo `temporal_monitor.py` |
| C.2 | Tendencia berm width | temporal | Muy alto | Alto (compartido C.1) | mismo |
| C.3 | Deformation rate | temporal | Muy alto | Alto | mismo |
| C.4 | Critical bench ID | calc | Alto | Medio (~150 ldc) | nuevo `critical_bench.py` |
| C.5 | Alert system | calc+UI | Alto | Medio (~120 ldc) | nuevo `alert_system.py` |
| C.6 | Health score 0-100 | calc | Muy alto | Medio (~80 ldc) | `stability_analysis.py` |

---

## 5. Seccion D — Mejoras en OPTIMIZACION del diseno (forward-looking)

### D.1 **Bench geometry optimizer**

**Concepto**: dada una calidad de roca (RQD o GSI) y un angulo de cara objetivo, encontrar la combinacion `(bench_height, berm_width)` optima que cumple:
- `FS_banco >= 1.3` (criterio estandar de banco individual)
- `catch_bench_width >= bench_height * tan(60°) - bench_height * tan(face_angle)` (criterio de retencion de caida de rocas)

**Estado actual**: cero. El diseno es estatico (provisto por el usuario).

**Computabilidad**: alta. Es un problema de optimizacion con restricciones:
- Variables: `(bench_height, berm_width)`
- Restricciones: FS_min, catch_bench_min
- Objetivo: maximizar angulo inter-rampa (talud mas agresivo = menos volumen de excavacion)

**Archivo**: nuevo `core/design_optimizer.py` (~250 ldc) usando `scipy.optimize.minimize`.

**Impacto**: muy alto. Permite al ingeniero **explorar el espacio de diseno** sistematicamente en lugar de iterar manualmente.

### D.2 **Slope angle optimizer**

**Concepto**: dado un angulo global objetivo (ej. 50°), encontrar la distribucion optima de angulos inter-rampa que cumple:
- Suma de angulos inter-rampa = angulo global (restriccion geometrica)
- Cada angulo inter-rampa <= FS-driven maximo
- Bermas y rampas compatibles con la operacion minera

**Estado actual**: cero.

**Computabilidad**: alta (programacion lineal o no-lineal).

**Archivo**: misma estructura que D.1, otro escenario.

**Impacto**: alto.

### D.3 **Sensitivity to PF** (que angulo de cara se obtiene si cambia PF)

**Concepto**: conectar el modelo PF→damage (`core/blast_model.py:45-133`) con el calculo de FS (B.1). Para un PF dado, predecir `face_angle_post = face_angle_design + arctan(delta_h / bench_height)`, luego calcular `FS_post`.

**Estado actual**: el modelo PF→damage existe pero **no se conecta al FS**. El usuario debe hacerlo mentalmente.

**Computabilidad**: alta, ya hay todos los ingredientes.

**Archivo**: nueva funcion en `core/design_optimizer.py` (~80 ldc). Salida: tabla `(PF, delta_h, face_angle_post, FS_post)`.

**Impacto**: alto. Cierra el ciclo "tronadura → dano → FS → decision".

### D.4 **What-if scenarios** (probar configuraciones alternativas de tronadura)

**Concepto**: UI que permita al usuario explorar:

```
PF_actual → PF_objetivo
  → delta_h_pred (modelo PF→damage)
  → face_angle_post
  → FS_post
  → catch_bench_post
  → recomendacion: SI/NO ajustar
```

**Estado actual**: el `blast_advisor.py` cubre la parte PF, pero **no encadena** los efectos hasta FS.

**Archivo**: nueva capa en `core/design_optimizer.py` + UI.

**Impacto**: alto en el flujo de trabajo del ingeniero.

### D.5 Resumen Seccion D

| # | Mejora | Tipo | Impacto | Esfuerzo | Archivos |
|---|---|---|---|---|---|
| D.1 | Bench geometry optimizer | calc | Muy alto | Alto (~250 ldc) | nuevo `design_optimizer.py` |
| D.2 | Slope angle optimizer | calc | Alto | Medio (~150 ldc) | mismo |
| D.3 | Sensitivity FS vs PF | calc | Alto | Medio (~80 ldc) | mismo |
| D.4 | What-if scenarios UI | calc+UI | Alto | Alto (~200 ldc) | mismo + UI |

---

## 6. Seccion E — Mejoras en INTEGRACION con sistemas geotecnicos externos

### E.1 **Rock Mass Rating (RMR) lookup por banco o sector**

**Concepto**: RMR (Bieniawski 1989) es el clasificador de macizo mas usado en la industria. Valor tipico: 0-100. Determina parametros resistentes (c, φ) y sostenimiento requerido.

**Estado actual**: cero.

**Fuente de datos**: el RMR viene del **mapeo geomecanico** de los sondajes + estaciones geomecanicas. Típicamente se almacena en una **tabla `rmr_por_banco.csv`** con columnas `sector`, `level`, `rmr`, `rqd`, `ucs_mpa`, `orientacion_j1_dip`, `orientacion_j1_dipdir`, etc.

**Integracion propuesta**: nuevo modulo `core/geology.py` (~150 ldc):
- `load_rmr_table(csv_path)` → DataFrame.
- `lookup_rmr(sector, level, level_tolerance_m=2.0)` → dict.
- Hook en `extract_parameters` para adjuntar `rmr` a cada `BenchParams` cuando esta disponible.

**Impacto**: muy alto. Habilita B.1, B.3, D.1.

### E.2 **Geological Strength Index (GSI)**

**Concepto**: GSI (Hoek 1995) es alternativa moderna al RMR, mejor para macizos heterogeneos. Rango 0-100. Se estima de tablas litologicas o de campo.

**Estado actual**: cero.

**Fuente**: tabla `gsi_por_litologia.csv` o calculo desde RMR via correlacion empirica `GSI = RMR - 5` (Hoek & Brown 1997, aproximada).

**Integracion**: misma estructura que E.1.

**Impacto**: muy alto. Habilita Hoek-Brown en B.1.

### E.3 **Discontinuity orientation** desde sondajes

**Concepto**: las familias de discontinuidades (juntas, fallas, estratificacion) son **el dato mas importante** para estabilidad. Cada familia tiene `(dip, dip_direction, persistencia, espaciamiento, JRC, JCS)`.

**Estado actual**: cero.

**Fuente**: archivo `.csv` con orientacion por estacion de mapeo, **o** base de datos del modelo geologico (Leapfrog, Vulcan).

**Integracion**: nuevo `core/discontinuities.py` (~300 ldc):
- `load_discontinuity_sets(csv_path)` → DataFrame con familias clusterizadas.
- `markland_test(face_orientation, discontinuity_set)` → dict con `(planar, wedge, toppling)` flags.
- Conexion con B.4.

**Impacto**: **muy alto**. Sin este dato, A.3 y A.4 quedan como proxies debiles.

### E.4 **Piezometer data** (nivel freatico por sector)

**Concepto**: el nivel freatico es **el dato que mas cambia el FS** de un talud. Un banco con `ru = 0.3` (relacion de presion de poros) puede reducir el FS de 1.5 a 1.05.

**Estado actual**: cero.

**Fuente**: CSV de piezometros con timestamp + coordenadas + nivel.

**Integracion**: nuevo `core/hydrogeology.py` (~100 ldc):
- `load_piezometers(csv_path)` → DataFrame.
- `lookup_water_table(sector, x, y, level)` → nivel freatico interpolado.
- Hook en B.1 para calcular `FS` con `ru` en lugar de seco.

**Impacto**: muy alto. Cambia el FS tipicamente en 20-40%.

### E.5 **Slope stability radar data** (time-series)

**Concepto**: el slope stability radar (SSR, ej. Reutech MSR) mide deformacion del talud con precision sub-mm cada 5-15 min. Series tipicas: 10.000+ puntos por banco.

**Estado actual**: cero.

**Fuente**: CSV/JSON del radar con timestamps + coordenadas + desplazamiento.

**Integracion**: nuevo `core/radar_data.py` (~200 ldc):
- `load_radar_csv(path)` → DataFrame.
- `compute_deformation_rate(radar_df)` → mm/dia + alertas segun umbrales Read & Stacey.
- Conexion con C.3.

**Impacto**: muy alto en operaciones con SSR instalado.

### E.6 **Prism monitoring data**

**Concepto**: prismas topograficos instalados en el talud, medidos con estacion total robotizada. Tipicamente 5-20 prismas por banco critico.

**Estado actual**: cero.

**Fuente**: CSV con `prism_id`, `timestamp`, `x, y, z`, `precision_mm`.

**Integracion**: nuevo `core/prism_monitor.py` (~150 ldc). Similar a E.5.

**Impacto**: alto (alternativa o complemento al radar).

### E.7 **Geotechnical model output** (Leapfrog/Vulcan DXF)

**Concepto**: el modelo geologico 3D del pit (litologia, RQD, alteracion) puede exportarse como DXF con atributos. Esto permite **join espacial** entre el BenchParams detectado y la litologia del modelo.

**Estado actual**: `core/mesh_handler.py:load_dxf_polyline` ya carga DXF polylines, pero **no atributos**.

**Integracion**: extender `load_dxf_polyline` para leer atributos, join espacial con benches.

**Impacto**: alto.

### E.8 Resumen Seccion E

| # | Mejora | Tipo | Impacto | Esfuerzo | Archivos |
|---|---|---|---|---|---|
| E.1 | RMR lookup | ext | Muy alto | Medio (~150 ldc) | nuevo `geology.py` |
| E.2 | GSI lookup | ext | Muy alto | Bajo (~80 ldc, similar a E.1) | mismo |
| E.3 | Discontinuity orientation | ext | **Muy alto** | Alto (~300 ldc) | nuevo `discontinuities.py` |
| E.4 | Piezometer data | ext | Muy alto | Medio (~100 ldc) | nuevo `hydrogeology.py` |
| E.5 | Slope stability radar | ext | Muy alto | Alto (~200 ldc) | nuevo `radar_data.py` |
| E.6 | Prism monitoring | ext | Alto | Alto (~150 ldc) | nuevo `prism_monitor.py` |
| E.7 | Geo model DXF atributos | ext | Alto | Medio (~150 ldc) | extender `mesh_handler.py` |

---

## 7. Roadmap priorizado (top 10)

Ordenado por **impacto en estabilidad geotecnica × esfuerzo × dependencias**.

### Posicion 1 — Overhangs + Rock bridges detection
- **Que**: anadir `_detect_overhangs_and_bridges(benches)` en `core/param_extractor.py`.
- **Impacto**: muy alto (precursor #1 de falla planar).
- **Esfuerzo**: bajo (~80 ldc + 10 tests).
- **Dependencias**: ninguna. Computable con datos existentes (`BenchParams.crest_distance`, `toe_distance`, `crest_elevation`, `toe_elevation`).
- **Archivos**: `core/param_extractor.py`, `tests/test_param_extractor.py`, `core/excel_writer.py` (reporte), `core/report_generator.py` (Word).

### Posicion 2 — Catch bench effectiveness
- **Que**: reportar `effective_berm_width / berm_design` con flag `catch_bench_adequate` segun criterio Ritchie/Hoek.
- **Impacto**: alto.
- **Esfuerzo**: bajo (~40 ldc + 5 tests). El calculo de `effective_berm_width` ya existe en `BenchParams` (`core/param_extractor.py:77,416`); solo falta exponerlo como flag.
- **Dependencias**: ninguna.
- **Archivos**: `core/param_extractor.py`, `core/excel_writer.py`.

### Posicion 3 — Health score por seccion (semáforo 0-100)
- **Que**: combinar `FS_proxy`, `effective_berm_pct`, `overhang_count`, `wedge_flag`, `toppling_flag` en un score 0-100.
- **Impacto**: muy alto en comunicacion.
- **Esfuerzo**: medio (~80 ldc + 15 tests). Requiere metricas #1 y #2 ya implementadas.
- **Dependencias**: #1, #2.
- **Archivos**: `core/stability_analysis.py` (nuevo), `core/excel_writer.py`, `core/report_generator.py`.

### Posicion 4 — RMR / GSI lookup por banco
- **Que**: modulo `core/geology.py` con carga de CSV + lookup espacial por sector/level.
- **Impacto**: muy alto. Habilita #5, #6, #7.
- **Esfuerzo**: medio (~150 ldc + 20 tests).
- **Dependencias**: input externo (CSV geotecnico del cliente). Sin ese CSV, el modulo se crea pero no opera.
- **Archivos**: nuevo `core/geology.py`, `core/config.py` (defaults de lookup), `core/__init__.py` (re-export).

### Posicion 5 — Factor de seguridad simplificado por banco
- **Que**: nueva funcion `compute_planar_factor_of_safety(bench, c_kpa, phi_deg, water_pressure_ratio)`. Sin RMR disponible, devuelve `FS_proxy = tan(35°) / tan(face_angle)`.
- **Impacto**: muy alto.
- **Esfuerzo**: alto (~250 ldc + 20 tests).
- **Dependencias**: #4 (preferible) o estimacion interna.
- **Archivos**: nuevo `core/stability_analysis.py`, tests.

### Posicion 6 — Markland screening cinematico (proxy)
- **Que**: screening automatico basado en `face_angle` + `bench_height` + geometria del perfil (diedros agudos). Marca planar / wedge / toppling potential.
- **Impacto**: alto como screening.
- **Esfuerzo**: medio (~120 ldc + 15 tests).
- **Dependencias**: #1 (overhang), A.3 (wedge proxy).
- **Archivos**: `core/stability_analysis.py`, `core/param_extractor.py`.

### Posicion 7 — Discontinuity orientation import + Markland test real
- **Que**: modulo `core/discontinuities.py` con carga CSV de discontinuidades + Markland test contra orientacion de cara detectada.
- **Impacto**: **muy alto** (cierra la principal brecha del sistema).
- **Esfuerzo**: alto (~300 ldc + 30 tests).
- **Dependencias**: input externo (CSV de mapeo geomecanico).
- **Archivos**: nuevo `core/discontinuities.py`.

### Posicion 8 — Sensitivity FS vs PF
- **Que**: conectar `blast_model.predict_damage_for_pf` con `compute_planar_factor_of_safety` para entregar tabla `(PF, delta_h, FS_post)`.
- **Impacto**: alto (cierra el ciclo tronadura → estabilidad).
- **Esfuerzo**: medio (~80 ldc + 10 tests).
- **Dependencias**: #5 (FS), modelo blast existente (`core/blast_model.py`).
- **Archivos**: `core/stability_analysis.py`, `core/blast_model.py` (integracion).

### Posicion 9 — Critical bench identification
- **Que**: nueva funcion `identify_critical_benches(sections_results)` que aplica reglas Hoek/Read&Stacey y ordena bancos por criticidad.
- **Impacto**: alto (directamente accionable en operaciones).
- **Esfuerzo**: medio (~150 ldc + 15 tests).
- **Dependencias**: #1, #2, #3, #5, #6.
- **Archivos**: nuevo `core/critical_bench.py`, `core/excel_writer.py`.

### Posicion 10 — Slope stability radar visual
- **Que**: spider/radar chart por seccion con 5-7 ejes de salud.
- **Impacto**: alto en comunicacion a stakeholders.
- **Esfuerzo**: medio (~150 ldc + 10 tests en matplotlib).
- **Dependencias**: #3 (health score), todas las metricas A+B.
- **Archivos**: `core/report_generator.py`, UI.

---

## 8. Tabla resumen final

Leyenda tipo: **calc** = computable hoy / **input** = requiere nueva columna del CSV / **ext** = requiere integracion externa / **partial** = proxy debil computable, mejora con datos externos.

| # | Mejora | Tipo | Impacto estabilidad | Esfuerzo | Prioridad | Archivo principal |
|---|---|---|---|---|---|---|
| **A.1** | Overhangs / bloques sueltos | calc | Muy alto | Bajo | 1 | `param_extractor.py` |
| **A.2** | Rock bridges | calc | Alto | Bajo | 1 | `param_extractor.py` |
| **A.3** | Wedge shape (proxy diedros) | partial | Medio | Bajo | 2 | `param_extractor.py` |
| **A.4** | Toppling potential (proxy) | partial | Medio | Bajo | 3 | `param_extractor.py` |
| **A.5** | Consistencia face vs inter-ramp | calc | Medio-alto | Bajo | 2 | `param_extractor.py` |
| **A.6** | Catch bench effectiveness | calc | Alto | Bajo | 1 | `param_extractor.py` |
| **A.7** | Slope drainage (proxy) | partial | Medio | Medio | 4 | `param_extractor.py` |
| **A.8** | Anisotropia de caras | partial | Bajo→Muy alto | Bajo | 3 | `param_extractor.py` |
| **B.1** | Factor de seguridad planar | ext (mejor) | Muy alto | Alto | 5 | nuevo `stability_analysis.py` |
| **B.2** | Probabilidad de falla por sector | calc | Alto | Medio | 3 | `blast_model.py` |
| **B.3** | Pseudo-aceleracion (sismic) | ext | Alto (zonas sismicas) | Medio | 4 | `stability_analysis.py` |
| **B.4** | Markland screening (proxy) | partial | Medio-alto | Medio | 6 | `stability_analysis.py` |
| **B.5** | Back-analysis | calc | Alto | Alto | 4 | `stability_analysis.py` |
| **B.6** | Sensitivity FS vs PF | calc | Alto | Medio | 8 | `stability_analysis.py` |
| **B.7** | Dilucion + costo economico | partial | Medio | Bajo | 4 | `stability_analysis.py` |
| **B.8** | Slope stability radar visual | UI | Alto (comunicacion) | Medio | 10 | `report_generator.py` |
| **C.1** | Tendencia face angle | temporal | Alto | Alto | 7 | nuevo `temporal_monitor.py` |
| **C.2** | Tendencia berm width | temporal | Muy alto | Alto (compartido) | 7 | mismo |
| **C.3** | Deformation rate | temporal | Muy alto | Alto | 7 | mismo |
| **C.4** | Critical bench ID | calc | Alto | Medio | 9 | nuevo `critical_bench.py` |
| **C.5** | Alert system | calc+UI | Alto | Medio | 9 | nuevo `alert_system.py` |
| **C.6** | Health score 0-100 | calc | Muy alto | Medio | 3 | `stability_analysis.py` |
| **D.1** | Bench geometry optimizer | calc | Muy alto | Alto | 11 | nuevo `design_optimizer.py` |
| **D.2** | Slope angle optimizer | calc | Alto | Medio | 11 | mismo |
| **D.3** | Sensitivity FS vs PF (opt) | calc | Alto | Medio | 8 | mismo |
| **D.4** | What-if scenarios UI | calc+UI | Alto | Alto | 12 | mismo + UI |
| **E.1** | RMR lookup | ext | Muy alto | Medio | 4 | nuevo `geology.py` |
| **E.2** | GSI lookup | ext | Muy alto | Bajo | 4 | mismo |
| **E.3** | Discontinuity orientation | ext | **Muy alto** | Alto | 7 | nuevo `discontinuities.py` |
| **E.4** | Piezometer data | ext | Muy alto | Medio | 5 | nuevo `hydrogeology.py` |
| **E.5** | Slope stability radar data | ext | Muy alto | Alto | 7 | nuevo `radar_data.py` |
| **E.6** | Prism monitoring | ext | Alto | Alto | 8 | nuevo `prism_monitor.py` |
| **E.7** | Geo model DXF atributos | ext | Alto | Medio | 6 | `mesh_handler.py` |

### Conteo rapido

- **Total mejoras identificadas**: 31 (A: 8, B: 8, C: 6, D: 4, E: 7, descontando duplicaciones logicas).
- **Computables hoy sin nuevos inputs** (incluyendo proxies parciales): **19** (~61%).
- **Requieren input externo** (CSV geotecnico del cliente): **12** (~39%).
- **Impacto Muy alto**: **14** mejoras (~45%).
- **Bajo esfuerzo + Alto impacto**: **6** (A.1, A.2, A.6, B.7, C.6 parcial, E.2).
- **Quick win absoluto**: **A.1 (overhangs)**. Unico PR que en <100 ldc + 10 tests detecta condiciones precursoras de falla planar que **hoy pasan inadvertidas**.

---

## 9. Recomendacion priorizada final

Si solo puedes elegir **3 mejoras** para el proximo mes:

1. **A.1 — Overhangs + A.2 — Rock bridges** (combinadas en una sola funcion `_detect_overhangs_and_bridges`). Es la mejora de **mayor impacto y menor esfuerzo** de toda la auditoria. Una vez implementada, **cualquier perfil procesado entregara un flag de riesgo** que antes era invisible.

2. **A.6 — Catch bench effectiveness** (wrapper sobre `effective_berm_width` ya existente). Esfuerzo minimo, valor inmediato en reportes de seguridad.

3. **E.1 — RMR lookup + B.1 — Factor de seguridad** (combinadas). Es la pieza que conecta el sistema con el mundo real del macizo rocoso. Una vez que el cliente entrega un CSV de RMR por banco, el sistema pasa de "conciliacion geometrica" a "evaluacion de estabilidad cuantitativa".

Si el alcance es **6 meses**, seguir el roadmap priorizado (10 posiciones) en orden.

---

**Fin del informe.**
