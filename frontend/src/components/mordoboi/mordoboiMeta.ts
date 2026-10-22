import type { MordoboiAction, MordoboiExchange, MordoboiOutcome } from "@/types";

export const ACTION_ORDER: MordoboiAction[] = ["jab", "hook", "uppercut", "block", "dodge"];

export const ACTION_META: Record<MordoboiAction, { label: string; emoji: string; hint: string; tone: string }> = {
  jab: { label: "Джеб", emoji: "👊", hint: "Быстрый и дешёвый, опережает апперкот", tone: "from-sky-500/30 to-sky-500/5 ring-sky-400/40" },
  hook: { label: "Хук", emoji: "🥊", hint: "Пробивает джеб, но вязнет в уклоне", tone: "from-orange-500/30 to-orange-500/5 ring-orange-400/40" },
  uppercut: { label: "Апперкот", emoji: "💥", hint: "Самый сильный, ловит уклон; бьёт хук", tone: "from-red-500/30 to-red-500/5 ring-red-400/40" },
  block: { label: "Блок", emoji: "🛡️", hint: "Режет урон и даёт отдышаться", tone: "from-emerald-500/30 to-emerald-500/5 ring-emerald-400/40" },
  dodge: { label: "Уклон", emoji: "💨", hint: "Гасит хук и бьёт в ответ", tone: "from-violet-500/30 to-violet-500/5 ring-violet-400/40" },
};

const OUTCOME_TEXT: Record<MordoboiOutcome, string> = {
  landed: "попал",
  beaten: "не успел",
  blocked: "в блок",
  slipped: "мимо — уклон",
  caught: "поймал на уклоне",
  counter: "контратака",
  none: "",
};

export const WIN_REASON_LABELS: Record<string, string> = {
  ko: "Нокаут",
  points: "По очкам",
  double_ko: "Двойной нокдаун — решили судьи",
  forfeit: "Отказ от боя",
  timeout: "Время вышло",
};

/** «Ты: Хук — попал (12) · Соперник: Джеб — не успел» */
export function describeExchange(e: MordoboiExchange): { mine: string; theirs: string } {
  const side = (action: MordoboiAction, outcome: MordoboiOutcome, dmg: number, auto: boolean) => {
    const what = OUTCOME_TEXT[outcome];
    const parts = [ACTION_META[action].label + (auto ? " (автопилот)" : "")];
    if (what) parts.push(what + (dmg > 0 ? ` −${dmg}` : ""));
    return parts.join(" · ");
  };
  return {
    mine: side(e.my_action, e.my_outcome, e.my_damage, e.my_auto),
    theirs: side(e.opponent_action, e.opponent_outcome, e.opponent_damage, e.opponent_auto),
  };
}

/** Who "won" the exchange for the punch animation: the side that dealt more. */
export function exchangeWinner(e: MordoboiExchange): "me" | "opponent" | "even" {
  if (e.my_damage === e.opponent_damage) return "even";
  return e.my_damage > e.opponent_damage ? "me" : "opponent";
}

export function pct(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((value / max) * 100)));
}
