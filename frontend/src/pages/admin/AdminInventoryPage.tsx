import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Boxes, CheckCircle2, XCircle, AlertTriangle, Pencil } from 'lucide-react';
import {
  adminApi,
  type AdminProduct,
  type InventorySummary,
} from '../../api/admin';

function StatCard({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string | number;
  icon: typeof Boxes;
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

export default function InventoryPage() {
  const [threshold, setThreshold] = useState(5);
  const [summary, setSummary] = useState<InventorySummary | null>(null);
  const [items, setItems] = useState<AdminProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());

  const load = () => {
    setLoading(true);
    Promise.all([
      adminApi.inventorySummary(threshold),
      adminApi.listProducts({ low_stock: true, threshold, per_page: 100 }),
    ])
      .then(([s, p]) => {
        setSummary(s);
        setItems(p.items);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threshold]);

  const adjust = async (id: number, variantId: number, value: number) => {
    setSavingIds((s) => new Set(s).add(id));
    try {
      const updatedVariant = await adminApi.updateVariant(variantId, { stock_quantity: value });
      setItems((prev) =>
        prev.map((p) =>
          p.id === id
            ? {
                ...p,
                variants: p.variants.map((v) => (v.id === variantId ? updatedVariant : v)),
              }
            : p,
        ),
      );
      setSummary(await adminApi.inventorySummary(threshold));
    } finally {
      setSavingIds((s) => {
        const next = new Set(s);
        next.delete(id);
        return next;
      });
    }
  };

  const getDefaultVariant = (p: AdminProduct) =>
    p.variants.find((v) => v.id === p.default_variant_id) ??
    p.variants.find((v) => v.is_default) ??
    p.variants[0] ??
    null;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Инвентарь</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Всего товаров"
          value={summary?.total_products ?? '—'}
          icon={Boxes}
          accent="bg-slate-700"
        />
        <StatCard
          label="В наличии"
          value={summary?.in_stock ?? '—'}
          icon={CheckCircle2}
          accent="bg-emerald-600"
        />
        <StatCard
          label="Нет в наличии"
          value={summary?.out_of_stock ?? '—'}
          icon={XCircle}
          accent="bg-red-600"
        />
        <StatCard
          label={`Заканчиваются (<${threshold})`}
          value={summary?.low_stock_count ?? '—'}
          icon={AlertTriangle}
          accent="bg-amber-600"
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-3 flex items-center gap-3 shadow-sm">
        <label className="text-sm text-slate-600">Порог «мало»:</label>
        <input
          type="number"
          min={0}
          max={1000}
          value={threshold}
          onChange={(e) => setThreshold(Math.max(0, Number(e.target.value) || 0))}
          className="w-24 px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-slate-400"
        />
        <span className="text-xs text-slate-500">показываем товары с остатком меньше указанного</span>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-12 text-center">
            <div className="animate-spin inline-block rounded-full h-8 w-8 border-b-2 border-slate-900" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            Нет товаров с остатком ниже порога — всё в норме.
          </div>
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[600px]">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">Товар</th>
                <th className="px-4 py-3 text-left">Категория</th>
                <th className="px-4 py-3 text-right">Остаток</th>
                <th className="px-4 py-3 text-center">Статус</th>
                <th className="px-4 py-3 text-right"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((p) => {
                const dv = getDefaultVariant(p);
                const stock = dv?.stock_quantity ?? 0;
                return (
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <p className="font-medium text-slate-900">{p.name}</p>
                    {dv && (dv.color || dv.size_label) && (
                      <p className="text-xs text-slate-500">
                        {[dv.color, dv.size_label].filter(Boolean).join(' · ')}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{p.category}</td>
                  <td className="px-4 py-3 text-right">
                    <input
                      type="number"
                      min={0}
                      defaultValue={stock}
                      disabled={!dv || savingIds.has(p.id)}
                      onBlur={(e) => {
                        if (!dv) return;
                        const v = Number(e.target.value);
                        if (!Number.isNaN(v) && v !== stock) adjust(p.id, dv.id, v);
                      }}
                      className="w-20 px-2 py-1 text-right border border-slate-200 rounded focus:outline-none focus:border-slate-400"
                    />
                  </td>
                  <td className="px-4 py-3 text-center">
                    {stock === 0 ? (
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">
                        Нет
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
                        Мало
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`/admin/products/${p.id}/edit`}
                      className="inline-flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900"
                    >
                      <Pencil className="w-3 h-3" /> карточка
                    </Link>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}
