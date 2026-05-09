import { NavLink } from 'react-router-dom';
import { LayoutGrid, Heart, ShoppingBag, Shield, X } from 'lucide-react';
import { useAuthStore, useFavoritesStore, useCartStore } from '../../stores';
import clsx from 'clsx';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

type NavItem = {
  to: string;
  icon: typeof LayoutGrid;
  label: string;
  countKey?: 'favorites' | 'cart';
  adminOnly?: boolean;
};

const navItems: NavItem[] = [
  { to: '/', icon: LayoutGrid, label: 'Каталог' },
  { to: '/favorites', icon: Heart, label: 'Избранное', countKey: 'favorites' },
  { to: '/orders', icon: ShoppingBag, label: 'Мои заказы' },
  { to: '/admin', icon: Shield, label: 'Админка', adminOnly: true },
];

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { user } = useAuthStore();
  const { favorites } = useFavoritesStore();
  const { items: cartItems } = useCartStore();

  const visibleItems = navItems.filter((item) => !item.adminOnly || user?.is_admin);

  const getCounts = (key?: 'favorites' | 'cart') => {
    if (key === 'favorites') return favorites.length;
    if (key === 'cart') return cartItems.length;
    return 0;
  };

  return (
    <aside
      className={clsx(
        'fixed lg:static inset-y-0 left-0 z-40 w-64 bg-white border-r border-slate-200 flex flex-col transform transition-transform duration-200 ease-out',
        'lg:transform-none',
        isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
      )}
    >
      {/* Logo + close button (mobile) */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-slate-200">
        <span className="text-xl font-bold text-slate-900">NF</span>
        <button
          onClick={onClose}
          className="lg:hidden p-1 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded"
          aria-label="Закрыть меню"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4">
        <ul className="space-y-1 px-3">
          {visibleItems.map((item) => {
            const count = item.countKey ? getCounts(item.countKey) : 0;

            return (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-slate-100 text-slate-900'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    )
                  }
                >
                  <item.icon className="w-5 h-5" />
                  <span className="flex-1">{item.label}</span>
                  {count > 0 && (
                    <span className="bg-slate-200 text-slate-700 text-xs px-2 py-0.5 rounded-full">
                      {count}
                    </span>
                  )}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
