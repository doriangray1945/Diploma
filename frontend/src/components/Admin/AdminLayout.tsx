import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, Package, Tags, ClipboardList, Users, Boxes } from 'lucide-react';
import clsx from 'clsx';

const adminNav = [
  { to: '/admin', end: true, icon: LayoutDashboard, label: 'Дашборд' },
  { to: '/admin/products', icon: Package, label: 'Товары' },
  { to: '/admin/categories', icon: Tags, label: 'Категории' },
  { to: '/admin/orders', icon: ClipboardList, label: 'Заказы' },
  { to: '/admin/users', icon: Users, label: 'Пользователи' },
  { to: '/admin/inventory', icon: Boxes, label: 'Инвентарь' },
];

export default function AdminLayout() {
  return (
    <div className="space-y-6">
      <nav className="flex flex-wrap gap-1 bg-white rounded-xl border border-slate-200 p-1.5 shadow-sm">
        {adminNav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-slate-900 text-white'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              )
            }
          >
            <item.icon className="w-4 h-4" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
