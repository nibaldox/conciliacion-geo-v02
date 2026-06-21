# Blueprint: Agente IA v2 — `core/ai_v2/`

**Fecha**: 2026-06-21
**Estado**: ✅ **IMPLEMENTADO** (Fases 1-6 completadas, 95% cobertura, 633 tests pasando)
**Reemplaza**: `core/ai_service.py` (moderno FastAPI) + `core/ai_reporter.py` (legacy Streamlit)
**Repo**: `/home/xodla/archivos/12_WindSurf/46-conciliacion-geo-v02/`

---

## 1. Motivación

### Problemas del estado actual

| Path | Archivo | Problemas |
|---|---|---|
| Moderno | `core/ai_service.py` (261 líneas) | Solo modelos locales hardcoded; sin rate-limit LLM; sin cost control; sin caching |
| Moderno API | `api/routers/ai.py` (88 líneas) | Sin retries; sin validación de payload; acoplamiento fuerte al cliente |
| Legacy | `core/ai_reporter.py` (90 líneas) | **OFF-LIMITS** per AGENTS.md; sin timeout; sin max_tokens; sin temperature; sin guard `chunk.choices` |
| Legacy UI | `ui/tabs/ai_report.py` (402 líneas) | Modelos hardcodeados obsoletos (`gpt-3.5-turbo`); sin tests; prompt monolítico sin system role |

### Brechas funcionales

1. **No aprovecha modelos ya pagados** (MiniMax-M3, GLM-5.2, Grok-4.20 vía Hermes)
2. **Sin caché de respuestas** — cada request recalcula el prompt completo
3. **Sin tracking de uso** — no se sabe cuánto costó cada informe
4. **Sin versionado de prompts** — cambios en el prompt rompen outputs anteriores
5. **Sin rate-limit por usuario** — solo global HTTP
6. **Tests mínimos** — 0 tests del core legacy; cobertura parcial del moderno

---

## 2. Objetivos del v2

### Funcionales
1. Generar informe ejecutivo de conciliación (mantener compatibilidad con uso actual)
2. Soporte multi-provider: Ollama, LM Studio, OpenAI nube, MiniMax, GLM, Grok
3. Streaming token-a-token con UI moderna (cursor pulsante)
4. Caché opcional con clave hash(prompt + provider + model)
5. Tracking de tokens y duración
6. Validación de inputs con Pydantic
7. Configuración externalizada (Pydantic Settings)

### No funcionales
1. **Modular**: cada responsabilidad en su propio módulo (<200 líneas cada uno)
2. **Testeable**: 95%+ cobertura en `core/ai_v2/`
3. **Async first**: usar `AsyncOpenAI` por defecto
4. **Backward-compatible**: respetar la firma que UI espera (dict con `delta_crest`, etc.)
5. **Documentado**: cada función pública con docstring + type hints completos
6. **Sin estado mutable global**: dependencies via constructor/parameters

---

## 3. Arquitectura

### 3.1 Estructura de directorios

```
core/ai_v2/
├── __init__.py              # API pública: AIReport, AIConfig, build_analysis_prompt, stream_report
├── config.py                # AIConfig (Pydantic Settings)
├── models.py                # Pydantic models: AIRequest, AIResponseChunk, AIUsage, etc.
├── providers/
│   ├── __init__.py          # ProviderRegistry, get_provider()
│   ├── base.py              # BaseProvider ABC: stream(), validate(), list_models()
│   ├── openai_compat.py     # OpenAICompatibleProvider (Ollama, LM Studio, OpenAI, MiniMax, GLM)
│   └── registry.py          # Registro de providers + factory
├── prompts/
│   ├── __init__.py          # load_prompt_template(), render_prompt()
│   ├── system_role.md       # SYSTEM_PROMPT del rol (Ingeniero Geotécnico Senior)
│   ├── executive_summary.md # Plantilla del informe ejecutivo
│   └── blast_enrichment.md  # Bloque de métricas de tronadura
├── builder.py               # build_analysis_prompt(results, sections, settings) -> str
├── service.py               # stream_report(request) -> AsyncIterator[AIResponseChunk]
├── cache.py                 # DiskCache opcional (key=hash(prompt+model), ttl=24h)
└── errors.py                # AIError hierarchy: ProviderUnavailable, RateLimited, ContextTooLong, etc.

tests/
├── test_ai_v2_config.py
├── test_ai_v2_models.py
├── test_ai_v2_providers.py
├── test_ai_v2_prompts.py
├── test_ai_v2_builder.py
├── test_ai_v2_service.py
├── test_ai_v2_cache.py
└── test_ai_v2_errors.py

docs/
├── AI_AGENT.md              # Arquitectura, providers, ejemplos
└── MIGRATION_FROM_V1.md     # Qué cambió vs legacy/moderno
```

