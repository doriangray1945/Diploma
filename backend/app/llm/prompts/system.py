"""System-prompt builder for the fine-tuned furniture model.

Produces the EXACT prompt format the model was trained on (see
`dataset/generator.py:render_system_prompt()`). Industry-standard
JSON Schema function-calling format with full descriptions for each
tool and field.

Critical invariant: this output must match the training-time format.
`filter_options` (categories/colors/materials from current DB state) is
threaded into each tool's `to_json_schema()` so the prompt always carries
fresh enum lists — adding a new category in DB shows up in the next
request without retrain.
"""
from __future__ import annotations

import json
from typing import Any

from app.llm.tools.base import ToolRegistry


_DISAMBIGUATION_HINTS = (
    "Различай:\n"
    "- Описательные слова (стиль, контекст, эмоция, персона: «уютный», «лофт», «детский», «для офиса») → поле search.\n"
    "- Числа после «штук», «по N штук», «пар(а/у)» → quantity (штук одного товара). "
    "Числа без квалификатора («первые N», «N товаров», «N диванов») → n (число разных товаров).\n\n"
    "Если запрос вне scope (заказ, оплата, приветствие, off-topic) — plan пустой []."
)


def build_system_prompt(tools: ToolRegistry, role: str,
                        filter_options: dict[str, Any] | None = None) -> str:
    """Build JSON Schema prompt for the fine-tuned furniture model.

    `tools` is already role-filtered (callers pass `tools.for_role(role)`).
    `role` controls only the prompt's role label — not what's in the registry.
    `filter_options` carries DB catalog state used by tools to inject dynamic
    enums (categories/colors/materials).
    """
    role_label = "админ-режим" if role == "admin" else "пользовательский чат"
    tool_specs = [t.to_json_schema(filter_options) for t in tools.all()]
    tools_json = json.dumps({"tools": tool_specs}, ensure_ascii=False, separators=(",", ":"))
    return (
        f"Ты помощник мебельного магазина Nova Furnish ({role_label}). "
        "Анализируй запрос пользователя и составь план tool-вызовов. "
        "Верни JSON с полем `plan` — массив шагов, каждый шаг {tool, args}.\n\n"
        f"Доступные tools (JSON Schema):\n{tools_json}\n\n"
        f"{_DISAMBIGUATION_HINTS}"
    )
