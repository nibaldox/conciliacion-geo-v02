# Fase 2 — Motor Determinista 3D de Mapas de Energía

**Estado**: remediación científica aplicada (rama `fix/fase-2-remediacion-cientifica`).
**Versión del contrato**: `SIMULATION_CONFIGURATION_VERSION = "2.0"` (bump por `support_radius_m`).
**Versión del motor**: `ENGINE_VERSION = "blast-sim-1.0.0"` (en `core/blast_simulation/engine.py:77`).
**Dependencias**: Fase 1 canónica (`ProcessingResult` con `accepted_rows`).

> ⚠ **ADVERTENCIA**: Los mapas corresponden a un **modelo energético
> ingenieril no calibrado**. No representan por sí solos daño,
> fragmentación, PPV ni estabilidad. Los resultados son **indicadores
> comparativos** para análisis y calibración futura.

---

## 1. Propósito

La Fase 2 transforma las filas aceptadas del `ProcessingResult` canónico
de la Fase 1 en un campo espacial y temporal de energía sobre un volumen
de roca discretizado en vóxeles. El motor es **determinista**: misma
entrada + misma configuración producen idéntico resultado.

La representación es:

```
macizo rocoso → grilla regular de vóxeles
pozos → cilindros 3D collar→toe
explosivo → segmentos de carga dentro del cilindro
detonación → fuentes radiales con tiempo de iniciación
resultado → campo de energía 3D + mapas 2D + perfiles
```

## 2. Alcance funcional

El motor puede:

1. Consumir únicamente las filas `accepted_rows` del `ProcessingResult`.
2. Reconstruir la trayectoria 3D collar→toe ya validada por la Fase 1.
3. Representar cada pozo como un cilindro orientado.
4. Diferenciar taco, columna explosiva, decks (cuando existan),
   longitud sin información y carga desconocida o inválida.
5. Discretizar cada columna explosiva en fuentes lineales.
6. Discretizar el volumen de roca en vóxeles.
7. Propagar energía radialmente desde cada segmento.
8. Incorporar tiempos o retardos cuando estén disponibles.
9. Superponer contribuciones de múltiples segmentos y pozos.
10. Producir energía acumulada, densidad energética, contribución
    máxima, pozo dominante, primera llegada, tiempo del máximo,
    número de fuentes contribuyentes, cobertura y zonas sin información.
11. Generar planta por elevación, sección vertical, perfil estadístico
    y volumen clasificado por bandas relativas.
12. Persistir configuración, resultados, advertencias y procedencia.
13. Exponer el resultado mediante API REST.
14. Visualizarlo en React.
15. Mantener Streamlit como adaptador de presentación.

## 3. Exclusiones científicas

La Fase 2 **no** simula todavía:

- movimiento explícito de fragmentos;
- contacto entre bloques;
- lanzamiento o muckpile;
- apertura dinámica de fracturas;
- FEM, DEM, SPH o CFD;
- fragmentación Kuz-Ram como verdad calibrada;
- PPV absoluto no calibrado;
- backbreak absoluto no calibrado;
- interacción compleja con discontinuidades;
- lógica difusa, modelo fractal, algoritmo evolutivo u OpenEvolve;
- optimización automática del diseño.

Los vóxeles son del macizo; **no** se convierten en cuerpos rígidos
independientes.

---

## 4. Modelo matemático

### 4.1 Energía de entrada

Para cada segmento explosivo:

```
E_quimica_J  = masa_explosivo_kg × energia_especifica_J_kg
E_acoplada_J = E_quimica_J × eficiencia_acoplamiento
```

Toda magnitud lleva `valor`, `unidad`, `estado`, `fuente`, `supuestos`
y `advertencias`. **No** se usa ANFO como fallback para explosivos
desconocidos. **No** se inventan densidad, energía específica,
diámetro, longitud cargada ni eficiencia.

Si una propiedad crítica está ausente:

- el cálculo absoluto se bloquea (HTTP 422 con `ABSOLUTE_MODE_BLOCKED`),
  o
- se permite un modo explícito `energy_mode=RELATIVE` que produce un
  campo **adimensional** etiquetado como tal (nunca reportado como J/m³).

### 4.2 Núcleo espacial

