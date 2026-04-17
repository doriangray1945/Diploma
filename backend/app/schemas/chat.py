from datetime import datetime
from typing import Any

from pydantic import BaseModel


class UiState(BaseModel):
    """Frontend UI state sent with each chat message for context awareness."""
    visible_product_ids: list[int] | None = None
    current_filters: dict[str, Any] | None = None
    open_product_id: int | None = None


class ChatMessageCreate(BaseModel):
    content: str
    ui_state: UiState | None = None


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    message: ChatMessageResponse
    action: dict | None = None  # Last action (backwards compat)
    actions: list[dict] = []    # All actions from plan execution


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]
