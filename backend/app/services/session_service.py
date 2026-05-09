"""ChatSession CRUD: get/create, merge with frontend UI state, apply tool updates."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_session import ChatSession
from app.llm.schemas import SessionContext


async def get_or_create_session(
    user_id: int, db: AsyncSession
) -> ChatSession:
    """Fetch the user's ChatSession row, or create an empty one."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        session = ChatSession(user_id=user_id)
        db.add(session)
        await db.flush()
    return session


def db_session_to_context(session: ChatSession) -> SessionContext:
    """Convert DB row → core SessionContext pydantic model."""
    return SessionContext(
        last_search=session.last_search,
        visible_product_ids=session.visible_product_ids or [],
        current_filters=session.current_filters or {},
        open_product_id=session.open_product_id,
        cart_summary=session.cart_summary,
        favorites_summary=session.favorites_summary,
        last_cache_hit_id=session.last_cache_hit_id,
    )


def merge_ui_state(
    session: ChatSession,
    ui_state: dict[str, Any] | None,
) -> None:
    """Merge frontend UI state into DB session (frontend wins on conflicts)."""
    if not ui_state:
        return
    if "visible_product_ids" in ui_state and ui_state["visible_product_ids"] is not None:
        session.visible_product_ids = ui_state["visible_product_ids"]
    if "current_filters" in ui_state and ui_state["current_filters"] is not None:
        session.current_filters = ui_state["current_filters"]
    if "open_product_id" in ui_state and ui_state["open_product_id"] is not None:
        session.open_product_id = ui_state["open_product_id"]


def apply_context_updates(
    session: ChatSession,
    context: SessionContext,
) -> None:
    """Persist updated SessionContext (after plan execution) back to DB row."""
    session.last_search = context.last_search
    session.visible_product_ids = context.visible_product_ids or []
    session.current_filters = context.current_filters or {}
    session.open_product_id = context.open_product_id
    session.cart_summary = context.cart_summary
    session.favorites_summary = context.favorites_summary
    session.last_cache_hit_id = context.last_cache_hit_id
