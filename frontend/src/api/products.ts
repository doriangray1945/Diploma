import api from './client';
import type { Product, ProductListResponse, ProductFilters, Category, FilterOptions } from '../types';

export const productsApi = {
  getProducts: async (
    page: number = 1,
    perPage: number = 12,
    filters?: ProductFilters
  ): Promise<ProductListResponse> => {
    const params = new URLSearchParams();
    params.append('page', page.toString());
    params.append('per_page', perPage.toString());

    if (filters) {
      if (filters.category) params.append('category', filters.category);
      if (filters.subcategory) params.append('subcategory', filters.subcategory);
      if (filters.room) params.append('room', filters.room);
      if (filters.min_price !== undefined) params.append('min_price', filters.min_price.toString());
      if (filters.max_price !== undefined) params.append('max_price', filters.max_price.toString());
      // Multi-value: append one query-param per element. FastAPI parses
      // repeated keys into a list[str].
      if (filters.color && filters.color.length > 0) {
        for (const c of filters.color) params.append('color', c);
      }
      if (filters.material && filters.material.length > 0) {
        for (const m of filters.material) params.append('material', m);
      }
      if (filters.in_stock !== undefined) params.append('in_stock', filters.in_stock.toString());
      if (filters.is_popular !== undefined) params.append('is_popular', filters.is_popular.toString());
      if (filters.is_new !== undefined) params.append('is_new', filters.is_new.toString());
      if (filters.search) params.append('search', filters.search);
      if (filters.sort_by) params.append('sort_by', filters.sort_by);
      if (filters.sort_order) params.append('sort_order', filters.sort_order);
    }

    const response = await api.get<ProductListResponse>(`/products?${params.toString()}`);
    return response.data;
  },

  getProduct: async (id: number): Promise<Product> => {
    const response = await api.get<Product>(`/products/${id}`);
    return response.data;
  },

  getCategories: async (): Promise<Category[]> => {
    const response = await api.get<Category[]>('/products/categories');
    return response.data;
  },

  getFilterOptions: async (): Promise<FilterOptions> => {
    const response = await api.get<FilterOptions>('/products/filter-options');
    return response.data;
  },

  getRooms: async (): Promise<string[]> => {
    const response = await api.get<string[]>('/products/rooms');
    return response.data;
  },
};
