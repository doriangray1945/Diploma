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
    # When true, the user has explicitly accepted clamping `insufficient`
    # items down to current stock (e.g. requested 2, only 1 available).
    # Sold-out items still block the checkout — must be removed by the user.
    accept_clamping: bool = False


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
