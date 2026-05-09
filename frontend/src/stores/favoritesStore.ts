import { create } from 'zustand';
import type { Favorite } from '../types';
import { favoritesApi } from '../api';

interface FavoritesState {
  favorites: Favorite[];
  isLoading: boolean;
  error: string | null;

  fetchFavorites: () => Promise<void>;
  addToFavorites: (variantId: number) => Promise<void>;
  removeFromFavorites: (variantId: number) => Promise<void>;
  // Product-level helper: any variant of this product is favorited.
  isFavorite: (productId: number) => boolean;
}

export const useFavoritesStore = create<FavoritesState>((set, get) => ({
  favorites: [],
  isLoading: false,
  error: null,

  fetchFavorites: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await favoritesApi.getFavorites();
      set({ favorites: response.items, isLoading: false });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка загрузки избранного';
      set({ error: message, isLoading: false });
    }
  },

  addToFavorites: async (variantId: number) => {
    try {
      await favoritesApi.addToFavorites(variantId);
      await get().fetchFavorites();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка добавления в избранное';
      set({ error: message });
      throw error;
    }
  },

  removeFromFavorites: async (variantId: number) => {
    try {
      await favoritesApi.removeFromFavorites(variantId);
      await get().fetchFavorites();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка удаления из избранного';
      set({ error: message });
    }
  },

  isFavorite: (productId: number) => {
    return get().favorites.some((fav) => fav.product_id === productId);
  },
}));
