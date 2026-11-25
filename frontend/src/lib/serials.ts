/** «Редкий номер»: copies whose serial collectors chase — the first one,
 * the last of a numbered edition, and the famous shirt numbers. */
const ICONIC = new Set([7, 9, 10, 11, 23, 77, 99, 100, 777, 1000]);

export function specialSerial(serial: number | null | undefined, editionSize?: number | null): string | null {
  if (serial == null || serial < 1) return null;
  if (serial === 1) return "Первый номер";
  if (editionSize != null && serial === editionSize) return "Последний номер тиража";
  if (ICONIC.has(serial)) return "Культовый номер";
  return null;
}
