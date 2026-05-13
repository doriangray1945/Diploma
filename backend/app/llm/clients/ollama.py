import json
import logging
from typing import Any, AsyncIterator

import httpx

from app.llm.config import CoreConfig
from app.llm.schemas import Message

log = logging.getLogger(__name__)


class OllamaProvider:
    def __init__(self, config: CoreConfig):
        self.config = config

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        format: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        ollama_messages = []
        for msg in messages:
            m: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            # Pass tool_calls back so the model sees the conversation flow
            if msg.tool_calls:
                m["tool_calls"] = [
                    {
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]
            ollama_messages.append(m)

        options: dict[str, Any] = {
            "temperature": temperature or self.config.temperature,
            "num_predict": self.config.max_tokens,
            "num_ctx": self.config.num_ctx,
        }

        payload: dict[str, Any] = {
            "model": self.config.chat_model,
            "messages": ollama_messages,
            "stream": False,
            "think": False,  # disable Qwen3 reasoning block for chat latency
            "keep_alive": self.config.keep_alive,
            "options": options,
        }

        if tools:
            payload["tools"] = tools

        if format is not None:
            # Ollama 0.4+: JSON Schema for constrained decoding
            payload["format"] = format

        log.debug(
            "[LLM] model=%s msgs=%d format=%s num_predict=%s",
            payload["model"], len(ollama_messages),
            "yes" if format else "no", options.get("num_predict"),
        )
        if format:
            log.debug("[LLM] schema tools enum: %s",
                      json.dumps(format, ensure_ascii=False)[:300])
        log.debug(
            "[LLM] system prompt (%d chars): %s",
            len(ollama_messages[0].get("content", "")),
            ollama_messages[0].get("content", "")[:200],
        )

        async with httpx.AsyncClient(timeout=self.config.request_timeout) as client:
            response = await client.post(
                f"{self.config.ollama_base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def chat_stream(
        self,
        messages: list[Message],
        temperature: float | None = None,
        num_predict: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream assistant tokens from Ollama as they're generated.

        Ollama returns NDJSON when stream=true; each line is one chunk with
        a partial content. We yield each non-empty `message.content` piece.
        Caller is responsible for accumulating the full text.
        """
        ollama_messages = [{"role": m.role.value, "content": m.content} for m in messages]
        options: dict[str, Any] = {
            "temperature": temperature if temperature is not None else self.config.temperature,
            "num_predict": num_predict if num_predict is not None else self.config.max_tokens,
            "num_ctx": self.config.num_ctx,
        }
        payload = {
            "model": self.config.chat_model,
            "messages": ollama_messages,
            "stream": True,
            "think": False,
            "keep_alive": self.config.keep_alive,
            "options": options,
        }
        async with httpx.AsyncClient(timeout=self.config.request_timeout) as client:
            async with client.stream(
                "POST", f"{self.config.ollama_base_url}/api/chat", json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        log.warning("[STREAM] non-JSON line: %r", line[:120])
                        continue
                    if chunk.get("done"):
                        return
                    piece = (chunk.get("message") or {}).get("content", "")
                    if piece:
                        yield piece
