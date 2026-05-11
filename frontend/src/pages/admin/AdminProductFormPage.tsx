import { FormEvent, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import {
  adminApi,
  type AdminProduct,
  type AdminProductCreate,
  type AdminProductUpdate,
  type AdminVariantUpdate,
} from '../../api/admin';
import { productsApi } from '../../api/products';
import ProductVariantsTable, { type FormVariant } from '../../components/Admin/ProductVariantsTable';

interface ProductFormState {
  name: string;
  description: string;
  category: string;
  subcategory: string | null;
  materials: string | null;
  dimensions_w: number | null;
  dimensions_d: number | null;
  dimensions_h: number | null;
  is_popular: boolean;
  is_new: boolean;
}

const empty: ProductFormState = {
  name: '',
  description: '',
  category: '',
  subcategory: null,
  materials: null,
  dimensions_w: null,
  dimensions_d: null,
  dimensions_h: null,
  is_popular: false,
  is_new: false,
};

const emptyVariant = (isFirst: boolean): FormVariant => ({
  color: null,
  size_label: null,
  price: 0,
  old_price: null,
  stock_quantity: 0,
  images: [],
  sku: null,
  is_default: isFirst,
  model_glb_url: null,
  model_usdz_url: null,
});

export default function ProductFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(id);
  const [form, setForm] = useState<ProductFormState>(empty);
  const [variants, setVariants] = useState<FormVariant[]>([emptyVariant(true)]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    productsApi.getCategories().then((cats) => setCategories(cats.map((c) => c.name)));
  }, []);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    adminApi
      .getProduct(Number(id))
      .then((p: AdminProduct) => {
        setForm({
          name: p.name,
          description: p.description,
          category: p.category,
          subcategory: p.subcategory ?? null,
          materials: p.materials ?? null,
          dimensions_w: p.dimensions?.width ?? null,
          dimensions_d: p.dimensions?.depth ?? null,
          dimensions_h: p.dimensions?.height ?? null,
          is_popular: p.is_popular,
          is_new: p.is_new,
        });
        setVariants(
          p.variants.map((v): AdminVariantUpdate => ({
            id: v.id,
            color: v.color,
            size_label: v.size_label,
            dimensions: v.dimensions,
            price: v.price,
            old_price: v.old_price,
            stock_quantity: v.stock_quantity,
            images: v.images,
            sku: v.sku,
            is_default: v.is_default,
            model_glb_url: v.model_glb_url ?? null,
            model_usdz_url: v.model_usdz_url ?? null,
          })),
        );
      })
      .catch(() => setError('Товар не найден'))
      .finally(() => setLoading(false));
  }, [id]);

  const update = <K extends keyof ProductFormState>(k: K, v: ProductFormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const dimensions = (() => {
    const { dimensions_w: w, dimensions_d: d, dimensions_h: h } = form;
    if (w == null && d == null && h == null) return null;
    return { width: w ?? 0, depth: d ?? 0, height: h ?? 0 };
  })();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (variants.length === 0) {
      setError('Добавьте хотя бы один вариант');
      return;
    }
    if (!variants.some((v) => v.is_default)) {
      // Force the first variant as default if user removed all defaults.
      variants[0].is_default = true;
    }
    setSaving(true);
    try {
      if (isEdit && id) {
        const payload: AdminProductUpdate = {
          name: form.name,
          description: form.description,
          category: form.category,
          subcategory: form.subcategory,
          materials: form.materials,
          dimensions,
          is_popular: form.is_popular,
          is_new: form.is_new,
          variants,
        };
        await adminApi.updateProduct(Number(id), payload);
      } else {
        const payload: AdminProductCreate = {
          name: form.name,
          description: form.description,
          category: form.category,
          subcategory: form.subcategory,
          materials: form.materials,
          dimensions,
          is_popular: form.is_popular,
          is_new: form.is_new,
          variants: variants.map((v) => ({
            color: v.color,
            size_label: v.size_label,
            dimensions: v.dimensions,
            price: v.price ?? 0,
            old_price: v.old_price ?? null,
            stock_quantity: v.stock_quantity ?? 0,
            images: v.images ?? [],
            sku: v.sku,
            is_default: v.is_default,
            model_glb_url: v.model_glb_url ?? null,
            model_usdz_url: v.model_usdz_url ?? null,
          })),
        };
        await adminApi.createProduct(payload);
      }
      navigate('/admin/products');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Не удалось сохранить');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-slate-900" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <button
        onClick={() => navigate('/admin/products')}
        className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft className="w-4 h-4" /> Назад к списку
      </button>

      <h1 className="text-2xl font-bold text-slate-900">
        {isEdit ? 'Редактирование товара' : 'Новый товар'}
      </h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}

      <form
        onSubmit={submit}
        className="space-y-6 bg-white border border-slate-200 rounded-xl p-6 shadow-sm"
      >
        {/* Product-level fields */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Field label="Название" required>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
              className="input"
            />
          </Field>

          <Field label="Категория" required>
            <input
              list="cat-list"
              required
              value={form.category}
              onChange={(e) => update('category', e.target.value)}
              className="input"
              placeholder="Например: Диваны"
            />
            <datalist id="cat-list">
              {categories.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </Field>

          <Field label="Подкатегория">
            <input
              type="text"
              value={form.subcategory ?? ''}
              onChange={(e) => update('subcategory', e.target.value || null)}
              className="input"
            />
          </Field>

          <Field label="Материалы">
            <input
              type="text"
              value={form.materials ?? ''}
              onChange={(e) => update('materials', e.target.value || null)}
              className="input"
              placeholder="ткань, дерево"
            />
          </Field>

          <Field label="Размеры (ШxГxВ см)" full>
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                placeholder="Ширина"
                min={0}
                value={form.dimensions_w ?? ''}
                onChange={(e) =>
                  update('dimensions_w', e.target.value === '' ? null : Number(e.target.value))
                }
                className="input"
              />
              <input
                type="number"
                placeholder="Глубина"
                min={0}
                value={form.dimensions_d ?? ''}
                onChange={(e) =>
                  update('dimensions_d', e.target.value === '' ? null : Number(e.target.value))
                }
                className="input"
              />
              <input
                type="number"
                placeholder="Высота"
                min={0}
                value={form.dimensions_h ?? ''}
                onChange={(e) =>
                  update('dimensions_h', e.target.value === '' ? null : Number(e.target.value))
                }
                className="input"
              />
            </div>
          </Field>

          <Field label="Описание" full>
            <textarea
              value={form.description}
              onChange={(e) => update('description', e.target.value)}
              rows={3}
              className="input"
            />
          </Field>

          <div className="flex items-center gap-6 lg:col-span-2 pt-2">
            <label className="inline-flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.is_popular}
                onChange={(e) => update('is_popular', e.target.checked)}
              />
              Популярный
            </label>
            <label className="inline-flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.is_new}
                onChange={(e) => update('is_new', e.target.checked)}
              />
              Новинка
            </label>
          </div>
        </div>

        {/* Variants section */}
        <div className="border-t border-slate-200 pt-6">
          <ProductVariantsTable variants={variants} onChange={setVariants} />
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
          <button
            type="button"
            onClick={() => navigate('/admin/products')}
            className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900"
          >
            Отмена
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50"
          >
            {saving ? 'Сохранение…' : isEdit ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  children,
  required,
  full,
}: {
  label: string;
  children: React.ReactNode;
  required?: boolean;
  full?: boolean;
}) {
  return (
    <div className={full ? 'lg:col-span-2' : undefined}>
      <label className="block text-sm font-medium text-slate-700 mb-1">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      {children}
    </div>
  );
}