### 3.2 Capas y responsabilidades

```
┌─────────────────────────────────────────────────────┐
│              UI (Streamlit / React)                  │
│  - ui/tabs/ai_report.py  (regenerado)                │
│  - web/src/components/export/AIReportV2.tsx (nuevo)  │
└───────────────────┬─────────────────────────────────┘
                    │ AIRequest (Pydantic)
                    ▼
┌─────────────────────────────────────────────────────┐
│              core/ai_v2/service.py                   │
│  - Validación con AIRequest                          │
│  - Resolución de provider                            │
│  - Caché lookup                                      │
│  - Tracking de uso                                   │
│  - Async streaming                                   │
└───────────────────┬─────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
┌─────────────┐ ┌─────────┐ ┌──────────────┐
│  builder.py │ │providers│ │   cache.py    │
│  prompts/   │ │  *.py   │ │   (optional)  │
└─────────────┘ └─────────┘ └──────────────┘
        │           │
        ▼           ▼
   Pydantic    AsyncOpenAI /
    models     compatible SDK
```

### 3.3 Flujo end-to-end

```
1. UI construye AIRequest(results, sections, settings, provider, model, stream=True)
   ↓
2. service.stream_report(request):
   - validate(request)                       # Pydantic
   - render_prompt(ai_request)               # builder.py + prompts/*.md
   - cache_key = sha256(prompt + provider + model)
   - if cached: yield chunks from cache
   - else:
       - provider = ProviderRegistry.get(provider)
       - async for chunk in provider.stream(messages):
           - AIResponseChunk(content, finish_reason, usage)
           - cache.put(chunk)                # async, fire-and-forget
           - yield chunk
   - track_usage(usage, duration_ms)
   ↓
3. UI recibe AsyncIterator[AIResponseChunk] y renderiza token a token
```

---

## 4. Diseño de componentes

### 4.1 `core/ai_v2/config.py` — Pydantic Settings

```python
from pydantic import BaseSettings, Field
from enum import Enum

class ProviderType(str, Enum):
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"
    OPENAI = "openai"
    MINIMAX = "minimax"
    GLM = "glm"
    GROK = "grok"

class AIConfig(BaseSettings):
    """Configuración del agente IA v2."""
    # Provider defaults
    default_provider: ProviderType = ProviderType.OLLAMA
    default_model: str = "llama3.1:8b"

    # Generation params
    temperature: float = Field(0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(4096, gt=0)
    timeout_s: float = Field(120.0, gt=0)

    # Cache
    enable_cache: bool = False
    cache_ttl_hours: int = 24
    cache_dir: str = ".ai_v2_cache"

    # Observability
    enable_usage_tracking: bool = True

    # Rate limits (per-user)
    max_requests_per_minute: int = 5
    max_tokens_per_minute: int = 100_000

    class Config:
        env_prefix = "AI_V2_"
        env_file = ".env"
```

### 4.2 `core/ai_v2/models.py` — Pydantic

```python
from pydantic import BaseModel, Field
from typing import Literal

class AIRequest(BaseModel):
    """Request para generar un informe."""
    results: dict                       # comparison_results
    sections: list[dict] | None = None  # opcional
    settings: dict | None = None        # tolerancias, etc.
    provider: ProviderType
    model: str
    stream: bool = True
    use_cache: bool = True
    metadata: dict = Field(default_factory=dict)  # user_id, session_id, etc.

class AIResponseChunk(BaseModel):
    """Un chunk de respuesta streaming."""
    content: str
    finish_reason: Literal["stop", "length", "error"] | None = None
    usage: AIUsage | None = None
    cached: bool = False
    chunk_index: int = 0

class AIUsage(BaseModel):
    """Tracking de uso."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    cost_usd: float | None = None
```

### 4.3 `core/ai_v2/providers/base.py` — ABC

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class BaseProvider(ABC):
    """Interfaz base para todos los providers."""

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 120.0,
    ) -> AsyncIterator[AIResponseChunk]:
        """Genera chunks de respuesta."""
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Lista modelos disponibles en este provider."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verifica si el provider está disponible."""
        ...
