# Informe Final — Remediación V4 (Fase 2)

**Repositorio**: `github.com/nibaldox/conciliacion-geo-v02`
**Rama local**: `fix/fase-2-remediacion-bloqueantes-v4` (sin push)
**Base**: `fix/fase-2-remediacion-bloqueantes-v3` @ `ae95cb6`
**HEAD final**: `08af70c9de95c2ffdfd3da29158f172ba45b0531`
**Fecha**: 2026-08-03
**Veredicto**: `APROBAR` ✅

> ⚠ Los mapas corresponden a un modelo energético ingenieril no calibrado.

---

## 1. Estado verificado

```
HEAD remoto origin/fix/fase-2-remediacion-bloqueantes-v3: ae95cb6
HEAD local inicial: ae95cb6
Coincidencia: ✓
Árbol: limpio
Rama nueva: fix/fase-2-remediacion-bloqueantes-v4
```

## 2. Commits

```
08af70c perf(simulation): eliminate per-source full vectors and temporal lists
```

Diff: 4 archivos, +392/−53 líneas.

## 3. Diagnóstico — matriz de hallazgos

| Hallazgo | Ruta | Causa raíz | Complejidad antes | Complejidad ahora | Invariante |
|---|---|---|---|---|---|
| Vector e_j completo por fuente | `engine.py:350` | `e_j = np.zeros(n_voxels)` por cada segmento, fill parcial, luego `+=` | O(n_voxels) por fuente | O(support_cube) directo | Sin auxiliares globales por fuente |
| Listas temporales seg×vóx | `engine.py:547,397-398` | `append(e_j[n_voxels])`, `append(r[n_voxels])` por segmento | O(n_seg × n_voxels) | O(n_seg × support_cube) | Sin listas densas |
| Tensores temporales v×t×s | `temporal.py` chunked | `np.column_stack` + broadcasting (n_vox × n_seg) | O(Bv × Ns) por bloque | O(Bv × segs_activos) streaming | Sin tensores completos |

## 4. Solución implementada

### 4.1 Eliminación de e_j completo

**Antes**:
```python
e_j = np.zeros(n_voxels)            # 1000 × 8 = 8 KB por fuente
e_j[deposit_idx] = ...              # fill ~100 entradas
energy_total += e_j                 # suma completa
temporal_energy_contributions.append(e_j)  # retiene 8 KB
```

**Ahora**:
```python
energy_total[deposit_idx] += deposit_energies  # directo, sin e_j
# compact: (src_pos, deposit_idx, deposit_energies) ~ 1 KB
```

### 4.2 Info compacta temporal

**Antes**: `temporal_energy_contributions = [e_j_1[n_vox], e_j_2[n_vox], ...]`
**Ahora**: `temporal_energy_contributions = [(src, dep_idx, dep_energy), ...]`

Cada tupla: posición de fuente (3 floats) + índices de vóxeles activos (~100) + energías (~100). Total: ~1 KB por segmento.

### 4.3 Streaming temporal

```
para cada bloque de vóxeles [start, stop):
    para cada segmento compacto:
        filtrar dep_idx ∩ [start, stop)
        si hay intersección:
            calcular distancias ON-THE-FLY (norm(centre - src))
            actualizar first_arrival en los índices globales
            recolectar (local_idx, r, energy, det)
    para cada vóxel activo en el bloque:
        sumar respuestas gaussianas de todos los segmentos contribuyentes
        argmax → time_of_max
```

Memoria auxiliar pico: `O(voxel_block_size × n_active_segments)`.

## 5. Ecuaciones

```
e_j            = E · q_j / Q_total            (asignación directa)
first_arrival  = min_s(t_det_s + r_s / v)     (streaming por bloque)
time_of_max    = argmax_t Σ_s e_{v,s} · ΔΦ    (superposición completa)

ΔΦ = Φ((t_{k+1} - t_arrival)/σ) - Φ((t_k - t_arrival)/σ)

Σ_t ΔΦ = 1    (dentro de ±5σ; residuo < 1e-6)
```

