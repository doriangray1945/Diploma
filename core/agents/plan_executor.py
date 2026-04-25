"""PlanExecutor — runs a list of PlanStepV2.

In the hybrid 2-step pipeline, args for each step are filled by ArgsFiller
AFTER the previous step has executed (so SessionContext is current). Then
hints are post-merged for double-defence and Python validation runs before
the tool is invoked. consumed_ids accumulates across steps for «оставшиеся»
semantics.
"""
from __future__ import annotations

import logging
from typing import Any

from core.agents.args_filler import ArgsFiller
from core.agents.refs import RefError, _walk_path
from core.parsing import ParseHints, apply_quantifier
from core.schemas import PlanStepV2, SessionContext, ToolResult, ValidationIssue
from core.tools.base import ToolRegistry


log = logging.getLogger(__name__)


# Tools whose successful execution "consumes" product_ids (subsequent
# «оставшиеся» / «remaining» quantifier excludes already-consumed ids).
CONSUMING_TOOLS = {"add_to_cart", "add_to_favorites"}

# Tools whose args are subject to hint merging.
PRODUCT_ID_TOOLS = {"add_to_cart", "add_to_favorites", "remove_from_favorites"}


class PlanExecutor:
    def __init__(self, tools: ToolRegistry, args_filler: ArgsFiller):
        self.tools = tools
        self.args_filler = args_filler

    async def execute(
        self,
        plan: list[PlanStepV2],
        context: SessionContext,
        user_id: int,
        hints: ParseHints | None = None,
        filter_options: dict[str, Any] | None = None,
        last_user_text: str = "",
    ) -> tuple[
        dict[str, dict[str, Any]],
        list[ToolResult],
        list[ValidationIssue],
    ]:
        """Execute steps; return (step_results_by_id, tool_results, validation_issues)."""
        step_results: dict[str, dict[str, Any]] = {}
        tool_results: list[ToolResult] = []
        issues: list[ValidationIssue] = []
        consumed_ids: set[int] = set()

        for step in plan:
            # 1. Fill args via ArgsFiller (deterministic-from-hints OR per-tool LLM).
            #    Skeleton plans arrive with empty args; legacy callers may pass
            #    non-empty args — in which case we honor them as a starting point.
            try:
                filled = await self.args_filler.fill(
                    tool_name=step.tool,
                    hints=hints,
                    context=context,
                    consumed_ids=consumed_ids,
                    last_user_text=last_user_text,
                    filter_options=filter_options,
                )
            except Exception as e:
                err = f"args_fill_error: {e}"
                log.warning("Step %s args fill failed: %r", step.step_id, e)
                step_results[step.step_id] = {"error": err}
                tool_results.append(
                    ToolResult(tool_name=step.tool, result={"error": err}, error=err)
                )
                continue

            # If the planner already provided concrete args (legacy single-call
            # path), prefer them as a base layer and let `filled` override only
            # when filled is non-empty.
            resolved_args: dict[str, Any] = dict(step.args or {})
            if filled:
                resolved_args.update(filled)

            # Normalize stray "context"-string product_ids → visible_product_ids.
            pid = resolved_args.get("product_ids")
            if pid is not None and not isinstance(pid, list):
                resolved_args["product_ids"] = list(context.visible_product_ids)
            resolved_args = {k: v for k, v in resolved_args.items() if v is not None}

            # 2. Post-merge deterministic hints over LLM args (regex more
            #    accurate on numbers; quantifier authoritative for product_ids).
            resolved_args = _merge_hints(
                step.tool, resolved_args, hints,
                visible=context.visible_product_ids,
                consumed=consumed_ids,
            )

            # 3. Strip args to fields the tool actually accepts. ArgsFiller
            #    already constrains via per-tool schema, but legacy tools/refs
            #    may smuggle in extras — defence in depth.
            resolved_args = _strip_to_tool_fields(self.tools, step.tool, resolved_args)

            # 4. Per-tool semantic validation
            step_issues = _validate_args(
                step.tool, resolved_args, context, filter_options
            )
            if step_issues:
                issues.extend(step_issues)
                err = "; ".join(i.message for i in step_issues)
                log.info("Validation rejected step %s (%s): %s",
                         step.step_id, step.tool, err)
                step_results[step.step_id] = {"error": err}
                tool_results.append(
                    ToolResult(
                        tool_name=step.tool,
                        result={"error": err},
                        error=err,
                    )
                )
                continue

            # 4. Execute tool
            result = await self.tools.execute(
                step.tool, user_id=user_id, **resolved_args
            )
            step_results[step.step_id] = result
            tool_results.append(
                ToolResult(
                    tool_name=step.tool,
                    result=result,
                    error=result.get("error") if isinstance(result, dict) else None,
                )
            )

            # 5. updates_context contracts
            tool_obj = self.tools.get(step.tool)
            if tool_obj and tool_obj.updates_context and "error" not in result:
                self._apply_updates(tool_obj.updates_context, result, context)

            # 6. Accumulate consumed product_ids (for "remaining" on later steps)
            if step.tool in CONSUMING_TOOLS and isinstance(result, dict):
                for added in result.get("added", []) or []:
                    if isinstance(added, dict) and "product_id" in added:
                        try:
                            consumed_ids.add(int(added["product_id"]))
                        except (TypeError, ValueError):
                            pass

        return step_results, tool_results, issues

    @staticmethod
    def _apply_updates(
        updates: dict[str, str],
        result: dict[str, Any],
        context: SessionContext,
    ) -> None:
        for ctx_key, path in updates.items():
            if not path.startswith("result"):
                log.warning(
                    "updates_context path must start with 'result': %r", path
                )
                continue
            inner = path[len("result"):].lstrip(".")
            try:
                value = result if not inner else _walk_path(result, inner, path)
            except RefError as e:
                log.debug("updates_context skip %s=%s: %s", ctx_key, path, e)
                continue

            if not hasattr(context, ctx_key):
                log.warning("SessionContext has no field %r", ctx_key)
                continue
            try:
                setattr(context, ctx_key, value)
            except Exception as e:
                log.warning(
                    "Failed to set context.%s = %r: %r", ctx_key, value, e
                )


