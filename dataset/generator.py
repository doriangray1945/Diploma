"""Hybrid dataset generator for fine-tune training examples.

Architecture:
    seeds.json (canonical intents, role-tagged)
        │
        ▼ load + infer slice/n_variants/schema_lock per intent
    AbstractIntent[] (~90)
        │
        ▼ for each intent: 1 GPT-4o-mini call → N phrasing variants in Russian
    phrasings (~270 total, ~$0.10 cost)
        │
        ▼ for each phrasing × random schema variant (5 variants):
        ▼   programmatic rename of tool/field names, render system prompt
    chat-format JSONL with augmented schema (train.jsonl ~270, eval.jsonl ~40)

Key invariant: validation runs on CANONICAL plan (variant A) before rendering;
the augmented JSONL is implicitly valid if the canonical was valid AND the
renderer is structure-preserving (only renames keys, never values).

CLI:
    python generator.py --pilot          # 8 intents, ~$0.01
    python generator.py --full           # all seeds, ~$0.10
    python generator.py --no-gpt         # use seed_query verbatim, no GPT
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from tool_schemas import (
    ADMIN_TOOL_NAMES, ALL_TOOL_NAMES, CATEGORIES, COLORS, MATERIALS,
    PRICE_LEVELS, QUANTIFIERS, ROOMS, SUBCATEGORIES, SUBCATEGORIES_FLAT,
    USER_TOOL_NAMES,
)
from validator import validate_example


HERE = Path(__file__).parent
load_dotenv(HERE / ".env")


# ---------------------------------------------------------------------------
# Schema variants — multi-axis augmentation:
#
# 1. NAME augmentation: tool/field NAMES vary across variants — model learns
#    "names come from prompt, not memory". Robust to backend renames.
#
# 2. VALUE augmentation: catalog enum VALUES (categories, colors, materials)
#    also vary across variants — model learns "enum values come from prompt
#    too". Robust to adding new categories/colors in catalog without retrain.
#
# 3. ENUM EXTRAS: some variants add NEW values to enum lists that are NOT
#    used in any plan — teaches model "enum can have more values than your
#    plan needs". Critical for handling future catalog growth.
#
# What stays STABLE across all variants:
# - API enums (quantifier=all/first_n/..., operation=set/add/subtract,
#   period=today/week/..., metric=revenue/units_sold/...) — these are
#   API-level contracts, not catalog data. Backend changing operation
#   semantics requires retrain anyway.
# ---------------------------------------------------------------------------

@dataclass
class SchemaVariant:
    id: str
    weight: float
    name_map: dict[str, str]  # canonical_name → variant_name; missing keys = identity
    # value_map: canonical catalog value → variant value. Applied to:
    #   - enum lists in system prompt schemas
    #   - matching values in plan args (e.g. {"category": "Диваны"} → {"category": "Sofa"})
    # Only covers CATEGORIES, COLORS, MATERIALS. API enums never substituted.
    value_map: dict[str, str] = dc_field(default_factory=dict)
    # Extra enum values added to system prompt only (never appear in plan).
    # Teaches model "enum can have values beyond the seeded set".
    # Format: {field_name: [extra_values]}
    enum_extras: dict[str, list[str]] = dc_field(default_factory=dict)


# ---------------------------------------------------------------------------
# Augmentation context (per training row) — generalisation, not memorisation.
#
# 1. Enum subset (15%): drop one canonical value from a field's enum and
#    rewrite the plan to use `search` instead → teaches "value not in enum
#    → fallback to search".
# 2. Field dropout (30%): remove unused optional fields from the rendered
#    schema → teaches "set of optional fields is variable".
# 3. Field injection (30%): add fake optional fields to the schema (never
#    used in plan) → teaches "ignore optional fields not mentioned by user".
# ---------------------------------------------------------------------------

@dataclass
class RowContext:
    # canonical field name → single canonical value to drop from its enum
    dropped_enum_values: dict[str, str] = dc_field(default_factory=dict)
    # canonical tool name → set of canonical property names to drop from schema
    dropped_fields: dict[str, set[str]] = dc_field(default_factory=dict)
    # canonical tool name → list of {"name", "schema"} to inject into schema
    injected_fields: dict[str, list[dict]] = dc_field(default_factory=dict)


EMPTY_CTX = RowContext()


# Canonical required fields per tool (mirrors `required` in _tool_full_schema)
_REQUIRED_FIELDS: dict[str, set[str]] = {
    "apply_filters": set(),
    "add_to_favorites": set(),
    "add_to_cart": set(),
    "remove_from_favorites": {"filter"},
    "remove_from_cart": {"filter"},
    "clear_favorites": set(),
    "clear_cart": set(),
    "update_stock": {"filter", "operation", "quantity"},
    "update_prices": {"filter", "operation", "value"},
    "get_sales_analytics": {"period", "group_by", "metric"},
}

# Canonical top-level property names per tool
_TOOL_PROPS: dict[str, set[str]] = {
    "apply_filters": {"category", "subcategory", "room", "material", "color",
                      "price_level", "min_price", "max_price", "search",
                      "in_stock"},
    "add_to_favorites": {"quantifier", "n", "product_ids"},
    "add_to_cart": {"quantifier", "n", "product_ids", "quantity"},
    "remove_from_favorites": {"filter"},
    "remove_from_cart": {"filter"},
    "clear_favorites": set(),
    "clear_cart": set(),
    "update_stock": {"filter", "operation", "quantity"},
    "update_prices": {"filter", "operation", "value"},
    "get_sales_analytics": {"period", "from_date", "to_date",
                            "group_by", "metric", "sort", "limit", "filter"},
}

# Property names inside admin filter sub-object (apply_filters-like + name/ids)
_ADMIN_FILTER_PROPS: set[str] = {
    "category", "subcategory", "room", "material", "color", "price_level",
    "min_price", "max_price", "search", "in_stock",
    "product_name", "product_ids",
}

# Property names inside remove_from_* filter sub-object
_REMOVE_FILTER_PROPS: set[str] = {
    "category", "color", "material", "product_name", "all",
}


# ── Value mapping tables (for variant B — full English translation) ────────
_CAT_TO_EN = {
    "Диваны": "Sofas", "Кресла": "Armchairs", "Столы": "Tables",
    "Стулья": "Chairs", "Шкафы": "Cabinets", "Кровати": "Beds",
}
_COL_TO_EN = {
    "Бежевый": "Beige", "Белый": "White", "Жёлтый": "Yellow",
    "Зелёный": "Green", "Коричневый": "Brown", "Красный": "Red",
    "Розовый": "Pink", "Серый": "Gray", "Синий": "Blue", "Чёрный": "Black",
}
_MAT_TO_EN = {
    "дерево": "wood", "металл": "metal", "стекло": "glass",
    "ткань": "fabric", "кожа": "leather", "пластик": "plastic",
}
# Подкатегории — варианту B нужна полная EN-карта, иначе variant.value_map
# не выровняет значения в plan'ах. Берём детерминированный transliteration-
# подобный перевод (нужен только для variant B аугментации).
_SUB_TO_EN = {
    "Модульный":      "Modular",
    "Прямой":         "Straight",
    "Угловой":        "Corner",
    "Классическое":   "Classic",
    "Кресло-кровать": "Recliner",
    "Поворотное":     "Swivel",
    "Двуспальная":    "DoubleBed",
    "Детская":        "KidsBed",
    "Модульная":      "ModularBed",
    "Журнальный":     "CoffeeTable",
    "Кухонный":       "KitchenTable",
    "Обеденный":      "Dining",
    "Письменный":     "Writing",
    "Офисный":        "Office",
    "Детский":        "Kids",
    "Навесной":       "Wall",
    "Распашной":      "Swing",
}
# Помещения — для variant B
_ROOM_TO_EN = {
    "гостиная": "living_room",
    "спальня":  "bedroom",
    "детская":  "kids_room",
    "офис":     "office",
    "кухня":    "kitchen",
    "прихожая": "hallway",
}
_VARIANT_B_VALUES = {**_CAT_TO_EN, **_COL_TO_EN, **_MAT_TO_EN,
                     **_SUB_TO_EN, **_ROOM_TO_EN}


VARIANTS: list[SchemaVariant] = [
    # A: canonical names + canonical values. Production-default (55%).
    SchemaVariant(id="A", weight=0.55, name_map={}),

    # B: English names AND English values. Teaches FULL value-grounding —
    # model must read enum values from prompt to decide what to output.
    SchemaVariant(id="B", weight=0.20,
        name_map={
            "apply_filters": "filter_products",
            "add_to_favorites": "save_to_wishlist",
            "remove_from_favorites": "remove_from_wishlist",
            "clear_favorites": "clear_wishlist",
            "add_to_cart": "add_to_basket",
            "remove_from_cart": "remove_from_basket",
            "clear_cart": "clear_basket",
            "update_stock": "modify_inventory",
            "update_prices": "modify_pricing",
            "get_sales_analytics": "fetch_sales_report",
            "category": "type", "subcategory": "subtype",
            "room": "intended_room",
            "material": "materials", "color": "colors",
            "price_level": "tier", "min_price": "price_from", "max_price": "price_to",
            "search": "query", "in_stock": "available",
            "quantifier": "scope", "n": "count", "product_ids": "items",
            "quantity": "units",
            "filter": "criteria", "operation": "action", "value": "amount",
            "period": "timeframe", "from_date": "start_date", "to_date": "end_date",
            "group_by": "aggregate_by", "metric": "kpi",
            "sort": "order", "limit": "top_n",
            "product_name": "name",
        },
        value_map=_VARIANT_B_VALUES,
    ),

    # C: verbose names + canonical values + EXTRA categories/colors/materials
    # in enums (not used in plans). Teaches "enum can be larger than seeds".
    SchemaVariant(id="C", weight=0.25,
        name_map={
            "apply_filters": "search_catalog_with_filters",
            "add_to_favorites": "append_to_favorite_items",
            "remove_from_favorites": "remove_from_favorite_items",
            "clear_favorites": "clear_all_favorite_items",
            "add_to_cart": "append_to_shopping_cart",
            "remove_from_cart": "remove_from_shopping_cart",
            "clear_cart": "clear_all_shopping_cart_items",
            "update_stock": "bulk_update_inventory_stock",
            "update_prices": "bulk_update_product_pricing",
            "get_sales_analytics": "compute_sales_performance_report",
            "category": "product_category",
            "subcategory": "product_subcategory_kind",
            "room": "intended_room_type",
            "material": "product_materials_list",
            "color": "product_colors_list", "price_level": "price_segment",
            "min_price": "minimum_price_rub", "max_price": "maximum_price_rub",
            "search": "free_text_query", "in_stock": "is_in_stock_only",
            "quantifier": "selection_mode", "n": "items_count",
            "product_ids": "product_id_list", "quantity": "units_per_item",
            "filter": "filter_criteria", "operation": "operation_type",
            "value": "operation_value",
            "period": "reporting_period", "from_date": "period_start_date",
            "to_date": "period_end_date", "group_by": "aggregation_dimension",
            "metric": "performance_metric", "sort": "sort_direction",
            "limit": "top_n_limit", "product_name": "product_full_name",
        },
        enum_extras={
            "category":    ["Тумбы", "Стеллажи", "Комоды"],   # new categories
            "color":       ["Бирюзовый", "Бордовый", "Хаки"],  # new colors
            "material":    ["ротанг", "бамбук", "акрил"],      # new materials
            "subcategory": ["Раскладной", "Угловой-L"],         # new subcat shapes
            "room":        ["балкон", "терраса"],               # new rooms
        },
    ),
]


# Sanity: each variant must rename ALL ten tools without collisions, +
# value_map values must be unique within variant
def _validate_variants() -> None:
    for v in VARIANTS:
        rendered = {}
        for canonical, vname in v.name_map.items():
            if canonical in ALL_TOOL_NAMES and vname in rendered:
                raise ValueError(
                    f"Variant {v.id}: tools {rendered[vname]!r} and {canonical!r} "
                    f"both rename to {vname!r}"
                )
            if canonical in ALL_TOOL_NAMES:
                rendered[vname] = canonical
        # value_map: no duplicates
        seen_values = {}
        for canonical, mapped in v.value_map.items():
            if mapped in seen_values:
                raise ValueError(
                    f"Variant {v.id}: values {seen_values[mapped]!r} and "
                    f"{canonical!r} both map to {mapped!r}"
                )
            seen_values[mapped] = canonical
    total = sum(v.weight for v in VARIANTS)
    if not 0.99 < total < 1.01:
        raise ValueError(f"Variant weights sum to {total}, expected 1.0")


_validate_variants()
_VARIANTS_BY_ID = {v.id: v for v in VARIANTS}


def _rename(name: str, variant: SchemaVariant) -> str:
    return variant.name_map.get(name, name)


def _remap_value(value: Any, variant: SchemaVariant) -> Any:
    """Substitute catalog values per variant.value_map. Recurses into lists/dicts.

    Used both by render_plan (for plan args) and _tool_full_schema (for enum
    lists in system prompt). API enums (quantifier values, operation strings,
    period names) are NOT in any variant.value_map so they pass through.
    """
    if isinstance(value, str):
        return variant.value_map.get(value, value)
    if isinstance(value, list):
        return [_remap_value(v, variant) for v in value]
    if isinstance(value, dict):
        return {k: _remap_value(v, variant) for k, v in value.items()}
    return value


def render_plan(canonical_plan: list[dict], variant: SchemaVariant) -> list[dict]:
    """Rename tool names + field keys + catalog values per variant.

    Tool/field keys → name_map. Catalog values (Диваны, Бежевый, ...) →
    value_map. API values (quantifier=all, operation=set, period=week, ...)
    are NEVER in value_map → pass through unchanged.
    """
    out: list[dict] = []
    for step in canonical_plan:
        new_tool = _rename(step["tool"], variant)
        new_args = _rename_keys_and_remap_values(step.get("args", {}), variant)
        out.append({"tool": new_tool, "args": new_args})
    return out


def _rename_keys_and_remap_values(obj: Any, variant: SchemaVariant) -> Any:
    if isinstance(obj, dict):
        return {
            _rename(k, variant): _rename_keys_and_remap_values(v, variant)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_rename_keys_and_remap_values(x, variant) for x in obj]
    if isinstance(obj, str):
        return variant.value_map.get(obj, obj)
    return obj


# ---------------------------------------------------------------------------
# System prompt rendering — JSON Schema with descriptions (industry-standard)
#
# ONE format. Tool/field NAMES rename per variant; descriptions and enum values
# stay invariant (they describe semantics, not API surface).
# ---------------------------------------------------------------------------

# Канонические descriptions — стабильны across variants
TOOL_DESCRIPTIONS: dict[str, str] = {
    "apply_filters": "Применить фильтры к каталогу для поиска товаров",
    "add_to_favorites": "Добавить товары в избранное (с указанием quantifier)",
    "remove_from_favorites": "Удалить товары из избранного по фильтру",
    "clear_favorites": "Очистить избранное полностью",
    "add_to_cart": "Добавить товары в корзину (с указанием количества)",
    "remove_from_cart": "Удалить товары из корзины по фильтру",
    "clear_cart": "Очистить корзину полностью",
    "update_stock": "[ADMIN] Bulk-обновление остатков по фильтру (set/add/subtract)",
    "update_prices": "[ADMIN] Bulk-изменение цен (discount/markup/set_price) по фильтру",
    "get_sales_analytics": "[ADMIN] Гибкая аналитика продаж по периоду и группировке",
}

FIELD_DESCRIPTIONS: dict[str, str] = {
    "category": "Одна категория товара",
    "subcategory": "Подкатегория внутри категории (журнальный/письменный для столов, угловой/прямой для диванов, обеденный/офисный для стульев и т.п.)",
    "room": "Тип помещения, для которого нужна мебель",
    "material": "Материалы (массив, можно несколько)",
    "color": "Цвета (массив, можно несколько)",
    "price_level": "Семантический ценовой сегмент",
    "min_price": "Минимальная цена в рублях",
    "max_price": "Максимальная цена в рублях",
    "search": "Описательные слова: стиль (лофт, минимализм), персона (детский, офисный), эмоция (уютный), конкретные сорта (дуб, велюр)",
    "in_stock": "Только товары в наличии",
    "quantifier": "Какие товары выбрать из видимых (all/first_n/last_n/remaining/specific)",
    "n": "Число РАЗНЫХ товаров (когда quantifier=first_n/last_n)",
    "product_ids": "Конкретные ID товаров",
    "quantity": "Число ШТУК каждого выбранного товара (default 1)",
    "filter": "Критерии фильтрации",
    "operation": "Тип операции",
    "value": "Значение (% для discount/markup, RUB для set_price)",
    "period": "Период отчёта (today/week/month/quarter/year/custom)",
    "from_date": "Начало периода YYYY-MM-DD (только при period=custom)",
    "to_date": "Конец периода YYYY-MM-DD (только при period=custom)",
    "group_by": "Измерение для группировки (product/category/color/material/price_level/day)",
    "metric": "Какой показатель считаем (revenue/units_sold/orders_count/avg_check)",
    "sort": "Направление сортировки (desc/asc)",
    "limit": "Ограничение количества результатов",
    "product_name": "Подстрока в имени товара",
    "all": "Очистить всё (для filter в remove_from_*)",
}


# ── Fake field pool — injected into random schemas to teach the model that
# unknown optional fields can appear and should be ignored if not mentioned
# by user. Names must NOT collide with any canonical or remapped field name
# (validated at module load).
FAKE_FIELDS_POOL: list[dict] = [
    {"name": "brand",             "schema": {"type": "string", "description": "Бренд производителя"}},
    {"name": "style",             "schema": {"type": "string", "enum": ["лофт", "классика", "минимализм", "сканди", "прованс"], "description": "Стиль интерьера"}},
    # NOTE: room_type удалён из FAKE — теперь `room` реальное поле в apply_filters.
    {"name": "discount_only",     "schema": {"type": "boolean", "description": "Только товары со скидкой"}},
    {"name": "min_year",          "schema": {"type": "integer", "description": "Минимальный год выпуска"}},
    {"name": "warranty_months",   "schema": {"type": "integer", "description": "Гарантия в месяцах"}},
    {"name": "country_origin",    "schema": {"type": "string", "description": "Страна происхождения"}},
    {"name": "eco_friendly",      "schema": {"type": "boolean", "description": "Эко-товары"}},
    {"name": "assembly_required", "schema": {"type": "boolean", "description": "Требуется сборка"}},
    {"name": "delivery_speed",    "schema": {"type": "string", "enum": ["express", "standard", "economy"], "description": "Скорость доставки"}},
    {"name": "weight_kg",         "schema": {"type": "number", "description": "Вес товара (кг)"}},
    {"name": "collection",        "schema": {"type": "string", "description": "Название коллекции"}},
    {"name": "is_new",            "schema": {"type": "boolean", "description": "Только новинки"}},
    {"name": "rating_min",        "schema": {"type": "number", "description": "Минимальный рейтинг"}},
    {"name": "tag",               "schema": {"type": "string", "description": "Произвольный тег"}},
]


def _validate_fake_pool() -> None:
    canonical = set()
    for props in _TOOL_PROPS.values():
        canonical |= props
    canonical |= _ADMIN_FILTER_PROPS | _REMOVE_FILTER_PROPS
    fake_names = {f["name"] for f in FAKE_FIELDS_POOL}
    coll = fake_names & canonical
    if coll:
        raise ValueError(f"FAKE_FIELDS_POOL collides with canonical field names: {coll}")
    for v in VARIANTS:
        coll = fake_names & set(v.name_map.values())
        if coll:
            raise ValueError(f"FAKE_FIELDS_POOL collides with variant {v.id} remap values: {coll}")


_validate_fake_pool()


def _enum_for(field_name: str, canonical_values: list[str], variant: SchemaVariant,
              ctx: RowContext = EMPTY_CTX) -> list[str]:
    """Build enum list for a field: drop ctx.dropped_enum_values, remap
    canonical via value_map, then append enum_extras[field_name].
    """
    drop = ctx.dropped_enum_values.get(field_name)
    base = [variant.value_map.get(v, v) for v in canonical_values if v != drop]
    extras = variant.enum_extras.get(field_name, [])
    return base + extras


def _apply_ctx_to_properties(scope_key: str, props: dict, variant: SchemaVariant,
                              ctx: RowContext) -> dict:
    """Drop ctx.dropped_fields[scope_key] and inject ctx.injected_fields[scope_key].
    `scope_key` is the canonical tool name (e.g. "apply_filters") OR
    "<tool>.filter" for nested filter sub-objects.
    """
    for canonical_field in ctx.dropped_fields.get(scope_key, set()):
        props.pop(_rename(canonical_field, variant), None)
    for fake in ctx.injected_fields.get(scope_key, []):
        props[fake["name"]] = fake["schema"]
    return props


def _admin_filter_full_schema(variant: SchemaVariant, ctx: RowContext = EMPTY_CTX,
                               owner_tool: str = "") -> dict:
    """Full JSON Schema for admin filter object — same shape as apply_filters
    PLUS product_name/product_ids."""
    rn = lambda k: _rename(k, variant)
    en = lambda fname, cvalues: _enum_for(fname, cvalues, variant, ctx)
    props: dict = {
        rn("category"):     {"type": "string", "enum": en("category", CATEGORIES), "description": FIELD_DESCRIPTIONS["category"]},
        rn("subcategory"):  {"type": "string", "enum": en("subcategory", SUBCATEGORIES_FLAT), "description": FIELD_DESCRIPTIONS["subcategory"]},
        rn("room"):         {"type": "string", "enum": en("room", ROOMS), "description": FIELD_DESCRIPTIONS["room"]},
        rn("material"):     {"type": "array", "items": {"type": "string", "enum": en("material", MATERIALS)}, "description": FIELD_DESCRIPTIONS["material"]},
        rn("color"):        {"type": "array", "items": {"type": "string", "enum": en("color", COLORS)}, "description": FIELD_DESCRIPTIONS["color"]},
        rn("price_level"):  {"type": "string", "enum": list(PRICE_LEVELS), "description": FIELD_DESCRIPTIONS["price_level"]},
        rn("min_price"):    {"type": "number", "description": FIELD_DESCRIPTIONS["min_price"]},
        rn("max_price"):    {"type": "number", "description": FIELD_DESCRIPTIONS["max_price"]},
        rn("search"):       {"type": "string", "description": FIELD_DESCRIPTIONS["search"]},
        rn("in_stock"):     {"type": "boolean", "description": FIELD_DESCRIPTIONS["in_stock"]},
        rn("product_name"): {"type": "string", "description": FIELD_DESCRIPTIONS["product_name"]},
        rn("product_ids"):  {"type": "array", "items": {"type": "integer"}, "description": FIELD_DESCRIPTIONS["product_ids"]},
    }
    if owner_tool:
        _apply_ctx_to_properties(f"{owner_tool}.filter", props, variant, ctx)
    return {
        "type": "object",
        "minProperties": 1,
        "properties": props,
    }


def _tool_full_schema(canonical_tool: str, variant: SchemaVariant,
                       ctx: RowContext = EMPTY_CTX) -> dict:
    """Build full JSON Schema spec for one tool (industry-standard format).

    Names rename per variant; descriptions/enums stay invariant — descriptions
    describe SEMANTICS (what the field means), not API surface.
    """
    rn = lambda k: _rename(k, variant)
    name = rn(canonical_tool)
    desc = TOOL_DESCRIPTIONS[canonical_tool]

    if canonical_tool in {"clear_favorites", "clear_cart"}:
        return {"name": name, "description": desc,
                "parameters": {"type": "object", "properties": {}}}

    en = lambda fname, cvalues: _enum_for(fname, cvalues, variant, ctx)

    if canonical_tool == "apply_filters":
        props = {
            rn("category"):    {"type": "string", "enum": en("category", CATEGORIES), "description": FIELD_DESCRIPTIONS["category"]},
            rn("subcategory"): {"type": "string", "enum": en("subcategory", SUBCATEGORIES_FLAT), "description": FIELD_DESCRIPTIONS["subcategory"]},
            rn("room"):        {"type": "string", "enum": en("room", ROOMS), "description": FIELD_DESCRIPTIONS["room"]},
            rn("material"):    {"type": "array", "items": {"type": "string", "enum": en("material", MATERIALS)}, "description": FIELD_DESCRIPTIONS["material"]},
            rn("color"):       {"type": "array", "items": {"type": "string", "enum": en("color", COLORS)}, "description": FIELD_DESCRIPTIONS["color"]},
            rn("price_level"): {"type": "string", "enum": list(PRICE_LEVELS), "description": FIELD_DESCRIPTIONS["price_level"]},
            rn("min_price"):   {"type": "number", "description": FIELD_DESCRIPTIONS["min_price"]},
            rn("max_price"):   {"type": "number", "description": FIELD_DESCRIPTIONS["max_price"]},
            rn("search"):      {"type": "string", "description": FIELD_DESCRIPTIONS["search"]},
            rn("in_stock"):    {"type": "boolean", "description": FIELD_DESCRIPTIONS["in_stock"]},
        }
        _apply_ctx_to_properties(canonical_tool, props, variant, ctx)
        return {"name": name, "description": desc,
                "parameters": {"type": "object", "properties": props}}

    if canonical_tool == "add_to_favorites":
        props = {
            rn("quantifier"):  {"type": "string", "enum": list(QUANTIFIERS), "description": FIELD_DESCRIPTIONS["quantifier"]},
            rn("n"):           {"type": "integer", "description": FIELD_DESCRIPTIONS["n"]},
            rn("product_ids"): {"type": "array", "items": {"type": "integer"}, "description": FIELD_DESCRIPTIONS["product_ids"]},
        }
        _apply_ctx_to_properties(canonical_tool, props, variant, ctx)
        return {"name": name, "description": desc,
                "parameters": {"type": "object", "properties": props}}

    if canonical_tool == "add_to_cart":
        props = {
            rn("quantifier"):  {"type": "string", "enum": list(QUANTIFIERS), "description": FIELD_DESCRIPTIONS["quantifier"]},
            rn("n"):           {"type": "integer", "description": FIELD_DESCRIPTIONS["n"]},
            rn("product_ids"): {"type": "array", "items": {"type": "integer"}, "description": FIELD_DESCRIPTIONS["product_ids"]},
            rn("quantity"):    {"type": "integer", "description": FIELD_DESCRIPTIONS["quantity"]},
        }
        _apply_ctx_to_properties(canonical_tool, props, variant, ctx)
        return {"name": name, "description": desc,
                "parameters": {"type": "object", "properties": props}}

    if canonical_tool in {"remove_from_favorites", "remove_from_cart"}:
        filter_props = {
            rn("category"):     {"type": "string", "enum": en("category", CATEGORIES), "description": FIELD_DESCRIPTIONS["category"]},
            rn("color"):        {"type": "array", "items": {"type": "string", "enum": en("color", COLORS)}, "description": FIELD_DESCRIPTIONS["color"]},
            rn("material"):     {"type": "array", "items": {"type": "string", "enum": en("material", MATERIALS)}, "description": FIELD_DESCRIPTIONS["material"]},
            rn("product_name"): {"type": "string", "description": FIELD_DESCRIPTIONS["product_name"]},
            "all":              {"type": "boolean", "description": FIELD_DESCRIPTIONS["all"]},
        }
        _apply_ctx_to_properties(f"{canonical_tool}.filter", filter_props, variant, ctx)
        props = {
            rn("filter"): {
                "type": "object",
                "minProperties": 1,
                "properties": filter_props,
            },
        }
        _apply_ctx_to_properties(canonical_tool, props, variant, ctx)
        return {"name": name, "description": desc,
                "parameters": {"type": "object", "properties": props,
                               "required": [rn("filter")]}}

    if canonical_tool == "update_stock":
        props = {
            rn("filter"):    _admin_filter_full_schema(variant, ctx, canonical_tool),
            rn("operation"): {"type": "string", "enum": ["set", "add", "subtract"], "description": FIELD_DESCRIPTIONS["operation"]},
            rn("quantity"):  {"type": "integer", "minimum": 0, "description": "Количество для операции (число штук)"},
        }
        _apply_ctx_to_properties(canonical_tool, props, variant, ctx)
        return {"name": name, "description": desc,
                "parameters": {"type": "object", "properties": props,
                               "required": [rn("filter"), rn("operation"), rn("quantity")]}}

    if canonical_tool == "update_prices":
        props = {
            rn("filter"):    _admin_filter_full_schema(variant, ctx, canonical_tool),
            rn("operation"): {"type": "string", "enum": ["discount", "markup", "set_price"], "description": FIELD_DESCRIPTIONS["operation"]},
            rn("value"):     {"type": "integer", "description": FIELD_DESCRIPTIONS["value"]},
        }
        _apply_ctx_to_properties(canonical_tool, props, variant, ctx)
        return {"name": name, "description": desc,
                "parameters": {"type": "object", "properties": props,
                               "required": [rn("filter"), rn("operation"), rn("value")]}}

    if canonical_tool == "get_sales_analytics":
        props = {
            rn("period"):    {"type": "string", "enum": ["today", "week", "month", "quarter", "year", "custom"], "description": FIELD_DESCRIPTIONS["period"]},
            rn("from_date"): {"type": "string", "description": FIELD_DESCRIPTIONS["from_date"]},
            rn("to_date"):   {"type": "string", "description": FIELD_DESCRIPTIONS["to_date"]},
            rn("group_by"):  {"type": "string", "enum": ["product", "category", "color", "material", "price_level", "day"], "description": FIELD_DESCRIPTIONS["group_by"]},
            rn("metric"):    {"type": "string", "enum": ["revenue", "units_sold", "orders_count", "avg_check"], "description": FIELD_DESCRIPTIONS["metric"]},
            rn("sort"):      {"type": "string", "enum": ["desc", "asc"], "description": FIELD_DESCRIPTIONS["sort"]},
            rn("limit"):     {"type": "integer", "description": FIELD_DESCRIPTIONS["limit"]},
            rn("filter"):    _admin_filter_full_schema(variant, ctx, canonical_tool),
        }
        _apply_ctx_to_properties(canonical_tool, props, variant, ctx)
        return {"name": name, "description": desc,
                "parameters": {"type": "object", "properties": props,
                               "required": [rn("period"), rn("group_by"), rn("metric")]}}

    return {"name": name, "description": desc, "parameters": {"type": "object", "properties": {}}}


_SYSTEM_PROMPT_TEMPLATE = """Ты помощник мебельного магазина Nova Furnish ({role_label}). Анализируй запрос пользователя и составь план tool-вызовов. Верни JSON с полем `plan` — массив шагов, каждый шаг {{tool, args}}.

