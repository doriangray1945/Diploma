from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.product import ProductResponse


class CartItemBase(BaseModel):
    variant_id: int
    quantity: int = Field(default=1, ge=1)


class CartItemCreate(CartItemBase):
    pass


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemResponse(BaseModel):
    id: int
    variant_id: int
    product_id: int
    quantity: int
    product: ProductResponse
    selected_color: str | None = None
    selected_size: str | None = None
    selected_price: float = 0.0
    selected_images: list[str] = []
    selected_stock: int = 0
    # True when backend clamped quantity to current variant stock (e.g. admin
    # decremented stock after item was added). UI shows a banner and the user
    # can re-checkout with the corrected number — no DB write happened.
    adjusted: bool = False
    # True when the variant is fully sold out (stock_quantity == 0). UI
    # renders the row greyed-out and disables checkout until item is removed.
    out_of_stock: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    total: float
    items_count: int
