"""Abstract base class for AI providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from core.ai_v2.errors import ProviderUnavailable

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

    from core.ai_v2.agent.turn import ChatTurn
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

    @property
    def supports_tool_calls(self) -> bool:
        """Whether this provider implements :meth:`stream_chat`.

        Conservative default: False. Only providers with VERIFIED
        function calling may report True; an OpenAI-compatible endpoint
        alone does not imply working tool calls (plan section 2,
        "Proveedores — regla por capacidad").
        """
        return False

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        tools: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_s: float = 120.0,
        tool_choice: str = "auto",
    ) -> "ChatTurn":
        """Complete ONE chat turn with tools available to the model.

        Unlike :meth:`stream` (an async iterator of report chunks),
        this returns a single :class:`core.ai_v2.agent.turn.ChatTurn`
        with the accumulated text, every tool call (including those
        fragmented across stream deltas), the raw finish reason and
        the provider usage.

        The default implementation signals that tool calling is not
        supported: callers must check :attr:`supports_tool_calls` and
        surface an explicit error instead of silently degrading.

        Raises:
            ProviderUnavailable: Always, in this base implementation.
        """
        raise ProviderUnavailable(
            "Provider does not support tool calling: stream_chat is not implemented."
        )