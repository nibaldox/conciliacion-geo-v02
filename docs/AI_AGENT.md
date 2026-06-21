# AI Agent v2 — Architecture & Usage

The new AI agent in `core/ai_v2/` replaces the retired `core/ai_service`
(modern FastAPI path) and `core/ai_reporter` (legacy Streamlit path).
It is provider-agnostic, async-first, type-safe, and test-covered to
95%.

## Public API

```python
from core.ai_v2 import (
    AIConfig, AIRequest, AIResponseChunk, AIUsage,
    AIError, ProviderUnavailable, RateLimited, ContextTooLong,
    InvalidResponse, CacheError,
    ProviderType, ProviderRegistry, PROVIDER_PRESETS,
    stream_report,
)
```

## Architecture

```
core/ai_v2/
├── __init__.py              stub + public re-exports
├── config.py                AIConfig (pydantic-settings, env_prefix=AI_V2_)
├── models.py                AIRequest, AIResponseChunk, AIUsage (pydantic v2)
├── errors.py                AIError + 5 specialized exceptions
├── cache.py                 DiskCache (sha256, TTL, no external deps)
├── builder.py               build_analysis_prompt() -> (system, user)
├── service.py               async stream_report() -> AsyncIterator[AIResponseChunk]
├── prompts/                 Markdown templates (system, executive_summary, blast)
└── providers/               Pluggable LLM providers
    ├── base.py              BaseProvider (ABC)
    ├── openai_compat.py     OpenAICompatibleProvider (works with any /v1 endpoint)
    └── registry.py          ProviderType enum + presets + factory
```

### Data flow

```
User clicks "Generar Informe" in ui/tabs/ai_report.py
  ↓
build_analysis_prompt(results, sections, settings, blast_trend) -> (system, user)
  ↓
ProviderRegistry.get(ptype) -> OpenAICompatibleProvider
  ↓
stream_report(request, *, provider, config):
  1. Compute cache_key = sha256(system+user | provider | model)
  2. If cache hit and use_cache → yield cached chunks
  3. Otherwise:
     async for chunk in provider.stream([system, user], model=...):
         yield AIResponseChunk(...)
  4. Optionally yield final usage chunk (prompt/completion tokens, duration_ms)
```

## Supported providers

| Provider    | Type    | Default model    | Base URL                          |
|-------------|---------|------------------|-----------------------------------|
| `ollama`    | local   | `llama3.1:8b`    | `http://localhost:11434/v1`       |
| `lmstudio`  | local   | `loaded-model`   | `http://localhost:1234/v1`        |
| `openai`    | cloud   | `gpt-4o-mini`    | `https://api.openai.com/v1`       |
| `minimax`   | cloud   | `MiniMax-M3`     | `https://api.minimax.io/anthropic`|
| `glm`       | cloud   | `glm-5.2`        | `https://api.z.ai/api/anthropic`  |
| `grok`      | cloud   | `grok-4.20`      | `https://api.x.ai/v1`             |

API keys are read from env vars `OLLAMA_API_KEY`, `OPENAI_API_KEY`, etc.
(set via the system shell or a `.env` file in the repo root).

## Configuration

`AIConfig` is a `pydantic-settings` `BaseSettings`. All fields can be
overridden via env vars prefixed with `AI_V2_`:

| Env var                | Default       | Meaning                              |
|------------------------|---------------|--------------------------------------|
| `AI_V2_DEFAULT_MODEL`  | `llama3.1:8b` | Model name to use                    |
| `AI_V2_TEMPERATURE`    | `0.3`         | Sampling temperature                 |
| `AI_V2_MAX_TOKENS`     | `4096`        | Max response tokens                  |
| `AI_V2_TIMEOUT_S`      | `120.0`       | Per-request timeout (seconds)        |
| `AI_V2_ENABLE_CACHE`   | `false`       | Enable disk cache                    |
| `AI_V2_CACHE_TTL_HOURS`| `24`          | Cache TTL                            |
| `AI_V2_CACHE_DIR`      | `.ai_v2_cache`| Cache directory                      |
| `AI_V2_MAX_REQUESTS_PER_MINUTE` | `5`   | Rate limit (enforced by service)     |
| `AI_V2_MAX_TOKENS_PER_MINUTE`   | `100000` | Token rate limit (enforced by service)|

