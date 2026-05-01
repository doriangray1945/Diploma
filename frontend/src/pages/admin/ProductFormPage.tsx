import { FormEvent, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Plus, Trash2 } from 'lucide-react';
import {
  adminApi,
  type AdminProduct,
  type AdminProductCreate,
} from '../../api/admin';
import { productsApi } from '../../api/products';

const empty: AdminProductCreate = {
  name: '',
  description: '',
  price: 0,
  old_price: null,
  category: '',
  subcategory: null,
  images: [],
  dimensions: null,
  materials: null,
  color: null,
  in_stock: true,
  stock_quantity: 0,
  is_popular: false,
  is_new: false,
  model_glb_url: null,
  model_usdz_url: null,
};

export default function ProductFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(id);
  const [form, setForm] = useState<AdminProductCreate>(empty);
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
      .then((p) => {
        const { id: _id, rating: _r, reviews_count: _rc, created_at: _ca, updated_at: _ua, ...rest } =
          p as AdminProduct;
        setForm(rest as AdminProductCreate);
      })
      .catch(() => setError('Товар не найден'))
      .finally(() => setLoading(false));
  }, [id]);

  const update = <K extends keyof AdminProductCreate>(k: K, v: AdminProductCreate[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      if (isEdit && id) {
        await adminApi.updateProduct(Number(id), form);
      } else {
        await adminApi.createProduct(form);
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
        className="grid grid-cols-1 lg:grid-cols-2 gap-4 bg-white border border-slate-200 rounded-xl p-6 shadow-sm"
      >
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

        <Field label="Цена" required>
          <input
            type="number"
            min={0}
            required
            value={form.price}
            onChange={(e) => update('price', Number(e.target.value))}
            className="input"
          />
        </Field>

        <Field label="Старая цена (зачёркнутая)">
          <input
            type="number"
            min={0}
            value={form.old_price ?? ''}
            onChange={(e) => update('old_price', e.target.value ? Number(e.target.value) : null)}
            className="input"
          />
        </Field>

        <Field label="Остаток на складе">
          <input
            type="number"
            min={0}
            value={form.stock_quantity}
            onChange={(e) => update('stock_quantity', Number(e.target.value))}
            className="input"
          />
        </Field>

        <Field label="Цвет">
          <input
            type="text"
            value={form.color ?? ''}
            onChange={(e) => update('color', e.target.value || null)}
            className="input"
          />
        </Field>

        <Field label="Размеры">
          <input
            type="text"
            placeholder="200x90x85"
            value={form.dimensions ?? ''}
            onChange={(e) => update('dimensions', e.target.value || null)}
            className="input"
          />
        </Field>

        <Field label="Материалы" full>
          <input
            type="text"
            value={form.materials ?? ''}
            onChange={(e) => update('materials', e.target.value || null)}
            className="input"
          />
        </Field>

        <Field label="Описание" full>
          <textarea
            value={form.description}
            onChange={(e) => update('description', e.target.value)}
            rows={3}
            className="input"
          />
        </Field>

        <Field label="Картинки (URL)" full>
          <div className="space-y-2">
            {form.images.map((img, i) => (
              <div key={i} className="flex gap-2">
                <input
                  type="text"
                  value={img}
                  onChange={(e) => {
                    const next = [...form.images];
                    next[i] = e.target.value;
                    update('images', next);
                  }}
                  className="input flex-1"
                  placeholder="https://example.com/image.jpg"
                />
                <button
                  type="button"
                  onClick={() => update('images', form.images.filter((_, idx) => idx !== i))}
                  className="px-3 text-slate-500 hover:text-red-600"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => update('images', [...form.images, ''])}
              className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900"
            >
              <Plus className="w-4 h-4" /> Добавить картинку
            </button>
          </div>
        </Field>

        <Field label="3D-модель GLB (для десктопа и Android AR)" full>
          <input
            type="text"
            value={form.model_glb_url ?? ''}
            onChange={(e) => update('model_glb_url', e.target.value || null)}
            className="input"
            placeholder="/models/sofa.glb"
          />
          <p className="text-xs text-slate-500 mt-1">
            Положи файл в <code>frontend/public/models/</code> и впиши путь, начиная с <code>/models/</code>.
          </p>
        </Field>

        <Field label="3D-модель USDZ (для iOS AR Quick Look)" full>
          <input
            type="text"
            value={form.model_usdz_url ?? ''}
            onChange={(e) => update('model_usdz_url', e.target.value || null)}
            className="input"
            placeholder="/models/sofa.usdz"
          />
          <p className="text-xs text-slate-500 mt-1">
            На iPhone Safari эта модель откроется в нативном AR (с использованием LiDAR).
          </p>
        </Field>

        <div className="flex items-center gap-6 lg:col-span-2 pt-2">
          <label className="inline-flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.in_stock}
              onChange={(e) => update('in_stock', e.target.checked)}
            />
            В наличии
          </label>
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

        <div className="flex justify-end gap-2 lg:col-span-2 border-t border-slate-100 pt-4">
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
