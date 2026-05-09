import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Package, AlertOctagon } from 'lucide-react';
import { useCartStore } from '../stores';
import { ordersApi } from '../api';

interface UnavailableItem {
  variant_id: number;
  name: string;
  color?: string | null;
  size_label?: string | null;
  reason: 'sold_out' | 'insufficient';
  available: number;
  requested: number;
}

export default function CheckoutPage() {
  const navigate = useNavigate();
  const { items, total, fetchCart } = useCartStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [stockModal, setStockModal] = useState<
    | {
        items: UnavailableItem[];
        canClamp: boolean;
      }
    | null
  >(null);

  const [formData, setFormData] = useState({
    address: '',
    phone: '',
    comment: '',
  });

  const submitOrder = async (acceptClamping: boolean) => {
    setIsLoading(true);
    setError('');
    try {
      const order = await ordersApi.createOrder({
        address: formData.address,
        phone: formData.phone,
        comment: formData.comment || undefined,
        accept_clamping: acceptClamping,
      });
      await fetchCart();
      navigate(`/orders`, { state: { newOrderId: order.id } });
    } catch (err: any) {
      if (err?.response?.status === 409) {
        const detail = err.response.data?.detail;
        await fetchCart();
        setStockModal({
          items: detail?.items ?? [],
          canClamp: !!detail?.can_clamp,
        });
      } else {
        setError('Ошибка оформления заказа. Попробуйте снова.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.address.trim() || !formData.phone.trim()) {
      setError('Заполните обязательные поля');
      return;
    }
    void submitOrder(false);
  };

  const confirmClampedCheckout = async () => {
    setStockModal(null);
    await submitOrder(true);
  };

  const closeModalAndGoToCart = () => {
    setStockModal(null);
    navigate('/cart');
  };

  if (items.length === 0) {
    return (
      <div className="max-w-2xl mx-auto text-center py-12">
        <Package className="w-16 h-16 text-slate-300 mx-auto mb-4" />
        <h2 className="text-2xl font-bold text-slate-900 mb-2">Корзина пуста</h2>
        <p className="text-slate-500 mb-6">Добавьте товары для оформления заказа</p>
        <button
          onClick={() => navigate('/')}
          className="inline-block bg-primary-600 text-white px-6 py-3 rounded-xl font-medium hover:bg-primary-700 transition-colors"
        >
          Перейти в каталог
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Back button */}
      <button
        onClick={() => navigate('/cart')}
        className="flex items-center gap-2 text-slate-600 hover:text-slate-900 mb-6 transition-colors"
      >
        <ArrowLeft className="w-5 h-5" />
        Вернуться в корзину
      </button>

      <h1 className="text-2xl font-bold text-slate-900 mb-6">Оформление заказа</h1>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        {/* Order summary */}
        <div className="p-6 bg-slate-50 border-b border-slate-200">
          <h3 className="font-semibold text-slate-900 mb-4">Ваш заказ</h3>
          <div className="space-y-2 text-sm">
            {items.map((item) => (
              <div key={item.id} className="flex justify-between">
                <span className="text-slate-600">
                  {item.product.name} x {item.quantity}
                </span>
                <span className="font-medium">
                  {(item.product.price * item.quantity).toLocaleString('ru-RU')} ₽
                </span>
              </div>
            ))}
          </div>
          <div className="border-t border-slate-200 mt-4 pt-4 flex justify-between">
            <span className="font-semibold text-slate-900">Итого:</span>
            <span className="font-bold text-xl text-slate-900">
              {total.toLocaleString('ru-RU')} ₽
            </span>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-4 bg-red-50 text-red-700 rounded-lg text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Адрес доставки *
            </label>
            <textarea
              value={formData.address}
              onChange={(e) => setFormData({ ...formData, address: e.target.value })}
              rows={3}
              className="w-full px-4 py-3 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              placeholder="Город, улица, дом, квартира"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Телефон *
            </label>
            <input
              type="tel"
              value={formData.phone}
              onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              className="w-full px-4 py-3 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              placeholder="+7 (999) 123-45-67"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Комментарий к заказу
            </label>
            <textarea
              value={formData.comment}
              onChange={(e) => setFormData({ ...formData, comment: e.target.value })}
              rows={2}
              className="w-full px-4 py-3 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              placeholder="Дополнительная информация"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-primary-600 text-white px-6 py-3 rounded-xl font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Оформляем...' : 'Подтвердить заказ'}
          </button>
        </form>
      </div>

      {stockModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden">
            <div className="p-6">
              <div className="flex items-start gap-3 mb-4">
                <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                  <AlertOctagon className="w-5 h-5 text-red-600" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Корзина изменилась</h3>
                  <p className="text-sm text-slate-600 mt-1">
                    {stockModal.canClamp
                      ? 'Количество некоторых товаров изменилось — на складе осталось меньше, чем вы запросили.'
                      : 'Часть товаров больше недоступна. Удалите их из корзины, чтобы продолжить.'}
                  </p>
                </div>
              </div>
              {stockModal.items.length > 0 && (
                <ul className="space-y-2 mb-6">
                  {stockModal.items.map((it) => {
                    const variantBits = [it.color, it.size_label].filter(Boolean).join(' · ');
                    return (
                      <li
                        key={it.variant_id}
                        className="flex items-start justify-between gap-3 p-3 rounded-lg bg-red-50 border border-red-100 text-sm"
                      >
                        <div>
                          <p className="font-medium text-slate-900">{it.name}</p>
                          {variantBits && <p className="text-xs text-slate-500">{variantBits}</p>}
                        </div>
                        <span className="text-xs text-red-700 whitespace-nowrap">
                          {it.reason === 'sold_out'
                            ? 'нет в наличии'
                            : `осталось ${it.available} вместо ${it.requested}`}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
              {stockModal.canClamp ? (
                <div className="space-y-2">
                  <button
                    type="button"
                    onClick={confirmClampedCheckout}
                    disabled={isLoading}
                    className="w-full bg-primary-600 text-white px-4 py-2.5 rounded-xl font-medium hover:bg-primary-700 transition-colors disabled:opacity-50"
                  >
                    {isLoading ? 'Оформляем…' : 'Оформить с обновлённым количеством'}
                  </button>
                  <button
                    type="button"
                    onClick={closeModalAndGoToCart}
                    disabled={isLoading}
                    className="w-full px-4 py-2.5 rounded-xl font-medium text-slate-700 hover:bg-slate-100 transition-colors disabled:opacity-50"
                  >
                    Изменить корзину
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={closeModalAndGoToCart}
                  className="w-full bg-primary-600 text-white px-4 py-2.5 rounded-xl font-medium hover:bg-primary-700 transition-colors"
                >
                  Перейти в корзину
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
