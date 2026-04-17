import api from './client';
import type { ChatMessage, ChatResponse, UiState } from '../types';

interface ChatHistoryResponse {
  messages: ChatMessage[];
}

export const chatApi = {
  sendMessage: async (content: string, uiState?: UiState): Promise<ChatResponse> => {
    const response = await api.post<ChatResponse>('/chat/message', {
      content,
      ui_state: uiState,
    });
    return response.data;
  },

  getHistory: async (): Promise<ChatHistoryResponse> => {
    const response = await api.get<ChatHistoryResponse>('/chat/history');
    return response.data;
  },

  clearHistory: async (): Promise<void> => {
    await api.delete('/chat/history');
  },
};
