import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '../types';
import { authApi } from '../api';

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      // Если в localStorage уже лежит токен — стартуем в isLoading=true, чтобы
      // ProtectedRoute показал спиннер на первом рендере, пока App.tsx
      // useEffect не успел вызвать fetchUser. Иначе при F5 на защищённой
      // странице мы успеваем отрендерить Navigate to /login раньше, чем
      // /auth/me вернёт юзера, — и пользователя «выкидывает» из аккаунта.
      isLoading: typeof window !== 'undefined' && !!localStorage.getItem('token'),
      error: null,

      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null });
        try {
          const { access_token } = await authApi.login(email, password);
          localStorage.setItem('token', access_token);
          set({ token: access_token });
          await get().fetchUser();
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : 'Ошибка входа';
          set({ error: message, isLoading: false });
          throw error;
        }
      },

      register: async (email: string, password: string, name: string) => {
        set({ isLoading: true, error: null });
        try {
          const { access_token } = await authApi.register(email, password, name);
          localStorage.setItem('token', access_token);
          set({ token: access_token });
          await get().fetchUser();
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : 'Ошибка регистрации';
          set({ error: message, isLoading: false });
          throw error;
        }
      },

      logout: () => {
        localStorage.removeItem('token');
        set({ user: null, token: null, error: null });
      },

      fetchUser: async () => {
        const token = localStorage.getItem('token');
        if (!token) {
          set({ isLoading: false });
          return;
        }

        set({ isLoading: true });
        try {
          const user = await authApi.getMe();
          set({ user, token, isLoading: false });
        } catch {
          localStorage.removeItem('token');
          set({ user: null, token: null, isLoading: false });
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ token: state.token }),
    }
  )
);
