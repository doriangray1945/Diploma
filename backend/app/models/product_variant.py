"""Per-SKU variants of a product (color × size_label).

Each row is one buyable SKU: own price, stock, image set. Frontend lets
the user pick a variant on the product page; cart and favorites store
variant_id (not product_id), so adding "grey 3-seater" doesn't conflict
with stock for "beige 2-seater" of the same model.

Sizes are free-form text (`size_label`) — encodes category-specific
concepts ("3-местный с механизмом", "180×200", "2-дверный 100см")
without an extra schema dimension.
"""
from datetime import datetime

from sqlalchemy import String, Integer, Numeric, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )

    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    size_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Real cm: {"width": 220, "depth": 95, "height": 80}. Optional — variant
    # may inherit Product.dimensions or carry a size-specific override.
    dimensions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    price: Mapped[float] = mapped_column(Numeric(10, 2))
    old_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)

    images: Mapped[list] = mapped_column(JSON, default=list)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Exactly one default per product. Frontend uses this when the user
    # hasn't picked a variant yet (catalog cards, default product page state).
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    product = relationship("Product", back_populates="variants", foreign_keys=[product_id])
    # passive_deletes=True: when a variant is deleted, let Postgres CASCADE
    # remove cart_items/favorites rows. Without this, SQLAlchemy ORM tries
    # to NULL out variant_id on related rows first → NotNullViolationError
    # because variant_id is NOT NULL.
    cart_items = relationship("CartItem", back_populates="variant", passive_deletes=True)
    favorites = relationship("Favorite", back_populates="variant", passive_deletes=True)
