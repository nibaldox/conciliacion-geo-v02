# Migration Guide: AI Agent v1 → v2

If you were using the old AI agent code, here's how to migrate to v2.

## What was removed

| Old symbol                                       | File                          | Status   |
|--------------------------------------------------|-------------------------------|----------|
| `core.ai_reporter.generate_geotech_report`       | `core/ai_reporter.py`         | DELETED  |
| `core.ai_service.build_analysis_prompt`          | `core/ai_service.py`          | DELETED  |
| `core.ai_service.PROVIDERS`                      | `core/ai_service.py`          | DELETED  |
| `core.ai_service.stream_report`                  | `core/ai_service.py`          | DELETED  |
| `core.ai_service.check_provider_health`          | `core/ai_service.py`          | DELETED  |
| `core.ai_service.get_available_models`           | `core/ai_service.py`          | DELETED  |
| `api.routers.ai.router`                          | `api/routers/ai.py`           | DELETED  |
| `web/src/components/export/AIReporter.tsx`       | `web/.../AIReporter.tsx`      | DELETED  |
| `ui/tabs/ai_report.py` (legacy)                  | `ui/tabs/ai_report.py`        | REWRITTEN|

## What replaces it

| New symbol                                       | File                          |
|--------------------------------------------------|-------------------------------|
| `core.ai_v2.stream_report`                       | `core/ai_v2/service.py`       |
| `core.ai_v2.builder.build_analysis_prompt`       | `core/ai_v2/builder.py`       |
| `core.ai_v2.AIConfig`                            | `core/ai_v2/config.py`        |
| `core.ai_v2.AIRequest / AIResponseChunk / AIUsage` | `core/ai_v2/models.py`     |
| `core.ai_v2.ProviderType / ProviderRegistry`     | `core/ai_v2/providers/registry.py` |
| `core.ai_v2.providers.OpenAICompatibleProvider`  | `core/ai_v2/providers/openai_compat.py` |

## Migration recipes

### Recipe 1: Replace `generate_geotech_report` calls

**Before** (v1, legacy Streamlit path):

```python
from core.ai_reporter import generate_geotech_report

for chunk in generate_geotech_report(stats, api_key, model_name, base_url):
    print(chunk, end="", flush=True)
```

**After** (v2, async):

```python
import asyncio
from core.ai_v2 import AIRequest, ProviderType, stream_report

request = AIRequest(
    provider="ollama",
    model="llama3.1:8b",
    results={"comparisons": [...]},
    metadata={"project_name": "X", "seccion": "S-1"},
)

async def main():
    async for chunk in stream_report(request):
        if chunk.content:
            print(chunk.content, end="", flush=True)

asyncio.run(main())
```

### Recipe 2: Replace `build_analysis_prompt` calls

**Before** (v1, modern path):

```python
from core.ai_service import build_analysis_prompt

prompt_str = build_analysis_prompt(
    results=results, sections=sections, settings=settings, blast_trend=trend
)
```

**After** (v2):

```python
from core.ai_v2.builder import build_analysis_prompt

system, user = build_analysis_prompt(
    results=results,
    sections=sections,
    settings=settings,
    blast_trend=trend,
    project_name="Mina Sur",
    fecha_informe="2026-06-21",
)
```

The v1 prompt is a single string; v2 returns `(system, user)`.
This matches the OpenAI/Anthropic chat completions format.

### Recipe 3: Replace `stream_report` (v1 modern) with v2

**Before** (v1, modern FastAPI path):

```python
from core.ai_service import stream_report

for chunk in stream_report(provider="ollama", model="llama3.1", user_prompt=prompt):
    yield chunk
```

**After** (v2):

```python
from core.ai_v2 import stream_report, AIRequest, ProviderType

request = AIRequest(
    provider=ProviderType.OLLAMA.value,
    model="llama3.1",
    results={"comparisons": [...]},
)

async for chunk in stream_report(request):
    yield chunk
```

### Recipe 4: Replace provider config

**Before** (v1, hardcoded in `core/ai_service.py`):

