from datetime import datetime
from pydantic import BaseModel


class ChatMessageCreate(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    message: ChatMessageResponse
    action: dict | None = None  # Action performed by AI (e.g., filter applied, item added to cart)


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]
