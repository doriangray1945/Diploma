import { create } from 'zustand';
import type { ChatMessage, ChatAction } from '../types';
import { chatApi } from '../api';

interface ChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  lastAction: ChatAction | null;
  isOpen: boolean;

  sendMessage: (content: string) => Promise<void>;
  fetchHistory: () => Promise<void>;
  clearHistory: () => Promise<void>;
  clearLastAction: () => void;
  toggleChat: () => void;
  setOpen: (open: boolean) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isLoading: false,
  error: null,
  lastAction: null,
  isOpen: true,

  sendMessage: async (content: string) => {
    // Add user message optimistically
    const userMessage: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage],
      isLoading: true,
      error: null,
    }));

    try {
      const response = await chatApi.sendMessage(content);
      set((state) => ({
        messages: [...state.messages.slice(0, -1), userMessage, response.message],
        lastAction: response.action || null,
        isLoading: false,
      }));
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка отправки сообщения';
      set({ error: message, isLoading: false });
    }
  },

  fetchHistory: async () => {
    try {
      const response = await chatApi.getHistory();
      set({ messages: response.messages });
    } catch (error) {
      console.error('Failed to fetch chat history:', error);
    }
  },

  clearHistory: async () => {
    try {
      await chatApi.clearHistory();
      set({ messages: [], lastAction: null });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка очистки истории';
      set({ error: message });
    }
  },

  clearLastAction: () => set({ lastAction: null }),

  toggleChat: () => set((state) => ({ isOpen: !state.isOpen })),

  setOpen: (open: boolean) => set({ isOpen: open }),
}));
