"""Semantic mappings for filter values that the LLM agent emits.

The fine-tuned LLM produces *labels* (price_level="budget", material="дерево")
instead of catalog-bound numbers or composite material strings. Backend
resolves those labels via the dictionaries below. Changing thresholds or
the synonym table here does NOT require model retraining — agent and
catalog are decoupled by design.

Two reasons we keep this in config rather than in training data:
  1. Catalog-agnostic agent — model stays valid even when prices shift.
  2. Tunability — diploma demo can adjust «недорогое» without touching
     the model. Single edit, no GPU.
"""
from __future__ import annotations


# ── Price level → numeric range ───────────────────────────────────────
#
# Bands chosen for our furniture catalog (~5 000 — 200 000 ₽). Edit max
# values here to shift what the agent treats as «недорогое»/«премиум».
PRICE_LEVELS: dict[str, dict[str, float | None]] = {
    "budget":  {"min": 0,      "max": 30000},
    "mid":     {"min": 30000,  "max": 80000},
    "premium": {"min": 80000,  "max": None},
}


# ── Material taxonomy → catalog-side substrings ───────────────────────
#
# Agent picks one of the keys (a coarse-grained material class).
# Backend expands to the OR'd list of substrings to match against the
# free-text `products.materials` column via ILIKE.
#
# Add new substrings here when seeding new products with novel materials —
# no retraining needed. Keys must stay stable (the model was trained on them).
MATERIAL_GROUPS: dict[str, list[str]] = {
    "дерево":  ["дуб", "сосна", "берёза", "береза", "массив", "бук",
                "ясень", "красное дерево"],
    "металл":  ["металл", "сталь", "хром", "алюминий"],
    "стекло":  ["стекло"],
    "ткань":   ["велюр", "рогожка", "кашемир", "текстиль"],
    "кожа":    ["кожа", "экокожа"],
    "пластик": ["пластик", "дсп", "лдсп", "мдф"],
}


def resolve_price_level(level: str) -> tuple[float | None, float | None]:
    """Return (min_price, max_price) for a price level label.

    Unknown level → (None, None) — caller falls back to no price filter.
    """
    band = PRICE_LEVELS.get(level)
    if not band:
        return (None, None)
    return (band.get("min"), band.get("max"))


def resolve_material(group: str) -> list[str]:
    """Return list of catalog substrings for a material group label.

    Used by SQL ILIKE expansion: `materials ILIKE '%дуб%' OR ILIKE '%сосна%'…`
    Unknown group → empty list (caller skips material filter).
    """
    return MATERIAL_GROUPS.get(group, [])