Доступные tools (JSON Schema):
{tools_json}

Различай:
- Описательные слова (стиль, контекст, эмоция, персона: «уютный», «лофт», «детский», «для офиса») → поле {search_field}.
- Числа после «штук», «по N штук», «пар(а/у)» → {quantity_field} (штук одного товара). Числа без квалификатора («первые N», «N товаров», «N диванов») → {n_field} (число разных товаров).

Если запрос вне scope (заказ, оплата, приветствие, off-topic) — plan пустой []."""


def render_system_prompt(variant: SchemaVariant, role: str,
                          ctx: RowContext = EMPTY_CTX) -> str:
    """Single canonical system prompt — JSON Schema with full descriptions."""
    available = USER_TOOL_NAMES if role == "user" else ALL_TOOL_NAMES
    tools = [_tool_full_schema(t, variant, ctx) for t in available]
    tools_json = json.dumps({"tools": tools}, ensure_ascii=False, separators=(",", ":"))
    return _SYSTEM_PROMPT_TEMPLATE.format(
        role_label="админ-режим" if role == "admin" else "пользовательский чат",
        tools_json=tools_json,
        search_field=_rename("search", variant),
        quantity_field=_rename("quantity", variant),
        n_field=_rename("n", variant),
    )


# ---------------------------------------------------------------------------
# Abstract intents — loaded from seeds.json with auto-inferred slice/locks
# ---------------------------------------------------------------------------

@dataclass
class AbstractIntent:
    slice: str
    role: str
    seed_query: str
    canonical_plan: list[dict]
    n_variants: int = 3
    schema_lock: str | None = None  # "A" | None — None means random by weight


def load_seeds() -> list[dict]:
    """Load seed examples. Skips comment-only entries (no `user` field) —
    seeds.json mixes data with structural comments like {"_comment": "...", "plan": []}.
    """
    with (HERE / "seeds.json").open() as f:
        return [
            e for e in json.load(f)["examples"]
            if "plan" in e and isinstance(e.get("user"), str) and e["user"].strip()
        ]


_QTY_DISAMB_HINTS = ("штук", "штуки", "штука", "по парочке", "по одной",
                     "две штуки", "купи мне")


def infer_intent(seed: dict) -> AbstractIntent:
    role = seed.get("role", "user")
    plan = seed["plan"]
    user = seed["user"]

    if not plan:
        slice_name = "user_conv" if role == "user" else "negative"
        return AbstractIntent(slice=slice_name, role=role,
                               seed_query=user, canonical_plan=plan,
                               n_variants=2, schema_lock=None)

    if role == "admin":
        tool = plan[0]["tool"]
        slice_name = {
            "update_stock": "admin_stock",
            "update_prices": "admin_prices",
            "get_sales_analytics": "admin_analytics",
        }.get(tool, "admin_misc")
        return AbstractIntent(slice=slice_name, role=role,
                               seed_query=user, canonical_plan=plan,
                               n_variants=3, schema_lock=None)

    # User intent
    if len(plan) > 1:
        return AbstractIntent(slice="user_multistep", role=role,
                               seed_query=user, canonical_plan=plan,
                               n_variants=3, schema_lock=None)

    tool = plan[0]["tool"]
    args = plan[0].get("args", {})

    # Quantity disambiguation: contains qty hint OR explicit quantity field
    is_cart = tool == "add_to_cart"
    has_qty_hint = any(h in user.lower() for h in _QTY_DISAMB_HINTS)
    if is_cart and (has_qty_hint or "quantity" in args):
        return AbstractIntent(slice="user_qty_disamb", role=role,
                               seed_query=user, canonical_plan=plan,
                               n_variants=2, schema_lock="A")

    # Semantic search examples — has 'search' field set without other strong attrs
    if tool == "apply_filters" and "search" in args:
        return AbstractIntent(slice="user_semantic", role=role,
                               seed_query=user, canonical_plan=plan,
                               n_variants=3, schema_lock=None)

    if tool in {"add_to_favorites", "remove_from_favorites", "clear_favorites"}:
        return AbstractIntent(slice="user_favorites", role=role,
                               seed_query=user, canonical_plan=plan,
                               n_variants=3, schema_lock=None)

    if tool in {"add_to_cart", "remove_from_cart", "clear_cart"}:
        return AbstractIntent(slice="user_cart", role=role,
                               seed_query=user, canonical_plan=plan,
                               n_variants=3, schema_lock=None)

    return AbstractIntent(slice="user_simple", role=role,
                           seed_query=user, canonical_plan=plan,
                           n_variants=3, schema_lock=None)


# ---------------------------------------------------------------------------
# Held-out eval intents — never appear in train (no overlap with seeds.json)
# ---------------------------------------------------------------------------

EVAL_INTENTS: list[AbstractIntent] = [
    # User simple (5)
    AbstractIntent("user_simple", "user", "покажи кресла",
                   [{"tool": "apply_filters", "args": {"category": "Кресла"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "столы от 15000 до 40000",
                   [{"tool": "apply_filters", "args": {"category": "Столы", "min_price": 15000, "max_price": 40000}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "премиальные шкафы",
                   [{"tool": "apply_filters", "args": {"category": "Шкафы", "price_level": "premium"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "бежевые стулья",
                   [{"tool": "apply_filters", "args": {"category": "Стулья", "color": ["Бежевый"]}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "что есть в наличии",
                   [{"tool": "apply_filters", "args": {"in_stock": True}}],
                   n_variants=1, schema_lock="A"),

    # User multistep (5)
    AbstractIntent("user_multistep", "user", "найди шкафы и сохрани в избранное",
                   [{"tool": "apply_filters", "args": {"category": "Шкафы"}},
                    {"tool": "add_to_favorites", "args": {"quantifier": "all"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_multistep", "user", "очисти корзину и положи туда первые 3 кресла",
                   [{"tool": "clear_cart", "args": {}},
                    {"tool": "apply_filters", "args": {"category": "Кресла"}},
                    {"tool": "add_to_cart", "args": {"quantifier": "first_n", "n": 3}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_multistep", "user", "найди дешёвые кровати и добавь в избранное",
                   [{"tool": "apply_filters", "args": {"category": "Кровати", "price_level": "budget"}},
                    {"tool": "add_to_favorites", "args": {"quantifier": "all"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_multistep", "user", "удали все из избранного и из корзины",
                   [{"tool": "clear_favorites", "args": {}},
                    {"tool": "clear_cart", "args": {}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_multistep", "user", "найди диваны от 20 до 80 тысяч и добавь все в избранное",
                   [{"tool": "apply_filters", "args": {"category": "Диваны", "min_price": 20000, "max_price": 80000}},
                    {"tool": "add_to_favorites", "args": {"quantifier": "all"}}],
                   n_variants=1, schema_lock="A"),

    # User quantity-disamb (5) — distinct from train
    AbstractIntent("user_qty_disamb", "user", "положи 7 штук в корзину",
                   [{"tool": "add_to_cart", "args": {"quantifier": "all", "quantity": 7}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_qty_disamb", "user", "добавь 3 стола в корзину",
                   [{"tool": "add_to_cart", "args": {"quantifier": "first_n", "n": 3}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_qty_disamb", "user", "первые 5 в корзину по 3 штуки",
                   [{"tool": "add_to_cart", "args": {"quantifier": "first_n", "n": 5, "quantity": 3}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_qty_disamb", "user", "по тройке всех в корзину",
                   [{"tool": "add_to_cart", "args": {"quantifier": "all", "quantity": 3}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_qty_disamb", "user", "положи 2 разных дивана",
                   [{"tool": "add_to_cart", "args": {"quantifier": "first_n", "n": 2}}],
                   n_variants=1, schema_lock="A"),

    # User semantic (5)
    AbstractIntent("user_semantic", "user", "что-то для маленькой кухни",
                   [{"tool": "apply_filters", "args": {"search": "кухня"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_semantic", "user", "винтажный шкаф из дерева",
                   [{"tool": "apply_filters", "args": {"category": "Шкафы", "material": ["дерево"], "search": "винтаж"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_semantic", "user", "лофт кресло",
                   [{"tool": "apply_filters", "args": {"category": "Кресла", "material": ["металл"], "search": "лофт"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_semantic", "user", "ищу что-то для дачи",
                   [{"tool": "apply_filters", "args": {"search": "дача"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_semantic", "user", "уютное кресло",
                   [{"tool": "apply_filters", "args": {"category": "Кресла", "material": ["ткань", "кожа"], "search": "уютный"}}],
                   n_variants=1, schema_lock="A"),

    # User conversational (5)
    AbstractIntent("user_conv", "user", "хеллоу", [], n_variants=1, schema_lock="A"),
    AbstractIntent("user_conv", "user", "благодарю вас", [], n_variants=1, schema_lock="A"),
    AbstractIntent("user_conv", "user", "как дела", [], n_variants=1, schema_lock="A"),
    AbstractIntent("user_conv", "user", "у вас есть бонусы", [], n_variants=1, schema_lock="A"),
    AbstractIntent("user_conv", "user", "оплатить заказ", [], n_variants=1, schema_lock="A"),

    # Admin stock (5)
    AbstractIntent("admin_stock", "admin", "пополни остаток зелёных кресел на 40",
                   [{"tool": "update_stock", "args": {
                       "filter": {"category": "Кресла", "color": ["Зелёный"]},
                       "operation": "add", "quantity": 40}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_stock", "admin", "установи остаток мягких диванов в 75 штук",
                   [{"tool": "update_stock", "args": {
                       "filter": {"category": "Диваны", "material": ["ткань", "кожа"]},
                       "operation": "set", "quantity": 75}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_stock", "admin", "спиши 5 штук премиум столов",
                   [{"tool": "update_stock", "args": {
                       "filter": {"category": "Столы", "price_level": "premium"},
                       "operation": "subtract", "quantity": 5}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_stock", "admin", "обнови остаток детских кроватей на 20",
                   [{"tool": "update_stock", "args": {
                       "filter": {"category": "Кровати", "search": "детский"},
                       "operation": "set", "quantity": 20}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_stock", "admin", "пополни всё что заканчивается на 100",
                   [{"tool": "update_stock", "args": {
                       "filter": {"in_stock": False},
                       "operation": "set", "quantity": 100}}],
                   n_variants=1, schema_lock="A"),

    # Admin prices (5)
    AbstractIntent("admin_prices", "admin", "сделай скидку 10% на бюджетные стулья",
                   [{"tool": "update_prices", "args": {
                       "filter": {"category": "Стулья", "price_level": "budget"},
                       "operation": "discount", "value": 10}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_prices", "admin", "поставь цену 80000 на премиум диваны",
                   [{"tool": "update_prices", "args": {
                       "filter": {"category": "Диваны", "price_level": "premium"},
                       "operation": "set_price", "value": 80000}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_prices", "admin", "наценка 20% на всё дороже 100к",
                   [{"tool": "update_prices", "args": {
                       "filter": {"min_price": 100000},
                       "operation": "markup", "value": 20}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_prices", "admin", "скидка 40% на чёрные кресла из ткани",
                   [{"tool": "update_prices", "args": {
                       "filter": {"category": "Кресла", "color": ["Чёрный"], "material": ["ткань"]},
                       "operation": "discount", "value": 40}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_prices", "admin", "установи цену 120000 на дубовые шкафы",
                   [{"tool": "update_prices", "args": {
                       "filter": {"category": "Шкафы", "material": ["дерево"], "search": "дуб"},
                       "operation": "set_price", "value": 120000}}],
                   n_variants=1, schema_lock="A"),

    # Admin analytics (5)
    AbstractIntent("admin_analytics", "admin", "топ-3 столов по выручке за квартал",
                   [{"tool": "get_sales_analytics", "args": {
                       "period": "quarter", "group_by": "product", "metric": "revenue",
                       "sort": "desc", "limit": 3, "filter": {"category": "Столы"}}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_analytics", "admin", "продажи по дням за неделю",
                   [{"tool": "get_sales_analytics", "args": {
                       "period": "week", "group_by": "day", "metric": "units_sold"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_analytics", "admin", "выручка за сегодня",
                   [{"tool": "get_sales_analytics", "args": {
                       "period": "today", "group_by": "day", "metric": "revenue"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_analytics", "admin", "что хуже всего продаётся за год",
                   [{"tool": "get_sales_analytics", "args": {
                       "period": "year", "group_by": "product", "metric": "units_sold",
                       "sort": "asc", "limit": 10}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("admin_analytics", "admin", "выручка с 1 января по 1 февраля",
                   [{"tool": "get_sales_analytics", "args": {
                       "period": "custom", "from_date": "2026-01-01", "to_date": "2026-02-01",
                       "group_by": "day", "metric": "revenue"}}],
                   n_variants=1, schema_lock="A"),

    # ───────────────────────────────────────────────────────────────────
    # v6 NEW: room queries (held-out — formulations differ from train seeds)
    # ───────────────────────────────────────────────────────────────────
    AbstractIntent("user_simple", "user", "что подойдёт для гостиной",
                   [{"tool": "apply_filters", "args": {"room": "гостиная"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "подбор мебели в спальню",
                   [{"tool": "apply_filters", "args": {"room": "спальня"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "что у вас для кухни",
                   [{"tool": "apply_filters", "args": {"room": "кухня"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "что для прихожей есть",
                   [{"tool": "apply_filters", "args": {"room": "прихожая"}}],
                   n_variants=1, schema_lock="A"),

    # v6 NEW: category + room
    AbstractIntent("user_simple", "user", "кресло для рабочего места",
                   [{"tool": "apply_filters", "args": {"category": "Кресла", "room": "офис"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "диван для гостиной комнаты",
                   [{"tool": "apply_filters", "args": {"category": "Диваны", "room": "гостиная"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "шкаф в коридор",
                   [{"tool": "apply_filters", "args": {"category": "Шкафы", "room": "прихожая"}}],
                   n_variants=1, schema_lock="A"),

    # v6 NEW: subcategory (held-out phrasings)
    AbstractIntent("user_simple", "user", "столик журнальный",
                   [{"tool": "apply_filters", "args": {"category": "Столы", "subcategory": "Журнальный"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "стол письменный для работы",
                   [{"tool": "apply_filters", "args": {"category": "Столы", "subcategory": "Письменный"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "хочу подобрать угловую модель дивана",
                   [{"tool": "apply_filters", "args": {"category": "Диваны", "subcategory": "Угловой"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "кровать двуспальная",
                   [{"tool": "apply_filters", "args": {"category": "Кровати", "subcategory": "Двуспальная"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "шкаф распашной",
                   [{"tool": "apply_filters", "args": {"category": "Шкафы", "subcategory": "Распашной"}}],
                   n_variants=1, schema_lock="A"),

    # v6 NEW: subcategory + color
    AbstractIntent("user_simple", "user", "журнальный стол серого цвета",
                   [{"tool": "apply_filters", "args": {
                       "category": "Столы", "subcategory": "Журнальный", "color": ["Серый"]}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "обеденный стол в белом",
                   [{"tool": "apply_filters", "args": {
                       "category": "Столы", "subcategory": "Обеденный", "color": ["Белый"]}}],
                   n_variants=1, schema_lock="A"),

    # v6 NEW: subcategory + room
    AbstractIntent("user_simple", "user", "обеденные стулья для кухни",
                   [{"tool": "apply_filters", "args": {
                       "category": "Стулья", "subcategory": "Обеденный", "room": "кухня"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "письменный стол в кабинет",
                   [{"tool": "apply_filters", "args": {
                       "category": "Столы", "subcategory": "Письменный", "room": "офис"}}],
                   n_variants=1, schema_lock="A"),

    # v6 NEW: ambiguity (детская как room vs subcategory)
    AbstractIntent("user_simple", "user", "что-то в детскую",
                   [{"tool": "apply_filters", "args": {"room": "детская"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "детская кроватка",
                   [{"tool": "apply_filters", "args": {"category": "Кровати", "subcategory": "Детская"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "шкаф для детской комнаты",
                   [{"tool": "apply_filters", "args": {"category": "Шкафы", "room": "детская"}}],
                   n_variants=1, schema_lock="A"),

    # v6 NEW: ambiguity (офис — room vs subcategory Офисный)
    AbstractIntent("user_simple", "user", "крутящийся стул офисного типа",
                   [{"tool": "apply_filters", "args": {"category": "Стулья", "subcategory": "Офисный"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "что есть из стульев в офис",
                   [{"tool": "apply_filters", "args": {"category": "Стулья", "room": "офис"}}],
                   n_variants=1, schema_lock="A"),

    # v6 NEW: обеденный стол vs обеденный стул
    AbstractIntent("user_simple", "user", "столы обеденные",
                   [{"tool": "apply_filters", "args": {"category": "Столы", "subcategory": "Обеденный"}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "стулья обеденные деревянные",
                   [{"tool": "apply_filters", "args": {
                       "category": "Стулья", "subcategory": "Обеденный", "material": ["дерево"]}}],
                   n_variants=1, schema_lock="A"),

    # v6 NEW: новая палитра (10 базовых цветов — проверка что модель НЕ генерит старые)
    AbstractIntent("user_simple", "user", "розовый диван",
                   [{"tool": "apply_filters", "args": {"category": "Диваны", "color": ["Розовый"]}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "жёлтое кресло",
                   [{"tool": "apply_filters", "args": {"category": "Кресла", "color": ["Жёлтый"]}}],
                   n_variants=1, schema_lock="A"),
    AbstractIntent("user_simple", "user", "коричневый стол из дерева",
                   [{"tool": "apply_filters", "args": {
                       "category": "Столы", "color": ["Коричневый"], "material": ["дерево"]}}],
                   n_variants=1, schema_lock="A"),
]


# ---------------------------------------------------------------------------
# GPT-4 phrasing variants
# ---------------------------------------------------------------------------

_PHRASING_PROMPT = """Дай {n} разнообразных русскоязычных перефразировок этого запроса {role_label}.

