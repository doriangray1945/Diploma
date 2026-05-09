import { useEffect, useState } from 'react';
import { Search, Shield, ShieldOff, Crown } from 'lucide-react';
import { adminApi, type AdminUser } from '../../api/admin';
import { useAuthStore } from '../../stores';

const fmtDate = (s: string) => new Date(s).toLocaleDateString('ru-RU');

export default function UsersPage() {
  const me = useAuthStore((s) => s.user);
  const [items, setItems] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    adminApi.listUsers(search || undefined).then(setItems).finally(() => setLoading(false));
  };

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const toggle = async (u: AdminUser) => {
    setError(null);
    setSavingIds((s) => new Set(s).add(u.id));
    try {
      const updated = await adminApi.setUserAdmin(u.id, !u.is_admin);
      setItems((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Не удалось изменить роль');
    } finally {
      setSavingIds((s) => {
        const n = new Set(s);
        n.delete(u.id);
        return n;
      });
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Пользователи</h1>

      <div className="relative max-w-md">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по email или имени"
          className="w-full pl-9 pr-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-slate-400"
        />
      </div>

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
          <div className="p-12 text-center text-slate-500">Никого не найдено.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">Email</th>
                <th className="px-4 py-3 text-left">Имя</th>
                <th className="px-4 py-3 text-right">Заказов</th>
                <th className="px-4 py-3 text-left">Регистрация</th>
                <th className="px-4 py-3 text-center">Роль</th>
                <th className="px-4 py-3 text-right"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((u) => {
                const isMe = me?.id === u.id;
                const targetIsSuper = u.is_superadmin;
                const meIsSuper = !!me?.is_superadmin;
                const blockedBySuperRule = targetIsSuper && !meIsSuper;
                const disabled = isMe || blockedBySuperRule || savingIds.has(u.id);
                const tooltip = isMe
                  ? 'Нельзя снять роль с себя'
                  : blockedBySuperRule
                  ? 'Только супер-админ может изменить эту роль'
                  : undefined;
                return (
                  <tr key={u.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-slate-900">
                      {u.email} {isMe && <span className="text-xs text-slate-400">(вы)</span>}
                    </td>
                    <td className="px-4 py-3 text-slate-700">{u.name}</td>
                    <td className="px-4 py-3 text-right text-slate-700">{u.orders_count}</td>
                    <td className="px-4 py-3 text-slate-500">{fmtDate(u.created_at)}</td>
                    <td className="px-4 py-3 text-center">
                      {u.is_superadmin ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-violet-100 text-violet-700">
                          <Crown className="w-3 h-3" /> Супер-админ
                        </span>
                      ) : u.is_admin ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">
                          <Shield className="w-3 h-3" /> Админ
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600">
                          Пользователь
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => toggle(u)}
                        disabled={disabled}
                        className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium ${
                          u.is_admin
                            ? 'text-red-700 bg-red-50 hover:bg-red-100'
                            : 'text-slate-700 bg-slate-100 hover:bg-slate-200'
                        } disabled:opacity-40 disabled:cursor-not-allowed`}
                        title={tooltip}
                      >
                        {u.is_admin ? (
                          <>
                            <ShieldOff className="w-3 h-3" /> Снять админа
                          </>
                        ) : (
                          <>
                            <Shield className="w-3 h-3" /> Сделать админом
                          </>
                        )}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
