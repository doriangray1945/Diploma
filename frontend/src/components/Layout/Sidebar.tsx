import { NavLink } from 'react-router-dom';
import { LayoutGrid, Heart, ShoppingBag, MessageCircle, HelpCircle, Shield } from 'lucide-react';
import { useAuthStore, useFavoritesStore, useCartStore } from '../../stores';
import clsx from 'clsx';

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

export default function Sidebar() {
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
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-slate-200">
        <span className="text-xl font-bold text-slate-900">NF</span>
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

        <div className="mt-8 px-3">
          <div className="border-t border-slate-200 pt-4">
            <ul className="space-y-1">
              <li>
                <a
                  href="#"
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors"
                >
                  <MessageCircle className="w-5 h-5" />
                  <span>Чаты</span>
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors"
                >
                  <HelpCircle className="w-5 h-5" />
                  <span>Поддержка</span>
                </a>
              </li>
            </ul>
          </div>
        </div>
      </nav>

      {/* Social links */}
      <div className="p-4 border-t border-slate-200">
        <div className="flex items-center gap-4 text-slate-400">
          <a href="#" className="hover:text-slate-600 transition-colors">
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073z"/>
            </svg>
          </a>
          <a href="#" className="hover:text-slate-600 transition-colors">
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-5.2 1.74 2.89 2.89 0 012.31-4.64 2.93 2.93 0 01.88.13V9.4a6.84 6.84 0 00-1-.05A6.33 6.33 0 005 20.1a6.34 6.34 0 0010.86-4.43v-7a8.16 8.16 0 004.77 1.52v-3.4a4.85 4.85 0 01-1-.1z"/>
            </svg>
          </a>
          <a href="#" className="hover:text-slate-600 transition-colors">
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
          </a>
        </div>
      </div>
    </aside>
  );
}
