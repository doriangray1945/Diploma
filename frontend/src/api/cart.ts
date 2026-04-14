import api from './client';
import type { Cart, CartItem } from '../types';

export const cartApi = {
  getCart: async (): Promise<Cart> => {
    const response = await api.get<Cart>('/cart');
    return response.data;
  },

  addToCart: async (productId: number, quantity: number = 1): Promise<CartItem> => {
    const response = await api.post<CartItem>('/cart/items', {
      product_id: productId,
      quantity,
    });
    return response.data;
  },

  updateCartItem: async (itemId: number, quantity: number): Promise<CartItem> => {
    const response = await api.put<CartItem>(`/cart/items/${itemId}`, { quantity });
    return response.data;
  },

  removeFromCart: async (itemId: number): Promise<void> => {
    await api.delete(`/cart/items/${itemId}`);
  },

  clearCart: async (): Promise<void> => {
    await api.delete('/cart');
  },
};
