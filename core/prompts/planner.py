"""Schema Router prompt and JSON Schema — built dynamically from tools + DB data.

No hardcoded examples or business-specific text. The prompt is assembled
from ToolRegistry metadata, filter_options (from DB), and CoreConfig.
"""
from __future__ import annotations

import json
from typing import Any


def build_planner_schema(
    tool_names: list[str],
    filter_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build JSON Schema for constrained decoding. Dynamic enum from DB."""
    # category: constrained enum from DB. search: free string for refinement.
    # Only these two in properties — more fields confuse 3B models.
    args_schema: dict[str, Any] = {"type": "object"}
    if filter_options:
        categories = filter_options.get("categories", [])
        if categories:
            args_schema["properties"] = {
                "category": {"type": "string", "enum": categories},
                "search": {"type": "string"},
                "product_ids": {},
                "max_price": {"type": "number"},
            }

    return {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["execute", "answer_only", "out_of_scope"],
            },
            "plan": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "string"},
                        "tool": {"type": "string", "enum": tool_names},
                        "args": args_schema,
                    },
                    "required": ["step_id", "tool", "args"],
                },
            },
            "user_message": {"type": "string"},
        },
        "required": ["intent", "plan", "user_message"],
    }


# Fixed protocol description (3 lines — format, not business logic).
# Does NOT change when you add products/categories/tools.
_FORMAT_INSTRUCTIONS = """\
Из запроса заполни JSON. intent: execute/answer_only/out_of_scope. \
plan: шаги [{step_id, tool, args}]. user_message: ответ на русском. \
category: СТРОГО из списка. search: уточнение внутри категории (детская, офисный, деревянный). \
product_ids: "context" = товары на экране. НЕ подставляй параметры которые не упомянуты.
Примеры:
"покажи кровати" → tool:apply_filters, args:{category:Кровати}
"детские кровати" → tool:apply_filters, args:{category:Кровати, search:детская}
"очисти корзину и избранное, найди стулья до 20000 и добавь в корзину и избранное" → [{tool:clear_cart, args:{}}, {tool:clear_favorites, args:{}}, {tool:apply_filters, args:{category:Стулья, max_price:20000}}, {tool:add_to_cart, args:{product_ids:context}}, {tool:add_to_favorites, args:{product_ids:context}}]"""


def build_system_prompt(
    business_prompt: str,
    tools: Any,  # ToolRegistry
    filter_options: dict[str, Any] | None,
    session_context: Any,  # SessionContext
) -> str:
    """Build system prompt dynamically from tools metadata + DB data.

    No hardcoded examples. Everything comes from:
    - business_prompt (from CoreConfig, set by backend)
    - tool.name + tool.parameters (from ToolRegistry)
    - filter_options (from DataProvider.get_filter_options — cached DB query)
    - session_context (per-user dialogue state)
    """
    parts: list[str] = []

    # Business context (from config — e.g. "Ты ассистент мебельного магазина...")
    if business_prompt:
        parts.append(business_prompt)

    # Format protocol (fixed 3 lines — never changes)
    parts.append(_FORMAT_INSTRUCTIONS)

    # Tool names only — parameter formats are enforced by JSON Schema constraint
    tool_names = [t.name for t in tools.all()]
    parts.append("Инструменты: " + ", ".join(tool_names))

    # Filter options from DB (categories, colors, prices)
    if filter_options:
        cats = filter_options.get("categories", [])
        if cats:
            parts.append("Категории: " + ", ".join(cats))
        # Colors omitted from prompt to save tokens — model can still
        # use color as free-form string via schema args

    # Session context (last search, visible products, etc.)
    ctx_dict = session_context.to_prompt_dict() if session_context else {}
    if ctx_dict:
        parts.append("Контекст диалога: " + json.dumps(ctx_dict, ensure_ascii=False))

    return "\n".join(parts)