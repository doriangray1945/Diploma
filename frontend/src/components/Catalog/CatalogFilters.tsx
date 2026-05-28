import { useState, useEffect, useRef } from 'react';
import {
  Search,
  SlidersHorizontal,
  X,
  Sofa,
  Bed,
  Utensils,
  Baby,
  Briefcase,
  Shirt,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useProductsStore } from '../../stores';
import { productsApi } from '../../api/products';
import { COLOR_HEX } from '../../lib/colorMap';
import type { FilterOptions } from '../../types';
import clsx from 'clsx';

// Фиксированный список помещений с иконками. Захардкожен, потому что иконки
// привязаны к значениям: бэкенд может вернуть новое помещение, но без иконки
// оно в UI не появится. Если потребуется ещё одна комната — добавить сюда.
const ROOMS: { value: string; label: string; Icon: LucideIcon }[] = [
  { value: 'гостиная', label: 'Гостиная', Icon: Sofa },
  { value: 'спальня',  label: 'Спальня',  Icon: Bed },
  { value: 'кухня',    label: 'Кухня',    Icon: Utensils },
  { value: 'детская',  label: 'Детская',  Icon: Baby },
  { value: 'офис',     label: 'Офис',     Icon: Briefcase },
  { value: 'прихожая', label: 'Прихожая', Icon: Shirt },
];

// Порядок цветов в фильтре: нейтральные → радуга → прозрачный.
const COLOR_ORDER: string[] = [
  'Белый', 'Чёрный', 'Серый', 'Бежевый', 'Коричневый',
  'Красный', 'Оранжевый', 'Жёлтый', 'Зелёный',
  'Голубой', 'Синий', 'Фиолетовый', 'Розовый',
  'Прозрачный',
];

function sortColors(colors: string[]): string[] {
  const order = new Map(COLOR_ORDER.map((c, i) => [c, i]));
  return [...colors].sort((a, b) =>
    (order.get(a) ?? 999) - (order.get(b) ?? 999),
  );
}

