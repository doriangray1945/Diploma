import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models import ChatMessage, User
from app.schemas import ChatMessageCreate, ChatMessageResponse, ChatResponse, ChatHistoryResponse
from app.api.deps import get_current_user
from app.adapters.core_adapter import process_message
from app.services.session_service import (
    get_or_create_session,
    db_session_to_context,
    merge_ui_state,
    apply_context_updates,
)
from core.parsing import is_negative_feedback


log = logging.getLogger(__name__)

router = APIRouter()

# Max user+assistant messages to pass as LLM context (tool role excluded)
HISTORY_LIMIT = 4


@router.post("/message", response_model=ChatResponse)
async def send_message(
    message_data: ChatMessageCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    # Save user message
    user_message = ChatMessage(
        user_id=current_user.id,
        role="user",
        content=message_data.content,
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    # Upsert ChatSession + merge frontend UI state + build SessionContext
    chat_session = await get_or_create_session(current_user.id, db)
    if message_data.ui_state:
        merge_ui_state(chat_session, message_data.ui_state.model_dump(exclude_none=True))

    # Negative feedback («не то» / «отмени» / «неправильно») is a complaint
    # about the previous turn — NOT an actionable intent. Two things happen:
    #   1. If we applied a cached plan last turn, downvote that entry
    #      (after 3 negatives plan_cache.record_negative deletes it).
    #   2. Short-circuit the pipeline entirely. Otherwise the LLM tries to
    #      "execute" the complaint — we observed it generating add_to_cart.
    if is_negative_feedback(message_data.content):
        if chat_session.last_cache_hit_id:
            from app.services import plan_cache
            log.info(
                "[CACHE] negative_feedback user=%d entry=%d",
                current_user.id, chat_session.last_cache_hit_id,
            )
            await plan_cache.record_negative(db, chat_session.last_cache_hit_id)
            chat_session.last_cache_hit_id = None
        clarification = (
            "Понял, что предыдущее не подошло. Что бы вы хотели вместо этого?"
        )
        assistant_msg = ChatMessage(
            user_id=current_user.id, role="assistant", content=clarification,
        )
        db.add(assistant_msg)
        await db.commit()
        await db.refresh(assistant_msg)
        return ChatResponse(
            message=ChatMessageResponse(
                id=assistant_msg.id,
                role=assistant_msg.role,
                content=assistant_msg.content,
                created_at=assistant_msg.created_at,
            ),
            action=None,
            actions=[],
        )

    session_context = db_session_to_context(chat_session)

    # Get chat history: only user+assistant (no tool), last N
    history_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.role.in_(["user", "assistant"]),
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(HISTORY_LIMIT)
    )
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in reversed(history_result.scalars().all())
    ]

    # Determine user role
    role = "admin" if getattr(current_user, "is_admin", False) else "user"

    try:
        result, updated_context = await process_message(
            text=message_data.content,
            user_id=current_user.id,
            role=role,
            history=history,
            session_context=session_context,
            db=db,
        )

        assistant_content = result.response

        # Collect all actions from tool results
        actions = [
            tr.result for tr in result.tool_results
            if isinstance(tr.result, dict) and "action" in tr.result
        ]
        action = actions[-1] if actions else result.action

        # Persist updated session context back to DB
        apply_context_updates(chat_session, updated_context)

    except Exception as e:
        import traceback
        traceback.print_exc()
        assistant_content = f"Извините, AI-ассистент временно недоступен. Ошибка: {repr(e)}"
        action = None
        actions = []
        result = None

    # Save tool results as a "tool" message for audit trail
    if result and result.tool_results:
        import json
        tool_data = json.dumps(
            [{"tool": tr.tool_name, "result": tr.result} for tr in result.tool_results],
            ensure_ascii=False,
        )
        tool_message = ChatMessage(
            user_id=current_user.id,
            role="tool",
            content=tool_data,
        )
        db.add(tool_message)

    # Save assistant message
    assistant_message = ChatMessage(
        user_id=current_user.id,
        role="assistant",
        content=assistant_content,
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)

    return ChatResponse(
        message=ChatMessageResponse(
            id=assistant_message.id,
            role=assistant_message.role,
            content=assistant_message.content,
            created_at=assistant_message.created_at,
        ),
        action=action,
        actions=actions,
    )


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(100)
    )
    messages = result.scalars().all()

    return ChatHistoryResponse(
        messages=[
            ChatMessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at,
            )
            for msg in messages
            if msg.role != "tool"  # Don't show tool results in UI
        ]
    )


@router.delete("/history")
async def clear_chat_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.user_id == current_user.id)
    )
    messages = result.scalars().all()

    for msg in messages:
        await db.delete(msg)

    await db.commit()
    return {"message": "Chat history cleared"}
