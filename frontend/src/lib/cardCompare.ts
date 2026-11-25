import { FINISH_LABELS, asFinish } from "@/lib/finish";
import { RARITY_LABELS, RARITY_ORDER } from "@/lib/rarity";
import type { UserCard } from "@/types";

export interface CompareRow {
  label: string;
  a: string;
  b: string;
  /** Which side is better on this line, if any. */
  win: "a" | "b" | null;
}

function better(a: number, b: number): "a" | "b" | null {
  return a > b ? "a" : b > a ? "b" : null;
}

/** The lines of «⚖️ Сравнение»: ratings, stars, rarity, skill, rare print, medals. */
export function compareRows(a: UserCard, b: UserCard): CompareRow[] {
  const rank = (c: UserCard) => RARITY_ORDER[c.player.rarity];
  const medals = (c: UserCard) => (c.arena_goals ?? 0) + (c.arena_assists ?? 0) + (c.arena_mvps ?? 0);
  const finish = (c: UserCard) => {
    const f = asFinish(c.finish);
    return f ? FINISH_LABELS[f] : "—";
  };
  return [
    { label: "Рейтинг", a: String(a.player.rating), b: String(b.player.rating), win: better(a.player.rating, b.player.rating) },
    { label: "Атака", a: String(a.player.attack_rating), b: String(b.player.attack_rating), win: better(a.player.attack_rating, b.player.attack_rating) },
    { label: "Защита", a: String(a.player.defense_rating), b: String(b.player.defense_rating), win: better(a.player.defense_rating, b.player.defense_rating) },
    { label: "Звёзды", a: "★".repeat(a.stars ?? 0) || "—", b: "★".repeat(b.stars ?? 0) || "—", win: better(a.stars ?? 0, b.stars ?? 0) },
    { label: "Редкость", a: RARITY_LABELS[a.player.rarity], b: RARITY_LABELS[b.player.rarity], win: better(rank(a), rank(b)) },
    { label: "Навык", a: a.skill_code ? "есть" : "—", b: b.skill_code ? "есть" : "—", win: better(Number(!!a.skill_code), Number(!!b.skill_code)) },
    { label: "Версия", a: finish(a), b: finish(b), win: better(Number(!!a.finish), Number(!!b.finish)) },
    { label: "Arena: Г+П+MVP", a: String(medals(a)), b: String(medals(b)), win: better(medals(a), medals(b)) },
  ];
}
