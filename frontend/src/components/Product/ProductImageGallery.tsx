import { useEffect, useState, useRef } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import clsx from 'clsx';

interface Props {
  images: string[];
  productName: string;
}

const PLACEHOLDER = (name: string) =>
  `https://placehold.co/600x600/e2e8f0/64748b?text=${encodeURIComponent(name)}`;

export default function ProductImageGallery({ images, productName }: Props) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // Reset index when the photo set changes (e.g. user picked a new colour).
  useEffect(() => {
    setCurrentIndex(0);
  }, [images]);

  const safeImages = images.length > 0 ? images : [PLACEHOLDER(productName)];
  const total = safeImages.length;

  const goPrev = () => setCurrentIndex((i) => (i - 1 + total) % total);
  const goNext = () => setCurrentIndex((i) => (i + 1) % total);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (total <= 1) return;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      goPrev();
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      goNext();
    }
  };

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      onKeyDown={onKeyDown}
      className="flex flex-col gap-3 outline-none"
    >
      {/* Main image */}
      <div className="relative group aspect-square bg-slate-100 rounded-xl overflow-hidden">
        <img
          src={safeImages[currentIndex]}
          alt={`${productName} — фото ${currentIndex + 1}`}
          className="w-full h-full object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).src = PLACEHOLDER(productName);
          }}
        />

        {total > 1 && (
          <>
            <button
              type="button"
              onClick={goPrev}
              aria-label="Предыдущее фото"
              className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-full bg-white/90 shadow opacity-0 group-hover:opacity-100 transition hover:bg-white"
            >
              <ChevronLeft className="w-5 h-5 text-slate-700" />
            </button>
            <button
              type="button"
              onClick={goNext}
              aria-label="Следующее фото"
              className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-full bg-white/90 shadow opacity-0 group-hover:opacity-100 transition hover:bg-white"
            >
              <ChevronRight className="w-5 h-5 text-slate-700" />
            </button>

            {/* Position counter */}
            <div className="absolute bottom-3 right-3 px-2 py-1 rounded-full bg-black/60 text-white text-xs font-medium">
              {currentIndex + 1} / {total}
            </div>
          </>
        )}
      </div>

      {/* Thumbnails */}
      {total > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {safeImages.map((src, i) => (
            <button
              key={`${src}-${i}`}
              type="button"
              onClick={() => setCurrentIndex(i)}
              aria-label={`Перейти к фото ${i + 1}`}
              className={clsx(
                'flex-shrink-0 w-20 h-20 rounded-lg overflow-hidden border-2 transition',
                i === currentIndex
                  ? 'border-primary-600 ring-2 ring-primary-600/30'
                  : 'border-slate-200 hover:border-slate-300'
              )}
            >
              <img
                src={src}
                alt=""
                className="w-full h-full object-cover"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = PLACEHOLDER(productName);
                }}
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
