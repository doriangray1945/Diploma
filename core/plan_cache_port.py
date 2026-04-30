"""Plan cache port — interface for the pipeline to call cache operations.

Pipeline lives in `core/`, plan_cache implementation in `backend/app/`. To
keep the dependency direction one-way (backend → core), pipeline depends on
this Protocol; backend supplies an adapter that captures the DB session.
"""
from __future__ import annotations

from typing import Any, Protocol


class PlanCachePort(Protocol):
    async def lookup(
        self,
        user_id: int,
        text: str,
        tools_signature: str,
        categories: list[str] | None = None,
    ) -> tuple[int, str, dict[str, Any], float] | None:
        """Return (entry_id, cached_query_text, cached_plan_json, similarity) or None.

        cached_query_text comes back so the pipeline can re-parse it for
        category/intent guards before trusting the plan.

        `categories` enables text normalization before embedding — same
        normalization is applied in `store`, so embeddings match
        regardless of specific numbers/categories in the raw text.
        """
        ...

    async def store(
        self,
        user_id: int,
        text: str,
        plan_json: dict[str, Any],
        tools_signature: str,
        categories: list[str] | None = None,
    ) -> int | None: ...

    async def record_hit(self, entry_id: int) -> None: ...

    async def record_negative(self, entry_id: int) -> None: ...
