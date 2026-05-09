import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Trash2, Pencil, Search, AlertTriangle } from 'lucide-react';
import { adminApi, type AdminProduct, type AdminVariant } from '../../api/admin';
import { productsApi } from '../../api/products';

function getDefaultVariant(p: AdminProduct): AdminVariant | null {
  return (
    p.variants.find((v) => v.id === p.default_variant_id) ??
    p.variants.find((v) => v.is_default) ??
    p.variants[0] ??
    null
  );
}

export default function ProductsPage() {
  const [items, setItems] = useState<AdminProduct[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const load = () => {
    setLoading(true);
    adminApi
      .listProducts({
        search: search || undefined,
        category: categoryFilter || undefined,
        low_stock: lowStockOnly || undefined,
        per_page: 100,
      })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    productsApi.getCategories().then((cats) => setCategories(cats.map((c) => c.name)));
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, categoryFilter, lowStockOnly]);

  const patchVariantField = async (
    productId: number,
    variantId: number,
    field: 'price' | 'stock_quantity',
    value: number,
  ) => {
    setSavingIds((s) => new Set(s).add(productId));
    try {
      const updatedVariant = await adminApi.updateVariant(variantId, { [field]: value });
      setItems((prev) =>
        prev.map((p) =>
          p.id === productId
            ? {
                ...p,
                variants: p.variants.map((v) => (v.id === variantId ? updatedVariant : v)),
              }
            : p,
        ),
      );
    } finally {
      setSavingIds((s) => {
        const next = new Set(s);
        next.delete(productId);
        return next;
      });
    }
  };

  const remove = async (id: number) => {
    if (!confirm('Удалить товар? Это действие нельзя отменить.')) return;
    setDeletingId(id);
    try {
      await adminApi.deleteProduct(id);
      setItems((prev) => prev.filter((p) => p.id !== id));
      setTotal((t) => t - 1);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Товары</h1>
          <p className="text-sm text-slate-500">Всего: {total}</p>
        </div>
        <Link
          to="/admin/products/new"
          className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800"
        >
          <Plus className="w-4 h-4" />
          Добавить товар
        </Link>
      </div>

      <div className="flex flex-wrap gap-3 bg-white border border-slate-200 rounded-xl p-3 shadow-sm">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по названию или описанию"
            className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-slate-400"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-slate-400"
        >
          <option value="">Все категории</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <label className="inline-flex items-center gap-2 px-3 py-2 border border-slate-200 rounded-lg text-sm cursor-pointer hover:bg-slate-50">
          <input
            type="checkbox"
            checked={lowStockOnly}
            onChange={(e) => setLowStockOnly(e.target.checked)}
            className="rounded"
          />
          Только заканчивающиеся
        </label>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-12 text-center">
            <div className="animate-spin inline-block rounded-full h-8 w-8 border-b-2 border-slate-900" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-slate-500">Ничего не найдено.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
                <tr>
                  <th className="px-4 py-3 text-left">Товар</th>
                  <th className="px-4 py-3 text-left">Категория</th>
                  <th className="px-4 py-3 text-right">Цена</th>
                  <th className="px-4 py-3 text-right">Остаток</th>
                  <th className="px-4 py-3 text-center">Статус</th>
                  <th className="px-4 py-3 text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((p) => {
                  const dv = getDefaultVariant(p);
                  const dvImages = dv?.images ?? [];
                  return (
                  <tr key={p.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3 max-w-md">
                        {dvImages[0] ? (
                          <img
                            src={dvImages[0]}
                            alt=""
                            className="w-10 h-10 rounded object-cover bg-slate-100"
                            onError={(e) => ((e.target as HTMLImageElement).style.visibility = 'hidden')}
                          />
                        ) : (
                          <div className="w-10 h-10 rounded bg-slate-100" />
                        )}
                        <div className="min-w-0">
                          <p className="font-medium text-slate-900 truncate">{p.name}</p>
                          <p className="text-xs text-slate-500 truncate">
                            {p.variants.length} вариант{p.variants.length === 1 ? '' : p.variants.length < 5 ? 'а' : 'ов'}
                            {dv?.color ? ` · ${dv.color}` : ''}
                            {dv?.size_label ? ` · ${dv.size_label}` : ''}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{p.category}</td>
                    <td className="px-4 py-3 text-right">
                      <input
                        type="number"
                        min={0}
                        defaultValue={dv?.price ?? 0}
                        disabled={!dv || savingIds.has(p.id)}
                        onBlur={(e) => {
                          if (!dv) return;
                          const v = Number(e.target.value);
                          if (!Number.isNaN(v) && v !== dv.price) patchVariantField(p.id, dv.id, 'price', v);
                        }}
                        className="w-24 px-2 py-1 text-right border border-slate-200 rounded focus:outline-none focus:border-slate-400"
                      />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <input
                        type="number"
                        min={0}
                        defaultValue={dv?.stock_quantity ?? 0}
                        disabled={!dv || savingIds.has(p.id)}
                        onBlur={(e) => {
                          if (!dv) return;
                          const v = Number(e.target.value);
                          if (!Number.isNaN(v) && v !== dv.stock_quantity)
                            patchVariantField(p.id, dv.id, 'stock_quantity', v);
                        }}
                        className="w-20 px-2 py-1 text-right border border-slate-200 rounded focus:outline-none focus:border-slate-400"
                      />
                    </td>
                    <td className="px-4 py-3 text-center">
                      {!dv?.in_stock ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">
                          <AlertTriangle className="w-3 h-3" /> Нет
                        </span>
                      ) : (dv?.stock_quantity ?? 0) < 5 ? (
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
                          Мало
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700">
                          В наличии
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Link
                          to={`/admin/products/${p.id}/edit`}
                          className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded"
                          title="Редактировать"
                        >
                          <Pencil className="w-4 h-4" />
                        </Link>
                        <button
                          onClick={() => remove(p.id)}
                          disabled={deletingId === p.id}
                          className="p-1.5 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded disabled:opacity-50"
                          title="Удалить"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
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