Kernel radial regularizado:

```
K(r) = exp(-α·r) / (r² + r0²)
```

con `α` coeficiente de atenuación `[1/m]` y `r0` radio de
regularización `[m]`. La energía se distribuye por fuente como:

```
w_j = K(r_j) × V_j        (V_j = volumen del vóxel)
W   = Σ_{j ∈ soporte efectivo} w_j     ← W_inf, no W_in_domain
e_j = E_acoplada × w_j / W_inf
```

`W_inf` es la integral del kernel sobre **todo el espacio 3D**,
calculada una sola vez por cuadratura trapezoidal:

```
W_inf = ∫₀^∞ 4π·r² · K(r) dr
```

Esto garantiza que **la suma en el dominio sea siempre ≤ E_acoplada**.
La diferencia es la **energía fuera del dominio**, reportada
explícitamente — nunca renormalizada en silencio.

```
energía acoplada       = Σ E_acoplada
energía en el dominio  = Σ_j e_j
energía fuera          = energía acoplada − energía en el dominio
fracción representada  = energía en el dominio / energía acoplada
```

### 4.3 Densidad energética

```
densidad_energía_J_m3 = energía_voxel_J / volumen_voxel_m3
```

Una fracción, índice o energía **nunca** se etiqueta `kg/m³`
(auditoría H-09).

### 4.4 Tiempo y retardos

Cuando existen retardos:

```
t_llegada = t_detonación + distancia / velocidad_propagación
```

La velocidad de propagación es una entrada **explícita con
procedencia**. El pulso gaussiano normalizado:

```
G(t) = exp(-0.5 × ((t − t_llegada) / σ_t)²)
```

La discretización temporal **no crea energía adicional**. Si no hay
retardos válidos, el motor opera en modo estático y marca:

```
temporal_status = NOT_AVAILABLE
```

Cuando se usa el sigma por defecto (`SIMULATION.fallback_temporal_sigma_s`),
el resultado se etiqueta:

```
temporal_status = PULSE_SIGMA_FALLBACK
```

### 4.5 Anisotropía

La Fase 2 admite `ISOTROPIC` y `ANISOTROPIC_TENSOR`. Para anisotropía,
se usa una métrica positiva definida:

```
r_aniso² = Δxᵀ · M · Δx
```

`M` se valida como simétrica positiva-definida por el criterio de
Sylvester (todos los menores principales leading > 0). El tensor
identidad reproduce exactamente el caso isotrópico (verificado por
test). Para preservar la masa total del kernel, el normalizador se
reescala:

```
W_inf_aniso = W_inf_iso / sqrt(det(M))
```

Si no hay información estructural, el operador debe declarar
`anisotropy_mode=ISOTROPIC` explícitamente.

---

## 5. Modelo del macizo rocoso

Contratos canónicos en `core/blast_simulation/contracts.py`:

```
RockMassConfiguration
VoxelGridSpecification
EnergyPropagationConfiguration
TemporalSimulationConfiguration
SimulationConfiguration
SimulationResult
VoxelEnergyField
SimulationDiagnostics
SimulationProvenance
```

El macizo puede llevar:

```
rock_unit_id
density_kg_m3
ucs_mpa
attenuation_coefficient_1_m
wave_velocity_m_s
anisotropy_mode
anisotropy_tensor
source
status           ← VALIDATED | UNVALIDATED_REFERENCE |
                   PROXY_EMPIRICAL_LOCAL | UNKNOWN | MISSING
assumptions
warnings
```

### 5.1 Proxy empírico drilling-time → UCS (unidad 1c)

El proxy para la unidad `1c (13)`:

```
menos de 35 min → roca media, referencia aproximada 60 MPa
más de 40 min   → roca dura, referencia aproximada 80 MPa
```

es una **estrategia configurable, versionada y etiquetada como proxy
empírico local**. Está **desactivada por defecto**
(`SIMULATION.enable_drilling_time_ucs_proxy = False`). El rango
intermedio (35–40 min) se resuelve explícitamente, nunca con un salto
oculto.

---

## 6. Arquitectura

Toda la física y matemática vive en `core/`:

