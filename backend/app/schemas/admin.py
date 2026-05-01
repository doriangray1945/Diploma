from datetime import datetime
from pydantic import BaseModel


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
