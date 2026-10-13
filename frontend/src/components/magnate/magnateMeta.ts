import type { MagnateCellType } from "@/types";

/** Grid squares per side for a board of `total` perimeter cells
 *  (24 → 7×7, 32 → 9×9). */
export function boardSide(total: number): number {
  return total / 4 + 1;
}

/** Grid position (1-based row/column, for CSS grid) of perimeter cell `index`
 *  on a board of `total` cells. 0 = «Стартовый свисток» in the bottom-right
 *  corner, then clockwise for the eye: bottom row right→left, left column
 *  bottom→top, top row left→right, right column top→bottom. */
export function cellCoord(index: number, total = 32): { row: number; col: number } {
  const side = boardSide(total);
  const edge = side - 1;
  const i = ((index % total) + total) % total;
  if (i <= edge) return { row: side, col: side - i };
  if (i <= edge * 2) return { row: side - (i - edge), col: 1 };
  if (i <= edge * 3) return { row: 1, col: 1 + (i - edge * 2) };
  return { row: 1 + (i - edge * 3), col: side };
}

export function isCorner(index: number, total: number): boolean {
  return index % (total / 4) === 0;
}

/** Token colours by seat — distinct from the club group colours. */
export const SEAT_COLORS = ["#3ed17e", "#38bdf8", "#f472b6", "#facc15"];

export const CELL_TYPE_LABELS: Record<MagnateCellType, string> = {
  start: "Стартовый свисток",
  club: "Клуб",
  stadium: "Стадион",
  var: "VAR — карточка события",
  transfer: "Трансферное окно — карточка события",
  fine: "Штраф федерации",
  jail: "Дисквалификация",
  break: "Перерыв",
  go_to_jail: "Красная карточка",
};

export const FINISH_REASON_LABELS: Record<string, string> = {
  last_standing: "Остался последний не обанкротившийся",
  rounds: "Сыграны все круги",
  time: "Вышло время партии",
  abandoned: "За столом не осталось игроков-людей",
};

export const MODE_LABELS: Record<string, string> = {
  bot: "Против ботов",
  public: "Онлайн-лобби",
  private: "Комната друзей",
};

/** In-match budget («миллионы»), not coins. */
export function formatMoney(value: number): string {
  return `${value.toLocaleString("ru-RU").replace(/\s/g, " ")} М`;
}

/** "Трибуны"/"Арена" level → short label. */
export function levelLabel(level: number): string {
  if (level <= 0) return "";
  if (level >= 4) return "Арена";
  return `Трибуны ×${level}`;
}

/** Seconds until `deadline`, corrected for the client/server clock skew
 *  observed when the match was fetched. */
export function secondsLeft(deadline: string | null, serverNow: string, fetchedAt: number, now = Date.now()): number | null {
  if (!deadline) return null;
  const skew = new Date(serverNow).getTime() - fetchedAt;
  return Math.max(0, Math.ceil((new Date(deadline).getTime() - (now + skew)) / 1000));
}

/** Pip positions (3×3 grid indices) for a die face. */
export const DIE_PIPS: Record<number, number[]> = {
  1: [4],
  2: [0, 8],
  3: [0, 4, 8],
  4: [0, 2, 6, 8],
  5: [0, 2, 4, 6, 8],
  6: [0, 2, 3, 5, 6, 8],
};
