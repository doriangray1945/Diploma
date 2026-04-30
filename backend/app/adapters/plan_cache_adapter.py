"""DB-bound adapter implementing PlanCachePort by delegating to plan_cache service.

Constructed per-request in core_adapter.process_message with the live
AsyncSession; passed into Pipeline so the pipeline can call lookup/store
without knowing about DB details.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import plan_cache


class PlanCacheAdapter:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def lookup(
        self,
        user_id: int,
        text: str,
        tools_signature: str,
        categories: list[str] | None = None,
    ) -> tuple[int, str, dict[str, Any], float] | None:
        result = await plan_cache.lookup(
            self.db, user_id, text, tools_signature, categories
        )
        if result is None:
            return None
        entry, similarity = result
        return entry.id, entry.query_text, entry.plan_json, similarity

    async def store(
        self,
        user_id: int,
        text: str,
        plan_json: dict[str, Any],
        tools_signature: str,
        categories: list[str] | None = None,
    ) -> int | None:
        return await plan_cache.store(
            self.db, user_id, text, plan_json, tools_signature, categories
        )

    async def record_hit(self, entry_id: int) -> None:
        await plan_cache.record_hit(self.db, entry_id)

    async def record_negative(self, entry_id: int) -> None:
        await plan_cache.record_negative(self.db, entry_id)
