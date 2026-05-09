import api from './client';
import type { Favorite } from '../types';

interface FavoritesResponse {
  items: Favorite[];
  total: number;
}

export const favoritesApi = {
  getFavorites: async (): Promise<FavoritesResponse> => {
    const response = await api.get<FavoritesResponse>('/favorites');
    return response.data;
  },

  addToFavorites: async (variantId: number): Promise<Favorite> => {
    const response = await api.post<Favorite>(`/favorites/${variantId}`);
    return response.data;
  },

  removeFromFavorites: async (variantId: number): Promise<void> => {
    await api.delete(`/favorites/${variantId}`);
  },
};
