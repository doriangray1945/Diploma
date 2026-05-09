import api from './client';
import type { Order } from '../types';

interface OrdersResponse {
  items: Order[];
  total: number;
}

interface CreateOrderData {
  address: string;
  phone: string;
  comment?: string;
  // True when the user has confirmed clamping insufficient items down to
  // current stock (e.g. 2 → 1). Sold-out items still block.
  accept_clamping?: boolean;
}

export const ordersApi = {
  getOrders: async (): Promise<OrdersResponse> => {
    const response = await api.get<OrdersResponse>('/orders');
    return response.data;
  },

  getOrder: async (id: number): Promise<Order> => {
    const response = await api.get<Order>(`/orders/${id}`);
    return response.data;
  },

  createOrder: async (data: CreateOrderData): Promise<Order> => {
    const response = await api.post<Order>('/orders', data);
    return response.data;
  },
};
