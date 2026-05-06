"""Deterministic Russian-language pre-parser.

Runs once per user message before the LLM call. Extracts prices, quantity,
quantifiers ("все"/"остальные"/"первые N") and category. Result is used to:
  1. Render hint-line into the planner prompt
  2. Trigger stale-context reset (new category or price)
  3. Post-merge over LLM args (regex is more accurate on numbers)

No external dependencies — DIMINUTIVES table covers diminutive forms by
prefix-match (no pymorphy2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pymorphy3


@dataclass
class ParseHints:
    max_price: float | None = None
    min_price: float | None = None
    quantity: int | None = None
    quantifier: str | None = None       # "all" | "remaining" | "first_N" | "last_N"
    quantifier_n: int | None = None
    category: str | None = None         # canonical from filter_options.categories
    triggers_reset: bool = False
    # NOTE: `search` is no longer a parser concern. It used to be filled from
    # a hardcoded list of stylistic qualifiers (SEARCH_QUALIFIERS) which
    # silently dropped any unknown adjective. Now `search` is a free-form
    # string filled by the LLM args-filler from the user's full text, then
    # matched semantically by pgvector cosine_distance against the product
    # embedding (which encodes name + description + materials + color).


# ── Morphological gating layer (POS-only) ─────────────────────────────
#
# Tier 2 of the neuro-symbolic cascade: after the deterministic regex/dict
# parser has extracted what it can (categories, prices, qty), the args
# filler asks `is_descriptor_candidate` whether a residual token is an
# open-class content word — i.e. plausibly a product descriptor worth
# feeding to the LLM. Closed-class function vocabulary (verbs, prepositions,
# pronouns, particles, conjunctions, interjections) is filtered out by
# pymorphy3 morphology, no hardcoded list.
#
# Per-step decomposition (see Decomposer + PlanExecutor) ensures each
# args-filler call only sees its own sub-action text — that's what keeps
# the LLM agent fully agnostic to catalog content. The gate just decides
# whether the LLM has anything to extract; it does not validate against
# what the catalog contains.

_MORPH = pymorphy3.MorphAnalyzer()
_OPEN_CLASS_POS = frozenset({"NOUN", "ADJF", "ADJS", "PRTF", "PRTS"})


def is_descriptor_candidate(token: str) -> bool:
    """True if `token` is an open-class content word (NOUN, ADJF, ADJS,
    PRTF, PRTS) per pymorphy3. Pure linguistic check — no coupling to
    the catalog. Typos are handled by pymorphy3's suffix-based OOV
    prediction («посаветуй» → still VERB → False).
    """
    if not token or len(token) < 2:
        return False
    parses = _MORPH.parse(token.lower())
    if not parses:
        return False
    return parses[0].tag.POS in _OPEN_CLASS_POS


# Russian diminutive/inflection prefixes per canonical category.
# Match: a token whose lowercase form starts with one of these stems
# (stem must be ≥ 5 chars to avoid false positives on short words).
DIMINUTIVES: dict[str, list[str]] = {
    "Кресла":  ["кресл", "креслиц"],
    "Диваны":  ["диван", "диванчик"],
    "Столы":   ["стол", "столик"],
    "Стулья":  ["стул", "стульчик"],
    "Шкафы":   ["шкаф", "шкафчик"],
    "Кровати": ["кроват", "кроватк"],
}


# Price patterns. Order matters — ranges with explicit "не <X>" must be tried
# BEFORE bare directional words, otherwise "не дороже" gets eaten by "дороже"
# in the min-class. Each match is masked from the input before next pattern runs.
#
# Group 1 = number; Group 2 = optional multiplier suffix (тыс/т/к/k → ×1000).
# We can't use \b between the number and a Cyrillic suffix in Python 3 because
# digits and Cyrillic letters are both \w-class — no boundary between them.
_NUM = r"(\d[\d\s]*)"
# `(?!\w)` after the suffix prevents matching a single Cyrillic letter that
# is actually the start of another word: "до 50000 ко мне" must NOT eat
# "к" of "ко" as a ×1000 multiplier.
_MULT = r"(?:\s*(тыс|т|к|k|руб|р|₽)(?!\w))?"

_PRICE_PATTERNS: list[tuple[str, str]] = [
    (rf"\bдо\s+{_NUM}{_MULT}",                                "max"),
    (rf"\bне\s+(?:более|больше|дороже)\s+{_NUM}{_MULT}",      "max"),
    (rf"\bв\s+пределах\s+{_NUM}{_MULT}",                      "max"),
    (rf"\bне\s+(?:менее|меньше|дешевле)\s+{_NUM}{_MULT}",     "min"),
    (rf"\bот\s+{_NUM}{_MULT}",                                "min"),
    (rf"\b(?:более|больше|дороже)\s+{_NUM}{_MULT}",           "min"),
    (rf"\b(?:менее|меньше|дешевле)\s+{_NUM}{_MULT}",          "max"),
]


_QTY_PATTERNS = [
    rf"\bпо\s+(\d+)\s*шт",
    rf"\b(\d+)\s*(?:штук[аи]?|шт\.?)\s+каждого\b",
]


# (regex, quantifier_name, group_idx_for_n_or_None)
_QUANTIFIER_PATTERNS: list[tuple[str, str, int | None]] = [
    (r"\b(остальн\w+|оставш\w+|других|прочих)\b", "remaining", None),
    (r"\bпервы[ехй]\s+(\d+)\b",                   "first_N",   1),
    (r"\bпоследни[ехй]\s+(\d+)\b",                "last_N",    1),
    (r"\b(все|всё)\b",                            "all",       None),
]


_THOUSANDS = {"тыс", "т", "к", "k"}


def _to_int(num_str: str, mult: str | None) -> int:
    cleaned = re.sub(r"\s+", "", num_str)
    n = int(cleaned)
    if mult and mult.lower() in _THOUSANDS:
        n *= 1000
    return n


def _extract_prices(text: str) -> tuple[int | None, int | None]:
    """Walk price patterns in priority order, masking matched spans."""
    max_p: int | None = None
    min_p: int | None = None
    work = text
    for pattern, kind in _PRICE_PATTERNS:
        m = re.search(pattern, work, re.IGNORECASE)
        if not m:
            continue
        num = _to_int(m.group(1), m.group(2))
        if kind == "max" and max_p is None:
            max_p = num
        elif kind == "min" and min_p is None:
            min_p = num
        # Mask this span so subsequent patterns don't re-match the same words
        start, end = m.span()
        work = work[:start] + (" " * (end - start)) + work[end:]
    return min_p, max_p


def _extract_quantity(text: str) -> int | None:
    for pattern in _QTY_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except (ValueError, IndexError):
                continue
    return None


def _extract_quantifier(text: str) -> tuple[str | None, int | None]:
    for pattern, name, n_group in _QUANTIFIER_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            n = None
            if n_group is not None:
                try:
                    n = int(m.group(n_group))
                except (ValueError, IndexError):
                    n = None
            return name, n
    return None, None


def normalize_category(text: str, categories: list[str]) -> str | None:
    """Find a canonical category by matching tokens against DIMINUTIVES stems.

    Tokenize on \\W+, lowercase. For each token, check if it starts with any
    stem of length ≥ 5. First match wins.

    Falls back to substring match against the canonical name (case-insensitive).
    """
    if not text or not categories:
        return None

    tokens = [t.lower() for t in re.split(r"\W+", text) if t]

    # Pass 1: DIMINUTIVES stems (preferred — handles "диванчики", "креслица")
    for token in tokens:
        for canonical, stems in DIMINUTIVES.items():
            if canonical not in categories:
                continue
            for stem in stems:
                if len(stem) >= 5 and token.startswith(stem):
                    return canonical

    # Pass 2: direct canonical containment ("диваны" matches "Диваны")
    text_lower = text.lower()
    for canonical in categories:
        if canonical.lower() in text_lower:
            return canonical

    return None


# Substrings that mark a user message as a complaint about the previous
# assistant turn, NOT an actionable intent. Used by chat.py to short-circuit
# the pipeline (avoid the LLM re-interpreting "не то" as a fresh action,
# which we observed: bot kept adding to cart while user was complaining).
# Stems chosen to match Russian inflections («не та», «отмени», «отменить»).
_NEGATIVE_FEEDBACK_PATTERNS = (
    "не то", "не это", "не так", "не такие", "не такой", "не такая",
    "неправильн", "не подход", "не устраив",
    "отмен",          # отмени, отменить, отменяй
    "ошиб",           # ошибка, ошибся
    "не хотел", "не хочу",
)


def normalize_for_embedding(text: str, categories: list[str] | None = None) -> str:
    """Strip values that should NOT influence semantic plan retrieval.

    The plan cache asks: «have we seen a query with the same INTENT before?»
    Intent is encoded by action verbs (найди / положи / удали), target words
    (корзина / избранное), and grammar of the request. Specific values —
    numbers, category names — go through the parser into args, NOT into the
    cache key, so we strip them from the embedded text.

    Without normalization, «найди диваны до 70000» and «найди диваны до
    90000» get distinct embeddings and miss the trust threshold, even
    though they want the same plan. After normalization both become «найди
    до» → identical embedding → cache hit.

    Stylistic qualifiers («уютные», «детские», «лофт») are NOT stripped —
    they signal genuinely different user intents («покажи уютные диваны»
    and «покажи детские диваны» should NOT collide in cache, even after
    semantic search swallows them downstream).

    Note: category match guard (`Pipeline._categories_match`) and intent
    match guard (`Pipeline._intent_match`) still run on the RAW texts, so
    aliasing risk doesn't grow.
    """
    if not text:
        return ""
    n = text.lower()
    # Strip digit sequences (prices, quantities, sizes — handled by parser)
    n = re.sub(r"\d+", " ", n)
    # Strip canonical category names and their diminutive inflections
    if categories:
        for cat in categories:
            n = re.sub(rf"\b{re.escape(cat.lower())}\w*\b", " ", n)
    for stems in DIMINUTIVES.values():
        for stem in stems:
            if len(stem) >= 5:
                n = re.sub(rf"\b{re.escape(stem)}\w*\b", " ", n)
    # Collapse whitespace
    n = re.sub(r"\s+", " ", n).strip()
    return n


def is_negative_feedback(text: str) -> bool:
    """True if `text` looks like a complaint about the previous turn."""
    if not text:
        return False
    low = text.lower()
    return any(pat in low for pat in _NEGATIVE_FEEDBACK_PATTERNS)


def parse_user_text(text: str, categories: list[str]) -> ParseHints:
    """Single-pass deterministic parse of a user message."""
    if not text:
        return ParseHints()

    min_p, max_p = _extract_prices(text)
    qty = _extract_quantity(text)
    quant, n = _extract_quantifier(text)
    cat = normalize_category(text, categories)

    triggers_reset = bool(cat) or (max_p is not None) or (min_p is not None)

    return ParseHints(
        max_price=max_p,
        min_price=min_p,
        quantity=qty,
        quantifier=quant,
        quantifier_n=n,
        category=cat,
        triggers_reset=triggers_reset,
    )


def apply_quantifier(
    hints: ParseHints,
    visible_ids: list[int],
    consumed_ids: set[int] | None = None,
) -> list[int] | None:
    """Resolve quantifier hint to a concrete list of product_ids.

    Returns None if no quantifier hint or no visible_ids.
    "all"       → all visible (no consumed filter — explicit select-all)
    "remaining" → visible minus consumed
    "first_N"   → first N from (visible minus consumed)
    "last_N"    → last N from (visible minus consumed)
    """
    if not hints.quantifier or not visible_ids:
        return None
    consumed = consumed_ids or set()

    if hints.quantifier == "all":
        return list(visible_ids)
    if hints.quantifier == "remaining":
        return [pid for pid in visible_ids if pid not in consumed]

    available = [pid for pid in visible_ids if pid not in consumed]
    n = hints.quantifier_n or 1
    if hints.quantifier == "first_N":
        return available[:n]
    if hints.quantifier == "last_N":
        return available[-n:] if available else []

    return None
