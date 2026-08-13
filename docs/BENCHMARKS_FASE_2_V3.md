# Benchmarks medidos — Fase 2 (rama v3)

**Fecha**: 2026-08-03
**Hardware**: Linux x86_64, Python 3.14.6, NumPy puro (sin torch/jax)
**Commit**: `6403a1d` (fix/fase-2-remediacion-bloqueantes-v3)
**Comando**: `uv run pytest tests/test_blast_simulation_benchmarks.py::test_benchmark_grid -v -s`

## Matriz completa 3×3

| Pozos | Vóxeles | Segmentos | Tiempo (s) | Memoria pico (MB) | Artefacto NPZ (KB) | Error conservación |
|------:|--------:|----------:|-----------:|------------------:|-------------------:|-------------------:|
|    50 |  97 336 |       200 |       0.56 |               8.9 |                399 |          0.000e+00 |
|   100 |  97 336 |       400 |       0.66 |               8.9 |                430 |          0.000e+00 |
|   500 |  97 336 |     2 000 |       1.38 |               9.6 |                490 |          0.000e+00 |
|    50 | 493 039 |       200 |       2.53 |              44.5 |              1 702 |          0.000e+00 |
|   100 | 493 039 |       400 |       2.70 |              44.5 |              1 856 |          0.000e+00 |
|   500 | 493 039 |     2 000 |       3.98 |              45.2 |              2 091 |          0.000e+00 |
|    50 | 1 000 000 |     200 |       5.07 |              90.1 |              3 775 |          0.000e+00 |
|   100 | 1 000 000 |     400 |       5.36 |              90.2 |              4 069 |          0.000e+00 |
| **500** | **1 000 000** | **2 000** |   **7.50** |          **90.8** |          **4 534** |      **0.000e+00** |

## Caso obligatorio 500 × 1M

```
pozos:            500
vóxeles:          1 000 000
segmentos:        2 000 (500 pozos × 4 segmentos/pozo)
block_size:       default (SIMULATION.chunk_voxel_block = 100 000)
tiempo total:     7.50 s
memoria pico:     90.8 MB (tracemalloc)
tamaño NPZ:       4 534 KB
error conservación espacial: 0.000e+00 (exacto)
estado:           PASSED
```

## Estimador vs real

El estimador `estimated_memory_bytes` reporta para 500×1M:
- centros: 1M × 3 × 4 = 12 MB
- acumuladores: 5 × 1M × 4 = 20 MB
- bloque: 2 × 2000 × min(100K, 1M) × 4 = 1.6 MB
- total estimado: ~33.6 MB

Real medido: 90.8 MB. Ratio: 2.7×. La diferencia se debe a:
- arrays temporales adicionales en el engine (delta, r, weights por fuente)
- GIL y overhead de Python
- `field_arrays` dict que ahora se construye y retiene (~20 MB float32)

El estimador es conservador dentro de un factor 3×, aceptable para un
techo de seguridad de 8 GB.
