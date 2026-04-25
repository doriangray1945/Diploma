"""ArgsFiller — fills `args` for a single plan step.

Called once per step in PlanExecutor's loop AFTER the previous step has
executed (so SessionContext reflects the live state). Used by the hybrid
2-step pipeline where Call 1 produces a tool-only plan skeleton and Call N
fills each tool's args under that tool's own (tiny, isolated) JSON Schema.

Three resolution paths in order:
  1. Tool has no parameters → return {}
  2. Hints fully cover the slot → deterministic Python resolution
  3. Otherwise → LLM call with `format=tool.param_schema(...)`

Path 3 is the only one that costs an LLM call. Skip-rules in path 2 keep
typical multi-step queries at 1 LLM call total (skeleton only).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from core.config import CoreConfig
from core.llm.base import LLMProvider
from core.parsing import ParseHints, apply_quantifier
from core.prompts.planner import build_args_prompt
from core.schemas import Message, Role, SessionContext
from core.tools.base import ToolRegistry


log = logging.getLogger(__name__)


PRODUCT_ID_TOOLS = {"add_to_cart", "add_to_favorites", "remove_from_favorites"}


class ArgsFiller:
    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        config: CoreConfig,
    ):
        self.llm = llm
        self.tools = tools
        self.config = config

    async def fill(
        self,
        tool_name: str,
        hints: ParseHints | None,
        context: SessionContext,
        consumed_ids: set[int],
        last_user_text: str,
        filter_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        tool = self.tools.get(tool_name)
        if tool is None:
            return {}

        schema = tool.param_schema(filter_options, context)
        props = schema.get("properties") or {}

        # Skip-rule 1: tool without parameters
        if not props:
            return {}

        # Skip-rule 2/3: deterministic resolution from hints
        det = _try_deterministic(tool_name, hints, context, consumed_ids)
        if det is not None:
            return det

        # LLM call with per-tool schema only
        prompt = build_args_prompt(
            tool, hints, context, consumed_ids, filter_options
        )
        messages = [
            Message(role=Role.SYSTEM, content=prompt),
            Message(role=Role.USER, content=last_user_text),
        ]
        try:
            response = await asyncio.wait_for(
                self.llm.chat(messages, format=schema, temperature=0.0),
                timeout=self.config.planner_schema_timeout,
            )
        except asyncio.TimeoutError:
            log.warning("ArgsFiller timeout for tool=%s", tool_name)
            return {}
        except Exception as e:
            log.warning("ArgsFiller LLM call failed for %s: %r", tool_name, e)
            return {}

        raw = (response.get("message") or {}).get("content", "")
        if not raw:
            return {}
        try:
            args = json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning("ArgsFiller bad JSON for %s: %r; raw=%r",
                        tool_name, e, raw[:300])
            return {}
        if not isinstance(args, dict):
            return {}
        return args


def _try_deterministic(
    tool: str,
    hints: ParseHints | None,
    ctx: SessionContext,
    consumed: set[int],
) -> dict[str, Any] | None:
    """Resolve args without an LLM call when possible. Returns None if not."""
    if hints is None:
        return None

    if tool == "apply_filters":
        # Skip LLM if parser found a category. We trust the regex/dictionary
        # parser more than the LLM on slot extraction — model tends to copy
        # numeric defaults (min_price=0/max_price=0) and miss `search`.
        if hints.category:
            args: dict[str, Any] = {"category": hints.category}
            if hints.search:
                args["search"] = hints.search
            if hints.max_price is not None:
                args["max_price"] = hints.max_price
            if hints.min_price is not None:
                args["min_price"] = hints.min_price
            return args
        return None

    if tool in PRODUCT_ID_TOOLS and hints.quantifier:
        ids = apply_quantifier(hints, list(ctx.visible_product_ids), consumed)
        if ids is None:
            return None
        # Empty resolution is still authoritative (e.g. «остальные» when cart
        # already consumed everything) — return empty list, validation will
        # short-circuit cleanly downstream.
        args = {"product_ids": ids}
        if tool == "add_to_cart":
            args["quantity"] = hints.quantity or 1
        return args

    return None
