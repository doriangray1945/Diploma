import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models import ChatMessage, User
from app.schemas import ChatMessageCreate, ChatMessageResponse, ChatResponse, ChatHistoryResponse
from app.api.deps import get_current_user
from app.services import ollama_service, TOOLS, execute_tool

router = APIRouter()


@router.post("/message", response_model=ChatResponse)
async def send_message(
    message_data: ChatMessageCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    # Save user message
    user_message = ChatMessage(
        user_id=current_user.id,
        role="user",
        content=message_data.content
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    # Get chat history
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )
    history = list(reversed(history_result.scalars().all()))

    # Build messages for Ollama
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in history
    ]

    try:
        # First call to Ollama with tools
        response = await ollama_service.chat(messages, tools=TOOLS)

        assistant_content = ""
        action = None

        if "message" in response:
            msg = response["message"]
            assistant_content = msg.get("content", "")

            # Check if tool calls were made
            if "tool_calls" in msg and msg["tool_calls"]:
                tool_results = []

                for tool_call in msg["tool_calls"]:
                    func = tool_call.get("function", {})
                    tool_name = func.get("name")
                    arguments = func.get("arguments", {})

                    if isinstance(arguments, str):
                        arguments = json.loads(arguments)

                    # Execute tool
                    result = await execute_tool(tool_name, arguments, db, current_user)
                    tool_results.append(result)

                    # If there's an action, store it
                    if "action" in result:
                        action = result

                # Add tool results to messages and get final response
                messages.append({"role": "assistant", "content": assistant_content, "tool_calls": msg["tool_calls"]})

                for i, tool_call in enumerate(msg["tool_calls"]):
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(tool_results[i], ensure_ascii=False)
                    })

                # Get final response after tool execution
                final_response = await ollama_service.chat(messages)
                if "message" in final_response:
                    assistant_content = final_response["message"].get("content", assistant_content)

        if not assistant_content:
            assistant_content = "Извините, произошла ошибка. Попробуйте ещё раз."

        # Save assistant message
        assistant_message = ChatMessage(
            user_id=current_user.id,
            role="assistant",
            content=assistant_content
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        return ChatResponse(
            message=ChatMessageResponse(
                id=assistant_message.id,
                role=assistant_message.role,
                content=assistant_message.content,
                created_at=assistant_message.created_at
            ),
            action=action
        )

    except Exception as e:
        # Fallback response if Ollama is not available
        error_content = f"Извините, AI-ассистент временно недоступен. Ошибка: {str(e)}"

        assistant_message = ChatMessage(
            user_id=current_user.id,
            role="assistant",
            content=error_content
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        return ChatResponse(
            message=ChatMessageResponse(
                id=assistant_message.id,
                role=assistant_message.role,
                content=assistant_message.content,
                created_at=assistant_message.created_at
            ),
            action=None
        )


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
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
                created_at=msg.created_at
            )
            for msg in messages
        ]
    )


@router.delete("/history")
async def clear_chat_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.user_id == current_user.id)
    )
    messages = result.scalars().all()

    for msg in messages:
        await db.delete(msg)

    await db.commit()

    return {"message": "Chat history cleared"}
