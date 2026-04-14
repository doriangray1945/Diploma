from datetime import datetime
from pydantic import BaseModel


class ProductBase(BaseModel):
    name: str
    description: str
    price: float
    old_price: float | None = None
    category: str
    subcategory: str | None = None
    images: list[str] = []
    dimensions: str | None = None
    materials: str | None = None
    color: str | None = None
    in_stock: bool = True
    stock_quantity: int = 0


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    old_price: float | None = None
    category: str | None = None
    subcategory: str | None = None
    images: list[str] | None = None
    dimensions: str | None = None
    materials: str | None = None
    color: str | None = None
    in_stock: bool | None = None
    stock_quantity: int | None = None


class ProductResponse(ProductBase):
    id: int
    rating: float
    reviews_count: int
    is_popular: bool
    is_new: bool
    created_at: datetime
    is_favorite: bool = False

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    per_page: int
    pages: int


class ProductFilters(BaseModel):
    category: str | None = None
    subcategory: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    color: str | None = None
    in_stock: bool | None = None
    is_popular: bool | None = None
    is_new: bool | None = None
    search: str | None = None


class CategoryResponse(BaseModel):
    name: str
    count: int
    subcategories: list[str] = []
