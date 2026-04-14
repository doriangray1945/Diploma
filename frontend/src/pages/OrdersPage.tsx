import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Package, ChevronDown, ChevronUp, CheckCircle } from 'lucide-react';
import { ordersApi } from '../api';
import type { Order } from '../types';
import clsx from 'clsx';

const statusLabels: Record<string, string> = {
  pending: 'Ожидает подтверждения',
  confirmed: 'Подтверждён',
  shipping: 'В доставке',
  delivered: 'Доставлен',
  cancelled: 'Отменён',
};

const statusColors: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-700',
  confirmed: 'bg-blue-100 text-blue-700',
  shipping: 'bg-violet-100 text-violet-700',
  delivered: 'bg-green-100 text-green-700',
  cancelled: 'bg-red-100 text-red-700',
};

export default function OrdersPage() {
  const location = useLocation();
  const newOrderId = location.state?.newOrderId;

  const [orders, setOrders] = useState<Order[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedOrder, setExpandedOrder] = useState<number | null>(newOrderId || null);

  useEffect(() => {
    const fetchOrders = async () => {
      try {
        const response = await ordersApi.getOrders();
        setOrders(response.items);
      } catch (error) {
        console.error('Failed to fetch orders:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchOrders();
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="max-w-4xl mx-auto text-center py-12">
        <Package className="w-16 h-16 text-slate-300 mx-auto mb-4" />
        <h2 className="text-2xl font-bold text-slate-900 mb-2">У вас пока нет заказов</h2>
        <p className="text-slate-500 mb-6">Оформите первый заказ в каталоге</p>
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
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Мои заказы</h1>

      {newOrderId && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-xl flex items-center gap-3">
          <CheckCircle className="w-6 h-6 text-green-600" />
          <p className="text-green-700 font-medium">
            Заказ №{newOrderId} успешно оформлен!
          </p>
        </div>
      )}

      <div className="space-y-4">
        {orders.map((order) => (
          <div
            key={order.id}
            className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden"
          >
            {/* Header */}
            <button
              onClick={() => setExpandedOrder(expandedOrder === order.id ? null : order.id)}
              className="w-full p-6 flex items-center justify-between hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center gap-4">
                <div className="text-left">
                  <p className="font-semibold text-slate-900">Заказ №{order.id}</p>
                  <p className="text-sm text-slate-500">
                    {new Date(order.created_at).toLocaleDateString('ru-RU', {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric',
                    })}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <span
                  className={clsx(
                    'px-3 py-1 text-sm font-medium rounded-full',
                    statusColors[order.status]
                  )}
                >
                  {statusLabels[order.status]}
                </span>
                <span className="font-bold text-slate-900">
                  {order.total.toLocaleString('ru-RU')} ₽
                </span>
                {expandedOrder === order.id ? (
                  <ChevronUp className="w-5 h-5 text-slate-400" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-slate-400" />
                )}
              </div>
            </button>

            {/* Details */}
            {expandedOrder === order.id && (
              <div className="px-6 pb-6 border-t border-slate-200 pt-4">
                {/* Items */}
                <div className="space-y-3 mb-4">
                  {order.items.map((item) => (
                    <div key={item.id} className="flex justify-between text-sm">
                      <span className="text-slate-600">
                        {item.product_name} x {item.quantity}
                      </span>
                      <span className="font-medium">
                        {(item.price * item.quantity).toLocaleString('ru-RU')} ₽
                      </span>
                    </div>
                  ))}
                </div>

                {/* Delivery info */}
                <div className="bg-slate-50 rounded-xl p-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Адрес:</span>
                    <span className="text-slate-900">{order.address}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Телефон:</span>
                    <span className="text-slate-900">{order.phone}</span>
                  </div>
                  {order.comment && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Комментарий:</span>
                      <span className="text-slate-900">{order.comment}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