```
core/blast_simulation/
├── __init__.py        # re-exporta la API pública
├── contracts.py       # SimulationConfiguration + sub-contratos
├── grid.py            # grilla de vóxeles (NumPy puro)
├── charges.py         # cilindros collar→toe + segmentación
├── kernels.py         # kernel radial + normalización conservativa
├── temporal.py        # retardos, llegada, pulso gaussiano
├── engine.py          # orquestador determinista
├── diagnostics.py     # bandas, estadísticas, cobertura
├── slicing.py         # cortes planta / sección vertical
├── persistence.py     # NPZ + JSON + SHA-256
└── export.py          # Excel multi-hoja
```

Reglas respetadas:

- Sin física en routers, React o Streamlit.
- Arrays NumPy vectorizados; iteración por fuente con accumulators
  reusados (sin matriz densa `n_sources × n_voxels`).
- El motor es determinista.
- El core **no depende** de FastAPI, Streamlit, React, Plotly ni SQLite.
- Se preserva la API pública legacy (`core/__init__.py`).
- `app.py` y el resto de `ui/` (salvo `ui/modulo_tronadura/`) son
  intocables.

---

## 7. Contrato y validación

La simulación exige explícitamente:

```
simulation_configuration_version
geometry_configuration_version
voxel_size_m
domain_bounds
kernel_type
attenuation_coefficient_1_m
regularization_radius_m
coupling_efficiency
energy_mode
temporal_mode
anisotropy_mode
user_confirmed
```

Se rechazan: campos desconocidos, duplicados, NaN/inf, vóxeles de
volumen cero, límites invertidos, eficiencia fuera de `[0,1]`,
atenuación negativa, radio de regularización no positivo, tensor no
simétrico o no PD, fuentes fuera del dominio sin diagnóstico,
configuración no confirmada, mezcla ambigua de unidades, carga fuera
de la trayectoria collar→toe, longitudes incompatibles, y filas
rechazadas por la Fase 1.

No hay defaults operacionales silenciosos. Los defaults puramente
numéricos seguros (tolerancias, chunk sizes, techos de recursos)
residen en `core/config.py::SimulationDefaults`.

---

## 8. Resultado canónico

`SimulationResult` es la única autoridad y contiene:

```
simulation_id
configuration
grid_metadata
source_summary
energy_field
plan_slices
section_slices
processing_summary
warnings
blocking_errors
spatial_diagnostics
temporal_diagnostics
provenance
created_at
engine_version
```

Para campos volumétricos grandes:

- no se guardan millones de valores como JSON dentro de SQLite;
- se guardan metadatos y resúmenes en SQLite;
- el artefacto binario es NPZ comprimido;
- se almacena hash SHA-256;
- se registra forma, dtype, orden de ejes, unidades y versión;
- el artefacto se puede reabrir y validar.

---

## 9. API

Endpoints:

```
POST /api/v1/blast/simulations
GET  /api/v1/blast/simulations/{simulation_id}
GET  /api/v1/blast/simulations/{simulation_id}/plan
GET  /api/v1/blast/simulations/{simulation_id}/section
GET  /api/v1/blast/simulations/{simulation_id}/export
```

El endpoint de creación:

1. recibe una referencia inequívoca al resultado canónico de pozos;
2. valida la configuración;
3. ejecuta el core en un hilo worker;
4. persiste el resultado (NPZ + JSON + SQLite);
5. devuelve resumen, diagnósticos y enlaces a cortes;
6. usa errores estructurados HTTP 400/422;
7. no envía silenciosamente filas rechazadas al motor.

Límites de seguridad:

```
max_voxel_count              = 2_000_000
max_charge_segments          = 50_000
max_estimated_memory_gb      = 8.0
max_wall_time_seconds        = 600.0
```

Antes de ejecutar, el motor informa la memoria estimada.

---

## 10. Benchmarks

Casos reproducibles para 50, 100 y 500 pozos sobre grillas de ~100k,
500k y 1M de vóxeles. Cada caso mide tiempo total, pico de memoria,
número de segmentos, número de vóxeles, backend, tamaño del artefacto.
Ver `tests/test_blast_simulation_benchmarks.py`.

---

## 11. Limitaciones

