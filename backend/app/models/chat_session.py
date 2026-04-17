from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ChatSession(Base):
    """Per-user dialogue state for the Schema Router pipeline.

    Stores last search results, visible products, current filters, etc.
    Used for resolving anaphoric references ('их', 'это') via $context.* refs.
    One row per user (upserted on every chat request).
    """

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    # Last search / filter result: {"filters": {...}, "product_ids": [...], "count": N}
    last_search: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Product IDs currently visible on the user's screen
    visible_product_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # Current catalog filters applied via UI or chat
    current_filters: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    # Product ID the user is currently viewing (detail page)
    open_product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Quick summaries to avoid extra tool calls
    cart_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    favorites_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = relationship("User", back_populates="chat_session")