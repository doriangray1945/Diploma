from datetime import datetime
from pydantic import BaseModel


class ProductVariantResponse(BaseModel):
    id: int
    product_id: int
    color: str | None = None
    size_label: str | None = None
    dimensions: dict | None = None
    price: float
    old_price: float | None = None
    stock_quantity: int = 0
    in_stock: bool = True
    images: list[str] = []
    sku: str | None = None
    is_default: bool = False
    model_glb_url: str | None = None
    model_usdz_url: str | None = None

    class Config:
        from_attributes = True


class ProductBase(BaseModel):
    name: str
    description: str
    category: str
    subcategory: str | None = None
    materials: str | None = None
    dimensions: dict | None = None


class ProductResponse(ProductBase):
    id: int
    rating: float
    reviews_count: int
    is_popular: bool
    is_new: bool
    created_at: datetime
    is_favorite: bool = False

    # Variant data: list of all variants (for selector UI) plus convenience
    # snapshot of the default variant's price/stock/images so existing
    # frontend code that reads product.price etc. keeps working.
    variants: list[ProductVariantResponse] = []
    default_variant_id: int | None = None
    # When a color filter is active, snapshot fields (price/images/color/stock)
    # represent the variant that matched the filter — not the product default.
    # `matched_variant_id` exposes that pick so the frontend can deep-link
    # `/product/{id}?variant=<matched_variant_id>` from the catalog card.
    matched_variant_id: int | None = None
    price: float = 0.0
    old_price: float | None = None
    images: list[str] = []
    color: str | None = None
    in_stock: bool = True
    stock_quantity: int = 0

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    per_page: int
    pages: int


class CategoryResponse(BaseModel):
    name: str
    count: int
    subcategories: list[str] = []
