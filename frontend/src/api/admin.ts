import api from './client';

export interface StatsOverview {
  revenue: number;
  orders_count: number;
  aov: number;
  new_users: number;
  period_start: string;
  period_end: string;
}

export interface RevenuePoint {
  date: string;
  revenue: number;
}

export interface TopProduct {
  product_id: number;
  name: string;
  category: string;
  units: number;
  revenue: number;
}

export interface CategoryBreakdown {
  category: string;
  revenue: number;
  units: number;
}

export interface LowStockProduct {
  id: number;
  name: string;
  category: string;
  stock_quantity: number;
  in_stock: boolean;
}

export interface InventorySummary {
  total_products: number;
  in_stock: number;
  out_of_stock: number;
  low_stock_count: number;
}

export interface AdminVariant {
  id: number;
  product_id: number;
  color?: string | null;
  size_label?: string | null;
  dimensions?: { width: number; depth: number; height: number } | null;
  price: number;
  old_price?: number | null;
  stock_quantity: number;
  in_stock: boolean;
  images: string[];
  sku?: string | null;
  is_default: boolean;
}

export interface AdminVariantCreate {
  color?: string | null;
  size_label?: string | null;
  dimensions?: { width: number; depth: number; height: number } | null;
  price: number;
  old_price?: number | null;
  stock_quantity?: number;
  images?: string[];
  sku?: string | null;
  is_default?: boolean;
}

export interface AdminVariantUpdate {
  // Optional id lets the parent PATCH /admin/products/{id} sync the list
  // (id present → update; id missing → insert; absent ids → delete).
  id?: number;
  color?: string | null;
  size_label?: string | null;
  dimensions?: { width: number; depth: number; height: number } | null;
  price?: number;
  old_price?: number | null;
  stock_quantity?: number;
  images?: string[];
  sku?: string | null;
  is_default?: boolean;
}

export interface AdminProduct {
  id: number;
  name: string;
  description: string;
  category: string;
  subcategory?: string | null;
  materials?: string | null;
  dimensions?: { width: number; depth: number; height: number } | null;
  rating: number;
  reviews_count: number;
  is_popular: boolean;
  is_new: boolean;
  model_glb_url?: string | null;
  model_usdz_url?: string | null;
  default_variant_id: number | null;
  variants: AdminVariant[];
  created_at: string;
  updated_at: string;
}

export interface AdminProductListResponse {
  items: AdminProduct[];
  total: number;
}

export interface AdminProductFilters {
  search?: string;
  category?: string;
  in_stock?: boolean;
  low_stock?: boolean;
  threshold?: number;
  sort_by?: 'created_at' | 'name';
  sort_order?: 'asc' | 'desc';
  page?: number;
  per_page?: number;
}

export interface AdminProductCreate {
  name: string;
  description: string;
  category: string;
  subcategory?: string | null;
  materials?: string | null;
  dimensions?: { width: number; depth: number; height: number } | null;
  is_popular?: boolean;
  is_new?: boolean;
  model_glb_url?: string | null;
  model_usdz_url?: string | null;
  variants: AdminVariantCreate[];
}

export interface AdminProductUpdate {
  name?: string;
  description?: string;
  category?: string;
  subcategory?: string | null;
  materials?: string | null;
  dimensions?: { width: number; depth: number; height: number } | null;
  is_popular?: boolean;
  is_new?: boolean;
  model_glb_url?: string | null;
  model_usdz_url?: string | null;
  variants?: AdminVariantUpdate[];
}

export interface AdminCategory {
  id: number;
  name: string;
  slug?: string | null;
  sort_order: number;
  created_at: string;
  products_count: number;
}

export interface AdminUser {
  id: number;
  email: string;
  name: string;
  phone?: string | null;
  is_admin: boolean;
  is_superadmin: boolean;
  created_at: string;
  orders_count: number;
}

export type OrderStatus = 'pending' | 'confirmed' | 'shipping' | 'delivered' | 'cancelled';

export interface AdminOrderItem {
  id: number;
  product_id?: number | null;
  product_name: string;
  quantity: number;
  price: number;
}

export interface AdminOrder {
  id: number;
  user_id: number;
  user_email: string;
  user_name: string;
  status: OrderStatus;
  total: number;
  address: string;
  phone: string;
  comment?: string | null;
  created_at: string;
  updated_at: string;
  items: AdminOrderItem[];
  allowed_transitions: OrderStatus[];
}