- El campo es un **modelo ingenieril**, no FEM/DEM/SPH.
- El kernel `exp(-αr)/(r²+r0²)` es una regularización pragmática; no
  deriva de una constitutiva calibrada.
- La velocidad de propagación es un escalar global; no depende de la
  orientación ni de la frecuencia.
- Los retardos se asignan por pozo; no hay modelado de interacción
  entre frentes de onda.
- El ancho de banda temporal es una sigma gaussiana única.

---

## 12. Interpretación correcta

- Comparar configuraciones **entre sí**: más/menos energía local, mejor
  distribución, etc.
- Identificar zonas con baja cobertura (poco confiable) y zonas
  saturadas (riesgo de sobre-energía).
- Calibrar futuramente contra PPV medido, fragmentación observada y
  backbreak real.

---

## 13. Calibración futura

Pasos sugeridos:

1. Cruzar `represented_energy_j` con PPV de sismógrafos.
2. Ajustar `α`, `r0`, `coupling_efficiency` por unidad geotécnica.
3. Introducir velocity por dominio litológico cuando esté disponible.
4. Validar contra backbreak observado en paredes finales.
5. Recién entonces los campos pueden reinterpretarse como predictivos.

---

## 14. Ejemplos reproducibles

Ver:

- `tests/test_blast_simulation_engine.py` — invariantes analíticas.
- `tests/test_blast_simulation_adversarial.py` — casos límite.
- `tests/test_blast_simulation_persistence.py` — NPZ/JSON/XLSX round-trip.
- `tests/test_api_blast_simulations.py` — API REST.
- `tests/test_phase2_integration.py` — integración real React→core→NPZ.
- `tests/test_streamlit_energy_simulation.py` — AppTest real.

Cada test es determinista y utiliza inputs sintéticos explícitos.

---

## 15. Riesgos científicos

| Riesgo | Mitigación |
|--------|-----------|
| Sobreinterpretación del campo como daño | Etiqueta visible "no calibrado"; bloqueo de etiquetas kg/m³ |
| Truncamiento silencioso de dominio | Normalización por `W_inf`; reporte explícito de outside_energy |
| Fallback ANFO para explosivo desconocido | `resolve_explosive` devuelve None; tests adversariales |
| Mezcla de unidades angulares | Contrato Fase 1 ya lo impide; Fase 2 lo consume |
| Tensor no positivo-definido | Validación por criterio de Sylvester |
| Memoria explosiva | Techos `max_voxel_count`, `max_estimated_memory_gb` |
| NPZ alterado | SHA-256 verificado en read-back; tests de tamper |
| Defaults silenciosos | Confirmación obligatoria + fingerprint por SHA-256 |

---

## 16. Deuda técnica

- `time_of_max` sólo registra la llegada del pico de la fuente
  dominante; una integración temporal completa con superposición de
  pulsos queda para una iteración posterior.
- El cutoff efectivo del kernel se evalúa sobre la grilla del dominio;
  para dominios muy pequeños vs. soporte del kernel, esto puede
  subestimar `outside_energy`. La integral `W_inf` sobre todo el
  espacio mitiga el sesgo.
- La capa temporal no está integrada en `export_field_arrays` más
  allá del placeholder; los tests de integración lo documentan.
- El adapter Streamlit no está conectado al `router.py` del módulo
  (eso requeriría tocar el router, fuera del alcance de Fase 2).

---

**Fin del documento.**


## 17. Remediación científica (2026-08)

Esta sección documenta los hallazgos de la auditoría de Fase 2 y los
cambios aplicados para remediarlos. Las 7 fallas bloqueantes + 7 brechas
adicionales fueron resueltas en commits atómicos sobre la rama
`fix/fase-2-remediacion-cientifica`.

### Causa raíz de Falla 1 (conservación)

El motor original normalizaba con `e_j = E × w_j / W_inf` donde `W_inf`
era una integral continua hasta `cutoff = max(50/α, 1000·r0)`. Esta
integral era independiente de la posición del voxel — pero los vóxeles
del dominio estaban en coordenadas absolutas fijas. Cuando la fuente
NO estaba en un centro de vóxel, `Σ w_j (in-domain)` podía exceder el
denominador `W_inf`, produciendo `Σ e_j > E` (320% observado).

### Solución de Falla 1

