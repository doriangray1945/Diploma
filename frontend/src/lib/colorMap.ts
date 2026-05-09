// Approximate hex codes for the catalog enum colors. Used for round
// swatches in the variant ColorPicker. Picked to be visually distinguishable
// against a white card background while staying close to the named colour.
export const COLOR_HEX: Record<string, string> = {
  Бежевый: "#d6c2a4",
  Белый: "#f5f5f0",
  Венге: "#3b2820",
  Жёлтый: "#e8c34a",
  Зелёный: "#5d7556",
  Изумрудный: "#1d6058",
  Коричневый: "#6b4226",
  Красный: "#a83232",
  Орех: "#7a5230",
  Прозрачный: "#e8eef4",
  Розовый: "#d8a8b6",
  Серый: "#8a8b8c",
  Синий: "#3a5b8a",
  Чёрный: "#1f1f1f",
};

export function getColorHex(name?: string | null): string {
  if (!name) return "#8a8b8c";
  return COLOR_HEX[name] ?? "#8a8b8c";
}
