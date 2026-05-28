import { useState, useRef, useEffect } from 'react';
import { Send, ChevronDown, ChevronUp, Trash2 } from 'lucide-react';
import { useChatStore, useProductsStore, useAuthStore, useCartStore, useFavoritesStore } from '../../stores';
import ChatMessage from './ChatMessage';
import ThinkingBlock from './ThinkingBlock';
import clsx from 'clsx';

export default function Chat() {
  const [input, setInput] = useState('');
  const { user } = useAuthStore();
  const {
    messages,
    isLoading,
    pendingThinking,
    error,
    streamMessage,
    clearHistory,
    lastActions,
    clearLastAction,
    clearError,
    isOpen,
    toggleChat,
  } = useChatStore();
  const { setFilters } = useProductsStore();
  const { fetchCart } = useCartStore();
  const { fetchFavorites } = useFavoritesStore();

  const chatContainerRef = useRef<HTMLDivElement>(null);

  // Scroll chat container to bottom (not the whole page). Also reacts to
  // pendingThinking so new thinking steps stay in view.
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, pendingThinking]);

  // Handle chat actions (process all actions from multi-step plans)
  useEffect(() => {
    if (lastActions.length > 0) {
      let shouldScrollToCatalog = false;
      for (const action of lastActions) {
        if (action.action === 'apply_filters' && action.filters) {
          setFilters(action.filters);
          shouldScrollToCatalog = true;
        }
        if (action.action === 'added_to_cart') {
          fetchCart();
        }
        if (action.action === 'added_to_favorites' || action.action === 'removed_from_favorites') {
          fetchFavorites();
        }
        if (action.action === 'order_created') {
          fetchCart();
        }
      }
      if (shouldScrollToCatalog) {
        setTimeout(() => {
          document.getElementById('catalog-grid')?.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      }
      clearLastAction();
    }
  }, [lastActions, setFilters, fetchCart, fetchFavorites, clearLastAction]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading || !user) return;

    // Collect current UI state for context-aware responses
    const pState = useProductsStore.getState();
    const uiState = {
      visible_product_ids: pState.products.map((p) => p.id),
      current_filters: pState.filters || undefined,
      open_product_id: undefined,
    };

    streamMessage(input.trim(), uiState);
    setInput('');
  };

  if (!user) {
    return null;
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden mb-10">
      {/* Chat header */}
      <button
        onClick={toggleChat}
        className="w-full px-6 py-4 flex items-center justify-between bg-gradient-to-r from-primary-50 to-violet-50 hover:from-primary-100 hover:to-violet-100 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-violet-500 rounded-full flex items-center justify-center">
            <span className="text-white font-semibold">AI</span>
          </div>
          <div className="text-left">
            <h3 className="font-semibold text-slate-900">Сделать заказ в Nova Furnish</h3>
            <p className="text-sm text-slate-500">AI-ассистент поможет подобрать мебель</p>
          </div>
        </div>
        {isOpen ? (
          <ChevronUp className="w-5 h-5 text-slate-400" />
        ) : (
          <ChevronDown className="w-5 h-5 text-slate-400" />
        )}
      </button>

      {/* Chat body */}
      <div
        className={clsx(
          'transition-all duration-300 overflow-hidden',
          isOpen ? 'max-h-[400px]' : 'max-h-0'
        )}
      >
        {/* Messages */}
        <div ref={chatContainerRef} className="h-[280px] overflow-y-auto p-4 space-y-4 bg-gradient-to-b from-slate-50 to-white">
          {messages.length === 0 ? (
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 bg-gradient-to-br from-primary-500 to-violet-500 rounded-full flex items-center justify-center flex-shrink-0">
                <span className="text-white text-xs font-semibold">AI</span>
              </div>
              <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border border-slate-100 max-w-[80%]">
                <p className="text-sm text-slate-700">
                  Здравствуйте! Я AI-ассистент Nova Furnish. Помогу вам подобрать мебель, расскажу о товарах и оформлю заказ. Что вас интересует?
                </p>
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <div key={message.id} className="space-y-1">
                {message.role === 'assistant' && message.thinking && (
                  <ThinkingBlock state={message.thinking} />
                )}
                <ChatMessage message={message} />
              </div>
            ))
          )}

          {pendingThinking && <ThinkingBlock state={pendingThinking} />}

          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <span className="flex-1">{error}</span>
              <button
                type="button"
                onClick={clearError}
                className="text-red-500 hover:text-red-700 font-semibold leading-none"
                aria-label="Закрыть"
              >
                ×
              </button>
            </div>
          )}

        </div>

        {/* Input */}
        <div className="p-4 border-t border-slate-100">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <div className="flex-1 relative">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Спросите что-нибудь..."
                disabled={isLoading}
                className="w-full px-4 py-3 bg-slate-100 rounded-full text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:bg-white transition-all disabled:opacity-50"
              />
            </div>
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="p-3 bg-primary-600 text-white rounded-full hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Send className="w-5 h-5" />
            </button>
            {messages.length > 0 && (
              <button
                type="button"
                onClick={clearHistory}
                className="p-3 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors"
                title="Очистить историю"
              >
                <Trash2 className="w-5 h-5" />
              </button>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
