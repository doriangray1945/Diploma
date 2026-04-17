"""Reference resolution for Structured Output plans.

Supported syntax inside step.args:
    "$step_1.products[0].id"        -> indexed access
    "$step_1.products[*].id"        -> extract list of ids from array of objects
    "$context.last_search.product_ids"  -> session context lookup
    "$context.visible_product_ids"      -> session context lookup

Refs that fail to resolve raise RefError; PlanExecutor turns this into a skipped step.
"""
from __future__ import annotations

import json
import re
from typing import Any


REF_RE = re.compile(r"^\$(step_\d+|context)\.(.+)$")
# segments inside the path part: either "name", "[idx]", or "[*]"
SEGMENT_RE = re.compile(r"([A-Za-z_][\w]*)|\[(\d+|\*)\]")


class RefError(Exception):
    """Reference could not be resolved."""


def compute_depends_on(args: dict[str, Any]) -> list[str]:
    """Find every $step_X.* reference inside args and return distinct step_ids."""
    blob = json.dumps(args, ensure_ascii=False)
    return sorted(set(re.findall(r"\$(step_\d+)\.", blob)))


def resolve_value(value: Any, step_results: dict[str, Any], context: dict[str, Any]) -> Any:
    """Recursively resolve $-refs in arbitrary value (str / dict / list / scalar)."""
    if isinstance(value, str) and value.startswith("$"):
        return _resolve_ref(value, step_results, context)
    if isinstance(value, dict):
        return {k: resolve_value(v, step_results, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_value(v, step_results, context) for v in value]
    return value


def _resolve_ref(ref: str, step_results: dict[str, Any], context: dict[str, Any]) -> Any:
    m = REF_RE.match(ref)
    if not m:
        raise RefError(f"Invalid ref syntax: {ref!r}")
    source, path = m.group(1), m.group(2)

    if source == "context":
        root: Any = context
    else:
        if source not in step_results:
            raise RefError(f"Step {source!r} has no result yet (referenced by {ref!r})")
        root = step_results[source]

    return _walk_path(root, path, ref)


def _walk_path(obj: Any, path: str, ref_for_error: str) -> Any:
    """Walk a dotted path with optional [idx] / [*] segments."""
    segments: list[tuple[str, str]] = SEGMENT_RE.findall(path)
    if not segments:
        raise RefError(f"Empty path in ref {ref_for_error!r}")

    cur: Any = obj
    i = 0
    while i < len(segments):
        name, idx = segments[i]
        if name:
            if not isinstance(cur, dict):
                raise RefError(f"Cannot read .{name} on non-dict in {ref_for_error!r}")
            if name not in cur:
                raise RefError(f"Key {name!r} not found in {ref_for_error!r}")
            cur = cur[name]
        elif idx == "*":
            # Map remaining path over the current list
            if not isinstance(cur, list):
                raise RefError(f"[*] requires list, got {type(cur).__name__} in {ref_for_error!r}")
            remaining = segments[i + 1:]
            if not remaining:
                return cur
            return [_walk_segments(item, remaining, ref_for_error) for item in cur]
        else:
            if not isinstance(cur, list):
                raise RefError(f"[{idx}] requires list in {ref_for_error!r}")
            try:
                cur = cur[int(idx)]
            except IndexError as e:
                raise RefError(f"Index {idx} out of range in {ref_for_error!r}") from e
        i += 1
    return cur


def _walk_segments(obj: Any, segments: list[tuple[str, str]], ref_for_error: str) -> Any:
    cur = obj
    for name, idx in segments:
        if name:
            if not isinstance(cur, dict):
                raise RefError(f"Cannot read .{name} on non-dict in {ref_for_error!r}")
            if name not in cur:
                raise RefError(f"Key {name!r} not found in {ref_for_error!r}")
            cur = cur[name]
        elif idx == "*":
            raise RefError(f"Nested [*] not supported in {ref_for_error!r}")
        else:
            if not isinstance(cur, list):
                raise RefError(f"[{idx}] requires list in {ref_for_error!r}")
            cur = cur[int(idx)]
    return cur