export default function CatalogFilters() {
  const [showFilters, setShowFilters] = useState(false);
  const [filterOpts, setFilterOpts] = useState<FilterOptions | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  // Список реально присутствующих в БД помещений. Используется чтобы
  // скрыть кнопку «Прихожая» если ни у одного товара такого нет.
  const [availableRooms, setAvailableRooms] = useState<string[] | null>(null);
  const { filters, setFilters, clearFilters, categories } = useProductsStore();
  const prevFiltersRef = useRef(filters);

  // Auto-open filter panel when chat sets category/price filters
  useEffect(() => {
    const prev = prevFiltersRef.current;
    const hasNewFilters = filters.category !== prev.category
      || filters.subcategory !== prev.subcategory
      || filters.room !== prev.room
      || filters.min_price !== prev.min_price
      || filters.max_price !== prev.max_price
      || JSON.stringify(filters.color) !== JSON.stringify(prev.color)
      || JSON.stringify(filters.material) !== JSON.stringify(prev.material);
    if (hasNewFilters) {
      setShowFilters(true);
    }
    prevFiltersRef.current = filters;
  }, [filters]);

  useEffect(() => {
    setSearchQuery(filters.search || '');
  }, [filters.search]);

  // Load enum values for material/color and the list of rooms that actually
  // have products in the DB. Both one-shot on mount.
  useEffect(() => {
    productsApi.getFilterOptions().then(setFilterOpts).catch(() => {/* swallow */});
    productsApi.getRooms().then(setAvailableRooms).catch(() => {/* swallow */});
  }, []);

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
      delete newFilters.subcategory; // снимаем категорию → сбрасываем подкатегорию
      setFilters(newFilters);
    } else {
      const newFilters = { ...filters, category };
      delete newFilters.subcategory; // смена категории → старая подкатегория невалидна
      setFilters(newFilters);
    }
  };

  const handleSubcategorySelect = (subcategory: string) => {
    if (filters.subcategory === subcategory) {
      const newFilters = { ...filters };
      delete newFilters.subcategory;
      setFilters(newFilters);
    } else {
      setFilters({ ...filters, subcategory });
    }
  };

  const handleRoomSelect = (room: string) => {
    if (filters.room === room) {
      const newFilters = { ...filters };
      delete newFilters.room;
      setFilters(newFilters);
    } else {
      setFilters({ ...filters, room });
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = searchQuery.trim();
    const newFilters = { ...filters };
    if (value) {
      newFilters.search = value;
    } else {
      delete newFilters.search;
    }
    setFilters(newFilters);
  };

  const handleSearchClear = () => {
    setSearchQuery('');
    const newFilters = { ...filters };
    delete newFilters.search;
    setFilters(newFilters);
  };

  // Подкатегории доступной категории. Если категории нет — пустой массив,
  // блок «Подкатегория» скрыт.
  const activeCategory = filters.category
    ? categories.find((c) => c.name === filters.category)
    : null;
  const availableSubcategories = activeCategory?.subcategories ?? [];

  const toggleArrayValue = (
    field: 'color' | 'material',
    value: string,
  ) => {
    const current = filters[field] || [];
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    const newFilters = { ...filters };
    if (next.length === 0) {
      delete newFilters[field];
    } else {
      newFilters[field] = next;
    }
    setFilters(newFilters);
  };

  const hasActiveFilters =
    filters.category
    || filters.subcategory
    || filters.room
    || filters.min_price
    || filters.max_price
    || filters.search
    || (filters.color && filters.color.length > 0)
    || (filters.material && filters.material.length > 0);

  return (
    <div className="mb-6">
      <div className="max-w-2xl mb-6">
        <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">
          Подберите товары для <span className="text-primary-600">дома</span>
        </h1>
      </div>

      <form onSubmit={handleSearchSubmit} className="mb-5">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Найти что-нибудь"
            className="w-full pl-10 pr-10 py-3 bg-white border border-slate-200 rounded-full text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 transition-all"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={handleSearchClear}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
              aria-label="Очистить поиск"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </form>

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

          {/* Subcategories — shown only when a category is selected */}
          {availableSubcategories.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-medium text-slate-700 mb-2">Подкатегория</h4>
              <div className="flex flex-wrap gap-2">
                {availableSubcategories.map((sub) => (
                  <button
                    key={sub}
                    onClick={() => handleSubcategorySelect(sub)}
                    className={clsx(
                      'px-3 py-1.5 rounded-full text-sm transition-colors',
                      filters.subcategory === sub
                        ? 'bg-primary-600 text-white'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    )}
                  >
                    {sub}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Rooms — pill-кнопки с lucide-иконкой. Single-select.
              Показываем только те помещения, где есть товары (список с бэка). */}
          {(() => {
            // Пока availableRooms === null (ещё грузится) — показываем всё;
            // иначе — только те, что в БД.
            const visibleRooms = availableRooms
              ? ROOMS.filter((r) => availableRooms.includes(r.value))
              : ROOMS;
            if (visibleRooms.length === 0) return null;
            return (
              <div className="mb-4">
                <h4 className="text-sm font-medium text-slate-700 mb-2">Помещение</h4>
                <div className="flex flex-wrap gap-2">
                  {visibleRooms.map(({ value, label, Icon }) => {
                    const selected = filters.room === value;
                    return (
                      <button
                        key={value}
                        onClick={() => handleRoomSelect(value)}
                        className={clsx(
                          'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-colors',
                          selected
                            ? 'bg-primary-600 text-white'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        )}
                      >
                        <Icon className="w-4 h-4" />
                        {label}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })()}

          {/* Material — multi-select */}
          {filterOpts && filterOpts.materials.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-medium text-slate-700 mb-2">Материалы</h4>
              <div className="flex flex-wrap gap-2">
                {filterOpts.materials.map((m) => {
                  const selected = (filters.material || []).includes(m);
                  return (
                    <button
                      key={m}
                      onClick={() => toggleArrayValue('material', m)}
                      className={clsx(
                        'px-3 py-1.5 rounded-full text-sm transition-colors capitalize',
                        selected
                          ? 'bg-primary-600 text-white'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      )}
                    >
                      {m}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Color — multi-select со swatch-кружками */}
          {filterOpts && filterOpts.colors.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-medium text-slate-700 mb-2">Цвет</h4>
              <div className="flex flex-wrap gap-2">
                {sortColors(filterOpts.colors).map((c) => {
                  const selected = (filters.color || []).includes(c);
                  const hex = COLOR_HEX[c];
                  const isWhite = c === 'Белый';
                  const isTransparent = c === 'Прозрачный';
                  return (
                    <button
                      key={c}
                      onClick={() => toggleArrayValue('color', c)}
                      className={clsx(
                        'inline-flex items-center gap-2 pl-1.5 pr-3 py-1 rounded-full text-sm transition-colors',
                        selected
                          ? 'bg-primary-600 text-white'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                      )}
                    >
                      <span
                        className={clsx(
                          'w-5 h-5 rounded-full inline-block',
                          // белый и прозрачный нуждаются в видимой границе
                          (isWhite || isTransparent) && 'border border-slate-300',
                          // выделение swatch при выборе — белая кайма поверх primary
                          selected && 'ring-2 ring-white ring-offset-1 ring-offset-primary-600',
                        )}
                        style={
                          isTransparent
                            ? {
                                // чекерборд для прозрачного
                                backgroundImage:
                                  'linear-gradient(45deg, #cbd5e1 25%, transparent 25%),' +
                                  'linear-gradient(-45deg, #cbd5e1 25%, transparent 25%),' +
                                  'linear-gradient(45deg, transparent 75%, #cbd5e1 75%),' +
                                  'linear-gradient(-45deg, transparent 75%, #cbd5e1 75%)',
                                backgroundSize: '8px 8px',
                                backgroundPosition: '0 0, 0 4px, 4px -4px, -4px 0px',
                                backgroundColor: '#ffffff',
                              }
                            : { backgroundColor: hex ?? '#94a3b8' }
                        }
                        aria-hidden
                      />
                      {c}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

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
