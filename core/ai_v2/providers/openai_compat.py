"""OpenAI-compatible provider. Works with Ollama, LM Studio, OpenAI,
MiniMax, GLM, Grok — anything that exposes an OpenAI-style /v1 endpoint."""
from __future__ import annotations

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from core.ai_v2.providers.base import BaseProvider


class OpenAICompatibleProvider(BaseProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str = "not-needed",
        name: str = "unknown",
        timeout_s: float = 120.0,
    ) -> None:
        self._client = AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout_s
        )
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def stream(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 120.0,
    ):
        return self._stream_impl(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )

    async def _stream_impl(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_s: float,
    ):
        from core.ai_v2.models import AIResponseChunk

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
        try:
            models = await self._client.models.list()
            return [m.id for m in models.data]
        except Exception:
            return []

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False