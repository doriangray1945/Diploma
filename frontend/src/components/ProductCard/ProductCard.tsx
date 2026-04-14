import { Link } from 'react-router-dom';
import { Heart, ShoppingCart } from 'lucide-react';
import type { Product } from '../../types';
import { useAuthStore, useCartStore, useFavoritesStore } from '../../stores';
import clsx from 'clsx';

interface ProductCardProps {
  product: Product;
}

export default function ProductCard({ product }: ProductCardProps) {
  const { user } = useAuthStore();
  const { addToCart } = useCartStore();
  const { addToFavorites, removeFromFavorites, isFavorite } = useFavoritesStore();

  const isInFavorites = isFavorite(product.id);

  const handleFavoriteClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (!user) return;

    try {
      if (isInFavorites) {
        await removeFromFavorites(product.id);
      } else {
        await addToFavorites(product.id);
      }
    } catch (error) {
      console.error('Failed to update favorites:', error);
    }
  };

  const handleAddToCart = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (!user) return;

    try {
      await addToCart(product.id);
    } catch (error) {
      console.error('Failed to add to cart:', error);
    }
  };

  // Placeholder image
  const imageUrl = product.images[0] || `https://placehold.co/400x300/e2e8f0/64748b?text=${encodeURIComponent(product.name)}`;

  return (
    <Link
      to={`/product/${product.id}`}
      className="group bg-white rounded-2xl overflow-hidden shadow-sm border border-slate-200 hover:shadow-lg hover:border-slate-300 transition-all"
    >
      {/* Image */}
      <div className="relative aspect-[4/3] overflow-hidden bg-slate-100">
        <img
          src={imageUrl}
          alt={product.name}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          onError={(e) => {
            (e.target as HTMLImageElement).src = `https://placehold.co/400x300/e2e8f0/64748b?text=${encodeURIComponent(product.name)}`;
          }}
        />

        {/* Badges */}
        <div className="absolute top-3 left-3 flex gap-2">
          {product.is_new && (
            <span className="px-2 py-1 bg-green-500 text-white text-xs font-medium rounded-full">
              Новинка
            </span>
          )}
          {product.old_price && (
            <span className="px-2 py-1 bg-red-500 text-white text-xs font-medium rounded-full">
              Скидка
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
              className="p-2 text-primary-600 hover:bg-primary-50 rounded-full transition-colors"
              title="Добавить в корзину"
            >
              <ShoppingCart className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>
    </Link>
  );
}
