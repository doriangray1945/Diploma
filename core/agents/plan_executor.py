"""PlanExecutor — runs a list of PlanStepV2 with reference resolution.

Resolves $step_X.field and $context.field refs in args, executes tools
sequentially, applies updates_context contracts, cascades skips on
failed dependencies.
"""
from __future__ import annotations

import logging
from typing import Any

from core.agents.refs import (
    RefError,
    _walk_path,
    compute_depends_on,
    resolve_value,
)
from core.schemas import PlanStepV2, SessionContext, ToolResult
from core.tools.base import ToolRegistry


log = logging.getLogger(__name__)


class PlanExecutor:
    def __init__(self, tools: ToolRegistry):
        self.tools = tools

    async def execute(
        self,
        plan: list[PlanStepV2],
        context: SessionContext,
        user_id: int,
    ) -> tuple[dict[str, dict[str, Any]], list[ToolResult]]:
        """Execute steps, return (step_results_by_id, tool_results_in_order)."""
        step_results: dict[str, dict[str, Any]] = {}
        tool_results: list[ToolResult] = []
        skipped: set[str] = set()

        # ctx_dict snapshot is recomputed after each successful step that touches context
        ctx_dict: dict[str, Any] = context.to_prompt_dict()

        for step in plan:
            deps = compute_depends_on(step.args)

            # Cascade skip if any dependency was skipped earlier
            failed_deps = [d for d in deps if d in skipped]
            if failed_deps:
                err = f"skipped: dependencies failed: {failed_deps}"
                skipped.add(step.step_id)
                step_results[step.step_id] = {"error": err}
                tool_results.append(
                    ToolResult(tool_name=step.tool, result={"error": err}, error=err)
                )
                continue

            # Resolve $-refs
            try:
                resolved_args = resolve_value(step.args, step_results, ctx_dict)
            except RefError as e:
                err = f"ref_error: {e}"
                log.warning("Step %s ref error: %s", step.step_id, e)
                skipped.add(step.step_id)
                step_results[step.step_id] = {"error": err}
                tool_results.append(
                    ToolResult(tool_name=step.tool, result={"error": err}, error=err)
                )
                continue

            # Execute the tool
            if not isinstance(resolved_args, dict):
                err = f"resolved args is not dict: {type(resolved_args).__name__}"
                skipped.add(step.step_id)
                step_results[step.step_id] = {"error": err}
                tool_results.append(
                    ToolResult(tool_name=step.tool, result={"error": err}, error=err)
                )
                continue

            # Normalize product_ids: "context" or non-list → visible_product_ids
            pid = resolved_args.get("product_ids")
            if pid is not None and not isinstance(pid, list):
                resolved_args["product_ids"] = context.visible_product_ids
            # Also strip null values so tools don't get None args
            resolved_args = {k: v for k, v in resolved_args.items() if v is not None}

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

            # Apply updates_context declarations from the tool
            tool_obj = self.tools.get(step.tool)
            if tool_obj and tool_obj.updates_context and "error" not in result:
                self._apply_updates(tool_obj.updates_context, result, context)
                ctx_dict = context.to_prompt_dict()  # refresh snapshot

        return step_results, tool_results

    @staticmethod
    def _apply_updates(
        updates: dict[str, str],
        result: dict[str, Any],
        context: SessionContext,
    ) -> None:
        """Apply tool.updates_context = {field: 'result.path'} to the SessionContext."""
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
