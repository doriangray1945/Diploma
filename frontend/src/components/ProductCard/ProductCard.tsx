import { Link } from 'react-router-dom';
import { Heart, ShoppingCart } from 'lucide-react';
import type { Product } from '../../types';
import { useAuthStore, useCartStore, useFavoritesStore } from '../../stores';
import clsx from 'clsx';

interface ProductCardProps {
  product: Product;
  // Optional: when a card represents a specific variant (favorite or cart row),
  // show the selected colour/size label under the category line.
  variantLabel?: string | null;
}

export default function ProductCard({ product, variantLabel }: ProductCardProps) {
  const { user } = useAuthStore();
  const { addToCart } = useCartStore();
  const { favorites, addToFavorites, removeFromFavorites } = useFavoritesStore();

  // Find which variant of this product is currently favorited (if any).
  // Source of truth is the favorites array — the heart removes exactly the
  // SKU the user originally added, not whichever default the product points
  // at right now.
  const favoritedVariantId =
    favorites.find((f) => f.product_id === product.id)?.variant_id ?? null;
  const isInFavorites = favoritedVariantId !== null;

  const defaultVariantId = product.default_variant_id ?? product.variants?.[0]?.id ?? null;
  // When the catalog request applied a color filter, backend snapshots the
  // matching variant into product.images/price/color and exposes its id here.
  // Deep-link to that variant so the product page opens it pre-selected.
  const linkTo = product.matched_variant_id
    ? `/product/${product.id}?variant=${product.matched_variant_id}`
    : `/product/${product.id}`;

  const handleFavoriteClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (!user) return;

    try {
      if (favoritedVariantId !== null) {
        await removeFromFavorites(favoritedVariantId);
      } else if (defaultVariantId !== null) {
        await addToFavorites(defaultVariantId);
      }
    } catch (error) {
      console.error('Failed to update favorites:', error);
    }
  };

  const handleAddToCart = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (!user || !defaultVariantId) return;

    try {
      await addToCart(defaultVariantId);
    } catch (error) {
      console.error('Failed to add to cart:', error);
    }
  };

  // Placeholder image
  const imageUrl = product.images[0] || `https://placehold.co/400x300/e2e8f0/64748b?text=${encodeURIComponent(product.name)}`;

  // Variant summary: when a color filter picked a specific variant for this
  // card, badge the actual colour (e.g. «Зелёный»). Otherwise — count of
  // distinct colours across all variants (RU: 2-4 цвета, 5+ цветов).
  const colorCount = new Set(
    (product.variants ?? []).map((v) => v.color).filter((c): c is string => !!c),
  ).size;
  const colorLabel = product.matched_variant_id && product.color
    ? product.color
    : colorCount > 1
      ? `${colorCount} ${colorCount >= 5 ? 'цветов' : 'цвета'}`
      : null;

  // Whole product is sold out when no variant has stock.
  const allSoldOut =
    product.variants && product.variants.length > 0
      ? product.variants.every((v) => !v.in_stock || v.stock_quantity === 0)
      : !product.in_stock;

  return (
    <Link
      to={linkTo}
      className="group bg-white rounded-2xl overflow-hidden shadow-sm border border-slate-200 hover:shadow-lg hover:border-slate-300 transition-all"
    >
      {/* Image */}
      <div className="relative aspect-[4/3] overflow-hidden bg-slate-100">
        <img
          src={imageUrl}
          alt={product.name}
          className={clsx(
            'w-full h-full object-cover group-hover:scale-105 transition-transform duration-300',
            allSoldOut && 'grayscale opacity-60',
          )}
          onError={(e) => {
            (e.target as HTMLImageElement).src = `https://placehold.co/400x300/e2e8f0/64748b?text=${encodeURIComponent(product.name)}`;
          }}
        />

        {allSoldOut && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className="px-3 py-1.5 bg-slate-900/80 text-white text-sm font-medium rounded-full backdrop-blur-sm">
              Нет в наличии
            </span>
          </div>
        )}

        {/* Badges */}
        <div className="absolute top-3 left-3 flex gap-2 flex-wrap">
          {!allSoldOut && product.is_new && (
            <span className="px-2 py-1 bg-green-500 text-white text-xs font-medium rounded-full">
              Новинка
            </span>
          )}
          {!allSoldOut && product.old_price && (
            <span className="px-2 py-1 bg-red-500 text-white text-xs font-medium rounded-full">
              Скидка
            </span>
          )}
          {!allSoldOut && colorLabel && (
            <span className="px-2 py-1 bg-slate-900/80 text-white text-xs font-medium rounded-full">
              {colorLabel}
            </span>
          )}
        </div>

        {/* Favorite button */}
        {user && (
          <button
            onClick={handleFavoriteClick}
            className={clsx(
              'absolute top-3 right-3 p-2 rounded-full transition-colors',
              isInFavorites
                ? 'bg-red-500 text-white'
                : 'bg-white/80 text-slate-600 hover:bg-white hover:text-red-500'
            )}
          >
            <Heart className={clsx('w-5 h-5', isInFavorites && 'fill-current')} />
          </button>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Category */}
        <p className="text-xs text-slate-500 mb-1">{product.category}</p>

        {/* Name */}
        <h3 className="font-semibold text-slate-900 mb-1 line-clamp-1">{product.name}</h3>

        {/* Variant label (only when card represents a specific SKU) */}
        {variantLabel && (
          <p className="text-xs text-slate-600 mb-1">{variantLabel}</p>
        )}

        {/* Description */}
        <p className="text-sm text-slate-500 mb-3 line-clamp-2">{product.description}</p>

        {/* Price and action */}
        <div className="flex items-center justify-between">
          <div>
            <p className="font-bold text-slate-900">
              {product.price.toLocaleString('ru-RU')} ₽
            </p>
            {product.old_price && (
              <p className="text-sm text-slate-400 line-through">
                {product.old_price.toLocaleString('ru-RU')} ₽
              </p>
            )}
          </div>

          {user && (
            <button
              onClick={handleAddToCart}
              disabled={allSoldOut}
              title={allSoldOut ? 'Нет в наличии' : 'Добавить в корзину'}
              className="p-2 text-primary-600 hover:bg-primary-50 rounded-full transition-colors disabled:text-slate-300 disabled:hover:bg-transparent disabled:cursor-not-allowed"
            >
              <ShoppingCart className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>
    </Link>
  );
}
