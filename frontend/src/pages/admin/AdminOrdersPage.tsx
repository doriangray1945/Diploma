import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, User } from 'lucide-react';
import { adminApi, type AdminOrder, type OrderStatus } from '../../api/admin';

const STATUSES: { value: OrderStatus | ''; label: string }[] = [
  { value: '', label: 'Все' },
  { value: 'pending', label: 'Ожидают' },
  { value: 'confirmed', label: 'Подтверждены' },
  { value: 'shipping', label: 'Доставка' },
  { value: 'delivered', label: 'Доставлены' },
  { value: 'cancelled', label: 'Отменены' },
];

const STATUS_LABEL: Record<OrderStatus, string> = {
  pending: 'Ожидает',
  confirmed: 'Подтверждён',
  shipping: 'Доставка',
  delivered: 'Доставлен',
  cancelled: 'Отменён',
};

const STATUS_COLOR: Record<OrderStatus, string> = {
  pending: 'bg-amber-100 text-amber-700',
  confirmed: 'bg-blue-100 text-blue-700',
  shipping: 'bg-violet-100 text-violet-700',
  delivered: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-slate-100 text-slate-600',
};

const fmtRub = (n: number) =>
  new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(n);
const fmtDate = (s: string) => new Date(s).toLocaleString('ru-RU');

export default function OrdersPage() {
  const [items, setItems] = useState<AdminOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<OrderStatus | ''>('');
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());

  const load = () => {
    setLoading(true);
    adminApi
      .listOrders({ status: filter || undefined })
      .then(setItems)
      .finally(() => setLoading(false));
  };

  useEffect(load, [filter]);

  const toggle = (id: number) => {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const changeStatus = async (id: number, next: OrderStatus) => {
    setSavingIds((s) => new Set(s).add(id));
    try {
      const updated = await adminApi.updateOrderStatus(id, next);
      setItems((prev) => prev.map((o) => (o.id === id ? updated : o)));
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Не удалось изменить статус');
    } finally {
      setSavingIds((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Заказы</h1>

      <div className="flex flex-wrap gap-1 bg-white border border-slate-200 rounded-xl p-1.5 shadow-sm">
        {STATUSES.map((s) => (
          <button
            key={s.value}
            onClick={() => setFilter(s.value)}
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              filter === s.value ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-12 text-center">
            <div className="animate-spin inline-block rounded-full h-8 w-8 border-b-2 border-slate-900" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-slate-500">Заказов не найдено.</div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {items.map((o) => (
              <li key={o.id} className="px-4 py-3 hover:bg-slate-50">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => toggle(o.id)}
                    className="text-slate-400 hover:text-slate-700"
                  >
                    {expanded.has(o.id) ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-semibold text-slate-900">#{o.id}</span>
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLOR[o.status]}`}>
                        {STATUS_LABEL[o.status]}
                      </span>
                      <span className="text-slate-400">·</span>
                      <span className="inline-flex items-center gap-1 text-slate-600">
                        <User className="w-3 h-3" /> {o.user_name} ({o.user_email})
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">{fmtDate(o.created_at)}</p>
                  </div>
                  <span className="font-semibold text-slate-900">{fmtRub(o.total)}</span>
                  {o.allowed_transitions.length > 0 ? (
                    <select
                      value=""
                      disabled={savingIds.has(o.id)}
                      onChange={(e) => {
                        const v = e.target.value as OrderStatus | '';
                        if (v) changeStatus(o.id, v);
                      }}
                      className="text-sm border border-slate-200 rounded-lg px-2 py-1 bg-white"
                    >
                      <option value="">Изменить статус…</option>
                      {o.allowed_transitions.map((s) => (
                        <option key={s} value={s}>
                          → {STATUS_LABEL[s]}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-xs text-slate-400">Финальный</span>
                  )}
                </div>

                {expanded.has(o.id) && (
                  <div className="mt-3 ml-7 grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Адрес</p>
                      <p className="text-slate-900">{o.address}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Телефон</p>
                      <p className="text-slate-900">{o.phone}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Комментарий</p>
                      <p className="text-slate-900">{o.comment || '—'}</p>
                    </div>
                    <div className="md:col-span-3">
                      <p className="text-xs text-slate-500 mb-1">Товары ({o.items.length})</p>
                      {o.items.length === 0 ? (
                        <p className="text-slate-400 text-xs italic">пусто</p>
                      ) : (
                        <ul className="space-y-1">
                          {o.items.map((it) => (
                            <li key={it.id} className="flex justify-between">
                              <span className="text-slate-700">
                                {it.product_name} × {it.quantity}
                              </span>
                              <span className="font-medium text-slate-900">{fmtRub(it.price * it.quantity)}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
