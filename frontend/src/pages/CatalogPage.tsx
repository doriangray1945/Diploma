import { useEffect } from 'react';
import { useProductsStore, useAuthStore } from '../stores';
import { Chat } from '../components/Chat';
import { ProductCard } from '../components/ProductCard';
import { CatalogFilters, Pagination } from '../components/Catalog';

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

      {/* Products grid */}
      <div id="catalog-grid">
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
    </div>
  );
}
