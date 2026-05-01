from app.models import Product


def build_product_text(product: Product) -> str:
    """Searchable text used to compute the product embedding.

    Mirrors the format used in seed_data.build_product_text so that admin-
    created products are searchable on the same axis as seeded ones.
    """
    parts = [product.name, product.description or "", product.category or ""]
    if product.color:
        parts.append(f"цвет: {product.color}")
    if product.materials:
        parts.append(f"материалы: {product.materials}")
    return " ".join(parts)


# Fields that, when changed, require recomputing the embedding. Other fields
# (price, stock, dimensions, flags) don't affect semantic search results.
EMBEDDING_FIELDS = frozenset({"name", "description", "category", "materials", "color"})
