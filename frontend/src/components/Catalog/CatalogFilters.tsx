import { useState, useEffect, useRef } from 'react';
import { SlidersHorizontal, X } from 'lucide-react';
import { useProductsStore } from '../../stores';
import clsx from 'clsx';

export default function CatalogFilters() {
  const [showFilters, setShowFilters] = useState(false);
  const { filters, setFilters, clearFilters, categories } = useProductsStore();
  const prevFiltersRef = useRef(filters);

  // Auto-open filter panel when chat sets category/price filters
  useEffect(() => {
    const prev = prevFiltersRef.current;
    const hasNewFilters = filters.category !== prev.category
      || filters.min_price !== prev.min_price
      || filters.max_price !== prev.max_price;
    if (hasNewFilters) {
      setShowFilters(true);
    }
    prevFiltersRef.current = filters;
  }, [filters]);

  const tabs = [
    { key: 'popular', label: 'Популярное', filter: { is_popular: true } },
    { key: 'new', label: 'Новое', filter: { is_new: true } },
  ];

  const activeTab = filters.is_popular ? 'popular' : filters.is_new ? 'new' : null;

  const handleTabClick = (tab: typeof tabs[0]) => {
    if (activeTab === tab.key) {
      const newFilters = { ...filters };
      delete newFilters.is_popular;
      delete newFilters.is_new;
      setFilters(newFilters);
    } else {
      const newFilters = { ...filters };
      delete newFilters.is_popular;
      delete newFilters.is_new;
      setFilters({ ...newFilters, ...tab.filter });
    }
  };

  const handleCategorySelect = (category: string) => {
    if (filters.category === category) {
      const newFilters = { ...filters };
      delete newFilters.category;
      setFilters(newFilters);
    } else {
      setFilters({ ...filters, category });
    }
  };

  const hasActiveFilters = filters.category || filters.min_price || filters.max_price || filters.search;

  return (
    <div className="mb-6">
      {/* Tabs + filter toggle */}
      <div className="flex items-center justify-center gap-2 mb-4">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => handleTabClick(tab)}
            className={clsx(
              'px-6 py-2.5 rounded-full text-sm font-medium transition-colors',
              activeTab === tab.key
                ? 'bg-slate-900 text-white'
                : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
            )}
          >
            {tab.label}
          </button>
        ))}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={clsx(
            'px-6 py-2.5 rounded-full text-sm font-medium transition-colors flex items-center gap-2',
            showFilters || hasActiveFilters
              ? 'bg-slate-900 text-white'
              : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
          )}
        >
          <SlidersHorizontal className="w-4 h-4" />
          Фильтры
          {hasActiveFilters && !showFilters && (
            <span className="w-2 h-2 bg-primary-400 rounded-full" />
          )}
        </button>

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="px-4 py-2.5 text-sm text-slate-500 hover:text-slate-700 transition-colors flex items-center gap-1"
          >
            <X className="w-4 h-4" />
            Сбросить
          </button>
        )}
      </div>

      {/* Expanded filters */}
      {showFilters && (
        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200 animate-in slide-in-from-top-2">
          {/* Categories */}
          <div className="mb-4">
            <h4 className="text-sm font-medium text-slate-700 mb-2">Категории</h4>
            <div className="flex flex-wrap gap-2">
              {categories.map((cat) => (
                <button
                  key={cat.name}
                  onClick={() => handleCategorySelect(cat.name)}
                  className={clsx(
                    'px-3 py-1.5 rounded-full text-sm transition-colors',
                    filters.category === cat.name
                      ? 'bg-primary-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  )}
                >
                  {cat.name} ({cat.count})
                </button>
              ))}
            </div>
          </div>

          {/* Price range */}
          <div>
            <h4 className="text-sm font-medium text-slate-700 mb-2">Цена</h4>
            <div className="flex items-center gap-2">
              <input
                type="number"
                placeholder="От"
                value={filters.min_price || ''}
                onChange={(e) =>
                  setFilters({
                    ...filters,
                    min_price: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                className="w-32 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
              <span className="text-slate-400">—</span>
              <input
                type="number"
                placeholder="До"
                value={filters.max_price || ''}
                onChange={(e) =>
                  setFilters({
                    ...filters,
                    max_price: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                className="w-32 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
              <span className="text-sm text-slate-500">₽</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}