/** Serials worth showing off — the twin of gift_service.special_serial
 * (the same cases in both tests). Codes in rarity order. */
export const SPECIAL_ORDER = ["first", "lucky", "jubilee", "twins", "round", "mirror"] as const;
export type SpecialSerial = (typeof SPECIAL_ORDER)[number];

export const SPECIAL_LABELS: Record<SpecialSerial, string> = {
  first: "Первый",
  lucky: "Счастливый",
  jubilee: "Юбилейный",
  twins: "Близнецы",
  round: "Круглый",
  mirror: "Зеркальный",
};

export function specialSerial(n: number | null | undefined): SpecialSerial | null {
  if (n == null || n < 1) return null;
  const s = String(n);
  if (n === 1) return "first";
  if (/^7+$/.test(s)) return "lucky";
  if (n >= 10 && /^10+$/.test(s)) return "jubilee";
  if (s.length >= 2 && new Set(s).size === 1) return "twins";
  if (n % 100 === 0) return "round";
  if (s.length >= 3 && s === [...s].reverse().join("")) return "mirror";
  return null;
}

/** Lower is rarer; ordinary serials go last. */
export function specialRank(n: number | null | undefined): number {
  const code = specialSerial(n);
  return code ? SPECIAL_ORDER.indexOf(code) : SPECIAL_ORDER.length;
}
