import json
import logging
from typing import Any

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
