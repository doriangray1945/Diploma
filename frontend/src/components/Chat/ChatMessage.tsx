import type { ChatMessage as ChatMessageType } from '../../types';
import clsx from 'clsx';

interface ChatMessageProps {
  message: ChatMessageType;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div
      className={clsx(
        'flex items-start gap-3 chat-message',
        isUser && 'flex-row-reverse'
      )}
    >
      {/* Avatar */}
      <div
        className={clsx(
          'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
          isUser
            ? 'bg-slate-200'
            : 'bg-gradient-to-br from-primary-500 to-violet-500'
        )}
      >
        {isUser ? (
          <span className="text-slate-600 text-xs font-semibold">Вы</span>
        ) : (
          <span className="text-white text-xs font-semibold">AI</span>
        )}
      </div>

      {/* Message bubble */}
      <div
        className={clsx(
          'px-4 py-3 rounded-2xl max-w-[80%] shadow-sm',
          isUser
            ? 'bg-primary-600 text-white rounded-tr-sm'
            : 'bg-white border border-slate-100 rounded-tl-sm'
        )}
      >
        <p className={clsx('text-sm whitespace-pre-wrap', !isUser && 'text-slate-700')}>
          {message.content}
        </p>
      </div>
    </div>
  );
}
