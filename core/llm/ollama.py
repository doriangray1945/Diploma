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

        import json as _json
        print(f"[LLM] model={payload['model']} msgs={len(ollama_messages)} format={'yes' if format else 'no'} num_predict={options.get('num_predict')}")
        if format:
            print(f"[LLM] schema tools enum: {_json.dumps(format, ensure_ascii=False)[:300]}")
        print(f"[LLM] system prompt ({len(ollama_messages[0].get('content',''))} chars): {ollama_messages[0].get('content','')[:200]}")

        async with httpx.AsyncClient(timeout=self.config.request_timeout) as client:
            response = await client.post(
                f"{self.config.ollama_base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