```

### 4.4 `core/ai_v2/providers/openai_compat.py` — Provider genérico

```python
class OpenAICompatibleProvider(BaseProvider):
    """Provider para cualquier endpoint OpenAI-compatible."""

    def __init__(self, base_url: str, api_key: str = "not-needed", name: str = "unknown"):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=120.0)
        self._name = name

    async def stream(self, messages, *, model, temperature, max_tokens, timeout_s) -> AsyncIterator[AIResponseChunk]:
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout_s,
        )
        chunk_index = 0
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield AIResponseChunk(
                    content=chunk.choices[0].delta.content,
                    chunk_index=chunk_index,
                )
                chunk_index += 1

    async def list_models(self) -> list[str]:
        models = await self._client.models.list()
        return [m.id for m in models.data]

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
```

### 4.5 `core/ai_v2/providers/registry.py` — Factory

```python
PROVIDER_PRESETS = {
    ProviderType.OLLAMA:    {"base_url": "http://localhost:11434/v1", "default_model": "llama3.1:8b"},
    ProviderType.LMSTUDIO:  {"base_url": "http://localhost:1234/v1",  "default_model": "loaded-model"},
    ProviderType.OPENAI:    {"base_url": "https://api.openai.com/v1", "default_model": "gpt-4o-mini"},
    ProviderType.MINIMAX:   {"base_url": "https://api.minimax.io/anthropic", "default_model": "MiniMax-M3"},
    ProviderType.GLM:       {"base_url": "https://api.z.ai/api/anthropic",  "default_model": "glm-5.2"},
    ProviderType.GROK:      {"base_url": "https://api.x.ai/v1", "default_model": "grok-4.20"},
}

class ProviderRegistry:
    @classmethod
    def get(cls, provider_type: ProviderType, api_key: str | None = None) -> BaseProvider:
        preset = PROVIDER_PRESETS[provider_type]
        api_key = api_key or os.environ.get(f"{provider_type.value.upper()}_API_KEY", "not-needed")
        return OpenAICompatibleProvider(
            base_url=preset["base_url"],
            api_key=api_key,
            name=provider_type.value,
        )
