# BLAST_ADVISOR — Motor de Recomendaciones Cuantitativas de Powder Factor

## 1. Resumen

El motor de recomendaciones cuantitativas `blast_advisor.py` resuelve el problema de ajustar la carga explosiva (powder factor, PF) para controlar la sobre-excavación en taludes finales. A partir de un modelo estadístico PF→daño calibrado con datos de tronaduras reales, el módulo calcula el PF objetivo necesario para alcanzar un daño predefinido (ej. 0.5 m de sobre-excavación) y emite recomendaciones accionables con indicadores de factibilidad y confianza. Permite así cerrar el ciclo de control: medir → modelar → ajustar → verificar, reduciendo la subjetividad en la toma de decisiones de tronadura.

## 2. Contexto técnico

El módulo `core/blast_advisor.py` opera como capa de interpretación y acción sobre los outputs del módulo de modelado estadístico `core/blast_model.py`.

### Dependencias de entrada

**Desde `core/blast_model.py`:**

- **`fit_powder_factor_damage_model()`** — Ajusta regresión lineal daño ~ PF y retorna dict con:
  ```python
  {
      "beta0": float,              # intercepto (m de daño a PF=0)
      "beta1": float,              # pendiente (m de daño por kg/m³ de PF)
      "r_squared": float,         # coeficiente de determinación R²
      "p_value": float,           # p-value de dos colas para beta1 == 0
      "n": int,                   # muestras utilizadas
      "std_err_beta1": float,     # error estándar de la pendiente
      "ci_beta1_low": float,      # límite inferior IC 95% para beta1
      "ci_beta1_high": float,     # límite superior IC 95% para beta1
      "mean_pf": float,           # media de PF muestral (para extrapolación)
      "confidence": str,          # "HIGH" / "MEDIUM" / "LOW" / "INSUFFICIENT"
      "is_significant": bool      # p_value < 0.05
  }
  ```

- **`predict_damage_for_pf(model, target_pf)`** — Predice daño para un PF específico y retorna:
  ```python
  {
      "predicted_damage": float,      # beta0 + beta1 * target_pf
      "delta_from_current": float,    # diferencial respecto a actual
      "uncertainty_m": float          # incertidumbre de la predicción
  }
  ```

**Desde `core/config.py` — `BlastAdvisorDefaults`:**

| Parámetro | Valor por defecto | Unidad | Descripción |
|-----------|-------------------|--------|-------------|
| `target_overbreak_m` | 0.5 | m | Objetivo de sobre-excavación aceptable |
| `target_underbreak_m` | -0.3 | m | Objetivo de sub-excavación (deuda) tolerable |
| `pf_optimal_default_kgm3` | 0.35 | kg/m³ | PF óptimo de referencia (fallback) |
| `max_recommendation_pct` | 30.0 | % | Cambio máximo de PF permitido en recomendación |
| `min_samples_for_advice` | 5 | count | Mínimo de secciones para emitir recomendación |
| `high_confidence_n` | 15 | count | Umbral n para confianza HIGH |
| `medium_confidence_n` | 8 | count | Umbral n para confianza MEDIUM |

**Desde `core/blast_correlation.py`:**

- **`compute_powder_factor(df_pozos)`** — Calcula PF volumétrico (kg/m³) y de área (kg/m²) por pozo
- **`aggregate_powder_factor_by_group()`** — Agrega PF por sección/nivel/malla
- **`compute_blast_geotech_correlation()`** — Proyecta pozos sobre secciones y une con desviaciones

## 3. Modelo matemático

El motor de recomendaciones opera sobre una regresión lineal simple:

```
damage = β₀ + β₁ × PF + ε
```

Donde:
- `damage` = sobre-excavación media (m), con signo (+ = sobre, − = deuda)
- `β₀` = intercepto (m de sobre-excavación con PF = 0)
- `β₁` = pendiente (m de sobre-excavación por kg/m³ adicional de PF)
- `PF` = powder factor (kg/m³)
- `ε` = residuo (variabilidad no explicada por el modelo)

### Inversión para calcular PF objetivo

Para un nivel de daño objetivo `damage_target`, se despeja PF:

```
PF_target = (damage_target - β₀) / β₁
```

El ajuste recomendado es:

```
ΔPF = PF_target - PF_current
ΔPF% = 100 × ΔPF / PF_current
```

### Incertidumbre de predicción

La incertidumbre en la predicción de daño para un PF fuera del rango muestral:

```
uncertainty = std_err_β₁ × |PF_target - mean_pf_muestral|
```

Esto permite advertir al usuario cuando se extrapolan valores fuera del rango de calibración del modelo.

## 4. API del módulo

