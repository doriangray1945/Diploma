import { useEffect, useState } from 'react';
import { Star, Pencil, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import { reviewsApi } from '../../api';
import { useAuthStore, useProductsStore } from '../../stores';
import type { Review, ReviewEligibility } from '../../types';

interface Props {
  productId: number;
}

function StarRow({
  value,
  size = 'md',
  onChange,
}: {
  value: number;
  size?: 'sm' | 'md' | 'lg';
  onChange?: (v: number) => void;
}) {
  const cls = size === 'lg' ? 'w-7 h-7' : size === 'sm' ? 'w-4 h-4' : 'w-5 h-5';
  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          onClick={() => onChange?.(star)}
          disabled={!onChange}
          className={clsx(
            'transition-colors',
            onChange && 'hover:scale-110 cursor-pointer',
            !onChange && 'cursor-default',
          )}
          aria-label={`${star} stars`}
        >
          <Star
            className={clsx(
              cls,
              star <= value
                ? 'text-amber-400 fill-current'
                : 'text-slate-300',
            )}
          />
        </button>
      ))}
    </div>
  );
}

function ReviewItem({ review }: { review: Review }) {
  const date = new Date(review.created_at).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
  return (
    <div className="border-b border-slate-100 py-4 last:border-b-0">
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 font-semibold text-sm">
            {review.user_name.slice(0, 1).toUpperCase()}
          </div>
          <div>
            <p className="font-medium text-slate-900 text-sm">{review.user_name}</p>
            <p className="text-xs text-slate-500">{date}</p>
          </div>
        </div>
        <StarRow value={review.rating} size="sm" />
      </div>
      {review.text && (
        <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">
          {review.text}
        </p>
      )}
    </div>
  );
}

function MyReviewForm({
  productId,
  initial,
  onDone,
  onCancel,
}: {
  productId: number;
  initial: Review | null;
  onDone: () => void;
  onCancel?: () => void;
}) {
  const [rating, setRating] = useState(initial?.rating ?? 5);
  const [text, setText] = useState(initial?.text ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      if (initial) {
        await reviewsApi.update(productId, { rating, text: text || null });
      } else {
        await reviewsApi.create(productId, { rating, text: text || undefined });
      }
      onDone();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Не удалось сохранить отзыв');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="bg-slate-50 border border-slate-200 rounded-xl p-4 sm:p-5"
    >
      <div className="mb-3">
        <p className="text-sm font-medium text-slate-700 mb-2">Ваша оценка</p>
        <StarRow value={rating} size="lg" onChange={setRating} />
      </div>
      <div className="mb-3">
        <label className="block text-sm font-medium text-slate-700 mb-2">
          Отзыв (опционально)
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={2000}
          rows={4}
          placeholder="Поделитесь впечатлениями от товара..."
          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
        />
        <p className="text-xs text-slate-400 mt-1">{text.length} / 2000</p>
      </div>
      {error && (
        <div className="mb-3 px-3 py-2 bg-red-50 text-red-700 rounded-lg text-sm">
          {error}
        </div>
      )}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors disabled:opacity-50"
        >
          {saving ? 'Сохраняем…' : initial ? 'Сохранить' : 'Опубликовать'}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-100 transition-colors"
          >
            Отмена
          </button>
        )}
      </div>
    </form>
  );
}

export default function ReviewSection({ productId }: Props) {
  const { user } = useAuthStore();
  const { fetchProduct } = useProductsStore();
  const [reviews, setReviews] = useState<Review[]>([]);
  const [total, setTotal] = useState(0);
  const [eligibility, setEligibility] = useState<ReviewEligibility | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState(false);

  const reload = async () => {
    setLoading(true);
    try {
      const list = await reviewsApi.list(productId, 1);
      setReviews(list.items);
      setTotal(list.total);
      setPage(1);
      if (user) {
        const elig = await reviewsApi.eligibility(productId);
        setEligibility(elig);
      } else {
        setEligibility(null);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId, user?.id]);

  const loadMore = async () => {
    const next = page + 1;
    const list = await reviewsApi.list(productId, next);
    setReviews((prev) => [...prev, ...list.items]);
    setPage(next);
  };

  const handleSaved = async () => {
    setEditing(false);
    await reload();
    // refresh product so the rating chip on top of the page updates
    await fetchProduct(productId);
  };

  const handleDelete = async () => {
    if (!confirm('Удалить ваш отзыв?')) return;
    await reviewsApi.remove(productId);
    await reload();
    await fetchProduct(productId);
  };

  // ---- top block: own review / form / eligibility hint ----
  let myBlock: React.ReactNode = null;
  if (!user) {
    myBlock = (
      <p className="text-sm text-slate-500 italic">
        Войдите, чтобы оставить отзыв.
      </p>
    );
  } else if (eligibility && !eligibility.can_review) {
    myBlock = (
      <p className="text-sm text-slate-500 italic">
        Оставить отзыв можно только после доставки заказа с этим товаром.
      </p>
    );
  } else if (eligibility?.has_review && eligibility.my_review && !editing) {
    const my = eligibility.my_review;
    myBlock = (
      <div className="bg-primary-50 border border-primary-100 rounded-xl p-4">
        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
          <p className="text-sm font-medium text-slate-700">Ваш отзыв</p>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="p-2 text-slate-600 hover:bg-white rounded-lg transition-colors"
              aria-label="Редактировать"
            >
              <Pencil className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={handleDelete}
              className="p-2 text-red-500 hover:bg-white rounded-lg transition-colors"
              aria-label="Удалить"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
        <StarRow value={my.rating} size="md" />
        {my.text && (
          <p className="text-sm text-slate-700 mt-2 whitespace-pre-line">{my.text}</p>
        )}
      </div>
    );
  } else if (eligibility?.can_review || editing) {
    myBlock = (
      <MyReviewForm
        productId={productId}
        initial={editing ? eligibility?.my_review ?? null : null}
        onDone={handleSaved}
        onCancel={editing ? () => setEditing(false) : undefined}
      />
    );
  }

  return (
    <div className="border-t border-slate-200 p-4 sm:p-8">
      <h3 className="font-semibold text-slate-900 mb-4">
        Отзывы {total > 0 && <span className="text-slate-500 font-normal">({total})</span>}
      </h3>

      {myBlock && <div className="mb-6">{myBlock}</div>}

      {loading ? (
        <p className="text-sm text-slate-500">Загрузка…</p>
      ) : reviews.length === 0 ? (
        <p className="text-sm text-slate-500 italic">
          Пока нет отзывов. Будьте первым!
        </p>
      ) : (
        <>
          <div>
            {reviews.map((r) => (
              <ReviewItem key={r.id} review={r} />
            ))}
          </div>
          {reviews.length < total && (
            <button
              type="button"
              onClick={loadMore}
              className="mt-4 w-full sm:w-auto px-4 py-2 rounded-lg text-sm font-medium text-slate-700 border border-slate-200 hover:bg-slate-50 transition-colors"
            >
              Показать ещё ({total - reviews.length})
            </button>
          )}
        </>
      )}
    </div>
  );
}
