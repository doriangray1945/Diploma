"""Path walker for tool-result projection (updates_context contracts).

PlanExecutor uses `_walk_path` to extract values from tool results along a
dotted path with optional `[idx]` / `[*]` segments. Failures raise RefError
and the caller skips the projection.
"""
from __future__ import annotations

import re
from typing import Any


# segments inside the path part: either "name", "[idx]", or "[*]"
SEGMENT_RE = re.compile(r"([A-Za-z_][\w]*)|\[(\d+|\*)\]")


class RefError(Exception):
    """Reference could not be resolved."""


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
