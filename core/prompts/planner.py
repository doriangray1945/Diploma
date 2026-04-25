"""Schema Router prompt and JSON Schema — built dynamically from tools + DB data.

No hardcoded examples or business-specific text. The plan items are a
discriminated `oneOf` union over registered tools — each tool owns its own
JSON Schema (via `BaseTool.param_schema`) and few-shot examples (via
`BaseTool.few_shot`). Adding a tool requires no changes here.
"""
from __future__ import annotations

import json
from typing import Any


def _merge_args_schemas(per_tool: list[dict[str, Any]]) -> dict[str, Any]:
    """Union of all per-tool args schemas into one flat properties dict.

    Per-tool `required` is intentionally dropped (different tools require
    different fields — enforced Python-side in plan_executor._validate_args).
    For shared keys (e.g. `product_ids`, `address`), enums are unioned so
    grammar-decoding stays as restrictive as possible without false-rejecting
    a valid alternative tool.
    """
    merged_props: dict[str, dict[str, Any]] = {}
    for s in per_tool:
        for key, val in (s.get("properties") or {}).items():
            if key not in merged_props:
                merged_props[key] = _clone(val)
            else:
                merged_props[key] = _widen(merged_props[key], val)
    return {"type": "object", "properties": merged_props, "required": []}


