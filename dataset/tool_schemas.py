"""Final tool schemas — the contract the fine-tuned model is trained against.

Mirrors core/tools/*.py registered tools at the time of dataset generation.
Schema augmentation (in generator.py) renames TOOL/FIELD names across 5 variants;
VALUES (Диваны, Бежевый, дерево, all, set, discount, week, ...) stay stable —
they are catalog truth, not API surface.

If these change after fine-tune, the model breaks. Keep this file as the
source of truth for what the model expects.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Catalog enums (current Nova Furnish catalog)
# ---------------------------------------------------------------------------

CATEGORIES = ["Диваны", "Кресла", "Столы", "Стулья", "Шкафы", "Кровати"]

COLORS = [
    "Бежевый", "Белый", "Венге", "Жёлтый", "Зелёный", "Изумрудный",
    "Коричневый", "Красный", "Орех", "Прозрачный", "Розовый",
    "Серый", "Синий", "Чёрный",
]

MATERIALS = ["дерево", "металл", "стекло", "ткань", "кожа", "пластик"]

PRICE_LEVELS = ["budget", "mid", "premium"]

QUANTIFIERS = ["all", "first_n", "last_n", "remaining", "specific"]


# ---------------------------------------------------------------------------
# Admin enums (new in this iteration)
# ---------------------------------------------------------------------------

OPERATIONS_STOCK = ["set", "add", "subtract"]
OPERATIONS_PRICE = ["discount", "markup", "set_price"]
PERIODS          = ["today", "week", "month", "quarter", "year", "custom"]
GROUP_BY_FIELDS  = ["product", "category", "color", "material", "price_level", "day"]
METRICS          = ["revenue", "units_sold", "orders_count", "avg_check"]
SORT_DIRS        = ["desc", "asc"]


# ---------------------------------------------------------------------------
# Tool inventory — names + JSON schemas as the model sees them (canonical)
# ---------------------------------------------------------------------------

# User tools — exposed in user-role chat
USER_TOOL_NAMES = [
    "apply_filters",
    "add_to_favorites",
    "remove_from_favorites",
    "clear_favorites",
    "add_to_cart",
    "remove_from_cart",
    "clear_cart",
]

# Admin tools — exposed in admin-role chat (added by backend in next iteration)
ADMIN_TOOL_NAMES = [
    "update_stock",
    "update_prices",
    "get_sales_analytics",
]

# Backward-compat alias (existing imports from validator.py)
TOOL_NAMES = USER_TOOL_NAMES

ALL_TOOL_NAMES = USER_TOOL_NAMES + ADMIN_TOOL_NAMES


# Allowed keys inside the admin filter sub-object — used by validator.py to
# whitelist arg keys in update_stock/update_prices/get_sales_analytics.filter.
_ADMIN_FILTER_KEYS = {
    "category", "material", "color", "price_level",
    "min_price", "max_price", "search", "in_stock",
    "product_name", "product_ids",
}
