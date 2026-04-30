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


_MODEL = "nomic-embed-text"
_TIMEOUT = 30.0


async def embed(text: str) -> list[float] | None:
    if not text or not text.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.OLLAMA_HOST}/api/embeddings",
                json={"model": _MODEL, "prompt": text},
            )
            r.raise_for_status()
            return r.json()["embedding"]
    except Exception as e:
        log.warning("embed failed for %r: %r", text[:80], e)
        return None
