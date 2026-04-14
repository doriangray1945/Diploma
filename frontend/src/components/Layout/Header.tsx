import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search, ShoppingCart, User, LogOut } from 'lucide-react';
import { useAuthStore, useCartStore, useProductsStore } from '../../stores';

export default function Header() {
  const [searchQuery, setSearchQuery] = useState('');
  const { user, logout } = useAuthStore();
  const { items: cartItems } = useCartStore();
  const { setFilters } = useProductsStore();
  const navigate = useNavigate();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      setFilters({ search: searchQuery.trim() });
      navigate('/');
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center px-6 gap-4">
      {/* Search */}
      <form onSubmit={handleSearch} className="flex-1 max-w-xl">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Найти что-нибудь"
            className="w-full pl-10 pr-4 py-2.5 bg-slate-100 border-0 rounded-full text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:bg-white transition-all"
          />
        </div>
      </form>

      {/* Actions */}
      <div className="flex items-center gap-3">
        {user ? (
          <>
            {/* Cart */}
            <Link
              to="/cart"
              className="relative p-2.5 text-slate-600 hover:bg-slate-100 rounded-full transition-colors"
            >
              <ShoppingCart className="w-5 h-5" />
              {cartItems.length > 0 && (
                <span className="absolute -top-1 -right-1 bg-primary-600 text-white text-xs w-5 h-5 flex items-center justify-center rounded-full">
                  {cartItems.length}
                </span>
              )}
            </Link>

            {/* User menu */}
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 bg-red-500 rounded-full flex items-center justify-center text-white font-medium">
                {user.name.charAt(0).toUpperCase()}
              </div>
              <button
                onClick={handleLogout}
                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors"
                title="Выйти"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          </>
        ) : (
          <Link
            to="/login"
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-full text-sm font-medium hover:bg-primary-700 transition-colors"
          >
            <User className="w-4 h-4" />
            Войти
          </Link>
        )}
      </div>
    </header>
  );
}
