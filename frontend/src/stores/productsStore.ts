import { create } from 'zustand';
import type { Product, ProductFilters, Category } from '../types';
import { productsApi } from '../api';

interface ProductsState {
  products: Product[];
  currentProduct: Product | null;
  categories: Category[];
  filters: ProductFilters;
  page: number;
  totalPages: number;
  total: number;
  isLoading: boolean;
  error: string | null;

  fetchProducts: (page?: number) => Promise<void>;
  fetchProduct: (id: number) => Promise<void>;
  fetchCategories: () => Promise<void>;
  setFilters: (filters: ProductFilters) => void;
  clearFilters: () => void;
  setPage: (page: number) => void;
}

export const useProductsStore = create<ProductsState>((set, get) => ({
  products: [],
  currentProduct: null,
  categories: [],
  filters: {},
  page: 1,
  totalPages: 1,
  total: 0,
  isLoading: false,
  error: null,

  fetchProducts: async (page?: number) => {
    const currentPage = page ?? get().page;
    set({ isLoading: true, error: null });

    try {
      const response = await productsApi.getProducts(currentPage, 12, get().filters);
      set({
        products: response.items,
        page: response.page,
        totalPages: response.pages,
        total: response.total,
        isLoading: false,
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка загрузки товаров';
      set({ error: message, isLoading: false });
    }
  },

  fetchProduct: async (id: number) => {
    set({ isLoading: true, error: null, currentProduct: null });

    try {
      const product = await productsApi.getProduct(id);
      set({ currentProduct: product, isLoading: false });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Товар не найден';
      set({ error: message, isLoading: false });
    }
  },

  fetchCategories: async () => {
    try {
      const categories = await productsApi.getCategories();
      set({ categories });
    } catch (error) {
      console.error('Failed to fetch categories:', error);
    }
  },

  setFilters: (filters: ProductFilters) => {
    set({ filters, page: 1 });
    get().fetchProducts(1);
  },

  clearFilters: () => {
    set({ filters: {}, page: 1 });
    get().fetchProducts(1);
  },

  setPage: (page: number) => {
    set({ page });
    get().fetchProducts(page);
  },
}));
