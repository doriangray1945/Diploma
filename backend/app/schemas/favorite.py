from datetime import datetime
from pydantic import BaseModel

from app.schemas.product import ProductResponse


class FavoriteResponse(BaseModel):
    id: int
    variant_id: int
    product_id: int
    selected_color: str | None = None
    selected_size: str | None = None
    product: ProductResponse
    created_at: datetime

    class Config:
        from_attributes = True


class FavoriteListResponse(BaseModel):
    items: list[FavoriteResponse]
    total: int
