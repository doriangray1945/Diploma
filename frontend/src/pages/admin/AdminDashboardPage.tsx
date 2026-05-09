import { useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { TrendingUp, ShoppingBag, Wallet, UserPlus, AlertTriangle } from 'lucide-react';

import {
  adminApi,
  type CategoryBreakdown,
  type LowStockProduct,
  type RevenuePoint,
  type StatsOverview,
  type TopProduct,
} from '../../api/admin';

type Period = '7d' | '30d';

const fmtRub = (n: number) =>
  new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(n);

const CATEGORY_COLORS = ['#2563eb', '#7c3aed', '#db2777', '#ea580c', '#16a34a', '#0891b2', '#ca8a04'];

function KpiCard({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string;
  icon: typeof TrendingUp;
  accent: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-500">{label}</p>
          <p className="text-2xl font-semibold text-slate-900 mt-1">{value}</p>
        </div>
        <div className={`p-2 rounded-lg ${accent}`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
      </div>
    </div>
  );
}

export default function AdminDashboardPage() {
  const [period, setPeriod] = useState<Period>('7d');
  const [overview, setOverview] = useState<StatsOverview | null>(null);
  const [revenue, setRevenue] = useState<RevenuePoint[]>([]);
  const [top, setTop] = useState<TopProduct[]>([]);
  const [categories, setCategories] = useState<CategoryBreakdown[]>([]);
  const [lowStock, setLowStock] = useState<LowStockProduct[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const days = period === '7d' ? 7 : 30;
    Promise.all([
      adminApi.overview(period),
      adminApi.revenueByDay(days),
      adminApi.topProducts(5, days),
      adminApi.categoryBreakdown(days),
      adminApi.lowStock(5),
    ])
      .then(([o, r, t, c, l]) => {
        if (cancelled) return;
        setOverview(o);
        setRevenue(r);
        setTop(t);
        setCategories(c);
        setLowStock(l);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [period]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Админ-панель</h1>
        <div className="flex bg-white rounded-lg border border-slate-200 p-1 shadow-sm">
          {(['7d', '30d'] as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-4 py-1.5 text-sm font-medium rounded transition-colors ${
                period === p ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {p === '7d' ? '7 дней' : '30 дней'}
            </button>
          ))}
        </div>
      </div>

      {loading && !overview ? (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-slate-900"></div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard
              label="Выручка"
              value={fmtRub(overview?.revenue || 0)}
              icon={Wallet}
              accent="bg-blue-600"
            />
            <KpiCard
              label="Заказов"
              value={String(overview?.orders_count || 0)}
              icon={ShoppingBag}
              accent="bg-violet-600"
            />
            <KpiCard
              label="Средний чек"
              value={fmtRub(overview?.aov || 0)}
              icon={TrendingUp}
              accent="bg-emerald-600"
            />
            <KpiCard
              label="Пользователи"
              value={`${overview?.total_users || 0} (+${overview?.new_users || 0})`}
              icon={UserPlus}
              accent="bg-amber-600"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">Выручка по дням</h2>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={revenue}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                    <Tooltip
                      formatter={(v: number) => fmtRub(v)}
                      contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0' }}
                    />
                    <Line type="monotone" dataKey="revenue" stroke="#2563eb" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
                <h2 className="text-lg font-semibold text-slate-900">Заканчиваются</h2>
              </div>
              {lowStock.length === 0 ? (
                <p className="text-sm text-slate-500">Все товары в достатке.</p>
              ) : (
                <ul className="space-y-2 max-h-72 overflow-auto">
                  {lowStock.map((p) => (
                    <li key={p.id} className="flex items-center justify-between text-sm">
                      <div className="min-w-0 mr-2">
                        <p className="font-medium text-slate-900 truncate">{p.name}</p>
                        <p className="text-xs text-slate-500">{p.category}</p>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          p.stock_quantity === 0
                            ? 'bg-red-100 text-red-700'
                            : 'bg-amber-100 text-amber-700'
                        }`}
                      >
                        {p.stock_quantity} шт
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">Продажи по категориям</h2>
              {categories.length === 0 ? (
                <p className="text-sm text-slate-500 py-12 text-center">Нет продаж за период.</p>
              ) : (
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={categories}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                      <Tooltip
                        formatter={(v: number) => fmtRub(v)}
                        contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0' }}
                      />
                      <Bar dataKey="revenue" radius={[6, 6, 0, 0]}>
                        {categories.map((_, i) => (
                          <Cell key={i} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">Топ-5 товаров</h2>
              {top.length === 0 ? (
                <p className="text-sm text-slate-500 py-12 text-center">Нет продаж за период.</p>
              ) : (
                <ul className="space-y-3">
                  {top.map((p, idx) => (
                    <li key={p.product_id} className="flex items-center gap-3 text-sm">
                      <span className="w-6 h-6 flex items-center justify-center rounded-full bg-slate-100 text-slate-700 text-xs font-semibold">
                        {idx + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-slate-900 truncate">{p.name}</p>
                        <p className="text-xs text-slate-500">{p.category} · {p.units} шт</p>
                      </div>
                      <span className="font-semibold text-slate-900">{fmtRub(p.revenue)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
