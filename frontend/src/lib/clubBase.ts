import type { ClubBaseBuilding, ClubBaseState } from "@/types";

/** Stadium seat colours (codes from the server's SEAT_COLORS). */
export const SEAT_COLORS: Record<string, string> = {
  red: "#d6443a", blue: "#2f6fd6", sky: "#5bb8f0", green: "#2f9e58", yellow: "#f2c230",
  white: "#eef0ea", black: "#2a2d2b", purple: "#8a4fd6", orange: "#f08a2f",
};

export const SEAT_COLOR_NAMES: Record<string, string> = {
  red: "Красные", blue: "Синие", sky: "Голубые", green: "Зелёные", yellow: "Жёлтые",
  white: "Белые", black: "Чёрные", purple: "Фиолетовые", orange: "Оранжевые",
};

/** Time left on a construction: "2 д 5 ч", "3 ч 05 мин", "4:09". */
export function formatBuildTime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (d > 0) return `${d} д ${h} ч`;
  return h > 0 ? `${h} ч ${String(m).padStart(2, "0")} мин` : `${m}:${String(s).padStart(2, "0")}`;
}

/** Build hours as shown on a button: whole days as "N д". */
export function hoursLabel(hours: number): string {
  return hours >= 24 && hours % 24 === 0 ? `${hours / 24} д` : `${hours} ч`;
}

/** Why the upgrade button is off, or null when it can be pressed (the
 * server re-checks all of it). */
export function upgradeBlocker(state: ClubBaseState, b: ClubBaseBuilding, balance: number): string | null {
  if (!state.enabled) return "База временно закрыта";
  if (b.next_cost == null) return "Максимальный уровень";
  if (b.locked) return `Нужна штаб-квартира ур. ${b.level + 1}`;
  if (state.construction) return `Бригада занята: ${state.construction.name}`;
  if (balance < b.next_cost) return "Не хватает монет";
  return null;
}