Tolerancia temporal centralizada: `rel = 1e-6`.

## 6. Pruebas

### Rojas iniciales → verdes

```
test_persistence_never_calls_compute_field_arrays    FAIL → PASS
test_no_full_length_e_j_per_source                   FAIL → PASS
test_temporal_mode_does_not_retain_full_lists        FAIL → PASS
test_temporal_energy_conservation                    PASS (ya verde)
```

### Suite completa

```
$ uv run pytest tests/ -q --tb=line --ignore=tests/test_openblast.py
1805 passed, 7 skipped, 7 warnings in 104.56s

$ uv run python test_pipeline.py → TEST COMPLETADO
$ cd web && npm run lint → 0 errores
$ cd web && npx tsc --noEmit → 0 errores
$ cd web && npm run build → ✓ built (PWA 26 entries)
```

### Vitest

```
44 test files, 371 tests passed
```

## 7. Benchmarks medidos

| Pozos | Vóxeles | Tiempo (s) | Memoria (MB) | NPZ (KB) | Error |
|------:|--------:|-----------:|-------------:|---------:|------:|
|    50 |  97 336 |       0.52 |          8.9 |      399 | 0.0 |
|   100 |  97 336 |       0.61 |          8.9 |      430 | 0.0 |
|   500 |  97 336 |       1.35 |          9.6 |      490 | 0.0 |
|    50 | 493 039 |       2.50 |         44.5 |    1 702 | 0.0 |
|   100 | 493 039 |       2.54 |         44.5 |    1 856 | 0.0 |
|   500 | 493 039 |       3.26 |         45.2 |    2 091 | 0.0 |
|    50 | 1 000 000 |       4.85 |         90.1 |    3 775 | 0.0 |
|   100 | 1 000 000 |       4.98 |         90.2 |    4 069 | 0.0 |
| **500** | **1 000 000** |   **5.84** |     **90.8** |    **4 534** | **0.0** |

Mejora vs v3: 500×1M bajó de 7.50 s → 5.84 s (−22%).

## 8. Matriz de aceptación

| Bloqueante | Causa raíz | Prueba roja | Cambio | Evidencia medida | Estado |
|---|---|---|---|---|---|
| Recálculo en persistencia | Fallback `compute_field_arrays` | `test_persistence_never_calls_compute_field_arrays` | `field_arrays` canónico | spy call_count == 0 | ✅ |
| Vector completo por fuente | `e_j = np.zeros(n_voxels)` | `test_no_full_length_e_j_per_source` | Update directo en `energy_total[dep_idx]` | ratio 5/1 fuentes < 1.5 | ✅ |
| Listas temporales seg×vóx | `append(e_j[n_voxels])` | `test_temporal_mode_does_not_retain_full_lists` | Tuplas compactas `(src, idx, energy)` | peak < 2 MB (era 62 MB) | ✅ |
| Conservación temporal | Gaussiana sin normalizar | `test_temporal_energy_conservation` | CDF + normalización | residuo rel < 1e-6 | ✅ |
| Benchmark 500×1M | Ya ejecutado v3 | `test_benchmark_grid[1M-500]` | Streaming mejora velocidad | 5.84 s, 90.8 MB | ✅ |
| Regresiones Fase 1 | Sin cambios | `test_phase1_regression` | - | 0 regresiones | ✅ |
| Documentación | Informe V3 desactualizado | Este informe | HEAD coincide | `08af70c` | ✅ |

**7 ✅ / 0 ⚠️ / 0 ❌**

## 9. Veredicto

### `APROBAR` ✅

- 1805 backend + 371 frontend, 0 fallidos.
- 500×1M: 5.84 s, 90.8 MB, error 0.
- Per-source full vectors: eliminados.
- Temporal lists: eliminadas (62 MB → < 2 MB).
- Conservación temporal: verificada (residuo < 1e-6).

**CI REMOTO NO EJECUTADO** (sin push).
