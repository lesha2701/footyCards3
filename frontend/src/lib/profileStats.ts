import type { ProfilePublic } from "@/types";

/** W-D-L per mode (Arena, Тактико, Пенальти). */
export function modeRows(p: ProfilePublic): [string, number, number, number][] {
  return [
    ["Arena", p.matches_won, p.matches_drawn, p.matches_lost],
    ["Тактико", p.tactics_matches_won, p.tactics_matches_drawn, p.tactics_matches_lost],
    ["Пенальти", p.penalty_matches_won, p.penalty_matches_drawn, p.penalty_matches_lost],
  ];
}

/** All modes summed: «12-3-5». */
export function record(p: ProfilePublic): string {
  const sum = (i: 1 | 2 | 3) => modeRows(p).reduce((acc, row) => acc + row[i], 0);
  return `${sum(1)}-${sum(2)}-${sum(3)}`;
}

export function dayStreakLabel(days: number): string {
  const mod10 = days % 10;
  const mod100 = days % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return "дня";
  return "дней";
}

/** 95500 → «95,5К», 1 250 000 → «1,3М». */
export function compact(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}М`;
  if (Math.abs(n) >= 10_000) return `${(n / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}К`;
  return n.toLocaleString("ru-RU");
}

