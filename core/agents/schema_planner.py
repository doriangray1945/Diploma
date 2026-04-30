"""SchemaPlannerAgent — single LLM call returning a StructuredPlan via JSON Schema."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import ValidationError

from core.config import CoreConfig
from core.llm.base import LLMProvider
from core.prompts.planner import (
    build_planner_schema,
    build_planner_schema_skeleton,
    build_planner_skeleton_prompt,
    build_system_prompt,
)
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
        hints: Any | None = None,
        extra_system: str | None = None,
    ) -> StructuredPlan:
        """Run one LLM call constrained to PLANNER_SCHEMA, return StructuredPlan."""
        schema = build_planner_schema(
            self.tools,
            filter_options=filter_options,
            session_context=session_context,
        )

        system_prompt = build_system_prompt(
            business_prompt=self.config.business_prompt,
            tools=self.tools,
            filter_options=filter_options,
            session_context=session_context,
            hints=hints,
        )
        if extra_system:
            system_prompt = system_prompt + "\n" + extra_system

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

    async def plan_skeleton(
        self,
        messages: list[Message],
        session_context: SessionContext,
        filter_options: dict[str, Any] | None = None,
        hints: Any | None = None,
        extra_system: str | None = None,
        few_shot_plan: dict[str, Any] | None = None,
    ) -> StructuredPlan:
        """Hybrid pipeline call 1: pick tool sequence, args left empty.

        The skeleton schema has no `args` property — model can't leak fields
        between tools. Args are filled later, per-step, by ArgsFiller.

        `few_shot_plan` (optional) is a previously-successful plan for a
        semantically similar query (cache hybrid tier, sim 0.85-0.95).
        Injected into the system prompt as a soft hint to tighten generation.
        """
        schema = build_planner_schema_skeleton(self.tools)
        system_prompt = build_planner_skeleton_prompt(
            business_prompt=self.config.business_prompt,
            tools=self.tools,
            filter_options=filter_options,
            session_context=session_context,
            hints=hints,
        )
        if few_shot_plan is not None:
            system_prompt = (
                system_prompt
                + "\nПример успешного плана для похожего запроса:\n"
                + json.dumps(few_shot_plan, ensure_ascii=False)
            )
        if extra_system:
            system_prompt = system_prompt + "\n" + extra_system

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
            log.warning("Skeleton planner timed out")
            return self._fallback("Извините, обработка заняла слишком много времени.")
        except Exception as e:
            log.warning("Skeleton planner LLM call failed: %r", e)
            return self._fallback(f"Извините, ассистент временно недоступен: {e}")

        raw = response.get("message", {}).get("content", "")
        if not raw:
            return self._fallback("Извините, не удалось сгенерировать ответ.")

        try:
            parsed = json.loads(raw)
            # Skeleton steps don't include `args` — coerce to empty so
            # PlanStepV2 validation passes (default factory is dict()).
            for step in parsed.get("plan", []) or []:
                if isinstance(step, dict) and "args" not in step:
                    step["args"] = {}
            return StructuredPlan.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("Failed to parse skeleton planner output: %r; raw=%r",
                        e, raw[:500])
            return self._fallback("Извините, не смог разобрать запрос.")

    @staticmethod
    def _fallback(message: str) -> StructuredPlan:
        return StructuredPlan(
            intent=Intent.ANSWER_ONLY,
            plan=[],
            user_message=message,
        )