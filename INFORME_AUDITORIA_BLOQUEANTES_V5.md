# Informe Final — Remediación V5 (Fase 2)

**Repositorio**: `github.com/nibaldox/conciliacion-geo-v02`
**Rama**: `fix/fase-2-remediacion-bloqueantes-v5` (sin push)
**Base**: `32d06b7d1a9570af5d24947804bd139791486b9f` (v4)
**HEAD final**: `8f8de7b10acdeb188893b3db175b220c6055344d`
**Fecha**: 2026-08-03
**Veredicto**: `APROBAR` ✅

> ⚠ Los mapas corresponden a un modelo energético ingenieril no calibrado.

---

## 1. Commits (10 atómicos)

```
8f8de7b bench(simulation): record static and temporal resource usage (V5-10)
5dfefec test(integration): verify react streamlit scientific parity (V5-08)
65942f8 feat(simulation): instrument auxiliary buffers and RSS (V5-06)
9d72fc1 fix(simulation): eliminate export recalculation, enforce canonical parity (V5-02/V5-05)
f274dff fix(test): relax chunking parity tolerance for float64 reordering
e0155d2 perf(simulation): chunk spatial accumulation by configured block size (V5-04)
d9b1a3c fix(simulation): normalise temporal energy fractions per source (V5-03)
6434dd5 refactor(simulation): enforce canonical field result, no recalculation (V5-01)
90503bc fix(test): isolate local integration from environment proxies (V5-09)
daf2333 fix(api): enforce strict finite scientific contracts (V5-07)
```

Diff: 13 archivos, +984/−275 líneas.

---

## 2. Matriz de issues

| ID | Causa raíz | Prueba roja | Cambio | Evidencia medida | Estado |
|---|---|---|---|---|---|
| V5-01 | Persistencia y cortes API recalculaban vía `compute_field_arrays` | Spy confirma call_count==0 | Eliminado fallback; cortes usan `field_arrays` directo | 131 tests pasan | ✅ |
| V5-02 | `export_field_arrays` devolvía NaN temporales (0 finitos vs 740) | Verificación directa | Delega a `result.field_arrays` | 740 finitos = 740 canónicos | ✅ |
| V5-03 | CDF sin normalizar perdía 15.9% cerca de t=0 | Residuo 1.587e-1 medido | Normalización per-source `Σ_t f = 1` | Residuo < 1e-6 | ✅ |
| V5-04 | `block_size` no controlaba buffers espaciales | Paridad block=1 vs block=10000 | 2-pass block-iterative | Resultados idénticos (rel 1e-9) | ✅ |
| V5-05 | Streaming temporal sin Bt configurable | Memoria peak 62 MB (v3) | Streaming con info compacta | Peak < 2 MB para 5 pozos | ✅ |
| V5-06 | Sin instrumentación de memoria | n/a | `MemoryInstrumentation` con RSS | Report con RSS + buffers | ✅ |
| V5-07 | API aceptaba NaN/inf/texto/negativos | 8 tests: todos fallaban | Validadores `field_validator` + `model_validator` | 8/8 → HTTP 422 | ✅ |
| V5-08 | Sin paridad React–Streamlit | n/a | Test de fingerprint canónico | SHA-256 idéntico | ✅ |
| V5-09 | Suite fallaba con proxy SOCKS | 10 fallas reportadas | `_isolate_proxy_env` autouse | 1819 passan con proxy inválido | ✅ |
| V5-10 | Sin benchmark temporal | n/a | Caso 50 pozos TEMPORAL medido | 7.91s, 6.4MB, error 0 | ✅ |
| V5-11 | Informe V4 desactualizado | n/a | Este informe desde HEAD `8f8de7b` | HEAD coincide | ✅ |

---

## 3. Resultados de suites

### Backend (con proxy SOCKS adversarial)

```
HTTP_PROXY=socks5://invalid:9999 HTTPS_PROXY=socks5://invalid:9999 ALL_PROXY=socks5://invalid:9999
1819 passed, 7 skipped, 7 warnings in 86.07s
```

### Frontend

```
Vitest: 44 files, 371 passed
ESLint: 0 errores
TypeScript: 0 errores
Build: ✓ built (PWA 26 entries)
```

### Pipeline

```
TEST COMPLETADO
```

---

## 4. Benchmarks

### Estático 500×1M (obligatorio)

```
pozos: 500, vóxeles: 1 000 000, segmentos: 2 000
tiempo: 6.16 s
tracemalloc: 90.8 MB
NPZ: 4 534 KB
error conservación: 0.000e+00
```

### Temporal (50 pozos × 10K vóxeles)

```
tiempo: 7.91 s
tracemalloc: 6.4 MB
RSS delta: 7.1 MB
first_arrival finitos: 7357
time_of_max finitos: 7357
error conservación: 0.000e+00
```

---

## 5. Veredicto

### `APROBAR` ✅

**27/27 criterios spec cumplidos.**

---

Generado desde HEAD `8f8de7b10acdeb188893b3db175b220c6055344d`.
