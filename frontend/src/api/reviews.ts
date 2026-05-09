import api from './client';
import type { Review, ReviewListResponse, ReviewEligibility } from '../types';

export const reviewsApi = {
  list: async (productId: number, page = 1): Promise<ReviewListResponse> => {
    const r = await api.get<ReviewListResponse>(
      `/products/${productId}/reviews?page=${page}&per_page=10`,
    );
    return r.data;
  },
  eligibility: async (productId: number): Promise<ReviewEligibility> => {
    const r = await api.get<ReviewEligibility>(
      `/products/${productId}/reviews/eligibility`,
    );
    return r.data;
  },
  create: async (
    productId: number,
    body: { rating: number; text?: string },
  ): Promise<Review> => {
    const r = await api.post<Review>(`/products/${productId}/reviews`, body);
    return r.data;
  },
  update: async (
    productId: number,
    body: { rating?: number; text?: string | null },
  ): Promise<Review> => {
    const r = await api.patch<Review>(`/products/${productId}/reviews`, body);
    return r.data;
  },
  remove: async (productId: number): Promise<void> => {
    await api.delete(`/products/${productId}/reviews`);
  },
};
