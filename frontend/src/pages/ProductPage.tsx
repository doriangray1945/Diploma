import { useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Heart, ShoppingCart, Star, Truck, Shield, RotateCcw } from 'lucide-react';
import { useProductsStore, useAuthStore, useCartStore, useFavoritesStore } from '../stores';
import clsx from 'clsx';

export default function ProductPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { currentProduct: product, isLoading, error, fetchProduct } = useProductsStore();
  const { addToCart } = useCartStore();
  const { addToFavorites, removeFromFavorites, isFavorite } = useFavoritesStore();

  const isInFavorites = product ? isFavorite(product.id) : false;

  useEffect(() => {
    if (id) {
      fetchProduct(Number(id));
    }
  }, [id, fetchProduct]);

  const handleAddToCart = async () => {
    if (!user || !product) return;
    try {
      await addToCart(product.id);
    } catch (error) {
      console.error('Failed to add to cart:', error);
    }
  };

  const handleToggleFavorite = async () => {
    if (!user || !product) return;
    try {
      if (isInFavorites) {
        await removeFromFavorites(product.id);
      } else {
        await addToFavorites(product.id);
      }
    } catch (error) {
      console.error('Failed to toggle favorite:', error);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-500 mb-4">{error || 'Товар не найден'}</p>
        <button
          onClick={() => navigate('/')}
          className="text-primary-600 hover:text-primary-700 font-medium"
        >
          Вернуться в каталог
        </button>
      </div>
    );
  }

  const imageUrl = product.images[0] || `https://placehold.co/600x400/e2e8f0/64748b?text=${encodeURIComponent(product.name)}`;

  return (
    <div className="max-w-6xl mx-auto">
      {/* Back button */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-slate-600 hover:text-slate-900 mb-6 transition-colors"
      >
        <ArrowLeft className="w-5 h-5" />
        Назад
      </button>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 p-8">
          {/* Image */}
          <div className="aspect-square bg-slate-100 rounded-xl overflow-hidden">
            <img
              src={imageUrl}
              alt={product.name}
              className="w-full h-full object-cover"
              onError={(e) => {
                (e.target as HTMLImageElement).src = `https://placehold.co/600x400/e2e8f0/64748b?text=${encodeURIComponent(product.name)}`;
              }}
            />
          </div>

          {/* Info */}
          <div>
            {/* Badges */}
            <div className="flex gap-2 mb-4">
              {product.is_new && (
                <span className="px-3 py-1 bg-green-100 text-green-700 text-sm font-medium rounded-full">
                  Новинка
                </span>
              )}
              {product.is_popular && (
                <span className="px-3 py-1 bg-amber-100 text-amber-700 text-sm font-medium rounded-full">
                  Популярное
                </span>
              )}
              {!product.in_stock && (
                <span className="px-3 py-1 bg-red-100 text-red-700 text-sm font-medium rounded-full">
                  Нет в наличии
                </span>
              )}
            </div>

            {/* Category */}
            <p className="text-sm text-slate-500 mb-2">{product.category}</p>

            {/* Name */}
            <h1 className="text-3xl font-bold text-slate-900 mb-4">{product.name}</h1>

            {/* Rating */}
            <div className="flex items-center gap-2 mb-6">
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((star) => (
                  <Star
                    key={star}
                    className={clsx(
                      'w-5 h-5',
                      star <= Math.round(product.rating)
                        ? 'text-amber-400 fill-current'
                        : 'text-slate-200'
                    )}
                  />
                ))}
              </div>
              <span className="text-sm text-slate-500">
                {product.rating.toFixed(1)} ({product.reviews_count} отзывов)
              </span>
            </div>

            {/* Price */}
            <div className="mb-6">
              <p className="text-3xl font-bold text-slate-900">
                {product.price.toLocaleString('ru-RU')} ₽
              </p>
              {product.old_price && (
                <p className="text-lg text-slate-400 line-through">
                  {product.old_price.toLocaleString('ru-RU')} ₽
                </p>
              )}
            </div>

            {/* Actions */}
            {user ? (
              <div className="flex gap-3 mb-8">
                <button
                  onClick={handleAddToCart}
                  disabled={!product.in_stock}
                  className="flex-1 bg-primary-600 text-white px-6 py-3 rounded-xl font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <ShoppingCart className="w-5 h-5" />
                  В корзину
                </button>
                <button
                  onClick={handleToggleFavorite}
                  className={clsx(
                    'p-3 rounded-xl border transition-colors',
                    isInFavorites
                      ? 'bg-red-50 border-red-200 text-red-500'
                      : 'border-slate-200 text-slate-400 hover:text-red-500 hover:border-red-200'
                  )}
                >
                  <Heart className={clsx('w-6 h-6', isInFavorites && 'fill-current')} />
                </button>
              </div>
            ) : (
              <Link
                to="/login"
                className="block w-full bg-primary-600 text-white px-6 py-3 rounded-xl font-medium hover:bg-primary-700 transition-colors text-center mb-8"
              >
                Войдите, чтобы купить
              </Link>
            )}

            {/* Features */}
            <div className="grid grid-cols-3 gap-4 mb-8">
              <div className="text-center p-4 bg-slate-50 rounded-xl">
                <Truck className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                <p className="text-xs text-slate-600">Бесплатная доставка</p>
              </div>
              <div className="text-center p-4 bg-slate-50 rounded-xl">
                <Shield className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                <p className="text-xs text-slate-600">Гарантия 2 года</p>
              </div>
              <div className="text-center p-4 bg-slate-50 rounded-xl">
                <RotateCcw className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                <p className="text-xs text-slate-600">Возврат 14 дней</p>
              </div>
            </div>

            {/* Specifications */}
            <div className="border-t border-slate-200 pt-6">
              <h3 className="font-semibold text-slate-900 mb-4">Характеристики</h3>
              <dl className="space-y-3">
                {product.dimensions && (
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Размеры</dt>
                    <dd className="text-slate-900 font-medium">{product.dimensions} см</dd>
                  </div>
                )}
                {product.materials && (
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Материалы</dt>
                    <dd className="text-slate-900 font-medium">{product.materials}</dd>
                  </div>
                )}
                {product.color && (
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Цвет</dt>
                    <dd className="text-slate-900 font-medium">{product.color}</dd>
                  </div>
                )}
              </dl>
            </div>
          </div>
        </div>

        {/* 3D / AR — only if model URLs present */}
        {(product.model_glb_url || product.model_usdz_url) && (
          <div className="border-t border-slate-200 p-8">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-900">3D-модель</h3>
              <p className="text-xs text-slate-500 hidden lg:block">
                Крутите модель мышкой
              </p>
              <p className="text-xs text-slate-500 lg:hidden">
                Тапните «AR» — товар встанет в вашей комнате
              </p>
            </div>
            <div className="w-full h-[400px] md:h-[500px] bg-slate-50 rounded-xl overflow-hidden">
              <model-viewer
                src={product.model_glb_url || undefined}
                ios-src={product.model_usdz_url || undefined}
                ar
                ar-modes="webxr scene-viewer quick-look"
                camera-controls
                auto-rotate
                shadow-intensity="1"
                alt={product.name}
                style={{ width: '100%', height: '100%', backgroundColor: '#f8fafc' }}
              />
            </div>
          </div>
        )}

        {/* Description */}
        <div className="border-t border-slate-200 p-8">
          <h3 className="font-semibold text-slate-900 mb-4">Описание</h3>
          <p className="text-slate-600 leading-relaxed">{product.description}</p>
        </div>
      </div>
    </div>
  );
}
