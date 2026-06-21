"""Abstract base class for AI providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

    from core.ai_v2.models import AIResponseChunk


class BaseProvider(ABC):
    @abstractmethod
    async def stream(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 120.0,
    ) -> AsyncIterator[AIResponseChunk]:
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...