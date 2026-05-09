import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Heart, ShoppingCart, Star, Truck, Shield, RotateCcw } from 'lucide-react';
import { useProductsStore, useAuthStore, useCartStore, useFavoritesStore } from '../stores';
import clsx from 'clsx';
import ProductImageGallery from '../components/Product/ProductImageGallery';
import ColorPicker from '../components/Product/ColorPicker';
import SizePicker from '../components/Product/SizePicker';

export default function ProductPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { currentProduct: product, isLoading, error, fetchProduct } = useProductsStore();
  const { items: cartItems, addToCart } = useCartStore();
  const { favorites, addToFavorites, removeFromFavorites } = useFavoritesStore();

  const [selectedVariantId, setSelectedVariantId] = useState<number | null>(null);

  useEffect(() => {
    if (id) {
      fetchProduct(Number(id));
    }
  }, [id, fetchProduct]);

  // When product loads/changes, snap to its default variant.
  useEffect(() => {
    if (!product) return;
    const defaultId =
      product.default_variant_id ??
      product.variants?.find((v) => v.is_default)?.id ??
      product.variants?.[0]?.id ??
      null;
    setSelectedVariantId(defaultId);
  }, [product]);

  const variants = product?.variants ?? [];

  const selectedVariant = useMemo(() => {
    if (!variants.length) return null;
    return (
      variants.find((v) => v.id === selectedVariantId) ??
      variants.find((v) => v.is_default) ??
      variants[0]
    );
  }, [variants, selectedVariantId]);

  // Unique colors / sizes across all variants of the product (preserves first-seen order).
  const uniqueColors = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const v of variants) {
      if (v.color && !seen.has(v.color)) {
        seen.add(v.color);
        out.push(v.color);
      }
    }
    return out;
  }, [variants]);

  const uniqueSizes = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const v of variants) {
      if (v.size_label && !seen.has(v.size_label)) {
        seen.add(v.size_label);
        out.push(v.size_label);
      }
    }
    return out;
  }, [variants]);

  // Sizes available for the currently-selected color (and vice versa).
  const sizesForCurrentColor = useMemo(() => {
    const set = new Set<string>();
    if (!selectedVariant?.color) {
      // No specific colour: all sizes are available across the product.
      for (const v of variants) if (v.size_label) set.add(v.size_label);
      return set;
    }
    for (const v of variants) {
      if (v.color === selectedVariant.color && v.size_label) set.add(v.size_label);
    }
    return set;
  }, [variants, selectedVariant?.color]);

  const colorsForCurrentSize = useMemo(() => {
    const set = new Set<string>();
    if (!selectedVariant?.size_label) {
      for (const v of variants) if (v.color) set.add(v.color);
      return set;
    }
    for (const v of variants) {
      if (v.size_label === selectedVariant.size_label && v.color) set.add(v.color);
    }
    return set;
  }, [variants, selectedVariant?.size_label]);

  // Heart reflects whether the *currently-displayed* variant is favorited.
  // Each colour/size combo is its own favorite SKU (industry standard) — user
  // can favourite multiple variants of the same model.
  const isInFavorites = !!selectedVariant && favorites.some(
    (f) => f.variant_id === selectedVariant.id,
  );

  const handleColorChange = (color: string) => {
    // Try (color, current size). Fallback: first variant of that color.
    const sameSize = variants.find(
      (v) => v.color === color && v.size_label === selectedVariant?.size_label,
    );
    const anyColor = variants.find((v) => v.color === color);
    const next = sameSize ?? anyColor;
    if (next) setSelectedVariantId(next.id);
  };

  const handleSizeChange = (size: string) => {
    const sameColor = variants.find(
      (v) => v.size_label === size && v.color === selectedVariant?.color,
    );
    const anySize = variants.find((v) => v.size_label === size);
    const next = sameColor ?? anySize;
    if (next) setSelectedVariantId(next.id);
  };

  const handleAddToCart = async () => {
    if (!user || !selectedVariant) return;
    try {
      await addToCart(selectedVariant.id);
    } catch (error) {
      console.error('Failed to add to cart:', error);
    }
  };

  const handleToggleFavorite = async () => {
    if (!user || !selectedVariant) return;
    try {
      if (isInFavorites) {
        await removeFromFavorites(selectedVariant.id);
      } else {
        await addToFavorites(selectedVariant.id);
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

  const galleryImages = selectedVariant?.images ?? product.images ?? [];
  const variantPrice = selectedVariant?.price ?? product.price;
  const variantOldPrice = selectedVariant?.old_price ?? product.old_price ?? null;
  const variantInStock = selectedVariant ? selectedVariant.in_stock : product.in_stock;
  const variantStock = selectedVariant?.stock_quantity ?? 0;
  // How many of this exact variant are already in the user's cart.
  const cartQty = selectedVariant
    ? cartItems.find((it) => it.variant_id === selectedVariant.id)?.quantity ?? 0
    : 0;
  const allInCart = variantInStock && cartQty >= variantStock && variantStock > 0;
  const showLowStock = variantInStock && variantStock > 0 && variantStock <= 5;

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
          {/* Image gallery */}
          <ProductImageGallery images={galleryImages} productName={product.name} />

          {/* Info */}
          <div>
            {/* Badges */}
            <div className="flex gap-2 mb-4 flex-wrap">
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
              {!variantInStock && (
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
                {variantPrice.toLocaleString('ru-RU')} ₽
              </p>
              {variantOldPrice && (
                <p className="text-lg text-slate-400 line-through">
                  {variantOldPrice.toLocaleString('ru-RU')} ₽
                </p>
              )}
              {showLowStock && (
                <p className="mt-2 text-sm text-amber-600 font-medium">
                  Осталось {variantStock} шт.
                </p>
              )}
            </div>

            {/* Variant selectors */}
            {(uniqueColors.length > 1 || uniqueSizes.length > 1) && (
              <div className="space-y-5 mb-6">
                {uniqueColors.length > 1 && (
                  <ColorPicker
                    colors={uniqueColors}
                    available={colorsForCurrentSize}
                    selected={selectedVariant?.color ?? null}
                    onChange={handleColorChange}
                  />
                )}
                {uniqueSizes.length > 1 && (
                  <SizePicker
                    sizes={uniqueSizes}
                    available={sizesForCurrentColor}
                    selected={selectedVariant?.size_label ?? null}
                    onChange={handleSizeChange}
                  />
                )}
              </div>
            )}

            {/* Actions */}
            {user ? (
              <div className="flex gap-3 mb-8">
                <button
                  onClick={handleAddToCart}
                  disabled={!variantInStock || allInCart}
                  title={allInCart ? 'Всё доступное уже в корзине' : undefined}
                  className="flex-1 bg-primary-600 text-white px-6 py-3 rounded-xl font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <ShoppingCart className="w-5 h-5" />
                  {allInCart ? 'Всё доступное в корзине' : 'В корзину'}
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
                    <dd className="text-slate-900 font-medium">
                      {typeof product.dimensions === 'object'
                        ? `${product.dimensions.width}×${product.dimensions.depth}×${product.dimensions.height} см`
                        : `${product.dimensions} см`}
                    </dd>
                  </div>
                )}
                {product.materials && (
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Материалы</dt>
                    <dd className="text-slate-900 font-medium">{product.materials}</dd>
                  </div>
                )}
                {selectedVariant?.color && (
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Цвет</dt>
                    <dd className="text-slate-900 font-medium">{selectedVariant.color}</dd>
                  </div>
                )}
                {selectedVariant?.size_label && (
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Размер</dt>
                    <dd className="text-slate-900 font-medium">{selectedVariant.size_label}</dd>
                  </div>
                )}
                {selectedVariant && variantInStock && selectedVariant.stock_quantity > 0 && (
                  <div className="flex justify-between">
                    <dt className="text-slate-500">В наличии</dt>
                    <dd className="text-slate-900 font-medium">
                      {selectedVariant.stock_quantity} шт.
                    </dd>
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