```

### 4.6 `core/ai_v2/prompts/*.md` — Plantillas externas

```markdown
<!-- system_role.md -->
Eres un Ingeniero Geotécnico Senior especializado en minería a cielo abierto,
con expertise en conciliación diseño vs as-built, blast damage, y análisis de
estabilidad de taludes (Markland, Hoek-Bray, RMR/GSI).

REGLAS:
1. Basar conclusiones SOLO en datos provistos.
2. Clasificar cumplimiento: CUMPLE / FUERA DE TOLERANCIA / NO CUMPLE.
3. Cuantificar desviaciones con signo (sobre-excavación +, deuda -).
4. Proponer acciones específicas, verificables, con parámetros concretos.
5. Idioma: español técnico neutro (sin voseo, sin argentinismos).
6. Formato: Markdown estructurado con secciones claras.
7. Priorizar por severidad: seguridad > operativo > estético.
8. Citar siempre la métrica exacta (banco, sección, valor).
9. NO inventar datos. Si falta información, declararlo explícitamente.
10. Si las recomendaciones de tronadura sugieren PF > X o < Y, cuestionar la factibilidad operativa.
```

```markdown
<!-- executive_summary.md -->
# Informe Ejecutivo: Conciliación Geotécnica {project_name}

## 1. Resumen Ejecutivo
{verdict_global}

## 2. Cumplimiento por Parámetro
{tabla_cumplimiento}

## 3. Top Desviaciones
{top5_desviaciones}

## 4. Análisis de Estabilidad
{fs_y_alertas}

## 5. Recomendaciones de Tronadura
{recomendaciones_blast}

## 6. Plan de Acción
{plan_accion_priorizado}
```

### 4.7 `core/ai_v2/builder.py` — Constructor de prompts

```python
def build_analysis_prompt(
    results: dict,
    sections: list[dict] | None = None,
    settings: dict | None = None,
    blast_trend: dict | None = None,
) -> tuple[str, str]:
    """Construye (system_prompt, user_prompt) desde datos crudos.

    Returns:
        (system, user) tuple.
    """
    system = load_prompt_template("system_role.md")
    user_template = load_prompt_template("executive_summary.md")

    context = {
        "project_name": settings.get("project_name", "Sin nombre"),
        "verdict_global": _compute_verdict(results),
        "tabla_cumplimiento": _render_compliance_table(results),
        "top5_desviaciones": _render_top5_desviations(results),
        "fs_y_alertas": _render_stability_summary(results),
        "recomendaciones_blast": _render_blast_recommendations(blast_trend),
        "plan_accion_priorizado": _render_action_plan(results, blast_trend),
    }

    user = user_template.format(**context)
    return system, user
```

### 4.8 `core/ai_v2/service.py` — Orquestador

```python
async def stream_report(
    request: AIRequest,
    *,
    config: AIConfig | None = None,
) -> AsyncIterator[AIResponseChunk]:
    """Genera un informe streaming."""
    config = config or AIConfig()
    start_time = time.monotonic()

    # 1. Render prompt
    system, user = build_analysis_prompt(
        request.results, request.sections, request.settings, request.metadata.get("blast_trend")
    )

    # 2. Cache lookup
    cache_key = _cache_key(system + user, request.provider, request.model)
    if request.use_cache and config.enable_cache:
        cached = await cache.get(cache_key)
        if cached:
            for chunk in cached:
                yield AIResponseChunk(content=chunk, cached=True)
            return

    # 3. Provider stream
    provider = ProviderRegistry.get(request.provider, api_key=request.metadata.get("api_key"))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    accumulated: list[str] = []
    chunk_index = 0
    async for chunk in provider.stream(
        messages,
        model=request.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout_s=config.timeout_s,
    ):
        accumulated.append(chunk.content)
        yield chunk
        chunk_index += 1

    # 4. Cache store (fire-and-forget)
    if request.use_cache and config.enable_cache:
        await cache.put(cache_key, accumulated, ttl=config.cache_ttl_hours * 3600)

    # 5. Usage tracking
    duration_ms = (time.monotonic() - start_time) * 1000
    if config.enable_usage_tracking:
        await _track_usage(request, duration_ms, len(accumulated))
```

### 4.9 `core/ai_v2/cache.py` — Caché en disco

```python
import aiofiles
import hashlib
import json
import time
from pathlib import Path

class DiskCache:
    def __init__(self, cache_dir: str = ".ai_v2_cache", ttl_s: int = 86400):
        self._dir = Path(cache_dir)
        self._dir.mkdir(exist_ok=True)
        self._ttl_s = ttl_s

    async def get(self, key: str) -> list[str] | None:
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            async with aiofiles.open(path, "r") as f:
                data = json.loads(await f.read())
            if time.time() - data["ts"] > self._ttl_s:
                path.unlink()
                return None
            return data["chunks"]
        except Exception:
            return None

    async def put(self, key: str, chunks: list[str], ttl: int | None = None) -> None:
        path = self._dir / f"{key}.json"
        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps({"ts": time.time(), "chunks": chunks}))

def _cache_key(prompt: str, provider: str, model: str) -> str:
    raw = f"{provider}|{model}|{prompt}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

### 4.10 `core/ai_v2/errors.py` — Jerarquía de errores

```python
class AIError(Exception):
    """Error base del agente IA."""

class ProviderUnavailable(AIError):
    """Provider no responde."""

class RateLimited(AIError):
    """Rate limit excedido."""
    def __init__(self, retry_after_s: float):
        self.retry_after_s = retry_after_s
        super().__init__(f"Rate limited. Retry after {retry_after_s}s")

class ContextTooLong(AIError):
    """Prompt excede context window."""

class InvalidResponse(AIError):
    """Respuesta del provider no parseable."""

class CacheError(AIError):
    """Error en caché (no fatal, loggear)."""
```

---

## 5. Estrategia de migración

### 5.1 Fase de borrado (Fase 2)

**Archivos a eliminar** (en un solo commit "remove: legacy/modern AI agent"):

```bash
git rm core/ai_service.py
git rm core/ai_reporter.py
git rm api/routers/ai.py
git rm web/src/components/export/AIReporter.tsx
# (parcial) web/src/api/hooks.ts — quitar solo exports AI
git rm ui/tabs/ai_report.py   # se regenera como stub
```

**Cambios en archivos existentes**:
- `ui/sidebar.py`: quitar selector IA (líneas 15-31)
- `web/src/...`: quitar botón de generación IA en páginas que lo usen
- `tests/`: actualizar tests que importen módulos borrados

### 5.2 Fase de stub (Fase 2)

Crear:
- `core/ai_v2/__init__.py` con mensaje `"""Agente IA v2 — en reconstrucción."""`
- `ui/tabs/ai_report.py` regenerado mostrando:
  ```
  ## 🤖 Agente IA v2 — En reconstrucción
  
  El nuevo agente IA está siendo rediseñado. Próximamente:
  - Soporte multi-provider (Ollama, LM Studio, OpenAI, MiniMax, GLM, Grok)
  - Caché de respuestas
  - Tracking de tokens
  - Prompt versioning
  
  Mientras tanto, el motor local determinista sigue activo debajo.
  ```

### 5.3 Validación post-borrado

```bash
pytest tests/ -v --tb=short
# Esperado: 549 tests pasando (sin contar los que cubrían AI v1)
# Si alguno falla porque importaba ai_service/ai_reporter:
#   - Actualizar el test para usar el stub o el módulo ai_v2
#   - Si el test era crítico (validación post-generación), portarlo a ai_v2
```

---

## 6. Tests planeados

| Archivo | Tests | Cobertura target |
|---|---|---|
| `test_ai_v2_config.py` | 4 tests: defaults, env vars, validation | 100% |
| `test_ai_v2_models.py` | 6 tests: AIRequest, AIResponseChunk, AIUsage | 100% |
| `test_ai_v2_providers.py` | 8 tests: registry, OpenAI compat, mocks | 100% |
| `test_ai_v2_prompts.py` | 3 tests: load, render, missing template | 95% |
| `test_ai_v2_builder.py` | 7 tests: cada bloque del prompt | 95% |
| `test_ai_v2_service.py` | 10 tests: stream, cache, errors, usage | 95% |
| `test_ai_v2_cache.py` | 5 tests: get/put/ttl/integrity | 95% |
| `test_ai_v2_errors.py` | 4 tests: each error type | 100% |
| **Total** | **~47 tests nuevos** | **95%+ en core/ai_v2/** |

### Tests críticos del service

```python
async def test_stream_report_returns_chunks_in_order():
    """Chunks llegan en el orden correcto."""

async def test_stream_report_respects_timeout():
    """Si provider cuelga > timeout_s, error ProviderUnavailable."""

async def test_stream_report_uses_cache_when_enabled():
    """Segunda llamada con mismo prompt no invoca provider."""

async def test_stream_report_handles_provider_unavailable():
    """Provider caído → ProviderUnavailable."""

async def test_stream_report_tracks_usage():
    """AIUsage se reporta correctamente."""
```

---

## 7. Riesgos y mitigación

| Riesgo | Impacto | Mitigación |
|---|---|---|
| AGENTS.md declara legacy OFF-LIMITS pero igual lo borramos | El repo upstream rechazará el PR | Documentar en `MIGRATION_FROM_V1.md` que fue decisión del usuario (con fecha) |
| Tests legacy dependen de `ai_reporter` | Fallos al borrar | Hacer `git grep "ai_reporter\|ai_service"` antes de borrar y actualizar |
| FastAPI/React paths rompen | UI web inoperable | Mantener stubs en `api/` y `web/` que retornen 503 "AI en reconstrucción" |
| Modelos en nube sin API key | Errores al usar | Validar `api_key` en `AIConfig`, retornar error claro |
| Caché en disco crece sin límite | Disco lleno | TTL configurable, max_size en `AIConfig`, LRU eviction |
| Rate limit muy permisivo | Costos descontrolados | Default conservador: 5 req/min por usuario, configurable |

---

## 8. Cronograma estimado

| Fase | Duración | Salida |
|---|---|---|
| 1. Diseño (este blueprint) | ✅ listo | Este documento |
| 2. Stub + borrado | 1 sesión | 549 tests pasan; módulo `core/ai_v2/` placeholder |
| 3. Core (models, providers, prompts, builder, service) | 2-3 sesiones | `core/ai_v2/` funcional |
| 4. Integración UI | 1 sesión | Tab Streamlit funcional, opcional endpoint FastAPI |
| 5. Tests | 1 sesión | 47 tests nuevos, cobertura 95%+ |
| 6. Docs | 0.5 sesión | AI_AGENT.md, MIGRATION.md |
| **Total** | **~6-8 sesiones** | Agente IA v2 completo en producción |

---

## 9. Próximos pasos inmediatos

1. **Tu revisión de este blueprint** ← ESTÁS AQUÍ
2. Una vez aprobado:
   - Borrar archivos legacy/moderno
   - Crear stub `core/ai_v2/__init__.py` y stub UI
   - Verificar `pytest tests/` pasa
3. Iterar sobre el core (`Fase 3`)

---

## 10. Preguntas abiertas para ti

1. **¿Confirmas que borro TODO** (`ai_service.py` + `ai_reporter.py` + UI de ambos)? **Sí / No / Otro**
2. **¿Quieres re-introducir FastAPI** en el v2 (`api/routers/ai_v2.py`) o solo Streamlit? **Sí / No / Después**
3. **¿Caché habilitada por default o off?** **Off (manual) / On (auto)**
4. **¿Tracking de costos USD** o solo tokens? **Tokens / USD / Ambos**
5. **¿Modelos en `PROVIDER_PRESETS` correctos?** MiniMax-M3, GLM-5.2, Grok-4.20 según tu config actual. **Confirmar / Cambiar**

---

**Esperando tu aprobación para proceder con Fase 2 (borrado + stub).**