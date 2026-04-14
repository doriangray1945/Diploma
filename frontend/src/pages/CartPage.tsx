import { Link } from 'react-router-dom';
import { Trash2, Plus, Minus, ShoppingBag } from 'lucide-react';
import { useCartStore } from '../stores';

export default function CartPage() {
  const { items, total, updateQuantity, removeItem } = useCartStore();

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

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        {/* Items */}
        <div className="divide-y divide-slate-200">
          {items.map((item) => {
            const imageUrl = item.product.images[0] || `https://placehold.co/200x150/e2e8f0/64748b?text=${encodeURIComponent(item.product.name)}`;

            return (
              <div key={item.id} className="p-6 flex gap-6">
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
                  <Link
                    to={`/product/${item.product.id}`}
                    className="font-semibold text-slate-900 hover:text-primary-600 transition-colors"
                  >
                    {item.product.name}
                  </Link>
                  <p className="text-sm text-slate-500 mt-1">{item.product.category}</p>

                  <div className="flex items-center justify-between mt-4">
                    {/* Quantity controls */}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => updateQuantity(item.id, item.quantity - 1)}
                        className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded transition-colors"
                      >
                        <Minus className="w-4 h-4" />
                      </button>
                      <span className="w-10 text-center font-medium">{item.quantity}</span>
                      <button
                        onClick={() => updateQuantity(item.id, item.quantity + 1)}
                        className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded transition-colors"
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    </div>

                    {/* Price */}
                    <div className="text-right">
                      <p className="font-bold text-slate-900">
                        {(item.product.price * item.quantity).toLocaleString('ru-RU')} ₽
                      </p>
                      <p className="text-sm text-slate-500">
                        {item.product.price.toLocaleString('ru-RU')} ₽ / шт
                      </p>
                    </div>
                  </div>
                </div>

                {/* Remove */}
                <button
                  onClick={() => removeItem(item.id)}
                  className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors self-start"
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

          <Link
            to="/checkout"
            className="block w-full bg-primary-600 text-white px-6 py-3 rounded-xl font-medium hover:bg-primary-700 transition-colors text-center"
          >
            Оформить заказ
          </Link>
        </div>
      </div>
    </div>
  );
}
