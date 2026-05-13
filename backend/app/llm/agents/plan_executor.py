"""PlanExecutor — runs a list of PlanStepV2.

The fine-tuned model emits args inline; PlanExecutor honors `step.args`
as-is (via `_NoOpArgsFiller.fill() → {}`) and merges ParseHints over the
top for numeric corrections and quantifier resolution. consumed_ids
accumulates across steps for «оставшиеся» semantics.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from app.llm.agents.refs import RefError, _walk_path
from app.llm.parsing import ParseHints, apply_quantifier, parse_user_text
from app.llm.schemas import PlanStepV2, SessionContext, ToolResult, ValidationIssue
from app.llm.tools.base import ToolRegistry


log = logging.getLogger(__name__)


# Tools whose successful execution "consumes" product_ids (subsequent
# «оставшиеся» / «remaining» quantifier excludes already-consumed ids).
# add_to_favorites НЕ consumes — корзина и избранное независимы, типовой
# запрос «и в корзину и в избранное» требует чтобы те же товары попали
# в оба места.
CONSUMING_TOOLS = {"add_to_cart"}

# Tools whose args are subject to hint merging.
PRODUCT_ID_TOOLS = {"add_to_cart", "add_to_favorites", "remove_from_favorites"}


class _ArgsFillerLike(Protocol):
    """Minimal protocol — Pipeline passes _NoOpArgsFiller (returns {})."""
    async def fill(self, *args, **kwargs) -> dict: ...


class PlanExecutor:
    def __init__(self, tools: ToolRegistry, args_filler: _ArgsFillerLike):
        self.tools = tools
        self.args_filler = args_filler

    async def execute(
        self,
        plan: list[PlanStepV2],
        context: SessionContext,
        user_id: int,
        hints: ParseHints | None = None,
        filter_options: dict[str, Any] | None = None,
        step_texts: list[str] | None = None,
        fallback_text: str = "",
    ) -> tuple[
        dict[str, dict[str, Any]],
        list[ToolResult],
        list[ValidationIssue],
    ]:
        """Execute steps; return (step_results_by_id, tool_results, validation_issues).

        `step_texts` carries the per-step decomposition produced by the
        Decomposer (one entry per plan step, ideally). When the decomposer
        was skipped or returned fewer items than the plan length, missing
        entries fall back to `fallback_text` (the original user message).
        Each step's args-filler then sees ONLY its own sub-action — the
        single biggest cause of LLM dump-into-search is that the model
        used to receive the full multi-action query for every step.
        """
        step_results: dict[str, dict[str, Any]] = {}
        tool_results: list[ToolResult] = []
        issues: list[ValidationIssue] = []
        consumed_ids: set[int] = set()
        categories = (filter_options or {}).get("categories", []) if filter_options else []
        # When a step does apply_filters {color/material/price_level}, the
        # user's visual selection is «green items» / «wooden items». The
        # next add_to_cart/add_to_favorites without an explicit filter must
        # inherit it — otherwise default_variant gets added (wrong colour).
        last_visual_filter: dict[str, Any] = {}

        for step_idx, step in enumerate(plan):
            # Per-step text + per-step parser hints. When step_texts is
            # absent or shorter than the plan, fall back to the whole
            # message so behaviour stays graceful.
            step_text = (
                step_texts[step_idx]
                if step_texts and step_idx < len(step_texts)
                else fallback_text
            )
            if step_texts and step_idx < len(step_texts):
                step_hints = parse_user_text(step_text, categories)
                # Cross-step quantifier/quantity stay global. The
                # decomposer routinely splits «все диваны → корзина по
                # 9» into «найди диваны / положи в корзину по 9» —
                # «все» appears only in step 1 but action-tools in
                # later steps still need it to resolve product_ids.
                # Inherit from `hints` only when the sub-text didn't
                # express its own value.
                if hints is not None:
                    if not step_hints.quantifier:
                        step_hints.quantifier = hints.quantifier
                        step_hints.quantifier_n = hints.quantifier_n
                    if step_hints.quantity is None:
                        step_hints.quantity = hints.quantity
            else:
                step_hints = hints

            # 1. Fill args via ArgsFiller (deterministic-from-hints OR per-tool LLM).
            #    Skeleton plans arrive with empty args; legacy callers may pass
            #    non-empty args — in which case we honor them as a starting point.
            try:
                filled = await self.args_filler.fill(
                    tool_name=step.tool,
                    hints=step_hints,
                    context=context,
                    consumed_ids=consumed_ids,
                    last_user_text=step_text,
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
                step.tool, resolved_args, step_hints,
                visible=context.visible_product_ids,
                consumed=consumed_ids,
            )

            # 2.5 Inherit visual filter (color/material/price_level) from a
            # preceding apply_filters into add_to_cart / add_to_favorites —
            # but ONLY when the tool arrived with a fully empty filter.
            # Reason: «покажи зелёные шкафы и добавь в корзину» — model often
            # leaves add_to_cart.args empty and we'd pick default_variant
            # (often non-green). If the model put ANY key in filter, it
            # expressed intent (e.g. «деревянные» in a green-filtered list) —
            # we respect that and don't merge.
            if step.tool in {"add_to_cart", "add_to_favorites"} and last_visual_filter:
                existing = resolved_args.get("filter")
                if not isinstance(existing, dict) or not existing:
                    resolved_args["filter"] = dict(last_visual_filter)

            # 3. Strip args to fields the tool actually accepts. ArgsFiller
            #    already constrains via per-tool schema, but legacy tools/refs
            #    may smuggle in extras — defence in depth.
            resolved_args = _strip_to_tool_fields(self.tools, step.tool, resolved_args)

            # Capture filter attrs from apply_filters for next steps to inherit.
            if step.tool == "apply_filters":
                captured = {
                    k: resolved_args[k]
                    for k in ("color", "material", "price_level")
                    if resolved_args.get(k)
                }
                if captured:
                    last_visual_filter = captured

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


# ---------- quantifier resolver for LLM-emitted args ----------

def _resolve_llm_quantifier(
    q: str,
    n: int | None,
    visible: list[int],
    consumed: set[int],
) -> list[int] | None:
    """Mirror of `core.parsing.apply_quantifier` but takes raw values from
    LLM args (lowercase enum: all/first_n/last_n/remaining/specific).

    Returns the resolved product_id list, or None if quantifier is
    `specific` (caller already has product_ids) or unrecognized.
    """
    if not q or not visible:
        return None
    if q == "all":
        return list(visible)
    if q == "remaining":
        return [pid for pid in visible if pid not in consumed]
    if q == "specific":
        return None
    available = [pid for pid in visible if pid not in consumed]
    n_val = n or 1
    if q == "first_n":
        return available[:n_val]
    if q == "last_n":
        return available[-n_val:] if available else []
    return None


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
        # `search` is now a free-form descriptor filled by the LLM and matched
        # semantically by pgvector — no parser-side override.
        return out

    if tool in PRODUCT_ID_TOOLS:
        # Quantifier resolution priority:
        #   1. LLM-emitted quantifier (explicit intent in args)
        #   2. Parser-extracted quantifier (regex from user text)
        # The fine-tuned model sets these directly; the parser is the
        # fallback for non-fine-tuned/baseline runs.
        llm_q = out.get("quantifier")
        if llm_q:
            resolved = _resolve_llm_quantifier(
                llm_q, out.get("n"), list(visible), consumed,
            )
            if resolved is not None:
                out["product_ids"] = resolved
            # Strip helper fields — tool execute() works on product_ids only.
            out.pop("quantifier", None)
            out.pop("n", None)
        else:
            resolved = apply_quantifier(hints, list(visible), consumed)
            if resolved is not None:
                out["product_ids"] = resolved
        # Ambiguity fallback: «положи в корзину» without quantifier after a
        # filter → default to all visible. Covers the cache-hit path where
        # the stored skeleton arrives with args={} and the parser finds no
        # «все/первые N» in the bare phrase. Explicit user intent (LLM or
        # parser quantifier above) wins by virtue of running first.
        if "product_ids" not in out and visible:
            out["product_ids"] = list(visible)
        if tool == "add_to_cart" and "quantity" not in out and hints.quantity is not None:
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
