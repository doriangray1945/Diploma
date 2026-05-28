"""PlanCacheEntry — semantic memory of (user query → successful plan).

A query is embedded via bge-m3 (dim=1024, multilingual). On a future
query we cosine-similarity-search this table; the *caller* (pipeline)
routes by similarity tier with additional intent/category guards.

The cache is GLOBAL: lookup does not filter by user_id. Plans are pure
tool sequences with no user-specific data (args are filled per-request),
so any user's plan for «положи в корзину» is good for any other user.
`user_id` is kept for audit ("who first taught the system this query")
but not used for retrieval. Negative-feedback signals aggregate across
users — bad plans get evicted faster than per-user silos would.

`tools_signature` (sha256 of sorted tool names) pins each entry to a
registry shape; entries with a different signature simply don't match.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class PlanCacheEntry(Base):
    __tablename__ = "plan_cache_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    query_text: Mapped[str] = mapped_column(Text)

    # 1024 = bge-m3 dim
    query_embedding = mapped_column(Vector(1024), nullable=False)

    plan_json: Mapped[dict] = mapped_column(JSON)
    tools_signature: Mapped[str] = mapped_column(String(16), index=True)

    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_signals: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
