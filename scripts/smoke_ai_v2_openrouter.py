"""Quick smoke test for the AI agent v2 with the user's OpenRouter key.

Usage:
    source /tmp/hermes_test_venv/bin/activate
    OPENROUTER_API_KEY='sk-or-v1-...' python scripts/smoke_ai_v2_openrouter.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime

from core.ai_v2 import AIConfig, AIRequest, AIResponseChunk, stream_report
from core.ai_v2.providers import OpenAICompatibleProvider

CANDIDATE_MODELS: list[str] = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "openai/gpt-oss-20b:free",
    "openai/gpt-oss-120b:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
    "cohere/north-mini-code:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
    "qwen/qwen3-coder:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
]

API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
BASE_URL: str = "https://openrouter.ai/api/v1"


async def try_model(model_id: str) -> tuple[bool, str]:
    provider = OpenAICompatibleProvider(
        base_url=BASE_URL,
        api_key=API_KEY,
        name=f"openrouter:{model_id}",
        timeout_s=60.0,
    )
    request = AIRequest(
        provider="ollama",
        model=model_id,
        results={"comparisons": []},
        metadata={"project_name": "Smoke Test", "seccion": "S-1"},
    )
    config = AIConfig(temperature=0.3, max_tokens=128, _env_file=None)
    chunks: list[AIResponseChunk] = []
    start = datetime.now()
    try:
        async for chunk in stream_report(request, provider=provider, config=config):
            chunks.append(chunk)
    except Exception as exc:
        elapsed = (datetime.now() - start).total_seconds()
        return False, f"{type(exc).__name__}: {str(exc)[:140]} ({elapsed:.1f}s)"
    elapsed = (datetime.now() - start).total_seconds()
    full = "".join(c.content for c in chunks if c.content)
    if not full.strip():
        return False, f"empty response ({elapsed:.1f}s)"
    return True, f"OK in {elapsed:.1f}s, {len(full)} chars — {full[:60].strip()!r}..."


async def main() -> None:
    if not API_KEY:
        print("ERROR: set OPENROUTER_API_KEY env var first.", file=sys.stderr)
        sys.exit(1)
    print(f"OpenRouter key: {API_KEY[:14]}...{API_KEY[-6:]}\n")
    print(f"Probing {len(CANDIDATE_MODELS)} free models sequentially...\n")
    working: list[tuple[str, str]] = []
    for model_id in CANDIDATE_MODELS:
        print(f"  {model_id:<55} ", end="", flush=True)
        ok, msg = await try_model(model_id)
        marker = "[OK]" if ok else "[FAIL]"
        print(f"{marker}  {msg}")
        if ok:
            working.append((model_id, msg))
            print("    stopping at first working model (save rate limit budget)")
            break
    print(f"\n{len(working)}/{len(CANDIDATE_MODELS)} worked.")
    if working:
        print("\nUse this in the Streamlit 'Analista IA' tab:")
        for model_id, _ in working:
            print(f"  Provider: openrouter   Model: {model_id}")


if __name__ == "__main__":
    asyncio.run(main())