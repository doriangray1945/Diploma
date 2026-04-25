"""Decomposer — pre-skeleton LLM step that rephrases tangled queries.

A 3B model in Ollama can't reliably do chain-of-thought decomposition of a
multi-action query in one shot. Examples that break the skeleton planner:
  «добавь в избранное и в корзину один по 4 шт, остальные по 5»
  «найди X, добавь в корзину, потом оформи заказ»
  с опечатками («коризну», «отсальные») — паттерн-матчинг ломается.

The decomposer takes the raw user text and emits a numbered list of simple
action phrases (typos fixed). The skeleton planner then picks tools off
that clean list, where each item maps cleanly to a single tool.

Skip-rule: short text without conjunction triggers — pipe-through unchanged.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from difflib import SequenceMatcher

from core.config import CoreConfig
from core.llm.base import LLMProvider
from core.schemas import Message, Role


log = logging.getLogger(__name__)


_SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {"type": "string", "maxLength": 120},
        }
    },
    "required": ["actions"],
}


_SYSTEM_PROMPT = (
    "Ты разбиваешь запрос пользователя на простые отдельные действия. "
    "Каждое действие — короткая ясная фраза на русском. "
    "Исправляй очевидные опечатки. "
    "Если в запросе несколько действий («X и Y», «найди и добавь», "
    "«остальные по 5») — раздели на отдельные пункты. "
    "Если запрос уже простой — верни список из одного элемента "
    "(не выдумывай дополнительные действия).\n\n"
    "Примеры:\n"
    'USER: «добавь все диваны до 50000 в корзину по 5 шт, остальные в избранное»\n'
    'JSON: {"actions": ["найди диваны до 50000", "добавь все найденные товары в корзину по 5 шт", "оставшиеся товары добавь в избранное"]}\n'
    'USER: «покажи диваны»\n'
    'JSON: {"actions": ["покажи диваны"]}\n'
    'USER: «найди X, добавь в корзину и оформи заказ»\n'
    'JSON: {"actions": ["найди X", "добавь все найденные товары в корзину", "оформи заказ"]}'
)


# Trigger substrings that hint at a multi-action query. Match is
# case-insensitive against the lowercased text. Whitespace boundary on each
# side is enforced via leading space (ensures «и » matches but not «или»).
_TRIGGERS = (
    " и ", " и,", "а также", "затем", "потом", "после ",
    "остальн", "оставш", "сначала", "далее",
)


def _has_trigger(text: str) -> bool:
    low = " " + text.lower() + " "
    return any(t in low for t in _TRIGGERS)


def _should_decompose(text: str) -> bool:
    """Skip-rule: pass simple short queries through unchanged."""
    if not text:
        return False
    if len(text) < 40 and "," not in text and not _has_trigger(text):
        return False
    return True


class Decomposer:
    def __init__(self, llm: LLMProvider, config: CoreConfig):
        self.llm = llm
        self.config = config

    async def maybe_decompose(self, text: str) -> str:
        """Return either the original text (skip) or a numbered action list."""
        if not _should_decompose(text):
            return text

        actions = await self._call(text)
        if not actions:
            return text

        # If single action almost identical to input, skip the decomposition.
        if len(actions) == 1:
            ratio = SequenceMatcher(None, text.lower(), actions[0].lower()).ratio()
            if ratio > 0.85:
                return text

        # Joined numbered list — easy for the skeleton planner to parse.
        return "\n".join(f"{i + 1}. {a.strip()}" for i, a in enumerate(actions))

    async def _call(self, text: str) -> list[str]:
        messages = [
            Message(role=Role.SYSTEM, content=_SYSTEM_PROMPT),
            Message(role=Role.USER, content=text),
        ]
        try:
            response = await asyncio.wait_for(
                self.llm.chat(messages, format=_SCHEMA, temperature=0.0),
                timeout=self.config.planner_schema_timeout,
            )
        except asyncio.TimeoutError:
            log.warning("Decomposer timed out")
            return []
        except Exception as e:
            log.warning("Decomposer LLM call failed: %r", e)
            return []

        raw = (response.get("message") or {}).get("content", "")
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning("Decomposer bad JSON: %r; raw=%r", e, raw[:300])
            return []

        actions = parsed.get("actions") if isinstance(parsed, dict) else None
        if not isinstance(actions, list):
            return []
        cleaned: list[str] = []
        for a in actions:
            if isinstance(a, str):
                s = re.sub(r"\s+", " ", a).strip()
                if s:
                    cleaned.append(s)
        return cleaned[:5]
