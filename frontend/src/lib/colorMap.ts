// Approximate hex codes for the catalog enum colors. Used for round
// swatches in the variant ColorPicker and catalog filters. Picked to be
// visually distinguishable against a white card background while staying
// close to the named colour. Прозрачный handled separately as checkerboard.
export const COLOR_HEX: Record<string, string> = {
  Белый:      "#f5f5f0",
  Чёрный:     "#1f1f1f",
  Серый:      "#8a8b8c",
  Бежевый:    "#d6c2a4",
  Коричневый: "#6b4226",
  Красный:    "#a83232",
  Оранжевый:  "#e07c2d",
  Жёлтый:     "#e8c34a",
  Зелёный:    "#5d7556",
  Голубой:    "#5fa8d3",
  Синий:      "#3a5b8a",
  Фиолетовый: "#7a4d9b",
  Розовый:    "#d8a8b6",
  Прозрачный: "#e8eef4",
};

export function getColorHex(name?: string | null): string {
  if (!name) return "#8a8b8c";
  return COLOR_HEX[name] ?? "#8a8b8c";
}
