import { Sparkles } from 'lucide-react';
import type { ThinkingState } from '../../types';

interface Props {
  state: ThinkingState;
}

export default function ThinkingBlock({ state }: Props) {
  const { isThinking, durationMs } = state;

  if (isThinking) {
    return (
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 bg-gradient-to-br from-primary-500 to-violet-500 rounded-full flex items-center justify-center flex-shrink-0">
          <Sparkles className="w-4 h-4 text-white" />
        </div>
        <div className="inline-flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-primary-50 to-violet-50 border border-primary-100 rounded-2xl rounded-tl-sm">
          <span className="thinking-active text-sm text-slate-600">Думаю…</span>
          <div className="flex gap-1">
            <span className="loading-dot w-1.5 h-1.5 bg-primary-400 rounded-full"></span>
            <span className="loading-dot w-1.5 h-1.5 bg-primary-400 rounded-full"></span>
            <span className="loading-dot w-1.5 h-1.5 bg-primary-400 rounded-full"></span>
          </div>
        </div>
      </div>
    );
  }

  if (durationMs == null) return null;
  const seconds = (durationMs / 1000).toFixed(1);
  return (
    <div className="ml-11 mb-1 inline-flex items-center gap-1.5 text-xs text-slate-400">
      <Sparkles className="w-3.5 h-3.5 text-violet-400" />
      <span>Подумал за {seconds}с</span>
    </div>
  );
}