`discrete_total_mass` ahora usa **cuadratura de midpoint en cascarones
esféricos concéntricos** de grosor `dx` desde `r=0` hasta `r=R`. La
muestra radial es idéntica a la usada por el motor al evaluar el
kernel sobre la grilla del dominio, por construcción
`Σ_{j in-domain} w_j ≤ Q_total` con igualdad cuando la fuente coincide
con un centro de vóxel y el dominio contiene el soporte completo.

### Causa raíz de Falla 2 (soporte finito)

El cutoff implícito `1000·r0` carecía de significado físico y no
estaba en el contrato. `α=0` requería un cutoff arbitrario para que
la integral no divergiera.

### Solución de Falla 2

`K(r) = 0` estricto para `r > support_radius_m`. `support_radius_m`
es campo obligatorio del contrato con validación `> regularization_radius_m > 0`.
`α=0` se acepta únicamente con `support_radius_m > 0`.

### Causa raíz de Falla 3 (temporal descartado)

`export_field_arrays` rellenaba `first_arrival_s` y `time_of_max_s`
con `np.full(N, NaN)`. El motor calculaba los valores reales durante
la ejecución pero el NPZ nunca los llevaba.

### Solución de Falla 3

- `compute_time_of_max` vectorizado por bloques, sin construir matriz
  `n_voxels × n_time_bins`.
- `engine.py` invoca `compute_first_arrival` y `compute_time_of_max`
  tras el bucle per-fuente, a partir de los acumuladores
  `temporal_energy_contributions`, `temporal_distances`,
  `temporal_detonation_times`.
- En modo `STATIC` las claves temporales NO aparecen en el NPZ (antes
  eran `NaN` placeholders).
- `VoxelEnergyField` expandido con escalares `first_arrival_s`,
  `time_of_max_s`, `dominant_hole_id`, `contributor_count`, `units`.

### Causa raíz de Falla 4 (mapas no llegan a UI)

Los cortes sólo guardaban `shape`, `max`, `mean`, `sha256` — sin la
matriz 2D. React/Streamlit no podían renderizar heatmaps.

### Solución de Falla 4

`PlanSlice` y `SectionSlice` ahora llevan:
- `values: tuple[float, ...]` — matriz 2D aplanada en row-major.
- `x_coordinates_m`, `y_coordinates_m` (plan) o `along_coordinates_m`,
  `vertical_coordinates_m` (sección).
- `valid_mask: tuple[bool, ...]`.
- `percentiles: dict[str, float]` (p5/p50/p90/p99).
- `source_holes_projection: tuple[dict, ...]`.
- `data_sha256` del array 2D.
- Endpoint nuevo `GET /profile` (interpolación lineal).

### Causa raíz de Falla 5 (anisotropía no editable)

`anisotropy_mode=ANISOTROPIC_TENSOR` era seleccionable en UI pero no
se podía ingresar el tensor 3×3.

### Solución de Falla 5

- React: `TensorEditor` con 9 NumberFields M11..M33, sincronización
  Mij↔Mji, validación Sylvester en vivo, botón identidad
  explícito (no default).
- Streamlit: 9 `st.number_input` con callbacks de sincronización,
  validación `_is_symmetric_pd` y `np.linalg.eigvalsh`.
- Ambos invalidan el fingerprint al modificar celdas.

### Causa raíz de Falla 6 (unidades de cortes)

`represented_energy_j = sum(slice_2d) × V / dx` multiplicaba por
volumen dos veces (el campo ya era J por vóxel). Para voxel_size=2 m
introducía factor 4×.

### Solución de Falla 6

- `PlanSlice.field_type ∈ {"energy_j", "energy_density_j_m3"}`.
- Si `energy_j`: suma directa.
- Si `energy_density_j_m3`: multiplicar por voxel_volume UNA vez
  (intersección, no doble).

### Causa raíz de Falla 7 (persistencia de bloqueadas)

La API escribía NPZ + JSON + SQLite ANTES de revisar blocking_errors.
Las simulaciones bloqueadas quedaban como artefactos válidos.

### Solución de Falla 7

