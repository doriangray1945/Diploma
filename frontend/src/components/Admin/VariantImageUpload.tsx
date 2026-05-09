import { useRef, useState } from 'react';
import { Upload, X, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { adminApi } from '../../api/admin';

interface Props {
  images: string[];
  onChange: (images: string[]) => void;
}

export default function VariantImageUpload({ images, onChange }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(0);
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = async (files: FileList | File[]) => {
    const list = Array.from(files).filter((f) => f.type.startsWith('image/'));
    if (list.length === 0) return;
    setUploading((n) => n + list.length);
    try {
      const uploads = await Promise.all(list.map((f) => adminApi.uploadImage(f)));
      onChange([...images, ...uploads.map((u) => u.url)]);
    } catch (e) {
      console.error('Image upload failed:', e);
      alert('Не удалось загрузить одно или несколько изображений');
    } finally {
      setUploading((n) => Math.max(0, n - list.length));
    }
  };

  const removeAt = (idx: number) => {
    const next = images.slice();
    next.splice(idx, 1);
    onChange(next);
  };

  return (
    <div>
      <div className="flex flex-wrap gap-2 items-center">
        {images.map((url, i) => (
          <div
            key={`${url}-${i}`}
            className="relative w-16 h-16 rounded-md overflow-hidden border border-slate-200 group"
          >
            <img src={url} alt="" className="w-full h-full object-cover" />
            <button
              type="button"
              onClick={() => removeAt(i)}
              aria-label="Удалить фото"
              className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-white/90 flex items-center justify-center shadow opacity-0 group-hover:opacity-100 transition"
            >
              <X className="w-3 h-3 text-slate-700" />
            </button>
          </div>
        ))}

        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
          }}
          className={clsx(
            'w-16 h-16 rounded-md border-2 border-dashed flex flex-col items-center justify-center cursor-pointer text-slate-500 transition',
            dragOver ? 'border-primary-500 bg-primary-50' : 'border-slate-300 hover:border-slate-400',
          )}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) handleFiles(e.target.files);
              if (fileInputRef.current) fileInputRef.current.value = '';
            }}
          />
          {uploading > 0 ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <>
              <Upload className="w-4 h-4" />
              <span className="text-[10px] mt-0.5">Фото</span>
            </>
          )}
        </label>
      </div>
    </div>
  );
}
