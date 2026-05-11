export interface User {
  id: number;
  email: string;
  name: string;
  phone?: string;
  is_admin: boolean;
  is_superadmin: boolean;
  created_at: string;
}

export interface DimensionsCm {
  width: number;
  depth: number;
  height: number;
}

export interface ProductVariant {
  id: number;
  product_id: number;
  color?: string | null;
  size_label?: string | null;
  dimensions?: DimensionsCm | null;
  price: number;
  old_price?: number | null;
  stock_quantity: number;
  in_stock: boolean;
  images: string[];
  sku?: string | null;
  is_default: boolean;
  model_glb_url?: string | null;
  model_usdz_url?: string | null;
}

export interface Product {
  id: number;
  name: string;
  description: string;
  // Default-variant snapshot fields (legacy compat with existing UI).
  price: number;
  old_price?: number;
  images: string[];
  color?: string;
  in_stock: boolean;
  stock_quantity: number;
  category: string;
  subcategory?: string;
  dimensions?: DimensionsCm | string;
  materials?: string;
  rating: number;
  reviews_count: number;
  is_popular: boolean;
  is_new: boolean;
  created_at: string;
  is_favorite: boolean;
  // Variant data
  variants: ProductVariant[];
  default_variant_id?: number | null;
}

export interface ProductFilters {
  category?: string;
  subcategory?: string;
  min_price?: number;
  max_price?: number;
  color?: string[];      // multi-value: «красные или синие»
  material?: string[];   // multi-value: «твёрдое» = ['дерево','металл']
  in_stock?: boolean;
  is_popular?: boolean;
  is_new?: boolean;
  search?: string;
  sort_by?: string;
  sort_order?: string;
}

export interface FilterOptions {
  categories: string[];
  colors: string[];
  materials: string[];
  price_range: { min: number; max: number };
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
  variant_id: number;
  quantity: number;
  product: Product;
  selected_color?: string | null;
  selected_size?: string | null;
  selected_price?: number;
  selected_images?: string[];
  // Backend exposes the variant's current stock so the UI can disable + at
  // the limit and show "осталось N" without re-querying the product.
  selected_stock?: number;
  // True when the displayed quantity was clamped down to the current stock
  // (e.g. admin lowered stock after the user added the item). UI surfaces
  // a one-shot banner.
  adjusted?: boolean;
  // True when the variant is fully sold out (stock_quantity == 0). UI
  // greys the row and disables checkout until the user removes it.
  out_of_stock?: boolean;
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
  variant_id: number;
  product: Product;
  selected_color?: string | null;
  selected_size?: string | null;
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

export interface Review {
  id: number;
  user_id: number;
  user_name: string;
  rating: number;
  text: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewListResponse {
  items: Review[];
  total: number;
}

export interface ReviewEligibility {
  can_review: boolean;
  has_review: boolean;
  my_review: Review | null;
}

export interface Token {
  access_token: string;
  token_type: string;
}
