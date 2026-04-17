from typing import Protocol, Any

from core.schemas import Message


class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        format: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]: ...
