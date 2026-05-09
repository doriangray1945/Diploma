"""Semantic plan cache — confidence-based plan retrieval via pgvector.

Each successfully executed plan is stored with the embedding of the user's
query. On a new query we cosine-similarity-search and the *caller* (pipeline)
routes by similarity tier:

    sim ≥ 0.95  → trust cached plan, skip skeleton LLM call entirely
    0.85-0.95   → run skeleton with cached plan as a few-shot example
    sim < 0.85  → full skeleton, no cache help

This module is pure DB I/O — threshold/guard logic lives in the pipeline.

Cache is GLOBAL — `lookup` does not filter by user_id. See model docstring.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan_cache import PlanCacheEntry
from app.services.embeddings import embed
from app.llm.parsing import normalize_for_embedding


log = logging.getLogger(__name__)


# After this many «не то / отмени» signals, an entry is considered toxic
# and removed entirely. Three tolerates one accidental negative without
# killing a useful entry, but reacts fast to a genuinely bad cache hit.
NEGATIVE_DELETE_THRESHOLD = 3


async def lookup(
    db: AsyncSession,
    user_id: int,
    text: str,
    tools_signature: str,
    categories: list[str] | None = None,
) -> tuple[PlanCacheEntry, float] | None:
    """Return the most-similar cached entry (entry, similarity) or None.

    `text` is normalized via parsing.normalize_for_embedding before
    embedding — strips numbers/categories/qualifiers so queries that
    differ only in those values share an embedding (e.g. «диваны до 70k»
    and «диваны до 90k» both embed as «до»). RAW text is kept in DB for
    debug; only the embedding sees normalized text.

    Cache is GLOBAL — no user_id filter.
    """
    norm = normalize_for_embedding(text, categories or [])
    emb = await embed(norm)
    if emb is None:
        return None

    distance_col = PlanCacheEntry.query_embedding.cosine_distance(emb)
    stmt = (
        select(PlanCacheEntry, distance_col.label("dist"))
        .where(
            PlanCacheEntry.tools_signature == tools_signature,
            PlanCacheEntry.negative_signals < NEGATIVE_DELETE_THRESHOLD,
        )
        .order_by(distance_col)
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    entry, dist = row
    return entry, 1.0 - float(dist)


async def store(
    db: AsyncSession,
    user_id: int,
    text: str,
    plan_json: dict[str, Any],
    tools_signature: str,
    categories: list[str] | None = None,
) -> int | None:
    """Store entry. Embedding uses normalized text (same rule as lookup)
    so future similar queries match. `query_text` field keeps raw text
    for audit/debug visibility."""
    norm = normalize_for_embedding(text, categories or [])
    emb = await embed(norm)
    if emb is None:
        return None
    entry = PlanCacheEntry(
        user_id=user_id,
        query_text=text,
        query_embedding=emb,
        plan_json=plan_json,
        tools_signature=tools_signature,
        hit_count=0,
        negative_signals=0,
    )
    db.add(entry)
    await db.flush()
    return entry.id


async def record_hit(db: AsyncSession, entry_id: int) -> None:
    await db.execute(
        update(PlanCacheEntry)
        .where(PlanCacheEntry.id == entry_id)
        .values(
            hit_count=PlanCacheEntry.hit_count + 1,
            last_used_at=datetime.utcnow(),
        )
    )


async def record_negative(db: AsyncSession, entry_id: int) -> None:
    """Increment negative_signals; at threshold, delete the entry entirely."""
    entry = await db.get(PlanCacheEntry, entry_id)
    if entry is None:
        return
    entry.negative_signals += 1
    if entry.negative_signals >= NEGATIVE_DELETE_THRESHOLD:
        await db.execute(
            delete(PlanCacheEntry).where(PlanCacheEntry.id == entry_id)
        )
        log.info(
            "[CACHE] evicted entry_id=%d after %d negative signals",
            entry_id, entry.negative_signals,
        )
