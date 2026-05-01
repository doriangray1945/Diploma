from fastapi import APIRouter

from app.api.routes.admin import stats, products, categories, orders, users

admin_router = APIRouter()

admin_router.include_router(stats.router, prefix="/stats", tags=["admin-stats"])
admin_router.include_router(products.router, prefix="/products", tags=["admin-products"])
admin_router.include_router(categories.router, prefix="/categories", tags=["admin-categories"])
admin_router.include_router(orders.router, prefix="/orders", tags=["admin-orders"])
admin_router.include_router(users.router, prefix="/users", tags=["admin-users"])
