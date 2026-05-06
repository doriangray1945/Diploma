"""Single-shot pipeline for the fine-tuned furniture model.

The fine-tuned `qwen2.5-3b-furniture` model emits a complete
`{"plan": [{tool, args}, ...]}` from one LLM call given a JSON-Schema
system prompt. We feed it that prompt (built from the role-filtered tool
registry with current DB enums), parse the JSON response, and let
`PlanExecutor` + `ParseHints` handle quantifier resolution and numeric
corrections.

Single execution path — the specialist model handles tool selection +
arg filling end-to-end.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from core.agents.plan_executor import PlanExecutor
from core.agents.validator import ValidatorAgent
from core.config import CoreConfig
from core.llm.base import LLMProvider
from core.parsing import parse_user_text
from core.prompts.system import build_system_prompt
from core.providers.base import DataProvider
from core.schemas import (
    AgentResult,
    Complexity,
    Message,
    PlanStepV2,
    Role,
    SessionContext,
    UserContext,
)
from core.tools.base import ToolRegistry


log = logging.getLogger(__name__)


class _NoOpArgsFiller:
    """Drop-in for ArgsFiller used by PlanExecutor.

    The fine-tuned model already supplies args for every step; we don't
    want PlanExecutor to issue another LLM call per step. Returning {}
    makes PlanExecutor honor `step.args` as-is, then merge ParseHints
    over the top (numbers, quantifier resolution) via its existing logic.
    """

    async def fill(self, *args, **kwargs) -> dict[str, Any]:
        return {}


class Pipeline:
    """Main entry point: text in → structured result out."""

    def __init__(
        self,
        llm: LLMProvider,
        provider: DataProvider,
        config: CoreConfig | None = None,
    ):
        self.llm = llm
        self.provider = provider
        self.config = config or CoreConfig()

    async def run(
        self,
        text: str,
        tools: ToolRegistry,
        user_context: UserContext,
        session_context: SessionContext | None = None,
    ) -> AgentResult:
        session_context = session_context or SessionContext()
        role = user_context.role
        role_filtered = tools.for_role(role)
        filter_options = await self.provider.get_filter_options()
        categories = (filter_options or {}).get("categories", [])

        hints = parse_user_text(text, categories)
        if hints.triggers_reset:
            session_context.last_search = None
            session_context.visible_product_ids = []
            session_context.current_filters = {}

        # Single-turn — model trained on system + user only, no prior turns.
        # filter_options carries fresh DB enums into each tool's schema.
        prompt_messages = [
            Message(role=Role.SYSTEM,
                    content=build_system_prompt(role_filtered, role, filter_options)),
            Message(role=Role.USER, content=text),
        ]

        log.info("[CHAT] role=%s model=%s text=%r", role, self.config.chat_model, text[:80])
        try:
            response = await asyncio.wait_for(
                self.llm.chat(prompt_messages, format=None, temperature=0.0),
                timeout=self.config.planner_schema_timeout,
            )
        except asyncio.TimeoutError:
            log.warning("[CHAT] LLM timeout")
            return AgentResult(response="", complexity=Complexity.SIMPLE)
        except Exception as e:
            log.warning("[CHAT] LLM error: %r", e)
            return AgentResult(response="", complexity=Complexity.SIMPLE)

        raw = (response.get("message") or {}).get("content", "") or ""
        plan_steps = self._parse_plan(raw)
        log.info("[CHAT] parsed %d steps from raw=%r", len(plan_steps), raw[:800])

        executor = PlanExecutor(role_filtered, _NoOpArgsFiller())
        _, tool_results, issues = await executor.execute(
            plan_steps,
            context=session_context,
            user_id=user_context.user_id,
            hints=hints,
            filter_options=filter_options,
            step_texts=[text],
            fallback_text=text,
        )

        action: dict[str, Any] | None = None
        for tr in reversed(tool_results):
            if isinstance(tr.result, dict) and "action" in tr.result:
                action = tr.result
                break

        result = AgentResult(
            response="",
            complexity=Complexity.COMPLEX if len(plan_steps) > 1 else Complexity.SIMPLE,
            tool_results=tool_results,
            action=action,
            validation_issues=issues,
        )

        validator = ValidatorAgent(self.provider)
        return await validator.validate(result)

    @staticmethod
    def _parse_plan(raw: str) -> list[PlanStepV2]:
        """Extract plan steps from the model's JSON response.

        Tolerates: bare `{...}` or wrapped in markdown ```json fences,
        and the rare bug where the model emits `"parameters"` instead of `"args"`.
        """
        if not raw:
            return []
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                return []
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError as e:
                log.warning("[CHAT] plan JSON parse failed: %r", e)
                return []
        if not isinstance(obj, dict):
            return []
        raw_steps = obj.get("plan") or []
        if not isinstance(raw_steps, list):
            return []
        steps: list[PlanStepV2] = []
        for i, s in enumerate(raw_steps):
            if not isinstance(s, dict):
                continue
            tool_name = s.get("tool")
            if not isinstance(tool_name, str) or not tool_name:
                continue
            args = s.get("args") if isinstance(s.get("args"), dict) else None
            if args is None and isinstance(s.get("parameters"), dict):
                args = s["parameters"]
            steps.append(PlanStepV2(step_id=f"step_{i + 1}", tool=tool_name, args=args or {}))
        return steps
