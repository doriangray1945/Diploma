import clsx from 'clsx';

interface Props {
  sizes: string[];
  available: Set<string>;
  selected: string | null | undefined;
  onChange: (size: string) => void;
}

export default function SizePicker({ sizes, available, selected, onChange }: Props) {
  if (sizes.length === 0) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-slate-700">Размер</span>
        {selected && <span className="text-sm text-slate-500">{selected}</span>}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {sizes.map((size) => {
          const isAvailable = available.has(size);
          const isSelected = size === selected;
          return (
            <button
              key={size}
              type="button"
              onClick={() => isAvailable && onChange(size)}
              disabled={!isAvailable}
              aria-pressed={isSelected}
              className={clsx(
                'px-3 py-2 rounded-lg border text-sm font-medium transition',
                isSelected
                  ? 'bg-primary-600 text-white border-primary-600'
                  : isAvailable
                  ? 'bg-white text-slate-900 border-slate-300 hover:border-slate-500 cursor-pointer'
                  : 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed'
              )}
            >
              {size}
            </button>
          );
        })}
      </div>
    </div>
  );
}
