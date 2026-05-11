import { Plus, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import { COLOR_HEX, getColorHex } from '../../lib/colorMap';
import VariantImageUpload from './VariantImageUpload';
import type { AdminVariantUpdate } from '../../api/admin';

// Variants in the form are loosely-typed: existing rows have id, new rows
// don't. We use AdminVariantUpdate everywhere because it has all fields
// optional except (effectively) price.
export type FormVariant = AdminVariantUpdate;

const COLOR_OPTIONS = Object.keys(COLOR_HEX);

interface Props {
  variants: FormVariant[];
  onChange: (variants: FormVariant[]) => void;
}

function emptyVariant(): FormVariant {
  return {
    color: null,
    size_label: null,
    price: 0,
    old_price: null,
    stock_quantity: 0,
    images: [],
    sku: null,
    is_default: false,
    model_glb_url: null,
    model_usdz_url: null,
  };
}

export default function ProductVariantsTable({ variants, onChange }: Props) {
  const update = (idx: number, patch: Partial<FormVariant>) => {
    const next = variants.slice();
    next[idx] = { ...next[idx], ...patch };
    if (patch.is_default) {
      // Only one default allowed.
      next.forEach((v, i) => {
        if (i !== idx) v.is_default = false;
      });
    }
    onChange(next);
  };

  const remove = (idx: number) => {
    const next = variants.slice();
    const wasDefault = next[idx]?.is_default;
    next.splice(idx, 1);
    if (wasDefault && next.length > 0) next[0].is_default = true;
    onChange(next);
  };

  const add = () => {
    const next = [...variants, emptyVariant()];
    if (next.length === 1) next[0].is_default = true;
    onChange(next);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-slate-900">
          Варианты <span className="text-slate-400 font-normal">({variants.length})</span>
        </h3>
        <button
          type="button"
          onClick={add}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800"
        >
          <Plus className="w-4 h-4" />
          Добавить вариант
        </button>
      </div>

      {variants.length === 0 ? (
        <div className="border border-dashed border-slate-300 rounded-xl p-6 text-center text-slate-500 text-sm">
          У товара нет вариантов. Добавьте хотя бы один — он станет вариантом по умолчанию.
        </div>
      ) : (
        <div className="space-y-3">
          {variants.map((v, idx) => (
            <div
              key={v.id ?? `new-${idx}`}
              className="border border-slate-200 rounded-xl p-4 bg-slate-50"
            >
              <div className="grid grid-cols-12 gap-3 items-start">
                {/* Default radio */}
                <div className="col-span-12 sm:col-span-1 flex items-center pt-1.5">
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                    <input
                      type="radio"
                      name="default-variant"
                      checked={!!v.is_default}
                      onChange={() => update(idx, { is_default: true })}
                      className="text-primary-600"
                    />
                    <span className="sm:hidden">По умолчанию</span>
                  </label>
                </div>

                {/* Color */}
                <div className="col-span-6 sm:col-span-2">
                  <label className="block text-xs text-slate-500 mb-1">Цвет</label>
                  <div className="relative">
                    <select
                      value={v.color ?? ''}
                      onChange={(e) => update(idx, { color: e.target.value || null })}
                      className="w-full pl-7 pr-2 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                    >
                      <option value="">—</option>
                      {COLOR_OPTIONS.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                    <span
                      className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full border border-slate-300"
                      style={{ backgroundColor: getColorHex(v.color) }}
                    />
                  </div>
                </div>

                {/* Size */}
                <div className="col-span-6 sm:col-span-2">
                  <label className="block text-xs text-slate-500 mb-1">Размер</label>
                  <input
                    type="text"
                    value={v.size_label ?? ''}
                    onChange={(e) => update(idx, { size_label: e.target.value || null })}
                    placeholder="3-местный"
                    className="w-full px-2 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                  />
                </div>

                {/* Price */}
                <div className="col-span-4 sm:col-span-2">
                  <label className="block text-xs text-slate-500 mb-1">Цена ₽</label>
                  <input
                    type="number"
                    min={0}
                    value={v.price ?? 0}
                    onChange={(e) => update(idx, { price: Number(e.target.value) || 0 })}
                    className="w-full px-2 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                  />
                </div>

                {/* Old price */}
                <div className="col-span-4 sm:col-span-1">
                  <label className="block text-xs text-slate-500 mb-1">Старая</label>
                  <input
                    type="number"
                    min={0}
                    value={v.old_price ?? ''}
                    onChange={(e) =>
                      update(idx, {
                        old_price: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                    className="w-full px-2 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                  />
                </div>

                {/* Stock */}
                <div className="col-span-4 sm:col-span-1">
                  <label className="block text-xs text-slate-500 mb-1">Остаток</label>
                  <input
                    type="number"
                    min={0}
                    value={v.stock_quantity ?? 0}
                    onChange={(e) => update(idx, { stock_quantity: Number(e.target.value) || 0 })}
                    className="w-full px-2 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                  />
                </div>

                {/* SKU */}
                <div className="col-span-9 sm:col-span-2">
                  <label className="block text-xs text-slate-500 mb-1">SKU</label>
                  <input
                    type="text"
                    value={v.sku ?? ''}
                    onChange={(e) => update(idx, { sku: e.target.value || null })}
                    placeholder="(автоматически)"
                    className="w-full px-2 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                  />
                </div>

                {/* Delete */}
                <div className="col-span-3 sm:col-span-1 flex justify-end">
                  <button
                    type="button"
                    onClick={() => remove(idx)}
                    aria-label="Удалить вариант"
                    className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

                {/* Images */}
                <div className="col-span-12">
                  <label className="block text-xs text-slate-500 mb-1">Фото варианта</label>
                  <VariantImageUpload
                    images={v.images ?? []}
                    onChange={(images) => update(idx, { images })}
                  />
                </div>

                {/* 3D models — per variant. */}
                <div className="col-span-12 sm:col-span-6">
                  <label className="block text-xs text-slate-500 mb-1">3D-модель GLB (web + Android AR)</label>
                  <input
                    type="text"
                    value={v.model_glb_url ?? ''}
                    onChange={(e) => update(idx, { model_glb_url: e.target.value || null })}
                    placeholder="https://.../models/sofa-grey.glb"
                    className="w-full px-2 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                  />
                </div>
                <div className="col-span-12 sm:col-span-6">
                  <label className="block text-xs text-slate-500 mb-1">3D-модель USDZ (iOS AR)</label>
                  <input
                    type="text"
                    value={v.model_usdz_url ?? ''}
                    onChange={(e) => update(idx, { model_usdz_url: e.target.value || null })}
                    placeholder="https://.../models/sofa-grey.usdz"
                    className="w-full px-2 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <p className={clsx('text-xs text-slate-500 mt-3', variants.length === 0 && 'hidden')}>
        Радиокнопка «По умолчанию» помечает вариант, который показывается на витрине каталога.
      </p>
    </div>
  );
}