# ---------- strip_to_tool_fields ----------

def _strip_to_tool_fields(
    tools: ToolRegistry,
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Drop args fields not declared in the tool's `parameters` schema.

    Defence-in-depth against legacy refs/skeleton-step args smuggling in
    extras. ArgsFiller already constrains via per-tool schema, so in the
    hybrid path this is usually a no-op.
    """
    tool = tools.get(tool_name)
    if tool is None:
        return args
    allowed = set((tool.parameters.get("properties") or {}).keys())
    if not allowed:
        return {}
    return {k: v for k, v in args.items() if k in allowed}


# ---------- merge_hints ----------

def _merge_hints(
    tool: str,
    args: dict[str, Any],
    hints: ParseHints | None,
    visible: list[int],
    consumed: set[int],
) -> dict[str, Any]:
    """Apply deterministic ParseHints on top of LLM args.

    Regex is more accurate than the LLM on numbers, so prices/quantity from
    hints overwrite. Quantifiers ("все"/"остальные"/"первые N") deterministically
    resolve product_ids using visible + consumed.
    """
    if hints is None:
        return args
    out = dict(args)

    if tool == "apply_filters":
        if hints.max_price is not None:
            out["max_price"] = hints.max_price
        if hints.min_price is not None:
            out["min_price"] = hints.min_price
        # category from hints overrides only if LLM left it blank
        if hints.category and not out.get("category"):
            out["category"] = hints.category
        # search from hints (regex over adjective dict) overrides ALWAYS —
        # 3B model frequently misses this slot or routes it to address/status
        if hints.search:
            out["search"] = hints.search
        return out

    if tool in PRODUCT_ID_TOOLS:
        # Quantifier deterministically resolves product_ids
        resolved = apply_quantifier(hints, list(visible), consumed)
        if resolved is not None:
            out["product_ids"] = resolved
        if tool == "add_to_cart" and hints.quantity is not None:
            out["quantity"] = hints.quantity
        return out

    return out


# ---------- validate_args ----------

def _validate_args(
    tool: str,
    args: dict[str, Any],
    ctx: SessionContext,
    filter_options: dict[str, Any] | None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if tool == "apply_filters":
        cat = args.get("category")
        if cat is not None and filter_options:
            allowed = filter_options.get("categories", [])
            if allowed and cat not in allowed:
                issues.append(ValidationIssue(
                    field="category",
                    message=f"category {cat!r} not in {allowed}",
                    severity="error",
                ))
        for key in ("min_price", "max_price"):
            v = args.get(key)
            if v is not None and v < 0:
                issues.append(ValidationIssue(
                    field=key, message=f"{key}={v} must be >= 0",
                    severity="error",
                ))
        mn, mx = args.get("min_price"), args.get("max_price")
        if mn is not None and mx is not None and mn > mx:
            issues.append(ValidationIssue(
                field="min_price",
                message=f"min_price={mn} > max_price={mx}",
                severity="error",
            ))
        s = args.get("search")
        if s is not None and len(str(s)) > 64:
            issues.append(ValidationIssue(
                field="search",
                message="search too long (>64 chars)",
                severity="warning",
            ))
        return issues

    if tool == "add_to_cart":
        ids = args.get("product_ids")
        if not isinstance(ids, list) or not ids:
            issues.append(ValidationIssue(
                field="product_ids",
                message="product_ids is empty (нет товаров для добавления)",
                severity="error",
            ))
        else:
            visible = set(ctx.visible_product_ids or [])
            if not visible:
                issues.append(ValidationIssue(
                    field="product_ids",
                    message="нельзя добавлять в корзину: каталог пуст (нет visible_product_ids — сначала покажите товары)",
                    severity="error",
                ))
            else:
                for pid in ids:
                    if not isinstance(pid, int):
                        issues.append(ValidationIssue(
                            field="product_ids",
                            message=f"product_id {pid!r} is not an integer",
                            severity="error",
                        ))
                    elif pid not in visible:
                        issues.append(ValidationIssue(
                            field="product_ids",
                            message=f"product_id {pid} not in visible products",
                            severity="error",
                        ))
                if len(set(ids)) != len(ids):
                    issues.append(ValidationIssue(
                        field="product_ids",
                        message="product_ids contains duplicates",
                        severity="warning",
                    ))
        qty = args.get("quantity", 1)
        if not isinstance(qty, int) or not (1 <= qty <= 99):
            issues.append(ValidationIssue(
                field="quantity",
                message=f"quantity={qty!r} out of range [1,99]",
                severity="error",
            ))
        return issues

    if tool == "add_to_favorites":
        ids = args.get("product_ids")
        if not isinstance(ids, list) or not ids:
            issues.append(ValidationIssue(
                field="product_ids",
                message="product_ids is empty (нет товаров для избранного)",
                severity="error",
            ))
        else:
            visible = set(ctx.visible_product_ids or [])
            if not visible:
                issues.append(ValidationIssue(
                    field="product_ids",
                    message="нельзя добавлять в избранное: каталог пуст (нет visible_product_ids — сначала покажите товары)",
                    severity="error",
                ))
            else:
                for pid in ids:
                    if not isinstance(pid, int):
                        issues.append(ValidationIssue(
                            field="product_ids",
                            message=f"product_id {pid!r} is not an integer",
                            severity="error",
                        ))
                    elif pid not in visible:
                        issues.append(ValidationIssue(
                            field="product_ids",
                            message=f"product_id {pid} not in visible products",
                            severity="error",
                        ))
        return issues

    if tool == "remove_from_favorites":
        ids = args.get("product_ids")
        if not isinstance(ids, list) or not ids:
            issues.append(ValidationIssue(
                field="product_ids",
                message="product_ids is empty",
                severity="error",
            ))
        return issues

    if tool == "get_product_details":
        pid = args.get("product_id")
        allowed = set(ctx.visible_product_ids or [])
        if ctx.open_product_id is not None:
            allowed.add(ctx.open_product_id)
        if pid is None:
            issues.append(ValidationIssue(
                field="product_id",
                message="product_id is required",
                severity="error",
            ))
        elif allowed and pid not in allowed:
            issues.append(ValidationIssue(
                field="product_id",
                message=f"product_id {pid} not in visible products",
                severity="error",
            ))
        return issues

    if tool == "create_order":
        import re as _re
        phone = args.get("phone", "")
        addr = args.get("address", "")
        if not _re.match(r"\+?[\d\s\-()]{7,}$", str(phone)):
            issues.append(ValidationIssue(
                field="phone",
                message=f"phone {phone!r} invalid (7+ digits, optional +/-/space/parens)",
                severity="error",
            ))
        if len(str(addr)) < 5:
            issues.append(ValidationIssue(
                field="address",
                message="address too short (< 5 chars)",
                severity="error",
            ))
        return issues

    return issues
