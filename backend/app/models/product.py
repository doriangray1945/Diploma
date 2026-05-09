from datetime import datetime
from sqlalchemy import String, Text, Integer, Numeric, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text)

    category: Mapped[str] = mapped_column(String(100), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)

    materials: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Default cm dimensions for the model — variants may override per size.
    dimensions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    rating: Mapped[float] = mapped_column(Numeric(2, 1), default=0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)

    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)

    # 3D-model URLs for AR / 3D-viewer on product page. Stays at product-level
    # (geometry doesn't change between color variants of the same model).
    model_glb_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_usdz_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    embedding = mapped_column(Vector(1024), nullable=True)

    # Which variant to show by default in catalog listings + initial state of
    # product page. Nullable so the FK can be created before variants exist;
    # seed pipeline sets this after inserting variants.
    default_variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    variants = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
        foreign_keys="ProductVariant.product_id",
    )
    # passive_deletes=True: order_items.product_id has ON DELETE SET NULL,
    # so deleting a product preserves order history with NULL product ref.
    # Without this flag, ORM would try to UPDATE the rows itself and could
    # conflict with the DB-level cascade.
    order_items = relationship("OrderItem", back_populates="product", passive_deletes=True)
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan", passive_deletes=True)
