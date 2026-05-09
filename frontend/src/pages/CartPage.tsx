import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Trash2, Plus, Minus, ShoppingBag, AlertTriangle, AlertOctagon } from 'lucide-react';
import clsx from 'clsx';
import { useCartStore, useAuthStore } from '../stores';

export default function CartPage() {
  const { items, total, updateQuantity, removeItem, fetchCart } = useCartStore();
  const { user } = useAuthStore();

  // Refresh on mount so we always see current stock state — handles the
  // "I left the page, came back, item is now sold out" scenario.
  useEffect(() => {
    if (user) fetchCart();
  }, [user, fetchCart]);
  const hasOutOfStock = items.some((it) => it.out_of_stock);
  // Don't double up — if there's a sold-out red banner, hide adjusted yellow banner.
  const hasAdjusted = !hasOutOfStock && items.some((it) => it.adjusted);
  const [removingUnavailable, setRemovingUnavailable] = useState(false);

  const removeAllOutOfStock = async () => {
    setRemovingUnavailable(true);
    try {
      const ids = items.filter((it) => it.out_of_stock).map((it) => it.id);
      await Promise.all(ids.map((id) => removeItem(id)));
    } finally {
      setRemovingUnavailable(false);
    }
  };

  if (items.length === 0) {
    return (
      <div className="max-w-4xl mx-auto text-center py-12">
        <ShoppingBag className="w-16 h-16 text-slate-300 mx-auto mb-4" />
        <h2 className="text-2xl font-bold text-slate-900 mb-2">Корзина пуста</h2>
        <p className="text-slate-500 mb-6">Добавьте товары из каталога</p>
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
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Корзина</h1>

      {hasOutOfStock && (
        <div className="mb-4 flex items-start gap-3 p-4 rounded-xl bg-red-50 border border-red-200 text-red-900 text-sm">
          <AlertOctagon className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-600" />
          <div className="flex-1">
            <p className="font-medium">Часть товаров больше недоступна</p>
            <p className="text-red-800/80 mt-0.5">
              Эти товары распроданы, пока вы оформляли заказ. Удалите их из корзины, чтобы продолжить.
            </p>
          </div>
          <button
            type="button"
            onClick={removeAllOutOfStock}
            disabled={removingUnavailable}
            className="self-center px-3 py-1.5 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition disabled:opacity-50"
          >
            {removingUnavailable ? 'Удаляем…' : 'Удалить недоступные'}
          </button>
        </div>
      )}

      {hasAdjusted && (
        <div className="mb-4 flex items-start gap-3 p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-sm">
          <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium">Количество товаров скорректировано</p>
            <p className="text-amber-800/80 mt-0.5">
              По некоторым позициям на складе осталось меньше — мы уменьшили их количество в корзине до доступного. Проверьте перед оформлением заказа.
            </p>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        {/* Items */}
        <div className="divide-y divide-slate-200">
          {items.map((item) => {
            // Prefer the variant's own photo set so the cart row reflects the
            // colour the user actually picked.
            const variantImage =
              item.selected_images?.[0] ?? item.product.images[0];
            const imageUrl =
              variantImage ||
              `https://placehold.co/200x150/e2e8f0/64748b?text=${encodeURIComponent(item.product.name)}`;
            const unitPrice = item.selected_price ?? item.product.price;
            const variantParts = [item.selected_color, item.selected_size].filter(Boolean);
            const stock = item.selected_stock ?? Number.POSITIVE_INFINITY;
            const atLimit = item.quantity >= stock;
            const lowStock = stock > 0 && stock <= 5;
            const soldOut = !!item.out_of_stock;

            return (
              <div
                key={item.id}
                className={clsx('p-6 flex gap-6', soldOut && 'opacity-60 bg-slate-50/50')}
              >
                {/* Image */}
                <Link
                  to={`/product/${item.product.id}`}
                  className="w-32 h-24 bg-slate-100 rounded-lg overflow-hidden flex-shrink-0"
                >
                  <img
                    src={imageUrl}
                    alt={item.product.name}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src = `https://placehold.co/200x150/e2e8f0/64748b?text=${encodeURIComponent(item.product.name)}`;
                    }}
                  />
                </Link>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Link
                      to={`/product/${item.product.id}`}
                      className="font-semibold text-slate-900 hover:text-primary-600 transition-colors"
                    >
                      {item.product.name}
                    </Link>
                    {soldOut && (
                      <span className="px-2 py-0.5 rounded-full bg-slate-200 text-slate-700 text-xs font-medium">
                        Нет в наличии
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-500 mt-1">{item.product.category}</p>
                  {variantParts.length > 0 && (
                    <p className="text-sm text-slate-600 mt-1">
                      {variantParts.join(' · ')}
                    </p>
                  )}

                  <div className="flex items-center justify-between mt-4">
                    {/* Quantity controls */}
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => updateQuantity(item.id, item.quantity - 1)}
                          disabled={soldOut}
                          className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                        >
                          <Minus className="w-4 h-4" />
                        </button>
                        <span className="w-10 text-center font-medium">{item.quantity}</span>
                        <button
                          onClick={() => updateQuantity(item.id, item.quantity + 1)}
                          disabled={atLimit || soldOut}
                          title={atLimit && !soldOut ? `На складе осталось ${stock} шт.` : undefined}
                          className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                        >
                          <Plus className="w-4 h-4" />
                        </button>
                      </div>
                      {!soldOut && lowStock && (
                        <span className={atLimit ? 'text-xs text-amber-600' : 'text-xs text-slate-500'}>
                          {atLimit ? 'максимум на складе' : `осталось ${stock} шт.`}
                        </span>
                      )}
                    </div>

                    {/* Price */}
                    <div className="text-right">
                      <p className={clsx('font-bold', soldOut ? 'text-slate-500 line-through' : 'text-slate-900')}>
                        {(unitPrice * item.quantity).toLocaleString('ru-RU')} ₽
                      </p>
                      <p className="text-sm text-slate-500">
                        {unitPrice.toLocaleString('ru-RU')} ₽ / шт
                      </p>
                    </div>
                  </div>
                </div>

                {/* Remove */}
                <button
                  onClick={() => removeItem(item.id)}
                  className={clsx(
                    'p-2 rounded transition-colors self-start',
                    soldOut
                      ? 'text-red-500 bg-red-50 hover:bg-red-100'
                      : 'text-slate-400 hover:text-red-500 hover:bg-red-50',
                  )}
                  title={soldOut ? 'Удалить недоступный товар' : 'Удалить из корзины'}
                >
                  <Trash2 className="w-5 h-5" />
                </button>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="p-6 bg-slate-50 border-t border-slate-200">
          <div className="flex items-center justify-between mb-4">
            <span className="text-lg text-slate-600">Итого:</span>
            <span className="text-2xl font-bold text-slate-900">
              {total.toLocaleString('ru-RU')} ₽
            </span>
          </div>

          {hasOutOfStock ? (
            <button
              type="button"
              disabled
              title="Сначала удалите недоступные товары"
              className="block w-full bg-slate-300 text-white px-6 py-3 rounded-xl font-medium text-center cursor-not-allowed"
            >
              Сначала удалите недоступные товары
            </button>
          ) : (
            <Link
              to="/checkout"
              className="block w-full bg-primary-600 text-white px-6 py-3 rounded-xl font-medium hover:bg-primary-700 transition-colors text-center"
            >
              Оформить заказ
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
