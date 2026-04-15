from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models import ChatMessage, User
from app.schemas import ChatMessageCreate, ChatMessageResponse, ChatResponse, ChatHistoryResponse
from app.api.deps import get_current_user
from app.adapters.core_adapter import process_message

router = APIRouter()


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

    # Get chat history
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    )
    history = []
    for msg in reversed(history_result.scalars().all()):
        content = msg.content
        # Truncate long tool results to save context window
        if msg.role == "tool" and len(content) > 500:
            content = content[:500] + "..."
        history.append({"role": msg.role, "content": content})

    # Determine user role (check for is_admin field or default to "user")
    role = "admin" if getattr(current_user, "is_admin", False) else "user"

    try:
        # Process through core pipeline
        result = await process_message(
            text=message_data.content,
            user_id=current_user.id,
            role=role,
            history=history,
            db=db,
        )

        assistant_content = result.response
        # Collect all actions from tool results
        actions = [
            tr.result for tr in result.tool_results
            if "action" in tr.result
        ]
        action = actions[-1] if actions else result.action

    except Exception as e:
        import traceback
        traceback.print_exc()
        assistant_content = f"Извините, AI-ассистент временно недоступен. Ошибка: {repr(e)}"
        action = None
        result = None

    # Save tool results as a "tool" message so LLM sees them in history
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