| Función | Inputs | Output | Uso principal |
|---|---|---|---|
| `recommend_pf_adjustment(model, current_pf, target_overbreak_m=None)` | `model` (dict de `fit_powder_factor_damage_model`)<br>`current_pf` (float, kg/m³ actual)<br>`target_overbreak_m` (float, opcional) | Dict con claves:<br>`target_pf`, `current_pf`, `delta_pf`, `delta_pf_pct`,<br>`predicted_current_damage`, `predicted_target_damage`,<br>`feasibility`, `message`, `confidence` | Calcular ajuste completo de PF con factibilidad |
| `recommend_charge_change_pct(model, current_pf, target_overbreak_m=None)` | Igual que anterior | Dict simplificado:<br>`{delta_pct, direction, feasibility}` | Solo el % de cambio y dirección (aumentar/reducir) |
| `recommend_by_sector(df_sections, model, group_col='sector')` | `df_sections` (DataFrame con columnas `pf_vol_avg`, `avg_over_break`, etc.)<br>`model` (dict de modelo)<br>`group_col` (columna de agrupación) | DataFrame con una fila por grupo, columnas:<br>`sector`, `current_pf`, `target_pf`, `delta_pf_pct`,<br>`feasibility`, `message`, `confidence` | Generar recomendaciones por sector/malla/nivel |
| `format_recommendation_text(rec, section_name='')` | `rec` (dict de recomendación)<br>`section_name` (str, opcional) | String en español con frase formateada | Generar mensaje legible para UI/reporte |

### Estructura del dict de recomendación (`recommend_pf_adjustment`)

```python
{
    "target_pf": float,               # PF objetivo calculado (kg/m³)
    "current_pf": float,              # PF actual ingresado
    "delta_pf": float,                # diferencia target - current (kg/m³)
    "delta_pf_pct": float,            # cambio porcentual (%)
    "predicted_current_damage": float, # daño proyectado con PF actual (m)
    "predicted_target_damage": float,  # daño proyectado con PF target (m)
    "feasibility": str,                # "APPLICABLE" / "CAUTION" / "INFEASIBLE" / "INSUFFICIENT_DATA"
    "message": str,                    # frase en español neutro
    "confidence": str                  # "HIGH" / "MEDIUM" / "LOW" / "INSUFFICIENT"
}
```

## 5. Ejemplo de uso

Flujo completo desde datos crudos hasta recomendación:

```python
from core.blast_correlation import compute_powder_factor, aggregate_powder_factor_by_group
from core.blast_model import fit_powder_factor_damage_model
from core.blast_advisor import recommend_pf_adjustment, format_recommendation_text

# 1. Calcular PF por pozo (df_pozos tiene columnas: kg, burden, espacio, altura)
df_pf = compute_powder_factor(df_pozos)

# 2. Agregar por sección y unir con daño medido
df_sections = aggregate_powder_factor_by_group(df_pf, group_col='seccion')
# df_sections ahora tiene: 'pf_vol_avg', 'avg_over_break', etc.

# 3. Ajustar modelo PF → daño
model = fit_powder_factor_damage_model(
    pf_values=df_sections['pf_vol_avg'].values,
    damage_values=df_sections['avg_over_break'].values,
)

# 4. Emitir recomendación para una sección con PF actual 0.55 kg/m³
rec = recommend_pf_adjustment(
    model=model,
    current_pf=0.55,
    target_overbreak_m=0.5  # opcional, usa default si no se provee
)

# 5. Formatear para UI
message = format_recommendation_text(rec, section_name='SEC_03')
print(message)
# → "Reducir PF de 0.55 a 0.38 kg/m³ (−31%) proyecta acotar sobre-excavación
#    de 0.6 m al objetivo de 0.5 m (modelo p=0.014, n=20, confianza HIGH)."
```

### Ejemplo de recomendación por sector

```python
from core.blast_advisor import recommend_by_sector

# df_sections tiene múltiples sectores con sus PF y daño promedio
df_recommendations = recommend_by_sector(
    df_sections=df_sections,
    model=model,
    group_col='malla'  # una recomendación por malla de tronadura
)

# df_recommendations es un DataFrame con columnas:
# ['malla', 'current_pf', 'target_pf', 'delta_pf_pct',
#  'predicted_current_damage', 'predicted_target_damage',
#  'feasibility', 'message', 'confidence']
```

## 6. Semántica de `feasibility`

La factibilidad indica si la recomendación es operacionalmente viable y estadísticamente confiable.

| Valor | Condición de activación | Significado para UI |
|---|---|---|
| `APPLICABLE` | - ΔPF dentro del rango permitido (≤ 30%)<br>- PF_target positivo y razonable<br>- Confianza del modelo ≥ LOW | Mostrar como recomendación accionable con indicador de confianza (color verde/amarillo/rojo según HIGH/MEDIUM/LOW) |
| `CAUTION` | - ΔPF > 30% (cambio muy grande)<br>- PF_target ≤ 0 (físicamente imposible)<br>- PF_target > 1.5 × óptimo (excesivo)<br>- Extrapolación fuera del rango muestral | Mostrar como advertencia, sugerir subdividir sector o revisar datos, no aplicar directamente sin supervisión |
| `INFEASIBLE` | (reservado para uso futuro) | No implementar en Fase 4; dejar placeholder en código y docs |
| `INSUFFICIENT_DATA` | - Modelo con confianza INSUFFICIENT (n < 5)<br>- β₁ ≈ 0 (sin relación detectada)<br>- p-value ≥ 0.10 (no significativo) | No mostrar recomendación cuantitativa; mostrar mensaje genérico de "insuficientes datos para recomendar ajuste" |

