"""SchemaPlannerAgent — single LLM call returning a StructuredPlan via JSON Schema."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import ValidationError

from core.config import CoreConfig
from core.llm.base import LLMProvider
from core.prompts.planner import build_planner_schema, build_system_prompt
from core.schemas import Intent, Message, Role, SessionContext, StructuredPlan
from core.tools.base import ToolRegistry


log = logging.getLogger(__name__)


class SchemaPlannerAgent:
    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        config: CoreConfig,
    ):
        self.llm = llm
        self.tools = tools
        self.config = config

    async def plan(
        self,
        messages: list[Message],
        session_context: SessionContext,
        filter_options: dict[str, Any] | None = None,
    ) -> StructuredPlan:
        """Run one LLM call constrained to PLANNER_SCHEMA, return StructuredPlan."""
        tool_names = [t.name for t in self.tools.all()]
        schema = build_planner_schema(tool_names, filter_options=filter_options)

        system_prompt = build_system_prompt(
            business_prompt=self.config.business_prompt,
            tools=self.tools,
            filter_options=filter_options,
            session_context=session_context,
        )

        full_messages = [
            Message(role=Role.SYSTEM, content=system_prompt),
            *messages,
        ]

        try:
            response: dict[str, Any] = await asyncio.wait_for(
                self.llm.chat(
                    full_messages,
                    format=schema,
                    temperature=0.0,
                ),
                timeout=self.config.planner_schema_timeout,
            )
        except asyncio.TimeoutError:
            log.warning("Schema planner timed out")
            return self._fallback("Извините, обработка заняла слишком много времени.")
        except Exception as e:
            log.warning("Schema planner LLM call failed: %r", e)
            return self._fallback(f"Извините, ассистент временно недоступен: {e}")

        raw = response.get("message", {}).get("content", "")
        if not raw:
            return self._fallback("Извините, не удалось сгенерировать ответ.")

        try:
            parsed = json.loads(raw)
            return StructuredPlan.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("Failed to parse planner output: %r; raw=%r", e, raw[:500])
            return self._fallback("Извините, не смог разобрать запрос.")

    @staticmethod
    def _fallback(message: str) -> StructuredPlan:
        return StructuredPlan(
            intent=Intent.ANSWER_ONLY,
            plan=[],
            user_message=message,
        )