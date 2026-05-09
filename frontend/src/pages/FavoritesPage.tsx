import { Link } from 'react-router-dom';
import { Heart } from 'lucide-react';
import { useFavoritesStore } from '../stores';
import { ProductCard } from '../components/ProductCard';

export default function FavoritesPage() {
  const { favorites, isLoading } = useFavoritesStore();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (favorites.length === 0) {
    return (
      <div className="max-w-4xl mx-auto text-center py-12">
        <Heart className="w-16 h-16 text-slate-300 mx-auto mb-4" />
        <h2 className="text-2xl font-bold text-slate-900 mb-2">Избранное пусто</h2>
        <p className="text-slate-500 mb-6">Добавьте товары, которые вам понравились</p>
        <Link
          to="/"
          className="inline-block bg-primary-600 text-white px-6 py-3 rounded-xl font-medium hover:bg-primary-700 transition-colors"
        >
          Перейти в каталог
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">
        Избранное <span className="text-slate-400 font-normal">({favorites.length})</span>
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {favorites.map((favorite) => {
          const parts = [favorite.selected_color, favorite.selected_size].filter(Boolean);
          const variantLabel = parts.length > 0 ? parts.join(' · ') : null;
          // Show the favorited SKU's photos, not the product's default variant.
          const variant = favorite.product.variants?.find((v) => v.id === favorite.variant_id);
          const product = variant?.images?.length
            ? { ...favorite.product, images: variant.images }
            : favorite.product;
          return (
            <ProductCard
              key={favorite.id}
              product={product}
              variantLabel={variantLabel}
            />
          );
        })}
      </div>
    </div>
  );
}