def _clone(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _clone(v)
        elif isinstance(v, list):
            out[k] = list(v)
        else:
            out[k] = v
    return out


def _widen(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Combine two schemas for the same property name into a more permissive one.

    Type mismatch → drop all constraints (any value).
    Same type:
      - both have enum     → union enums
      - only one has enum  → keep that enum (other tool path validated Python-side)
    Same array type with integer items: same rules applied to `items.enum`.
    """
    if a.get("type") != b.get("type"):
        return {}

    out = _clone(a)
    if a.get("type") == "array":
        ai = a.get("items") or {}
        bi = b.get("items") or {}
        if ai.get("type") == bi.get("type") == "integer":
            ai_enum = ai.get("enum")
            bi_enum = bi.get("enum")
            if ai_enum and bi_enum:
                out_items = _clone(ai)
                out_items["enum"] = sorted(set(ai_enum) | set(bi_enum))
                out["items"] = out_items
            elif bi_enum and not ai_enum:
                out_items = _clone(bi)
                out["items"] = out_items
            # else: keep a (already cloned)
        return out

    a_enum = a.get("enum")
    b_enum = b.get("enum")
    if a_enum and b_enum:
        out["enum"] = sorted(set(a_enum) | set(b_enum))
    elif b_enum and not a_enum:
        out["enum"] = list(b_enum)
    return out


def build_planner_schema(
    tools: Any,  # ToolRegistry
    filter_options: dict[str, Any] | None = None,
    session_context: Any | None = None,
) -> dict[str, Any]:
    """Build JSON Schema for constrained decoding.

    Ollama's grammar converter (llama.cpp GBNF) does not handle JSON Schema
    union types (oneOf/anyOf), so we cannot use a per-tool discriminated
    union. Instead we collect each tool's args schema via `tool.param_schema`,
    union the properties into one flat `args` object (preserving enums via
    set-union for shared keys), and rely on Python-side per-tool validation
    in `plan_executor._validate_args` for required/cross-field checks.

    What grammar still enforces: `tool` ∈ enum of registered names; per-field
    types, enums (categories from DB, product_ids from session), numeric
    ranges (quantity 1-99, prices ≥ 0), string patterns (phone), maxLength.
    """
    tool_names = [t.name for t in tools.all()]
    per_tool_schemas = [
        t.param_schema(filter_options, session_context) for t in tools.all()
    ]
    args_schema = _merge_args_schemas(per_tool_schemas)

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


# Generic format note — no tool/parameter names, no business specifics.
_FORMAT_NOTE = (
    "Из запроса заполни JSON. "
    "intent: execute (есть действие) / answer_only / out_of_scope. "
    "plan: упорядоченные шаги [{step_id, tool, args}]. "
    "user_message: короткий ответ на русском. "
    "ВАЖНО: НЕ подставляй параметры, которые не упомянуты в запросе и не нужны "
    "для действия — пустые/нулевые значения только засоряют. "
    "Для product_ids можно использовать $context.visible_product_ids."
)


def _render_few_shot(tools: Any) -> str:
    """Compact inline format: '"<user>" → <tool> args={...}'.

    The compact form is dramatically more effective on small models than
    embedding examples inside full {intent, plan, user_message} JSON
    objects — the latter buries the signal in structural noise that the
    model then mimics (verbose plan wrapper + empty user_message).
    """
    lines: list[str] = []
    for tool in tools.all():
        for ex in tool.few_shot() or []:
            user = ex.get("user", "")
            args = ex.get("args", {})
            args_json = json.dumps(args, ensure_ascii=False)
            lines.append(f'"{user}" → {tool.name} args={args_json}')
    return "\n".join(lines)


def _render_hints(hints: Any) -> str:
    """Render ParseHints as a one-line hint string for the LLM."""
    if hints is None:
        return ""
    parts: list[str] = []
    if getattr(hints, "category", None):
        parts.append(f"category={hints.category}")
    if getattr(hints, "search", None):
        parts.append(f"search={hints.search}")
    if getattr(hints, "max_price", None) is not None:
        parts.append(f"max_price={int(hints.max_price)}")
    if getattr(hints, "min_price", None) is not None:
        parts.append(f"min_price={int(hints.min_price)}")
    if getattr(hints, "quantity", None) is not None:
        parts.append(f"quantity={hints.quantity}")
    if getattr(hints, "quantifier", None):
        n = getattr(hints, "quantifier_n", None)
        parts.append(
            f"quantifier={hints.quantifier}" + (f"({n})" if n else "")
        )
    if not parts:
        return ""
    return "Подсказки парсера: " + ", ".join(parts)


def _render_tool_field_map(
    tools: Any,
    filter_options: dict[str, Any] | None,
    session_context: Any,
) -> str:
    """Per-tool list of allowed args fields.

    Built dynamically from each tool's own `param_schema()` — same source the
    JSON Schema uses for grammar enforcement. Teaches the model which fields
    belong to which tool (the flat-merged args schema in `build_planner_schema`
    can't express this constraint, so we surface it textually here).
    """
    lines: list[str] = []
    for tool in tools.all():
        schema = tool.param_schema(filter_options, session_context)
        fields = list((schema.get("properties") or {}).keys())
        if fields:
            lines.append(f"- {tool.name}: {', '.join(fields)}")
        else:
            lines.append(f"- {tool.name}: (без параметров)")
    return "\n".join(lines)


def build_system_prompt(
    business_prompt: str,
    tools: Any,  # ToolRegistry
    filter_options: dict[str, Any] | None,
    session_context: Any,  # SessionContext
    hints: Any | None = None,
) -> str:
    """Assemble the system prompt from purely dynamic sources.

    Sources: business_prompt (CoreConfig), tool.name + tool.few_shot()
    (per-tool), filter_options (DB), session_context (per-user state),
    hints (deterministic parser output for current user message).
    """
    parts: list[str] = []

    if business_prompt:
        parts.append(business_prompt)

    parts.append(_FORMAT_NOTE)

    tool_names = [t.name for t in tools.all()]
    if tool_names:
        parts.append("Инструменты: " + ", ".join(tool_names))

    field_map = _render_tool_field_map(tools, filter_options, session_context)
    if field_map:
        parts.append(
            "Разрешённые поля args для каждого инструмента "
            "(НЕ передавай поля из других инструментов):\n" + field_map
        )

    if filter_options:
        cats = filter_options.get("categories", [])
        if cats:
            parts.append("Категории: " + ", ".join(cats))

    examples = _render_few_shot(tools)
    if examples:
        parts.append("Примеры:\n" + examples)

    ctx_dict = session_context.to_prompt_dict() if session_context else {}
    if ctx_dict:
        parts.append("Контекст диалога: " + json.dumps(ctx_dict, ensure_ascii=False))

    hint_line = _render_hints(hints)
    if hint_line:
        parts.append(hint_line)

    return "\n".join(parts)


# ============================================================================
# Hybrid 2-step pipeline: skeleton plan + per-tool args fill
# ============================================================================
#
# Old single-call schema (`build_planner_schema` / `build_system_prompt`)
# leaks args from other tools because Ollama can't enforce per-tool oneOf.
# The hybrid splits planning from arg filling: call 1 picks tools, call N
# fills each tool's args under that tool's own (small, isolated) schema.


def build_planner_schema_skeleton(tools: Any) -> dict[str, Any]:
    """JSON Schema for plan-skeleton call: intent + tool sequence, NO args.

    Tiny schema → grammar leaves the model with nowhere to invent values.
    """
    tool_names = [t.name for t in tools.all()]
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
                    },
                    "required": ["step_id", "tool"],
                },
            },
            "user_message": {"type": "string"},
        },
        "required": ["intent", "plan", "user_message"],
    }


_SKELETON_FORMAT_NOTE = (
    "Из запроса определи: intent (execute/answer_only/out_of_scope), "
    "последовательность инструментов (plan = [{step_id, tool}]) "
    "и короткий ответ на русском (user_message). "
    "Args на этом шаге не заполняй — они придут отдельно. "
    "Не вызывай инструменты которые пользователь явно не просил."
)


def _render_tool_catalog(tools: Any) -> str:
    """Human-readable list of tools with their descriptions, for the
    skeleton prompt. The model picks tools by purpose, not by parameters."""
    lines = []
    for tool in tools.all():
        desc = (tool.description or "").strip()
        if desc:
            lines.append(f"- {tool.name}: {desc}")
        else:
            lines.append(f"- {tool.name}")
    return "\n".join(lines)


def _render_skeleton_examples(tools: Any) -> str:
    """Compact intent → tool mapping examples, sourced per-tool via
    `BaseTool.skeleton_examples()`. Teaches the model «which Russian phrase
    triggers which tool» before any args matter — critical for selection
    stability on a 3B model.
    """
    lines: list[str] = []
    for tool in tools.all():
        for phrase in tool.skeleton_examples() or []:
            lines.append(f'"{phrase}" → {tool.name}')
    return "\n".join(lines)


def build_planner_skeleton_prompt(
    business_prompt: str,
    tools: Any,
    filter_options: dict[str, Any] | None,
    session_context: Any,
    hints: Any | None = None,
) -> str:
    """System prompt for the skeleton (plan-without-args) call."""
    parts: list[str] = []

    if business_prompt:
        parts.append(business_prompt)

    parts.append(_SKELETON_FORMAT_NOTE)

    catalog = _render_tool_catalog(tools)
    if catalog:
        parts.append("Доступные инструменты:\n" + catalog)

    examples = _render_skeleton_examples(tools)
    if examples:
        parts.append("Примеры выбора инструмента:\n" + examples)

    if filter_options:
        cats = filter_options.get("categories", [])
        if cats:
            parts.append("Категории каталога: " + ", ".join(cats))

    ctx_dict = session_context.to_prompt_dict() if session_context else {}
    if ctx_dict:
        parts.append("Контекст диалога: " + json.dumps(ctx_dict, ensure_ascii=False))

    hint_line = _render_hints(hints)
    if hint_line:
        parts.append(hint_line)

    return "\n".join(parts)


def build_args_prompt(
    tool: Any,  # BaseTool
    hints: Any | None,
    session_context: Any,
    consumed_ids: set[int] | None,
    filter_options: dict[str, Any] | None,
) -> str:
    """System prompt for a per-tool args-fill call.

    Includes ONLY this tool's own context: name, description, its few_shot.
    Other tools are not mentioned — fewer distractor signals.
    """
    parts: list[str] = []

    parts.append(f"Заполни args для инструмента: {tool.name}")
    if tool.description:
        parts.append(f"Назначение: {tool.description.strip()}")

    parts.append(
        "Передавай только поля упомянутые в запросе или необходимые для действия. "
        "Не подставляй пустые/нулевые значения."
    )

    examples = tool.few_shot() or []
    if examples:
        ex_lines = []
        for ex in examples:
            user = ex.get("user", "")
            args = ex.get("args", {})
            ex_lines.append(f'"{user}" → {json.dumps(args, ensure_ascii=False)}')
        parts.append("Примеры:\n" + "\n".join(ex_lines))

    ctx_dict = session_context.to_prompt_dict() if session_context else {}
    if ctx_dict:
        parts.append("Контекст: " + json.dumps(ctx_dict, ensure_ascii=False))

    if consumed_ids:
        parts.append(
            "Уже добавлено в этом запросе (исключай при «остальные»): "
            + json.dumps(sorted(consumed_ids))
        )

    hint_line = _render_hints(hints)
    if hint_line:
        parts.append(hint_line)

    return "\n".join(parts)
