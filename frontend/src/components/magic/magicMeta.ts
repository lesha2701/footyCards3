import type { MagicEvent, MagicFactionCode, MagicStack } from "@/types";

export const ROMAN = ["", "I", "II", "III", "IV", "V"];
export const RACE: Record<string, string> = { dawn: "Рассвет", ash: "Пепел", wild: "Дикие" };

/** Literal Tailwind classes per faction (no string building — the purge needs them whole). */
export const FACTION_THEME: Record<MagicFactionCode, {
  card: string; ring: string; chip: string; text: string; glow: string; token: string;
}> = {
  dawn: {
    card: "bg-gradient-to-br from-amber-300/25 via-sky-500/15 to-indigo-900/40",
    ring: "ring-amber-300/60",
    chip: "bg-amber-300/20 text-amber-100",
    text: "text-amber-200",
    glow: "shadow-[0_0_24px_rgba(252,211,77,0.35)]",
    token: "from-amber-200 to-sky-500",
  },
  ash: {
    card: "bg-gradient-to-br from-red-500/25 via-purple-700/20 to-zinc-950/60",
    ring: "ring-red-400/60",
    chip: "bg-red-500/20 text-red-100",
    text: "text-red-200",
    glow: "shadow-[0_0_24px_rgba(248,113,113,0.35)]",
    token: "from-orange-400 to-purple-700",
  },
};

export const DIFFICULTY_TONE: Record<string, string> = {
  easy: "text-emerald-300",
  normal: "text-amber-300",
  hard: "text-red-300",
};

export const fmt = (n: number) => n.toLocaleString("ru-RU");

/** A readable line for the battle ticker. */
export function describeEvent(e: MagicEvent, units: Map<string, MagicStack>): string | null {
  const name = (id?: string) => {
    const u = id ? units.get(id) : undefined;
    if (!u) return id === "hero" ? "Герой" : "";
    return `${u.emoji} ${u.card ? u.name : u.unit_name}`;
  };
  switch (e.kind) {
    case "hit":
    case "shoot":
      return `${name(e.src)} → ${name(e.target)}: −${e.damage}${e.killed ? `, пало ${e.killed}` : ""}`;
    case "retaliate":
      return `Ответный удар ${name(e.src)}: −${e.damage}${e.killed ? `, пало ${e.killed}` : ""}`;
    case "spell":
      return `Магия бьёт ${name(e.target)}: −${e.damage}${e.killed ? `, пало ${e.killed}` : ""}`;
    case "cast":
      return `${e.side === "me" ? "Твой герой" : "Герой соперника"} колдует «${e.name}»`;
    case "heal":
      return `${name(e.target)}: +${e.amount} здоровья${e.raised ? `, встали ${e.raised}` : ""}`;
    case "down":
      return `${name(e.target)} — отряд пал`;
    case "rebirth":
      return `${name(e.target)} возрождается!`;
    case "hypno":
      return `🌀 Гипноз! ${name(e.target)} сражается за Безликого`;
    case "hypno_end":
      return `${name(e.target)} очнулся от гипноза`;
    case "ward":
      return `🕯️ Оберег Святилища сгорел: ${name(e.target)} не поддался гипнозу`;
    case "hook":
      return `⛓️ ${name(e.src)} притягивает ${name(e.target)} цепью`;
    case "defend":
      return `${name(e.src)} в обороне`;
    case "wait":
      return `${name(e.src)} выжидает`;
    case "lucky":
      return `🍀 Удача! ${name(e.src)} бьёт вдвое`;
    case "morale":
      return `🔥 Боевой дух: ${name(e.src)} ходит ещё раз`;
    case "round":
      return `Раунд ${e.round}`;
    case "start":
      return e.text ?? "Бой!";
    default:
      return null;
  }
}

/** Which hero class each skin dresses (mirrors the backend's SKIN_CLASS). */
export const SKIN_CLASS: Record<string, string> = {
  gold: "knight", frost: "knight", shadow: "mage", ember: "mage", grove: "ranger", night: "ranger",
};
export const CLASS_LABEL: Record<string, string> = { knight: "рыцарь", mage: "маг", ranger: "следопыт" };
