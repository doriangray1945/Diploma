import api from './client';
import type { User, Token } from '../types';

export const authApi = {
  register: async (email: string, password: string, name: string): Promise<Token> => {
    const response = await api.post<Token>('/auth/register', { email, password, name });
    return response.data;
  },

  login: async (email: string, password: string): Promise<Token> => {
    const response = await api.post<Token>('/auth/login', { email, password });
    return response.data;
  },

  getMe: async (): Promise<User> => {
    const response = await api.get<User>('/auth/me');
    return response.data;
  },
};
