import { create } from 'zustand';
import type { CartItem } from '../types';
import { cartApi } from '../api';

interface CartState {
  items: CartItem[];
  total: number;
  isLoading: boolean;
  error: string | null;

  fetchCart: () => Promise<void>;
  addToCart: (variantId: number, quantity?: number) => Promise<void>;
  updateQuantity: (itemId: number, quantity: number) => Promise<void>;
  removeItem: (itemId: number) => Promise<void>;
  clearCart: () => Promise<void>;
}

export const useCartStore = create<CartState>((set, get) => ({
  items: [],
  total: 0,
  isLoading: false,
  error: null,

  fetchCart: async () => {
    set({ isLoading: true, error: null });
    try {
      const cart = await cartApi.getCart();
      set({ items: cart.items, total: cart.total, isLoading: false });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка загрузки корзины';
      set({ error: message, isLoading: false });
    }
  },

  addToCart: async (variantId: number, quantity: number = 1) => {
    try {
      await cartApi.addToCart(variantId, quantity);
      await get().fetchCart();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка добавления в корзину';
      set({ error: message });
      throw error;
    }
  },

  updateQuantity: async (itemId: number, quantity: number) => {
    try {
      if (quantity <= 0) {
        await get().removeItem(itemId);
        return;
      }
      await cartApi.updateCartItem(itemId, quantity);
      await get().fetchCart();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка обновления корзины';
      set({ error: message });
    }
  },

  removeItem: async (itemId: number) => {
    try {
      await cartApi.removeFromCart(itemId);
      await get().fetchCart();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка удаления из корзины';
      set({ error: message });
    }
  },

  clearCart: async () => {
    try {
      await cartApi.clearCart();
      set({ items: [], total: 0 });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка очистки корзины';
      set({ error: message });
    }
  },
}));
