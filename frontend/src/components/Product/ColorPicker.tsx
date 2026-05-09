import clsx from 'clsx';
import { getColorHex } from '../../lib/colorMap';

interface Props {
  colors: string[];
  available: Set<string>;
  selected: string | null | undefined;
  onChange: (color: string) => void;
}

export default function ColorPicker({ colors, available, selected, onChange }: Props) {
  if (colors.length === 0) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-slate-700">Цвет</span>
        {selected && <span className="text-sm text-slate-500">{selected}</span>}
      </div>
      <div className="flex flex-wrap gap-3">
        {colors.map((color) => {
          const isAvailable = available.has(color);
          const isSelected = color === selected;
          return (
            <button
              key={color}
              type="button"
              onClick={() => isAvailable && onChange(color)}
              disabled={!isAvailable}
              title={color}
              aria-label={color}
              aria-pressed={isSelected}
              className={clsx(
                'w-10 h-10 rounded-full border-2 transition-all relative',
                isSelected
                  ? 'border-primary-600 ring-2 ring-primary-600/30 scale-105'
                  : 'border-white shadow-sm',
                !isAvailable && 'opacity-40 cursor-not-allowed',
                isAvailable && !isSelected && 'hover:scale-105 cursor-pointer'
              )}
              style={{ backgroundColor: getColorHex(color) }}
            >
              {!isAvailable && (
                <span
                  className="absolute inset-0 flex items-center justify-center"
                  aria-hidden
                >
                  <span className="block w-full h-0.5 bg-slate-400 rotate-45" />
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
