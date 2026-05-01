export interface User {
  id: number;
  email: string;
  name: string;
  phone?: string;
  is_admin: boolean;
  is_superadmin: boolean;
  created_at: string;
}

export interface Product {
  id: number;
  name: string;
  description: string;
  price: number;
  old_price?: number;
  category: string;
  subcategory?: string;
  images: string[];
  dimensions?: string;
  materials?: string;
  color?: string;
  in_stock: boolean;
  stock_quantity: number;
  rating: number;
  reviews_count: number;
  is_popular: boolean;
  is_new: boolean;
  created_at: string;
  is_favorite: boolean;
}

export interface ProductFilters {
  category?: string;
  subcategory?: string;
  min_price?: number;
  max_price?: number;
  color?: string;
  in_stock?: boolean;
  is_popular?: boolean;
  is_new?: boolean;
  search?: string;
  sort_by?: string;
  sort_order?: string;
}

export interface ProductListResponse {
  items: Product[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface Category {
  name: string;
  count: number;
  subcategories: string[];
}

export interface CartItem {
  id: number;
  product_id: number;
  quantity: number;
  product: Product;
  created_at: string;
}

export interface Cart {
  items: CartItem[];
  total: number;
  items_count: number;
}

export interface OrderItem {
  id: number;
  product_id?: number;
  product_name: string;
  quantity: number;
  price: number;
}

export interface Order {
  id: number;
  status: string;
  total: number;
  address: string;
  phone: string;
  comment?: string;
  created_at: string;
  updated_at: string;
  items: OrderItem[];
}

export interface Favorite {
  id: number;
  product_id: number;
  product: Product;
  created_at: string;
}

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface ChatAction {
  action: string;
  products?: Array<{
    id: number;
    name: string;
    price: number;
    category: string;
  }>;
  filters?: ProductFilters;
  product?: Product;
  order_id?: number;
  message?: string;
}

export interface UiState {
  visible_product_ids?: number[];
  current_filters?: ProductFilters;
  open_product_id?: number;
}

export interface ChatResponse {
  message: ChatMessage;
  action?: ChatAction;
  actions?: ChatAction[];
}

export interface Token {
  access_token: string;
  token_type: string;
}
