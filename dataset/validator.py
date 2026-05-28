"""Validate generated training examples against tool_schemas.

Each example: {"role": "user"|"admin"?, "user": str,
               "plan": [{"tool": str, "args": dict}, ...]}.

Validation runs on CANONICAL plans (variant A names) before any schema
augmentation — the augmented JSONL output is implicitly valid if the
canonical input was valid and the rendering is identity-preserving on
structure.

Returns (is_valid, errors). Examples with errors are dropped.

CLI:
    python validator.py seeds.json
    python validator.py --jsonl train.jsonl
    python validator.py --jsonl train.jsonl --report
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from tool_schemas import (
    ADMIN_TOOL_NAMES, ALL_TOOL_NAMES, CATEGORIES, COLORS, GROUP_BY_FIELDS,
    MATERIALS, METRICS, OPERATIONS_PRICE, OPERATIONS_STOCK, PERIODS,
    PRICE_LEVELS, QUANTIFIERS, ROOMS, SORT_DIRS, SUBCATEGORIES,
    SUBCATEGORIES_FLAT, USER_TOOL_NAMES, _ADMIN_FILTER_KEYS,
)

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_example(ex: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []

    if not isinstance(ex, dict):
        return False, ["root is not a dict"]
    if not isinstance(ex.get("user"), str) or not ex["user"].strip():
        errors.append("user must be non-empty string")
    if not isinstance(ex.get("plan"), list):
        return False, errors + ["plan must be a list"]

    role = ex.get("role", "user")
    if role not in {"user", "admin"}:
        errors.append(f"role must be 'user' or 'admin', got {role!r}")
        role = "user"  # keep going for better diagnostics

    allowed_tools = ALL_TOOL_NAMES if role == "admin" else USER_TOOL_NAMES

    for i, step in enumerate(ex["plan"]):
        if not isinstance(step, dict):
            errors.append(f"plan[{i}] not a dict")
            continue
        tool = step.get("tool")
        args = step.get("args", {})
        if tool not in ALL_TOOL_NAMES:
            errors.append(f"plan[{i}] tool '{tool}' not in ALL_TOOL_NAMES")
            continue
        if tool not in allowed_tools:
            errors.append(f"plan[{i}] tool '{tool}' not allowed for role={role!r}")
            continue
        if not isinstance(args, dict):
            errors.append(f"plan[{i}] args not a dict")
            continue
        errors.extend(_validate_args(tool, args, idx=i))

    return (len(errors) == 0), errors


def _validate_args(tool: str, args: dict[str, Any], idx: int) -> list[str]:
    errors: list[str] = []

    if tool == "apply_filters":
        errors.extend(_validate_apply_filters(args, idx))
    elif tool in {"add_to_favorites", "add_to_cart"}:
        errors.extend(_validate_add_quantifier(tool, args, idx))
    elif tool in {"remove_from_favorites", "remove_from_cart"}:
        errors.extend(_validate_remove_filter(args, idx))
    elif tool in {"clear_favorites", "clear_cart"}:
        if args:
            errors.append(f"plan[{idx}] {tool} expects no args, got {list(args.keys())}")
    elif tool == "update_stock":
        errors.extend(_validate_update_stock(args, idx))
    elif tool == "update_prices":
        errors.extend(_validate_update_prices(args, idx))
    elif tool == "get_sales_analytics":
        errors.extend(_validate_get_sales_analytics(args, idx))

    return errors


def _validate_apply_filters(args: dict[str, Any], idx: int) -> list[str]:
    errors: list[str] = []
    allowed = {"category", "subcategory", "room", "material", "color",
               "price_level", "min_price", "max_price", "search", "in_stock"}
    for key in args:
        if key not in allowed:
            errors.append(f"plan[{idx}].args.{key} not in apply_filters schema")

    if "category" in args and args["category"] not in CATEGORIES:
        errors.append(f"plan[{idx}].category invalid: {args['category']!r}")
    if "subcategory" in args:
        sv = args["subcategory"]
        if sv not in SUBCATEGORIES_FLAT:
            errors.append(f"plan[{idx}].subcategory invalid: {sv!r}")
        # If category specified, subcategory must belong to it.
        cat = args.get("category")
        if cat in SUBCATEGORIES and sv not in SUBCATEGORIES[cat]:
            errors.append(
                f"plan[{idx}].subcategory {sv!r} does not belong to category {cat!r} "
                f"(allowed: {SUBCATEGORIES[cat]})"
            )
    if "room" in args and args["room"] not in ROOMS:
        errors.append(f"plan[{idx}].room invalid: {args['room']!r}")
    if "material" in args:
        v = args["material"]
        if not isinstance(v, list) or not v:
            errors.append(f"plan[{idx}].material must be non-empty array")
        else:
            for m in v:
                if m not in MATERIALS:
                    errors.append(f"plan[{idx}].material item invalid: {m!r}")
    if "color" in args:
        v = args["color"]
        if not isinstance(v, list) or not v:
            errors.append(f"plan[{idx}].color must be non-empty array")
        else:
            for c in v:
                if c not in COLORS:
                    errors.append(f"plan[{idx}].color item invalid: {c!r}")
    if "price_level" in args and args["price_level"] not in PRICE_LEVELS:
        errors.append(f"plan[{idx}].price_level invalid: {args['price_level']!r}")
    for k in ("min_price", "max_price"):
        if k in args and not isinstance(args[k], (int, float)):
            errors.append(f"plan[{idx}].{k} not numeric")
        elif k in args and args[k] < 0:
            errors.append(f"plan[{idx}].{k} negative")
    if "price_level" in args and ("min_price" in args or "max_price" in args):
        errors.append(f"plan[{idx}] price_level mixed with min/max_price")
    if "in_stock" in args and not isinstance(args["in_stock"], bool):
        errors.append(f"plan[{idx}].in_stock must be boolean")
    if "search" in args and not isinstance(args["search"], str):
        errors.append(f"plan[{idx}].search must be string")
    return errors


def _validate_add_quantifier(tool: str, args: dict[str, Any], idx: int) -> list[str]:
    errors: list[str] = []
    allowed = {"quantifier", "n", "product_ids"}
    if tool == "add_to_cart":
        allowed = allowed | {"quantity"}
    for key in args:
        if key not in allowed:
            errors.append(f"plan[{idx}].args.{key} not in {tool} schema")

    q = args.get("quantifier")
    if q is not None and q not in QUANTIFIERS:
        errors.append(f"plan[{idx}].quantifier invalid: {q!r}")
    if q in {"first_n", "last_n"} and "n" not in args:
        errors.append(f"plan[{idx}].quantifier={q} requires n")
    if q == "specific" and "product_ids" not in args:
        errors.append(f"plan[{idx}].quantifier=specific requires product_ids")
    if "n" in args and (not isinstance(args["n"], int) or args["n"] < 1):
        errors.append(f"plan[{idx}].n invalid: {args['n']!r}")
    if "product_ids" in args:
        v = args["product_ids"]
        if not isinstance(v, list) or not v:
            errors.append(f"plan[{idx}].product_ids must be non-empty array")
        else:
            for pid in v:
                if not isinstance(pid, int) or pid < 1:
                    errors.append(f"plan[{idx}].product_ids item invalid: {pid!r}")
    if tool == "add_to_cart" and "quantity" in args:
        v = args["quantity"]
        if not isinstance(v, int) or v < 1 or v > 99:
            errors.append(f"plan[{idx}].quantity out of [1,99]: {v!r}")
    return errors


def _validate_remove_filter(args: dict[str, Any], idx: int) -> list[str]:
    errors: list[str] = []
    if list(args.keys()) != ["filter"]:
        bad = [k for k in args if k != "filter"]
        if bad:
            errors.append(f"plan[{idx}] only 'filter' allowed, got extra: {bad}")
    flt = args.get("filter")
    if not isinstance(flt, dict) or not flt:
        errors.append(f"plan[{idx}].filter must be non-empty dict")
        return errors

    allowed = {"category", "color", "material", "product_name", "all"}
    for k in flt:
        if k not in allowed:
            errors.append(f"plan[{idx}].filter.{k} unknown key")
    if "category" in flt and flt["category"] not in CATEGORIES:
        errors.append(f"plan[{idx}].filter.category invalid: {flt['category']!r}")
    if "color" in flt:
        v = flt["color"]
        if not isinstance(v, list) or not v:
            errors.append(f"plan[{idx}].filter.color must be non-empty array")
        else:
            for c in v:
                if c not in COLORS:
                    errors.append(f"plan[{idx}].filter.color item invalid: {c!r}")
    if "material" in flt:
        v = flt["material"]
        if not isinstance(v, list) or not v:
            errors.append(f"plan[{idx}].filter.material must be non-empty array")
        else:
            for m in v:
                if m not in MATERIALS:
                    errors.append(f"plan[{idx}].filter.material item invalid: {m!r}")
    if "all" in flt and not isinstance(flt["all"], bool):
        errors.append(f"plan[{idx}].filter.all must be boolean")
    if flt.get("all") is True and any(k != "all" for k in flt):
        errors.append(f"plan[{idx}].filter has all:true mixed with other criteria")
    return errors


def _validate_admin_filter(flt: Any, idx: int, key_path: str = "filter") -> list[str]:
    """Filter schema for admin tools — same as apply_filters PLUS
    product_name/product_ids. Must be non-empty (otherwise updates would
    target the entire catalog, which is dangerous and almost never intended)."""
    errors: list[str] = []
    if not isinstance(flt, dict) or not flt:
        errors.append(f"plan[{idx}].{key_path} must be non-empty dict")
        return errors
    for k in flt:
        if k not in _ADMIN_FILTER_KEYS:
            errors.append(f"plan[{idx}].{key_path}.{k} unknown key")
    if "category" in flt and flt["category"] not in CATEGORIES:
        errors.append(f"plan[{idx}].{key_path}.category invalid: {flt['category']!r}")
    if "subcategory" in flt:
        sv = flt["subcategory"]
        if sv not in SUBCATEGORIES_FLAT:
            errors.append(f"plan[{idx}].{key_path}.subcategory invalid: {sv!r}")
        cat = flt.get("category")
        if cat in SUBCATEGORIES and sv not in SUBCATEGORIES[cat]:
            errors.append(
                f"plan[{idx}].{key_path}.subcategory {sv!r} does not belong to "
                f"category {cat!r}"
            )
    if "room" in flt and flt["room"] not in ROOMS:
        errors.append(f"plan[{idx}].{key_path}.room invalid: {flt['room']!r}")
    if "material" in flt:
        v = flt["material"]
        if not isinstance(v, list) or not v:
            errors.append(f"plan[{idx}].{key_path}.material must be non-empty array")
        else:
            for m in v:
                if m not in MATERIALS:
                    errors.append(f"plan[{idx}].{key_path}.material item invalid: {m!r}")
    if "color" in flt:
        v = flt["color"]
        if not isinstance(v, list) or not v:
            errors.append(f"plan[{idx}].{key_path}.color must be non-empty array")
        else:
            for c in v:
                if c not in COLORS:
                    errors.append(f"plan[{idx}].{key_path}.color item invalid: {c!r}")
    if "price_level" in flt and flt["price_level"] not in PRICE_LEVELS:
        errors.append(f"plan[{idx}].{key_path}.price_level invalid: {flt['price_level']!r}")
    for k in ("min_price", "max_price"):
        if k in flt and not isinstance(flt[k], (int, float)):
            errors.append(f"plan[{idx}].{key_path}.{k} not numeric")
        elif k in flt and flt[k] < 0:
            errors.append(f"plan[{idx}].{key_path}.{k} negative")
    if "price_level" in flt and ("min_price" in flt or "max_price" in flt):
        errors.append(f"plan[{idx}].{key_path} price_level mixed with min/max_price")
    if "in_stock" in flt and not isinstance(flt["in_stock"], bool):
        errors.append(f"plan[{idx}].{key_path}.in_stock must be boolean")
    if "search" in flt and not isinstance(flt["search"], str):
        errors.append(f"plan[{idx}].{key_path}.search must be string")
    if "product_name" in flt and not isinstance(flt["product_name"], str):
        errors.append(f"plan[{idx}].{key_path}.product_name must be string")
    if "product_ids" in flt:
        v = flt["product_ids"]
        if not isinstance(v, list) or not v:
            errors.append(f"plan[{idx}].{key_path}.product_ids must be non-empty array")
        else:
            for pid in v:
                if not isinstance(pid, int) or pid < 1:
                    errors.append(f"plan[{idx}].{key_path}.product_ids item invalid: {pid!r}")
    return errors


def _validate_update_stock(args: dict[str, Any], idx: int) -> list[str]:
    errors: list[str] = []
    allowed = {"filter", "operation", "quantity"}
    for k in args:
        if k not in allowed:
            errors.append(f"plan[{idx}].args.{k} not in update_stock schema")
    for req in ("filter", "operation", "quantity"):
        if req not in args:
            errors.append(f"plan[{idx}].update_stock missing required: {req}")

    if "filter" in args:
        errors.extend(_validate_admin_filter(args["filter"], idx))
    if "operation" in args and args["operation"] not in OPERATIONS_STOCK:
        errors.append(f"plan[{idx}].operation invalid: {args['operation']!r} (expected one of {OPERATIONS_STOCK})")
    if "quantity" in args:
        v = args["quantity"]
        if not isinstance(v, int) or v < 0 or v > 100_000:
            errors.append(f"plan[{idx}].quantity out of [0, 100000]: {v!r}")
    return errors


def _validate_update_prices(args: dict[str, Any], idx: int) -> list[str]:
    errors: list[str] = []
    allowed = {"filter", "operation", "value"}
    for k in args:
        if k not in allowed:
            errors.append(f"plan[{idx}].args.{k} not in update_prices schema")
    for req in ("filter", "operation", "value"):
        if req not in args:
            errors.append(f"plan[{idx}].update_prices missing required: {req}")

    if "filter" in args:
        errors.extend(_validate_admin_filter(args["filter"], idx))
    if "operation" in args and args["operation"] not in OPERATIONS_PRICE:
        errors.append(f"plan[{idx}].operation invalid: {args['operation']!r} (expected one of {OPERATIONS_PRICE})")
    if "value" in args:
        v = args["value"]
        if not isinstance(v, int) or v < 1:
            errors.append(f"plan[{idx}].value must be positive int, got {v!r}")
        elif args.get("operation") in {"discount", "markup"} and v > 100:
            errors.append(f"plan[{idx}].value percent must be ≤ 100, got {v!r}")
        elif args.get("operation") == "set_price" and v > 10_000_000:
            errors.append(f"plan[{idx}].value price > 10M RUB, suspicious: {v!r}")
    return errors


def _validate_get_sales_analytics(args: dict[str, Any], idx: int) -> list[str]:
    errors: list[str] = []
    allowed = {"period", "from_date", "to_date", "group_by", "metric",
               "sort", "limit", "filter"}
    for k in args:
        if k not in allowed:
            errors.append(f"plan[{idx}].args.{k} not in get_sales_analytics schema")
    for req in ("period", "group_by", "metric"):
        if req not in args:
            errors.append(f"plan[{idx}].get_sales_analytics missing required: {req}")

    if "period" in args and args["period"] not in PERIODS:
        errors.append(f"plan[{idx}].period invalid: {args['period']!r}")
    if args.get("period") == "custom":
        for d in ("from_date", "to_date"):
            if d not in args:
                errors.append(f"plan[{idx}].period=custom requires {d}")
    else:
        for d in ("from_date", "to_date"):
            if d in args:
                errors.append(f"plan[{idx}].period={args.get('period')!r} forbids {d}")
    for d in ("from_date", "to_date"):
        if d in args:
            v = args[d]
            if not isinstance(v, str) or not ISO_DATE_RE.match(v):
                errors.append(f"plan[{idx}].{d} must be YYYY-MM-DD: {v!r}")

    if "group_by" in args and args["group_by"] not in GROUP_BY_FIELDS:
        errors.append(f"plan[{idx}].group_by invalid: {args['group_by']!r}")
    if "metric" in args and args["metric"] not in METRICS:
        errors.append(f"plan[{idx}].metric invalid: {args['metric']!r}")
    if "sort" in args and args["sort"] not in SORT_DIRS:
        errors.append(f"plan[{idx}].sort invalid: {args['sort']!r}")
    if "limit" in args:
        v = args["limit"]
        if not isinstance(v, int) or v < 1 or v > 1000:
            errors.append(f"plan[{idx}].limit out of [1, 1000]: {v!r}")
    if "filter" in args:
        errors.extend(_validate_admin_filter(args["filter"], idx))
    return errors


# ---------------------------------------------------------------------------
# CLI: validate seeds.json (canonical) or generated train.jsonl (chat-format)
# ---------------------------------------------------------------------------

def _validate_canonical_file(path: Path) -> int:
    with path.open() as f:
        data = json.load(f)
    examples = data.get("examples", data) if isinstance(data, dict) else data
    n_ok = 0
    by_role: Counter = Counter()
    by_tool: Counter = Counter()
    for ex in examples:
        ok, errs = validate_example(ex)
        by_role[ex.get("role", "user")] += 1
        for step in ex.get("plan", []):
            by_tool[step.get("tool", "?")] += 1
        if ok:
            n_ok += 1
        else:
            print(f"FAIL: {ex.get('user', '')!r}")
            for e in errs:
                print(f"  - {e}")
    print(f"\n{n_ok}/{len(examples)} valid")
    print(f"By role: {dict(by_role)}")
    print(f"By tool: {dict(by_tool)}")
    return 0 if n_ok == len(examples) else 1


def _validate_jsonl_file(path: Path, report: bool) -> int:
    """Lightweight check on generated chat-format JSONL.

    Schema-augmented JSONL has variant tool/field names; full canonical
    re-validation requires SchemaVariant knowledge (lives in generator.py).
    Here we just check structural validity:
      - each line is JSON
      - has messages list of length 3 (system, user, assistant)
      - assistant content parses to {"plan": [{"tool": str, "args": dict}, ...]}
    """
    n_total = 0
    n_ok = 0
    fails: list[tuple[int, str]] = []
    tool_freq: Counter = Counter()
    plan_lens: Counter = Counter()
    role_in_system: Counter = Counter()  # heuristic: detect admin vs user prompt
    sys_lens: list[int] = []
    user_lens: list[int] = []
    asst_lens: list[int] = []

    with path.open() as f:
        for i, line in enumerate(f, 1):
            n_total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                fails.append((i, f"bad JSON: {e}"))
                continue
            msgs = row.get("messages")
            if not isinstance(msgs, list) or len(msgs) != 3:
                fails.append((i, f"messages must have 3 entries, got {len(msgs) if isinstance(msgs, list) else type(msgs).__name__}"))
                continue
            roles = [m.get("role") for m in msgs]
            if roles != ["system", "user", "assistant"]:
                fails.append((i, f"message roles must be system/user/assistant, got {roles}"))
                continue
            sys_c = msgs[0].get("content", "") or ""
            user_c = msgs[1].get("content", "") or ""
            asst_c = msgs[2].get("content", "") or ""
            sys_lens.append(len(sys_c))
            user_lens.append(len(user_c))
            asst_lens.append(len(asst_c))
            # Heuristic role detection
            sys_lower = sys_c.lower()
            if any(t in sys_lower for t in ("update_stock", "update_prices",
                                              "get_sales_analytics", "modify_inventory",
                                              "modify_pricing", "fetch_sales_report",
                                              "stk_upd", "prc_upd", "admin.")):
                role_in_system["admin"] += 1
            else:
                role_in_system["user"] += 1
            try:
                parsed = json.loads(asst_c)
            except json.JSONDecodeError as e:
                fails.append((i, f"assistant content not JSON: {e}"))
                continue
            plan = parsed.get("plan")
            if not isinstance(plan, list):
                fails.append((i, "assistant.plan missing or not list"))
                continue
            plan_lens[len(plan)] += 1
            row_ok = True
            for j, step in enumerate(plan):
                if not isinstance(step, dict):
                    fails.append((i, f"plan[{j}] not a dict"))
                    row_ok = False
                    break
                tool = step.get("tool")
                args = step.get("args")
                if not isinstance(tool, str) or not tool:
                    fails.append((i, f"plan[{j}].tool missing or not string"))
                    row_ok = False
                    break
                if not isinstance(args, dict):
                    fails.append((i, f"plan[{j}].args not a dict (got {type(args).__name__})"))
                    row_ok = False
                    break
                tool_freq[tool] += 1
            if row_ok:
                n_ok += 1

    print(f"\n=== JSONL Validation: {path.name} ===")
    print(f"{n_ok}/{n_total} structurally valid")
    if fails:
        print(f"\nFirst 15 failures:")
        for i, msg in fails[:15]:
            print(f"  line {i}: {msg}")

    if report:
        print(f"\n--- Distribution Report ---")
        print(f"Detected role from system prompt: {dict(role_in_system)}")
        print(f"Plan length histogram: {dict(sorted(plan_lens.items()))}")
        print(f"\nDistinct tool names emitted: {len(tool_freq)}")
        for tool, n in tool_freq.most_common(50):
            print(f"  {n:4d}  {tool}")
        if sys_lens:
            print(f"\nSystem prompt char length:  p50={_p(sys_lens, 50):4d}  p95={_p(sys_lens, 95):4d}  max={max(sys_lens):4d}")
            print(f"User msg    char length:    p50={_p(user_lens, 50):4d}  p95={_p(user_lens, 95):4d}  max={max(user_lens):4d}")
            print(f"Assistant   char length:    p50={_p(asst_lens, 50):4d}  p95={_p(asst_lens, 95):4d}  max={max(asst_lens):4d}")

    return 0 if n_ok == n_total else 1


def _p(values: list[int], pct: int) -> int:
    if not values:
        return 0
    s = sorted(values)
    return s[max(0, min(len(s) - 1, int(len(s) * pct / 100)))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="seeds.json",
                        help="Path to seeds.json (canonical) — default")
    parser.add_argument("--jsonl", help="Validate chat-format JSONL (train.jsonl/eval.jsonl)")
    parser.add_argument("--report", action="store_true",
                        help="Print distribution report (only with --jsonl)")
    args = parser.parse_args()

    if args.jsonl:
        rc = _validate_jsonl_file(Path(args.jsonl), report=args.report)
    else:
        rc = _validate_canonical_file(Path(args.path))
    sys.exit(rc)


if __name__ == "__main__":
    main()
