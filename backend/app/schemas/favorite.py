from datetime import datetime
from pydantic import BaseModel

from app.schemas.product import ProductResponse


class FavoriteResponse(BaseModel):
    id: int
    product_id: int
    product: ProductResponse
    created_at: datetime

    class Config:
        from_attributes = True


class FavoriteListResponse(BaseModel):
    items: list[FavoriteResponse]
    total: int
