from datetime import datetime
from pydantic import BaseModel


class OrderItemBase(BaseModel):
    product_id: int
    quantity: int


class OrderItemResponse(BaseModel):
    id: int
    product_id: int | None
    product_name: str
    quantity: int
    price: float

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    address: str
    phone: str
    comment: str | None = None


class OrderResponse(BaseModel):
    id: int
    status: str
    total: float
    address: str
    phone: str
    comment: str | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
