import api from './client';
import type { Product, ProductListResponse, ProductFilters, Category } from '../types';

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
      if (filters.min_price !== undefined) params.append('min_price', filters.min_price.toString());
      if (filters.max_price !== undefined) params.append('max_price', filters.max_price.toString());
      if (filters.color) params.append('color', filters.color);
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
};
