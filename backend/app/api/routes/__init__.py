from fastapi import APIRouter

from app.api.routes import auth, products, cart, orders, favorites, chat, reviews
from app.api.routes.admin import admin_router

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
# Reviews live under /products/{id}/reviews — separate file but shares prefix
# so REST hierarchy stays clean (resource-nested URLs).
api_router.include_router(reviews.router, prefix="/products", tags=["reviews"])
api_router.include_router(cart.router, prefix="/cart", tags=["cart"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(favorites.router, prefix="/favorites", tags=["favorites"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(admin_router, prefix="/admin")
