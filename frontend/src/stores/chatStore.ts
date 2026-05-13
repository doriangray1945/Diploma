import { create } from 'zustand';
import type { ChatMessage, ChatAction, ThinkingState, UiState } from '../types';
import { chatApi } from '../api';

interface ChatState {
  messages: ChatMessage[];
  // True between request start and the first streamed token. Drives input
  // disabled state. Thinking-block uses pendingThinking, not this flag.
  isLoading: boolean;
  isStreaming: boolean;
  // Active thinking state for the current in-flight request. Becomes null
  // as soon as the first token arrives — the thinking attaches to the new
  // assistant message instead.
  pendingThinking: ThinkingState | null;
  error: string | null;
  lastAction: ChatAction | null;
  lastActions: ChatAction[];
  isOpen: boolean;

  sendMessage: (content: string, uiState?: UiState) => Promise<void>;
  streamMessage: (content: string, uiState?: UiState) => Promise<void>;
  fetchHistory: () => Promise<void>;
  clearHistory: () => Promise<void>;
  clearLastAction: () => void;
  clearError: () => void;
  toggleChat: () => void;
  setOpen: (open: boolean) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isLoading: false,
  isStreaming: false,
  pendingThinking: null,
  error: null,
  lastAction: null,
  lastActions: [],
  isOpen: true,

  sendMessage: async (content: string, uiState?: UiState) => {
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
      const response = await chatApi.sendMessage(content, uiState);
      const actions = response.actions || (response.action ? [response.action] : []);
      set((state) => ({
        messages: [...state.messages.slice(0, -1), userMessage, response.message],
        lastAction: response.action || null,
        lastActions: actions,
        isLoading: false,
      }));
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка отправки сообщения';
      set({ error: message, isLoading: false });
    }
  },

  streamMessage: async (content: string, uiState?: UiState) => {
    const userMessage: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    const startedAt = Date.now();
    // No empty assistant placeholder — we render the active thinking block
    // from `pendingThinking` instead, and create the assistant message on
    // the first token. This avoids the «empty bubble + Думаю…» double UI.
    set((state) => ({
      messages: [...state.messages, userMessage],
      isLoading: true,
      isStreaming: true,
      pendingThinking: {
        isThinking: true,
        startedAt,
        durationMs: null,
      },
      error: null,
    }));

    try {
      await chatApi.streamMessage(content, uiState, {
        onMeta: ({ action, actions }) => {
          set({ lastAction: action, lastActions: actions });
        },
        onToken: (chunk) => {
          set((state) => {
            const msgs = state.messages.slice();
            const last = msgs[msgs.length - 1];
            // First token → spawn assistant message, attach (now collapsed)
            // thinking state from pendingThinking.
            if (!last || last.role !== 'assistant') {
              const finalizedThinking: ThinkingState | undefined = state.pendingThinking
                ? {
                    ...state.pendingThinking,
                    isThinking: false,
                    durationMs: Date.now() - (state.pendingThinking.startedAt ?? Date.now()),
                  }
                : undefined;
              const assistant: ChatMessage = {
                id: Date.now() + 1,
                role: 'assistant',
                content: chunk,
                created_at: new Date().toISOString(),
                thinking: finalizedThinking,
              };
              return {
                messages: [...msgs, assistant],
                pendingThinking: null,
                isLoading: false,
              };
            }
            // Subsequent tokens — append.
            msgs[msgs.length - 1] = { ...last, content: (last.content || '') + chunk };
            return { messages: msgs, isLoading: false };
          });
        },
        onDone: (messageId) => {
          set((state) => {
            const msgs = state.messages.slice();
            const last = msgs[msgs.length - 1];
            if (last && last.role === 'assistant') {
              msgs[msgs.length - 1] = { ...last, id: messageId };
            }
            return {
              messages: msgs,
              pendingThinking: null,
              isLoading: false,
              isStreaming: false,
            };
          });
        },
        onError: (errMsg) => {
          set({
            pendingThinking: null,
            error: errMsg,
            isLoading: false,
            isStreaming: false,
          });
        },
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка отправки сообщения';
      set({
        pendingThinking: null,
        error: message,
        isLoading: false,
        isStreaming: false,
      });
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
      set({ messages: [], lastAction: null, lastActions: [] });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка очистки истории';
      set({ error: message });
    }
  },

  clearLastAction: () => set({ lastAction: null, lastActions: [] }),

  clearError: () => set({ error: null }),

  toggleChat: () => set((state) => ({ isOpen: !state.isOpen })),

  setOpen: (open: boolean) => set({ isOpen: open }),
}));
