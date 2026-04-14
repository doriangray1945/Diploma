import { useEffect } from 'react';
import { useProductsStore, useAuthStore } from '../stores';
import { Chat } from '../components/Chat';
import { ProductCard } from '../components/ProductCard';
import { CatalogFilters, Pagination } from '../components/Catalog';
import { HelpCircle } from 'lucide-react';

export default function CatalogPage() {
  const { user } = useAuthStore();
  const { products, isLoading, total, fetchProducts, fetchCategories } = useProductsStore();

  useEffect(() => {
    fetchProducts();
    fetchCategories();
  }, [fetchProducts, fetchCategories]);

  return (
    <div className="max-w-6xl mx-auto">
      {/* AI Chat */}
      {user && <Chat />}

      {/* Filters */}
      <CatalogFilters />

      {/* Help button */}
      <div className="fixed bottom-6 right-6 z-50">
        <button className="bg-primary-600 text-white px-4 py-2.5 rounded-full shadow-lg hover:bg-primary-700 transition-colors flex items-center gap-2">
          <HelpCircle className="w-5 h-5" />
          Помощь
        </button>
      </div>

      {/* Products grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
        </div>
      ) : products.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-slate-500">Товары не найдены</p>
        </div>
      ) : (
        <>
          <p className="text-sm text-slate-500 mb-4">
            Найдено товаров: {total}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {products.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>

          <Pagination />
        </>
      )}
    </div>
  );
}
