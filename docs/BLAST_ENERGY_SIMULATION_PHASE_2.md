# Fase 2 — Motor Determinista 3D de Mapas de Energía

**Estado**: implementación inicial (`feat/fase-2-motor-energia-3d`).
**Versión del contrato**: `SIMULATION_CONFIGURATION_VERSION = "1.0"`.
**Versión del motor**: `ENGINE_VERSION = "blast-sim-1.0.0"`.
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
