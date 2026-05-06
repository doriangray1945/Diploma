"""Embedding service — wraps Ollama's nomic-embed-text endpoint.

Used by:
  - PlanCacheService to embed user queries for semantic plan lookup
  - (future) seed_data.py for product embeddings — same model, dim=768

Failures return None; callers must treat that as «can't compute» and fall
back gracefully (typically: skip cache, run full pipeline).
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings


log = logging.getLogger(__name__)


# BGE-M3 — multilingual embedding model. Picked over nomic-embed-text after
# the latter produced near-identical vectors for distinct Russian
# adjectives (single-token tokenizer collisions for non-English). BGE-M3
# is dim=1024 — Product.embedding and PlanCacheEntry.query_embedding
# columns are sized accordingly.
_MODEL = "bge-m3"
_EMBED_DIM = 1024
_TIMEOUT = 60.0


async def embed(text: str) -> list[float] | None:
    """Encode `text` with nomic-embed-text via Ollama's /api/embed endpoint.

    NOTE: We use the newer /api/embed (not the legacy /api/embeddings) — in
    Ollama 0.20.7 the legacy endpoint returns the same constant vector for
    every prompt, which silently breaks all semantic comparisons.
    /api/embed accepts `input` and returns `embeddings: [[...]]`.
    """
    if not text or not text.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.OLLAMA_HOST}/api/embed",
                json={"model": _MODEL, "input": text},
            )
            r.raise_for_status()
            data = r.json()
            embeddings = data.get("embeddings") or []
            return embeddings[0] if embeddings else None
    except Exception as e:
        log.warning("embed failed for %r: %r", text[:80], e)
        return None