```python
PROVIDERS = {
    "ollama": {"base_url": "http://localhost:11434/v1", "default_model": "llama3.1:8b"},
    "lmstudio": {"base_url": "http://localhost:1234/v1", "default_model": "loaded-model"},
}
```

**After** (v2, in `core/ai_v2/providers/registry.py`):

```python
from core.ai_v2.providers import PROVIDER_PRESETS, ProviderRegistry, ProviderType

# 6 providers (incl. cloud: openai, minimax, glm, grok)
for p in ProviderType:
    print(p.value, PROVIDER_PRESETS[p])

# Get an instance
provider = ProviderRegistry.get(ProviderType.OPENAI)  # reads OPENAI_API_KEY
```

API keys come from env vars (`OLLAMA_API_KEY`, `OPENAI_API_KEY`, etc.)
or are passed explicitly:

```python
provider = ProviderRegistry.get(ProviderType.OPENAI, api_key="sk-...")
```

### Recipe 5: Replace FastAPI streaming endpoint

**Before** (v1, `api/routers/ai.py`):

```python
@router.post("/report")
async def report(request: AIRequest, ...):
    return StreamingResponse(
        stream_report(provider, model, request.user_prompt),
        media_type="text/event-stream",
    )
```

**After** (v2 — endpoint removed, here's how to bring it back):

```python
# api/routers/ai.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from core.ai_v2 import AIRequest, stream_report, AIConfig

router = APIRouter()

@router.post("/report")
async def report(request: AIRequest):
    config = AIConfig()
    async def event_stream():
        async for chunk in stream_report(request, config=config):
            yield f"data: {chunk.model_dump_json()}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

## Configuration migration

| v1 (Streamlit UI)                | v2 (env var or code)             |
|----------------------------------|----------------------------------|
| `ui/sidebar.py` checkbox "Habilitar IA" | always enabled in `ui/tabs/ai_report.py` |
| `text_input("OpenAI API Key")`   | `OPENAI_API_KEY` env var         |
| `selectbox(["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"])` | `text_input` in tab (any model name) |
| `text_input("Base URL", value="http://localhost:1234/v1")` | auto-populated from `PROVIDER_PRESETS` |

## Behavior changes

| Aspect              | v1                                  | v2                              |
|---------------------|-------------------------------------|---------------------------------|
| Temperature         | Legacy: not set (default ~1.0)     | `0.3` by default                |
| Max tokens          | Legacy: not set (unlimited)        | `4096` by default               |
| Timeout             | Legacy: not set (hangs forever)     | `120s` by default               |
| Stream              | Yes, but `chunk.choices[0]` unguarded (IndexError on LM Studio) | Yes, with `if chunk.choices` guard |
| Async               | Legacy sync, modern async          | Async everywhere                |
| Error types         | Generic `Exception`                | `AIError` hierarchy             |
| Cache               | None                               | Optional disk cache (sha256)    |
| Rate limit          | HTTP-level only                    | Token + request rate limits     |
| Providers           | OpenAI nube + 2 locales            | 6 providers (4 cloud + 2 local) |

## What stays the same

- The 3 Markdown prompt templates (system_role, executive_summary,
  blast_enrichment) are still loaded from `core/ai_v2/prompts/*.md`.
- The `AIUsage` / `AIRequest` / `AIResponseChunk` Pydantic v2 models
  are similar in spirit to the v1 `build_analysis_prompt` payload,
  but stricter (Literal types, `extra="forbid"`).
- The Streamlit tab still lives at `ui/tabs/ai_report.py` and is
  still rendered under the "🤖 Analista IA" tab in step 4.

## Rollback plan

If you need to roll back to the old code (v1 modern + v1 legacy):

```bash
git log --oneline | grep "Phase 2"   # find the commit that removed v1
git revert <sha>                     # creates a new commit that brings v1 back
```

The Phase 2 commit message documents what was removed and why. See
`docs/AI_AGENT_V2_BLUEPRINT.md` for the full architectural plan.

## Questions?

See `docs/AI_AGENT.md` for the full architecture and usage guide.