ВАЖНО:
- Сохрани СМЫСЛ и ВСЕ упомянутые сущности (категории, цвета, числа, имена, операции) — НЕ удаляй и не меняй их семантику.
- НЕ добавляй атрибуты, которых нет в оригинале (если оригинал не упоминает цвет — не добавляй цвет).
- Варьируй: формальность, разговорность, длину, порядок слов. Можно опечатки в ~25% (модель должна быть к ним устойчива).
- Каждая перефразировка ≥ 2 слов.

Оригинал: "{seed_query}"

Верни строго JSON-объект:
{{"phrasings": ["...", "...", ...]}}

Без комментариев, без markdown, ровно {n} элементов в списке."""


def gpt_phrasings(client: OpenAI, intent: AbstractIntent, n: int,
                  model: str = "gpt-4o-mini") -> list[str]:
    if n <= 0:
        return []
    role_label = ("админ-панели мебельного магазина" if intent.role == "admin"
                  else "мебельному магазину")
    prompt = _PHRASING_PROMPT.format(
        n=n, role_label=role_label, seed_query=intent.seed_query
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Ты эксперт по русскому языку и генерации обучающих данных."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.95,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        parsed = json.loads(raw)
        phrasings = parsed.get("phrasings", [])
        if not isinstance(phrasings, list):
            return []
        # Filter: must be string, non-empty, not literally equal to seed
        out = []
        for p in phrasings:
            if isinstance(p, str) and p.strip() and p.strip().lower() != intent.seed_query.strip().lower():
                out.append(p.strip())
        return out[:n]
    except Exception as e:
        print(f"  GPT phrasing error for {intent.seed_query!r}: {e}")
        return []


# Token sanity: drop phrasings that lost key tokens from the original
_NUMBER_RE = re.compile(r"\d+")
_KEYWORD_TOKENS = {
    "красн", "син", "зелён", "зелен", "жёлт", "желт", "чёрн", "черн",
    "беж", "бел", "коричн", "сер", "розов", "оранж",
    "диван", "крес", "стол", "стул", "шкаф", "кроват",
    "дерев", "металл", "стекл", "ткан", "кож", "пластик",
    "дуб", "сосн", "велюр", "лофт", "уют", "элегант", "винтаж",
    "детск", "офис", "минимал", "скандинав", "гостин", "кух", "дач",
    "спальн", "прихож",
    "журнальн", "обеден", "письменн", "поворотн", "двуспальн", "прямой",
    "угловой", "модульн", "классическ", "навесн", "распашн", "кухонн",
    "набор", "комплект",
    "недорог", "дешёв", "дешов", "бюджет", "премиум", "дорог", "люкс",
    "первы", "последн", "разных", "штук", "шт", "по ", "пар",
    "скидк", "наценк", "цен", "остат", "пополн", "обнул", "спиш",
    "продаж", "выручк", "топ", "анал", "за нед", "за мес", "за квар", "за год", "за день",
    "избранн", "корзин",
}


def phrasing_preserves_meaning(phrase: str, seed: str) -> bool:
    """Heuristic: phrasings must preserve numeric values + key topical tokens."""
    p = phrase.lower()
    s = seed.lower()
    seed_numbers = set(_NUMBER_RE.findall(s))
    phrase_numbers = set(_NUMBER_RE.findall(p))
    if seed_numbers != phrase_numbers:
        return False
    seed_keywords = {tok for tok in _KEYWORD_TOKENS if tok in s}
    phrase_keywords = {tok for tok in _KEYWORD_TOKENS if tok in p}
    # Allow loss of up to 1 keyword (paraphrasing tolerance)
    if len(seed_keywords - phrase_keywords) > 1:
        return False
    return True


# ---------------------------------------------------------------------------
# Variant picker
# ---------------------------------------------------------------------------

def pick_variant(intent: AbstractIntent, rng: random.Random) -> SchemaVariant:
    if intent.schema_lock == "A":
        return _VARIANTS_BY_ID["A"]
    if intent.schema_lock == "NOT-A":
        non_a = [v for v in VARIANTS if v.id != "A"]
        weights = [v.weight for v in non_a]
        return rng.choices(non_a, weights=weights, k=1)[0]
    weights = [v.weight for v in VARIANTS]
    return rng.choices(VARIANTS, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Augmentation: enum subset + field dropout + field injection
# ---------------------------------------------------------------------------

import copy as _copy

# Mutually-exclusive augmentation: a single dice roll picks ONE of these
# (or no augmentation at all). This keeps each training row's signal clean —
# the model never sees enum_subset + dropout + injection compounded together.
# Targets ≈ 15% rows per type, 55% rows clean canonical.
P_ENUM_SUBSET = 0.15
P_FIELD_DROPOUT = 0.15
P_FIELD_INJECT = 0.15
_AUG_THRESHOLDS = (
    P_ENUM_SUBSET,
    P_ENUM_SUBSET + P_FIELD_DROPOUT,
    P_ENUM_SUBSET + P_FIELD_DROPOUT + P_FIELD_INJECT,
)  # < t[0]: enum_subset; < t[1]: dropout; < t[2]: injection; else canonical


# Which (canonical) sub-filter scope each tool's "filter" arg refers to.
# scope_key conventions in RowContext:
#   - "<tool>"        — top-level properties of that tool
#   - "<tool>.filter" — nested filter sub-object properties
_FILTER_SCOPE_PROPS: dict[str, set[str]] = {
    "remove_from_favorites": _REMOVE_FILTER_PROPS,
    "remove_from_cart":      _REMOVE_FILTER_PROPS,
    "update_stock":          _ADMIN_FILTER_PROPS,
    "update_prices":         _ADMIN_FILTER_PROPS,
    "get_sales_analytics":   _ADMIN_FILTER_PROPS,
}


def _used_fields_for_tool(plan: list[dict], canonical_tool: str) -> set[str]:
    used: set[str] = set()
    for step in plan:
        if step.get("tool") != canonical_tool:
            continue
        used |= set((step.get("args") or {}).keys())
    return used


def _used_fields_for_filter(plan: list[dict], canonical_tool: str) -> set[str]:
    used: set[str] = set()
    for step in plan:
        if step.get("tool") != canonical_tool:
            continue
        flt = (step.get("args") or {}).get("filter") or {}
        if isinstance(flt, dict):
            used |= set(flt.keys())
    return used


# Containers where search-fallback is impossible because the schema doesn't
# expose a `search` field there (remove_from_* filter sub-object).
_NO_SEARCH_FILTER_TOOLS: set[str] = {"remove_from_favorites", "remove_from_cart"}


def _all_value_mentions(plan: list[dict], field: str, value: str
                         ) -> list[tuple[list[Any], bool]]:
    """Return [(container_path, would_collapse_to_search), ...] for every
    container in `plan` that mentions `value` in `field`.
    `would_collapse_to_search` is True when the rewrite would have to delete
    the whole field and create a `search` token (string field, or list of
    length 1 containing only this value)."""
    out: list[tuple[list[Any], bool]] = []
    for idx, step in enumerate(plan):
        for container_path in ([idx, "args"], [idx, "args", "filter"]):
            container: Any = step
            for key in container_path[1:]:
                container = (container or {}).get(key) if isinstance(container, dict) else None
            if not isinstance(container, dict) or field not in container:
                continue
            v = container[field]
            if isinstance(v, str) and v == value:
                out.append((container_path, True))
            elif isinstance(v, list) and value in v:
                collapse = (len(v) == 1)
                out.append((container_path, collapse))
    return out


def _enum_candidates(plan: list[dict]) -> list[tuple[int, list[str], str, Any]]:
    """Find (step_idx, path_to_args, field_name, value) tuples eligible for
    enum_subset augmentation: dropping `value` from `field`'s enum must allow
    valid rewrites of EVERY container in the plan that mentions it.
    Disallowed when any mention sits in a search-less filter (remove_from_*)
    AND the rewrite there would have to collapse to a search token."""
    canonical_sets = {
        "category": set(CATEGORIES),
        "color":    set(COLORS),
        "material": set(MATERIALS),
    }
    seen_pairs: set[tuple[str, str]] = set()
    out: list[tuple[int, list[str], str, Any]] = []
    for idx, step in enumerate(plan):
        for container_path in ([idx, "args"], [idx, "args", "filter"]):
            container: Any = step
            for key in container_path[1:]:
                container = (container or {}).get(key) if isinstance(container, dict) else None
            if not isinstance(container, dict):
                continue
            for field, allowed in canonical_sets.items():
                if field not in container:
                    continue
                v = container[field]
                values_here: list[str] = []
                if isinstance(v, str) and v in allowed:
                    values_here = [v]
                elif isinstance(v, list):
                    values_here = [e for e in v if isinstance(e, str) and e in allowed]
                for value in values_here:
                    if (field, value) in seen_pairs:
                        continue
                    seen_pairs.add((field, value))
                    # Global eligibility: every mention must be rewritable
                    mentions = _all_value_mentions(plan, field, value)
                    blocked = any(
                        collapse and (
                            len(p) == 3 and plan[p[0]].get("tool") in _NO_SEARCH_FILTER_TOOLS
                        )
                        for p, collapse in mentions
                    )
                    if blocked:
                        continue
                    out.append((idx, container_path, field, value))
    return out


def _resolve_container(plan: list[dict], path: list[Any]) -> dict:
    container: Any = plan[path[0]]
    for key in path[1:]:
        container = container[key]
    return container


def _apply_enum_subset_to_plan(plan: list[dict], path: list[Any],
                                field: str, value: str) -> None:
    """Mutate plan in-place: remove `value` from the field at `path`. If the
    field becomes empty, drop the field and append a lowercased token to
    `search` (creating it when absent). Search lives in the same container."""
    container = _resolve_container(plan, path)
    cur = container[field]
    fallback_token = value.lower()
    if isinstance(cur, list):
        new_list = [x for x in cur if x != value]
        if new_list:
            container[field] = new_list
            return
        del container[field]
    else:
        del container[field]
    existing_search = container.get("search", "")
    container["search"] = (existing_search + " " + fallback_token).strip() if existing_search else fallback_token


def build_row_context(canonical_plan: list[dict], variant: SchemaVariant,
                       role: str, rng: random.Random
                       ) -> tuple[list[dict], RowContext]:
    """Build a RowContext (per-row augmentation state) and return a possibly-
    rewritten plan. The plan is rewritten BEFORE render_plan applies name/value
    remapping. Returned plan is always valid against the rendered schema for
    this row (enforced by safety invariants)."""
    plan = _copy.deepcopy(canonical_plan)
    ctx = RowContext()

    # Single dice roll picks ONE augmentation (or canonical). This keeps each
    # row's training signal clean — never enum_subset + dropout + injection
    # all on the same row.
    roll = rng.random()

    # Branch 1: Enum subset (~15% rows). Drop one value from a categorical
    # enum, rewrite plan to use search-fallback wherever that value appeared.
    if roll < _AUG_THRESHOLDS[0] and plan:
        candidates = _enum_candidates(plan)
        if candidates:
            _idx, _path, field, value = rng.choice(candidates)
            ctx.dropped_enum_values[field] = value
            for path, _collapse in _all_value_mentions(plan, field, value):
                _apply_enum_subset_to_plan(plan, path, field, value)
        return plan, ctx

    available_tools = (USER_TOOL_NAMES if role == "user" else ALL_TOOL_NAMES)

    # Branch 2: Field dropout (~15% rows). Remove unused optional fields
    # from one or two scopes (top-level tool or its nested filter).
    if roll < _AUG_THRESHOLDS[1]:
        drop_candidates: list[tuple[str, set[str]]] = []
        for tool in available_tools:
            used = _used_fields_for_tool(plan, tool)
            required = _REQUIRED_FIELDS.get(tool, set())
            droppable = _TOOL_PROPS.get(tool, set()) - required - used
            if droppable:
                drop_candidates.append((tool, droppable))
            if tool in _FILTER_SCOPE_PROPS:
                scope_key = f"{tool}.filter"
                filter_props = _FILTER_SCOPE_PROPS[tool]
                droppable_f = filter_props - _used_fields_for_filter(plan, tool)
                if droppable_f:
                    drop_candidates.append((scope_key, droppable_f))
        if drop_candidates:
            n_scopes = min(rng.randint(1, 2), len(drop_candidates))
            for scope_key, droppable in rng.sample(drop_candidates, n_scopes):
                k = min(rng.randint(1, 2), len(droppable))
                ctx.dropped_fields[scope_key] = set(rng.sample(sorted(droppable), k))
        return plan, ctx

    # Branch 3: Field injection (~15% rows). Inject 1-2 fake optional fields
    # into one or two scopes. Fake fields never appear in the plan — model
    # learns to ignore unknown fields the user didn't mention.
    if roll < _AUG_THRESHOLDS[2]:
        inject_scopes: list[str] = []
        for tool in available_tools:
            inject_scopes.append(tool)
            if tool in _FILTER_SCOPE_PROPS:
                inject_scopes.append(f"{tool}.filter")
        used_fake_names: set[str] = set()
        if inject_scopes:
            n_scopes = min(rng.randint(1, 2), len(inject_scopes))
            for scope_key in rng.sample(inject_scopes, n_scopes):
                available_fakes = [f for f in FAKE_FIELDS_POOL if f["name"] not in used_fake_names]
                if not available_fakes:
                    break
                k = min(rng.randint(1, 2), len(available_fakes))
                chosen = rng.sample(available_fakes, k)
                ctx.injected_fields[scope_key] = chosen
                used_fake_names |= {f["name"] for f in chosen}
        return plan, ctx

    # Else: canonical row (no augmentation, ~55%)
    return plan, ctx


# ---------------------------------------------------------------------------
# Safety: rendered plan MUST be valid against the rendered schema
# ---------------------------------------------------------------------------

def _assert_plan_schema_consistent(rendered_plan: list[dict], sys_prompt: str,
                                    variant: SchemaVariant,
                                    canonical_plan: list[dict],
                                    ctx: RowContext) -> None:
    """Parse the tools array out of the system prompt and verify that every
    arg key in `rendered_plan` exists in the rendered schema, and every enum
    value used in the plan is present in its rendered enum list."""
    start = sys_prompt.find('{"tools":')
    if start < 0:
        return  # nothing to validate
    decoder = json.JSONDecoder()
    tools_obj, _ = decoder.raw_decode(sys_prompt[start:])
    tools_by_name = {t["name"]: t for t in tools_obj["tools"]}

    def _check_args(args: dict, schema_props: dict, scope: str) -> None:
        for k, v in args.items():
            if k not in schema_props:
                raise AssertionError(
                    f"plan/schema mismatch: arg {k!r} not in {scope} props "
                    f"{sorted(schema_props.keys())}; canonical={canonical_plan}; ctx={ctx}"
                )
            field_schema = schema_props[k]
            enum = field_schema.get("enum")
            items = field_schema.get("items") or {}
            items_enum = items.get("enum")
            if enum is not None and isinstance(v, str) and v not in enum:
                raise AssertionError(
                    f"plan/schema mismatch: value {v!r} for {k!r} not in enum {enum}; "
                    f"canonical={canonical_plan}; ctx={ctx}"
                )
            if items_enum is not None and isinstance(v, list):
                for elem in v:
                    if isinstance(elem, str) and elem not in items_enum:
                        raise AssertionError(
                            f"plan/schema mismatch: list elem {elem!r} for {k!r} "
                            f"not in items.enum {items_enum}; canonical={canonical_plan}; ctx={ctx}"
                        )

    for step in rendered_plan:
        tool_name = step["tool"]
        if tool_name not in tools_by_name:
            raise AssertionError(f"tool {tool_name!r} not in rendered tools")
        tool_schema = tools_by_name[tool_name]
        params = tool_schema.get("parameters") or {}
        props = params.get("properties") or {}
        args = step.get("args") or {}
        _check_args(args, props, f"tool {tool_name}")
        # Nested filter sub-object
        # The filter field name is renamed by variant — find it by checking
        # which key in args is itself a dict (filter is the only nested dict
        # in our schemas).
        for arg_key, arg_val in args.items():
            if isinstance(arg_val, dict):
                sub_schema = props.get(arg_key) or {}
                sub_props = (sub_schema.get("properties") or {})
                _check_args(arg_val, sub_props, f"{tool_name}.{arg_key}")


def _print_aug_debug(ctx: RowContext, canonical_plan: list[dict]) -> None:
    if ctx.dropped_enum_values:
        print(f"  AUG: enum_subset {dict(ctx.dropped_enum_values)} (canonical={canonical_plan})", file=sys.stderr)
    if ctx.dropped_fields:
        print(f"  AUG: dropout {dict((k, sorted(v)) for k, v in ctx.dropped_fields.items())}", file=sys.stderr)
    if ctx.injected_fields:
        names = {k: [f['name'] for f in v] for k, v in ctx.injected_fields.items()}
        print(f"  AUG: inject {names}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Row construction
# ---------------------------------------------------------------------------

def make_row(query: str, canonical_plan: list[dict], variant: SchemaVariant,
             role: str, rng: random.Random | None = None,
             aug_debug: bool = False) -> dict:
    """Build one training row. If `rng` is provided, augmentation fires
    (enum subset 15%, field dropout 30%, field injection 30%); otherwise
    the row is canonical (used for eval rows)."""
    if rng is None:
        rewritten_plan, ctx = canonical_plan, EMPTY_CTX
    else:
        rewritten_plan, ctx = build_row_context(canonical_plan, variant, role, rng)
    rendered_plan = render_plan(rewritten_plan, variant)
    sys_prompt = render_system_prompt(variant, role, ctx)
    _assert_plan_schema_consistent(rendered_plan, sys_prompt, variant, canonical_plan, ctx)
    if aug_debug and rng is not None:
        _print_aug_debug(ctx, canonical_plan)
    return {
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": query},
            {"role": "assistant", "content": json.dumps(
                {"plan": rendered_plan}, ensure_ascii=False)},
        ]
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true",
                        help="Pilot: 8 random intents, ~$0.01")
    parser.add_argument("--full", action="store_true",
                        help="Full run: all seeds, ~$0.10-0.50")
    parser.add_argument("--no-gpt", action="store_true",
                        help="Skip GPT phrasing — use seed_query verbatim")
    parser.add_argument("--model", default="gpt-4o-mini",
                        help="Phrasing model (gpt-4o-mini default; gpt-4o for higher quality)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-train", default="train.jsonl")
    parser.add_argument("--out-eval", default="eval.jsonl")
    parser.add_argument("--aug-debug", action="store_true",
                        help="Print per-row augmentation details to stderr")
    args = parser.parse_args()

    if not (args.pilot or args.full):
        print("Specify --pilot or --full")
        sys.exit(1)

    rng = random.Random(args.seed)

    raw_seeds = load_seeds()
    intents = [infer_intent(s) for s in raw_seeds]
    if args.pilot:
        intents = rng.sample(intents, k=min(8, len(intents)))

    # Validate canonical plans first
    print(f"\nValidating {len(intents)} train intents (canonical)...")
    n_invalid = 0
    for intent in intents:
        ex = {"role": intent.role, "user": intent.seed_query, "plan": intent.canonical_plan}
        ok, errs = validate_example(ex)
        if not ok:
            print(f"  INVALID: {intent.seed_query!r}: {errs}")
            n_invalid += 1
    if n_invalid:
        print(f"\n{n_invalid} invalid intents — fix seeds.json first")
        sys.exit(1)

    print(f"Validating {len(EVAL_INTENTS)} eval intents...")
    for intent in EVAL_INTENTS:
        ex = {"role": intent.role, "user": intent.seed_query, "plan": intent.canonical_plan}
        ok, errs = validate_example(ex)
        if not ok:
            print(f"  EVAL INVALID: {intent.seed_query!r}: {errs}")
            sys.exit(1)

    # No leakage between train & eval (exact-string)
    train_queries = {i.seed_query.strip().lower() for i in intents}
    eval_queries = {i.seed_query.strip().lower() for i in EVAL_INTENTS}
    overlap = train_queries & eval_queries
    if overlap:
        print(f"WARNING: {len(overlap)} queries appear in both train and eval: {list(overlap)[:5]}")

    # GPT phrasings
    client = None
    if not args.no_gpt:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("OPENAI_API_KEY missing. Use --no-gpt or add it to dataset/.env")
            sys.exit(1)
        client = OpenAI(api_key=api_key)

    # Slices that should NOT use GPT phrasing — qty disamb is too fragile
    NO_GPT_SLICES = {"user_qty_disamb"}

    train_rows: list[dict] = []
    started = time.time()
    by_slice: dict[str, int] = {}
    by_variant: dict[str, int] = {}
    by_role: dict[str, int] = {}

    for i, intent in enumerate(intents):
        # Determine actual phrasings to render
        n_phrasings = intent.n_variants
        phrasings: list[str]
        if intent.slice in NO_GPT_SLICES or args.no_gpt or client is None:
            # Use seed_query and (optionally) hand-crafted variants
            phrasings = [intent.seed_query]
            # Pad to n_variants by repeating with variant changes (different variant per row)
            while len(phrasings) < n_phrasings:
                phrasings.append(intent.seed_query)
        else:
            generated = gpt_phrasings(client, intent, n_phrasings, model=args.model)
            # Filter for meaning preservation
            generated = [p for p in generated if phrasing_preserves_meaning(p, intent.seed_query)]
            # Always include seed_query as one of the phrasings
            phrasings = [intent.seed_query] + generated
            phrasings = phrasings[:n_phrasings]
            # If too few, repeat seed_query
            while len(phrasings) < n_phrasings:
                phrasings.append(intent.seed_query)

        # For each phrasing, pick a variant and emit a row
        for phrase in phrasings:
            variant = pick_variant(intent, rng)
            row = make_row(phrase, intent.canonical_plan, variant, intent.role,
                           rng=rng, aug_debug=args.aug_debug)
            train_rows.append(row)
            by_slice[intent.slice] = by_slice.get(intent.slice, 0) + 1
            by_variant[variant.id] = by_variant.get(variant.id, 0) + 1
            by_role[intent.role] = by_role.get(intent.role, 0) + 1

        elapsed = time.time() - started
        if (i + 1) % 10 == 0:
            print(f"  [{i + 1}/{len(intents)}] +{n_phrasings} phrasings, total {len(train_rows)}, {elapsed:.0f}s")

    # Eval rows: each intent rendered with EVERY variant (no augmentation —
    # keeps eval clean for measuring canonical accuracy per namespace).
    eval_rows = []
    for intent in EVAL_INTENTS:
        for variant in VARIANTS:
            row = make_row(intent.seed_query, intent.canonical_plan, variant, intent.role)
            eval_rows.append(row)

    # Write
    out_train = HERE / args.out_train
    out_eval = HERE / args.out_eval
    if args.pilot:
        out_train = HERE / "pilot.jsonl"
        out_eval = HERE / "pilot_eval.jsonl"
    write_jsonl(out_train, train_rows)
    write_jsonl(out_eval, eval_rows)

    print(f"\nTrain: {len(train_rows)} rows → {out_train}")
    print(f"Eval:  {len(eval_rows)} rows → {out_eval}")
    print(f"\nBy slice:   {dict(sorted(by_slice.items()))}")
    print(f"By variant: {dict(sorted(by_variant.items()))}")
    print(f"By role:    {dict(sorted(by_role.items()))}")
    print(f"\nDone in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