`should_persist(result)` = False cuando `len(blocking_errors) > 0`.
La API gatea la escritura: no llama `write_atomic_simulation` ni
`db.save_blast_simulation` cuando hay bloqueos. Devuelve HTTP 422 con
`error_code="SIMULATION_BLOCKED"` y `blocking_errors`.

### Causa raíz de Brecha 3.1 (extra=forbid)

Pydantic aceptaba campos desconocidos y los descartaba silenciosamente.

### Solución de Brecha 3.1

`SimulationCreateRequest.model_config = ConfigDict(extra="forbid")`.
Helper `_translate_validation_error` convierte `pydantic.ValidationError`
en HTTP 422 con `error_code="UNKNOWN_FIELD"`.

### Causa raíz de Brecha 3.2 (decks)

`segment_type="deck_gap"` existía en el dataclass pero
`_segment_single_hole` nunca lo instanciaba.

### Solución de Brecha 3.2

`charges.py` parsea el campo `Decks` (lista de dicts por fila). Cada
deck tiene explosivo propio, masa propia (`mass_kg`), y se discretiza
en `n_segments_per_deck` sub-segmentos. Validaciones:
- `TACO_INVADED` si `from_m < Taco_m`.
- `OUT_OF_HOLE` si `to_m > geom_len`.
- `OVERLAP` con otro deck.
- `ZERO_LENGTH` si `from_m >= to_m`.
- `UNKNOWN_EXPLOSIVE` si explosivo no resuelto.

### Causa raíz de Brecha 3.4 (cobertura parcial)

`shape = floor((x_max - x_min) / dx)` podía dejar una franja del
dominio sin cubrir.

### Solución de Brecha 3.4

`shape = ceil(...)`. La propiedad `effective_bounds` reporta los
límites efectivos. `intersection_mask_flat` indica qué vóxeles
intersectan el dominio solicitado.

### Causa raíz de Brecha 3.6 (lint ausente)

`eslint` no estaba en `devDependencies`. `npm run lint` fallaba por
paquete ausente.

### Solución de Brecha 3.6

- `web/package.json`: `eslint@^9`, `@eslint/js@^9`, `typescript-eslint@^8`.
- `web/eslint.config.js`: flat config (ESLint 9).
- `web/package-lock.json`: regenerado.
- `.github/workflows/ci.yml`: nuevo step `npm run lint` después de tsc.

### Causa raíz de Brecha 3.7 (socksio "ambiental")

`socksio` aparece como import opcional de `httpcore._async.socks_proxy`
cuando httpx resuelve una URL con esquema `socks5://`. No hay ningún
test ni fuente del repo que configure tal proxy.

### Solución de Brecha 3.7

Confirmado: NO es falla real. La dependencia `socksio` se carga
únicamente si hay un proxy SOCKS configurado, lo cual no ocurre en
este repo. La falla atribuida a "socksio ausente" es ambiental del
entorno del auditor, no del código.

## 18. Resultados de la remediación

| Métrica | Antes | Después |
|---|---|---|
| Conservación verificada | NO (320% observado) | SÍ (Σe_j ≤ E_acoplada) |
| `support_radius_m` explícito | NO (cutoff 1000·r0) | SÍ (validado en contrato) |
| `time_of_max_s` real en NPZ | NO (NaN placeholder) | SÍ (vectorizado por bloques) |
| Matrices 2D en UI | NO (sólo sha256+max+mean) | SÍ (values, coords, percentiles, pozos) |
| Tensor 3×3 editable en UI | NO | SÍ (con validación Sylvester) |
| Cortes con unidades correctas | NO (factor 4×) | SÍ (field_type='energy_j'/'energy_density_j_m3') |
| Simulaciones bloqueadas sin NPZ | NO (se persistían) | SÍ (should_persist gate) |
| extra=forbid en API | NO | SÍ (HTTP 422 UNKNOWN_FIELD) |
| Decks reales | NO (sólo segmento monolítico) | SÍ (parse + validación + discretización) |
| Cobertura completa del dominio | NO (floor) | SÍ (ceil + intersection_mask) |
| `npm run lint` | fallaba | pasa (0 errores) |
| Tests backend | 1603 passed | **1699 passed** (+96) |
| Tests frontend | 367 passed | 367 passed |
| Conservación verificada en suite | parcial | 26/26 categorías |