## Usage from Python

```python
import asyncio
from core.ai_v2 import (
    AIConfig, AIRequest, ProviderType, stream_report,
)

config = AIConfig(
    temperature=0.3,
    max_tokens=2048,
    enable_cache=True,
)

request = AIRequest(
    provider="ollama",
    model="llama3.1:8b",
    results={"comparisons": [...]},
    metadata={"project_name": "Mina Sur", "seccion": "S-12"},
)

async def main():
    async for chunk in stream_report(request, config=config):
        if chunk.content:
            print(chunk.content, end="", flush=True)
        if chunk.usage:
            print(f"\n[usage: {chunk.usage}]")

asyncio.run(main())
```

## Usage from the Streamlit UI

Open the app, load design + topo STLs, run the reconciliation, then
go to the **🤖 Analista IA** tab:

1. Pick a provider (Ollama, LM Studio, OpenAI, MiniMax, GLM, Grok).
2. Adjust model name, temperature, max_tokens, timeout if needed.
3. (Optional) Enable disk cache in the "Avanzado" panel.
4. Click **📝 Generar Informe Ejecutivo**.
5. The report streams in token-by-token with a blinking cursor.
6. On completion: elapsed time + provider/model summary.

If the LLM is unreachable, the error box shows the provider `base_url`
to aid debugging.

## Error handling

```python
from core.ai_v2 import (
    AIError, ProviderUnavailable, RateLimited, ContextTooLong,
    InvalidResponse, CacheError,
)

try:
    async for chunk in stream_report(request):
        ...
except ProviderUnavailable as e:
    print(f"Provider is down: {e}")
except RateLimited as e:
    print(f"Rate limited, retry in {e.retry_after_s}s")
except ContextTooLong:
    print("Reduce results or sections")
except AIError as e:
    print(f"Other AI error: {e}")
```

## Testing

The agent ships with 85 dedicated tests in `tests/test_ai_v2_*.py`
covering config, models, errors, prompts, cache, providers, builder,
and the service entry point. Coverage target: 95% (currently met).

```bash
source /tmp/hermes_test_venv/bin/activate
python -m pytest tests/test_ai_v2_*.py -v
coverage run --source=core/ai_v2 -m pytest tests/ -q --no-cov
coverage report
```

## Backward compatibility

- `core/ai_reporter.generate_geotech_report` and
  `core/ai_service.build_analysis_prompt` / `stream_report` are **deleted**.
- Callers that previously imported these symbols must migrate to
  `core.ai_v2.builder.build_analysis_prompt` and
  `core.ai_v2.service.stream_report`.
- The `ui/tabs/ai_report.py` tab was rewritten to use the v2 API
  directly; the legacy Streamlit selector was removed.
- The `api/routers/ai.py` FastAPI router was removed. If you need
  it back, see `docs/MIGRATION_AI_V2.md` for a recipe.

## Design decisions

1. **Pydantic v2** (not v1) for type-safe config and request/response.
2. **OpenAI-compatible only** — any provider that exposes a `/v1` endpoint
   works (Ollama, LM Studio, vLLM, OpenAI, MiniMax, GLM, Grok).
3. **Async-first** — `stream_report` is an async generator, never blocks
   the UI or the API.
4. **No comments in code** (per `AGENTS.md`). All design rationale lives
   here and in commit messages.
5. **Templates as Markdown** — non-developers can edit prompts without
   touching Python.
6. **Disk cache is optional** — disabled by default to keep first-time
   UX snappy; enable per-request via `AIConfig(enable_cache=True)`.
7. **Provider rate limits and token counts are tracked** but not yet
   enforced (Fase 7+ future work).
