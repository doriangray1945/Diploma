import json
from typing import Any

import httpx

from core.config import CoreConfig
from core.schemas import Message


class OllamaProvider:
    def __init__(self, config: CoreConfig):
        self.config = config

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
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

        payload: dict[str, Any] = {
            "model": self.config.chat_model,
            "messages": ollama_messages,
            "stream": False,
            "think": False,  # disable Qwen3 reasoning block for chat latency
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=self.config.request_timeout) as client:
            response = await client.post(
                f"{self.config.ollama_base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
