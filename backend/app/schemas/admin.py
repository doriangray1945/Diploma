from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class StatsOverview(BaseModel):
    revenue: float
    orders_count: int
    aov: float
    new_users: int
    period_start: datetime
    period_end: datetime


class RevenuePoint(BaseModel):
    date: str
    revenue: float


class TopProduct(BaseModel):
    product_id: int
    name: str
    category: str
    units: int
    revenue: float


class CategoryBreakdown(BaseModel):
    category: str
    revenue: float
    units: int


class LowStockProduct(BaseModel):
    id: int
    name: str
    category: str
    stock_quantity: int
    in_stock: bool


class InventorySummary(BaseModel):
    total_products: int
    in_stock: int
    out_of_stock: int
    low_stock_count: int


# ---------------------------------------------------------------------------
# Bulk admin operations (for chat tools)
# ---------------------------------------------------------------------------

class AdminFilter(BaseModel):
    """Filter for bulk admin operations and analytics queries.
    At least one field must be set (minProperties: 1) — empty filter
    would target the entire catalog, which is dangerous."""
    category: str | None = None
    color: list[str] | None = None
    material: list[str] | None = None
    price_level: Literal["budget", "mid", "premium"] | None = None
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    search: str | None = Field(default=None, max_length=200)
    in_stock: bool | None = None
    product_name: str | None = Field(default=None, max_length=200)
    product_ids: list[int] | None = None

    @model_validator(mode="after")
    def at_least_one(self):
        if not any(v is not None for v in self.model_dump().values()):
            raise ValueError("AdminFilter must specify at least one criterion")
        if self.price_level and (self.min_price is not None or self.max_price is not None):
            raise ValueError("price_level cannot be combined with min_price/max_price")
        return self


class BulkStockUpdate(BaseModel):
    filter: AdminFilter
    operation: Literal["set", "add", "subtract"]
    quantity: int = Field(ge=0, le=100000)


class BulkPriceUpdate(BaseModel):
    filter: AdminFilter
    operation: Literal["discount", "markup", "set_price"]
    value: int = Field(ge=1, le=10_000_000)

    @model_validator(mode="after")
    def percent_range(self):
        if self.operation in ("discount", "markup") and self.value > 100:
            raise ValueError(f"{self.operation} percent must be ≤ 100, got {self.value}")
        return self


class BulkUpdateResult(BaseModel):
    affected_count: int
    operation: str
    revenue_impact: float | None = None  # only for price updates


class AnalyticsQuery(BaseModel):
    """Flexible analytics query — single endpoint replaces overview/top-products/etc."""
    period: Literal["today", "week", "month", "quarter", "year", "custom"]
    from_date: date | None = None
    to_date: date | None = None
    group_by: Literal["product", "category", "color", "material", "price_level", "day"]
    metric: Literal["revenue", "units_sold", "orders_count", "avg_check"]
    sort: Literal["desc", "asc"] = "desc"
    limit: int = Field(default=10, ge=1, le=1000)
    filter: AdminFilter | None = None

    @model_validator(mode="after")
    def custom_period_dates(self):
        if self.period == "custom":
            if self.from_date is None or self.to_date is None:
                raise ValueError("period=custom requires both from_date and to_date")
        else:
            if self.from_date is not None or self.to_date is not None:
                raise ValueError(f"from_date/to_date only valid with period=custom")
        return self


class AnalyticsBucket(BaseModel):
    """Single row of analytics result. `key` depends on group_by:
    product → product name; category → category name; day → ISO date."""
    key: str
    value: float
    units: int | None = None  # secondary metric for context