export const adminApi = {
  listProducts: async (filters: AdminProductFilters = {}): Promise<AdminProductListResponse> => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') params.append(k, String(v));
    });
    const r = await api.get<AdminProductListResponse>(`/admin/products?${params}`);
    return r.data;
  },
  createProduct: async (body: AdminProductCreate): Promise<AdminProduct> => {
    const r = await api.post<AdminProduct>('/admin/products', body);
    return r.data;
  },
  updateProduct: async (id: number, body: AdminProductUpdate): Promise<AdminProduct> => {
    const r = await api.patch<AdminProduct>(`/admin/products/${id}`, body);
    return r.data;
  },
  deleteProduct: async (id: number): Promise<void> => {
    await api.delete(`/admin/products/${id}`);
  },
  getProduct: async (id: number): Promise<AdminProduct> => {
    const r = await api.get<AdminProduct>(`/admin/products/${id}`);
    return r.data;
  },

  // Single-variant operations (used by inline edit on ProductsPage).
  addVariant: async (productId: number, body: AdminVariantCreate): Promise<AdminVariant> => {
    const r = await api.post<AdminVariant>(`/admin/products/${productId}/variants`, body);
    return r.data;
  },
  updateVariant: async (variantId: number, body: AdminVariantUpdate): Promise<AdminVariant> => {
    const r = await api.patch<AdminVariant>(`/admin/products/variants/${variantId}`, body);
    return r.data;
  },
  deleteVariant: async (variantId: number): Promise<void> => {
    await api.delete(`/admin/products/variants/${variantId}`);
  },

  // Image upload to MinIO. Returns { url, key }; we keep `url` and put it on
  // a variant's images list before the next save.
  uploadImage: async (file: File): Promise<{ url: string; key: string }> => {
    const fd = new FormData();
    fd.append('file', file);
    const r = await api.post<{ url: string; key: string }>(
      '/admin/products/images/upload',
      fd,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return r.data;
  },

  listCategories: async (): Promise<AdminCategory[]> => {
    const r = await api.get<AdminCategory[]>('/admin/categories');
    return r.data;
  },
  createCategory: async (body: { name: string; sort_order?: number }): Promise<AdminCategory> => {
    const r = await api.post<AdminCategory>('/admin/categories', body);
    return r.data;
  },
  updateCategory: async (
    id: number,
    body: { name?: string; sort_order?: number },
  ): Promise<AdminCategory> => {
    const r = await api.patch<AdminCategory>(`/admin/categories/${id}`, body);
    return r.data;
  },
  deleteCategory: async (id: number): Promise<void> => {
    await api.delete(`/admin/categories/${id}`);
  },

  listOrders: async (filters: { status?: OrderStatus; user_id?: number } = {}): Promise<AdminOrder[]> => {
    const params = new URLSearchParams();
    if (filters.status) params.append('status', filters.status);
    if (filters.user_id) params.append('user_id', String(filters.user_id));
    const r = await api.get<AdminOrder[]>(`/admin/orders?${params}`);
    return r.data;
  },
  updateOrderStatus: async (id: number, status: OrderStatus): Promise<AdminOrder> => {
    const r = await api.patch<AdminOrder>(`/admin/orders/${id}/status`, { status });
    return r.data;
  },

  listUsers: async (search?: string): Promise<AdminUser[]> => {
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    const r = await api.get<AdminUser[]>(`/admin/users?${params}`);
    return r.data;
  },
  setUserAdmin: async (id: number, is_admin: boolean): Promise<AdminUser> => {
    const r = await api.patch<AdminUser>(`/admin/users/${id}`, { is_admin });
    return r.data;
  },
  overview: async (period: '7d' | '30d' = '7d'): Promise<StatsOverview> => {
    const r = await api.get<StatsOverview>(`/admin/stats/overview?period=${period}`);
    return r.data;
  },
  revenueByDay: async (days: number = 30): Promise<RevenuePoint[]> => {
    const r = await api.get<RevenuePoint[]>(`/admin/stats/revenue-by-day?days=${days}`);
    return r.data;
  },
  topProducts: async (limit: number = 5, days: number = 30): Promise<TopProduct[]> => {
    const r = await api.get<TopProduct[]>(`/admin/stats/top-products?limit=${limit}&days=${days}`);
    return r.data;
  },
  categoryBreakdown: async (days: number = 30): Promise<CategoryBreakdown[]> => {
    const r = await api.get<CategoryBreakdown[]>(`/admin/stats/category-breakdown?days=${days}`);
    return r.data;
  },
  lowStock: async (threshold: number = 5): Promise<LowStockProduct[]> => {
    const r = await api.get<LowStockProduct[]>(`/admin/stats/low-stock?threshold=${threshold}`);
    return r.data;
  },
  inventorySummary: async (threshold: number = 5): Promise<InventorySummary> => {
    const r = await api.get<InventorySummary>(`/admin/stats/inventory-summary?threshold=${threshold}`);
    return r.data;
  },
};
