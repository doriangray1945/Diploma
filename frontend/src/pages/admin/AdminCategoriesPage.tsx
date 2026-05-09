import { FormEvent, useEffect, useState } from 'react';
import { Plus, Trash2, Pencil, Check, X } from 'lucide-react';
import { adminApi, type AdminCategory } from '../../api/admin';

export default function CategoriesPage() {
  const [items, setItems] = useState<AdminCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');

  const load = () => {
    setLoading(true);
    adminApi.listCategories().then(setItems).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!newName.trim()) return;
    try {
      await adminApi.createCategory({ name: newName.trim() });
      setNewName('');
      load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Не удалось создать');
    }
  };

  const startEdit = (c: AdminCategory) => {
    setEditingId(c.id);
    setEditName(c.name);
    setError(null);
  };

  const saveEdit = async (id: number) => {
    if (!editName.trim()) return;
    try {
      await adminApi.updateCategory(id, { name: editName.trim() });
      setEditingId(null);
      load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Не удалось сохранить');
    }
  };

  const remove = async (c: AdminCategory) => {
    setError(null);
    if (c.products_count > 0) {
      setError(`Нельзя удалить «${c.name}» — в категории ${c.products_count} товар(ов).`);
      return;
    }
    if (!confirm(`Удалить категорию «${c.name}»?`)) return;
    try {
      await adminApi.deleteCategory(c.id);
      load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Не удалось удалить');
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Категории</h1>

      <form
        onSubmit={create}
        className="flex gap-2 bg-white border border-slate-200 rounded-xl p-3 shadow-sm"
      >
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Новая категория, например «Полки»"
          className="input flex-1"
        />
        <button
          type="submit"
          className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800"
        >
          <Plus className="w-4 h-4" />
          Добавить
        </button>
      </form>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-12 text-center">
            <div className="animate-spin inline-block rounded-full h-8 w-8 border-b-2 border-slate-900" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-slate-500">Пока нет категорий.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">Название</th>
                <th className="px-4 py-3 text-right">Товаров</th>
                <th className="px-4 py-3 text-right"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    {editingId === c.id ? (
                      <input
                        autoFocus
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveEdit(c.id);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        className="input"
                      />
                    ) : (
                      <span className="font-medium text-slate-900">{c.name}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-600">{c.products_count}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {editingId === c.id ? (
                        <>
                          <button
                            onClick={() => saveEdit(c.id)}
                            className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded"
                            title="Сохранить"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            className="p-1.5 text-slate-500 hover:bg-slate-100 rounded"
                            title="Отмена"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => startEdit(c)}
                            className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded"
                            title="Переименовать"
                          >
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => remove(c)}
                            className="p-1.5 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded disabled:opacity-50"
                            title="Удалить"
                            disabled={c.products_count > 0}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