## 7. Interpretación del coeficiente β₁

La pendiente β₁ (m de daño por kg/m³ de PF) es el parámetro clave para interpretar la sensibilidad del daño al powder factor.

| β₁ (m por kg/m³) | Lectura operativa |
|---|---|
| **β₁ > 1.0** | PF es muy sensible al daño; cada 0.1 kg/m³ extra produce >0.1 m adicional de sobre-excavación. Sugerir revisar si hay buzamiento favorable o fracturamiento que amplifica el efecto. |
| **0.3 < β₁ < 1.0** | Sensibilidad moderada; la relación PF→daño es clara pero no excesiva. Revisar variabilidad geológica dentro del sector (posible heterogeneidad). |
| **β₁ < 0.3** | PF casi no afecta el daño en este sector; puede indicar que el daño está controlado por otros factores (geología estructural, secuencia de iniciación, tiempo de confinamiento). No esperar grandes mejoras ajustando solo PF. |
| **β₁ < 0** | **Anómalo**: más PF produce menos daño. Revisar calidad de datos o posible error de signo en la medición del daño. Puede indicar correlación espúrea (ej. más PF en zonas más competentes). |
| **β₁ ≈ 0** | Sin relación PF→daño detectable (no rechazar el modelo; puede indicar que el daño depende de otras variables no consideradas). |

**Nota sobre intervalos de confianza:** El módulo reporta `ci_beta1_low` y `ci_beta1_high` (IC 95%). Si el intervalo cruza 0, la relación no es estadísticamente significativa (p-value alto). En este caso, la recomendación debe emitirse con `INSUFFICIENT_DATA` aunque el valor puntual de β₁ sea alto.

## 8. Limitaciones actuales (lo que el módulo NO hace)

- **No segmenta por tipo de roca** — Asume uniformidad geológica dentro del sector. La segmentación por dominio/litología queda para Fase 3 con columna `Dominio`/`Litologia` en el DataFrame de entrada.

- **No considera variabilidad espacial** — No modela cambios locales de PF dentro de una malla (asume PF constante por sección).

- **No optimiza simultáneamente PF y patrón de mallas** — Solo recomienda ajuste de carga total (PF); no sugiere cambios de burden/espaciamiento.

- **Asume linealidad** — El modelo β₁ constante no captura efectos de umbral (ej. saturación de daño a PF altos). Si se sospecha no-linealidad, usar `fit_powder_factor_damage_model` con transformaciones (futuro).

- **Requiere n ≥ 5 secciones con PF válido** — Por debajo de este umbral, retorna `INSUFFICIENT_DATA` sin recomendación cuantitativa.

- **No se ajusta automáticamente** — El modelo se recalibra manualmente con cada campaña de tronaduras; no hay aprendizaje incremental online (futuro).

- **No considera restricciones operativas** — No verifica si el PF recomendado es compatible con el diámetro de perforación disponible o con el tipo de explosivo en stock.

- **Extrapola con cautela** — Si PF_target está fuera del rango muestral, la incertidumbre aumenta proporcionalmente a la distancia desde `mean_pf`.

## 9. Referencias

- **Commit `f0f1da9`** (Fase 2) — Implementación de `core/blast_model.py` con regresión PF→daño
- **Commit `2a6cea4`** (Fase 1) — Cálculo de powder factor en `core/blast_correlation.py`
- **Commit `7b26bae`** (Fase 0) — Desviaciones con signo (sobre-excavación / deuda)
- **`AGENTS.md`** — Sección "Drill & Blast" con descripción de módulos de tronadura

## 10. Glosario

| Término | Definición |
|---|---|
| **Powder Factor (PF)** | Cantidad de explosivo por unidad de volumen (kg/m³) o de área (kg/m²) de roca a tronar. |
| **Sobre-excavación (overbreak)** | Desviación positiva respecto al diseño: la pared real queda más atrás que lo proyectado. |
| **Sub-excavación / deuda (underbreak)** | Desviación negativa: la pared real queda más adelante que lo proyectado (no se alcanzó el diseño). |
| **β₁** | Pendiente de la regresión lineal daño ~ PF; mide sensibilidad del daño al PF. |
| **R²** | Coeficiente de determinación; proporción de variabilidad del daño explicada por el PF. |
| **p-value** | Probabilidad de observar el β₁ muestral si no hubiera relación real (β₁ = 0). p < 0.05 indica significancia estadística. |
| **IC 95%** | Intervalo de confianza al 95% para β₁; rango de valores plausibles para la pendiente verdadera. |
| **Extrapolación** | Predicción fuera del rango de PF observados; incertidumbre mayor. |
| **Factibilidad** | Viabilidad operativa de implementar la recomendación (APPLICABLE / CAUTION / INFEASIBLE). |
