import api from './client';
import type { ChatAction, ChatMessage, ChatResponse, UiState } from '../types';

interface ChatHistoryResponse {
  messages: ChatMessage[];
}

export interface StreamHandlers {
  onMeta: (data: { action: ChatAction | null; actions: ChatAction[] }) => void;
  onToken: (chunk: string) => void;
  onDone: (messageId: number, elapsedMs: number) => void;
  onError: (msg: string) => void;
}

export const chatApi = {
  sendMessage: async (content: string, uiState?: UiState): Promise<ChatResponse> => {
    const response = await api.post<ChatResponse>('/chat/message', {
      content,
      ui_state: uiState,
    });
    return response.data;
  },

  // SSE streaming: parses event: TYPE / data: JSON blocks from a fetch stream.
  // Returns once the server signals done/error or the connection closes.
  streamMessage: async (
    content: string,
    uiState: UiState | undefined,
    handlers: StreamHandlers,
  ): Promise<void> => {
    const token = localStorage.getItem('token');
    const res = await fetch('/api/chat/message/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content, ui_state: uiState }),
    });
    if (!res.ok || !res.body) {
      throw new Error(`HTTP ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const m = block.match(/^event: (\w+)\ndata: ([\s\S]+)$/);
        if (!m) continue;
        const type = m[1];
        let data: {
          content?: string;
          action?: ChatAction | null;
          actions?: ChatAction[];
          message_id?: number;
          message?: string;
          step?: string;
          elapsed_ms?: number;
        };
        try { data = JSON.parse(m[2]); }
        catch { continue; }
        if (type === 'meta') {
          handlers.onMeta({ action: data.action ?? null, actions: data.actions ?? [] });
        } else if (type === 'token' && typeof data.content === 'string') {
          handlers.onToken(data.content);
        } else if (type === 'done' && typeof data.message_id === 'number') {
          handlers.onDone(data.message_id, data.elapsed_ms ?? 0);
        } else if (type === 'error') {
          handlers.onError(data.message ?? 'stream error');
        }
        // event: thinking — ignored on the client; UI shows a single
        // «Думаю…» indicator without per-step labels.
      }
    }
  },

  getHistory: async (): Promise<ChatHistoryResponse> => {
    const response = await api.get<ChatHistoryResponse>('/chat/history');
    return response.data;
  },

  clearHistory: async (): Promise<void> => {
    await api.delete('/chat/history');
  },
};
