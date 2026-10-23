import type { KontraEvent, KontraUnit } from "@/types";

/** Border colour per card tier (legendary-level tiers share the gold). */
export const TIER_RING: Record<string, string> = {
  common: "ring-slate-400/70",
  rare: "ring-blue-400/80",
  epic: "ring-purple-400/80",
  legendary: "ring-amber-400/90",
  diamond: "ring-cyan-300/90",
  path: "ring-emerald-300/90",
  my_player: "ring-lime-300/90",
  boss: "ring-red-500/90",
};

export const TIER_LABELS: Record<string, string> = {
  common: "Обычная", rare: "Редкая", epic: "Эпическая", legendary: "Легендарная",
  diamond: "Бриллиант", path: "Академия", my_player: "Мой игрок", boss: "Босс",
};

export const ROLE_SHORT: Record<string, string> = {
  attacker: "Нап.", midfielder: "Полузащ.", defender: "Защ.", goalkeeper: "Врат.", boss: "Босс",
};

export const ROLE_FILTERS: { id: string; label: string }[] = [
  { id: "all", label: "Все" },
  { id: "attacker", label: "Нап." },
  { id: "midfielder", label: "Полузащ." },
  { id: "defender", label: "Защ." },
  { id: "goalkeeper", label: "Врат." },
];

export const EFFECT_SHORT: Record<string, string> = {
  stun: "оглуш.", yellow: "жёлтая", slow: "замедл.", shield: "щит", taunt: "провок.",
  blind: "офсайд", injury: "травма", haste: "ускор.",
};

/** «RW · Пенальти → E2 −312» style line for the battle ticker. */
export function describeEvent(e: KontraEvent, units: Map<string, KontraUnit>, abilityNames: Map<string, string>): string | null {
  const name = (id?: string) => (id ? units.get(id)?.card?.position ?? units.get(id)?.name ?? id : "");
  switch (e.kind) {
    case "hit":
      return `${name(e.actor)} · ${abilityNames.get(e.ability ?? "") ?? ""} → ${name(e.target)} −${e.damage}${e.crit ? " крит!" : ""}`;
    case "miss":
      return `${name(e.actor)} — промах (офсайд)`;
    case "heal":
      return `${name(e.target)} +${e.amount} HP`;
    case "down":
      return `${name(e.target)} выбит`;
    case "stunned":
      return `${name(e.target)} пропускает ход`;
    case "passive":
      return `${name(e.target)}: Звёздный час!`;
    case "tick":
      return `${name(e.target)} — травма −${e.damage}`;
    default:
      return null;
  }
}

/** Order of the next turns, by the turn meter (the client's preview). */
export function turnOrder(units: KontraUnit[], current: string | null, size = 5): KontraUnit[] {
  const alive = units.filter((u) => u.alive);
  const first = alive.find((u) => u.id === current);
  const rest = alive.filter((u) => u.id !== current).sort((a, b) => b.meter_pct - a.meter_pct);
  return [...(first ? [first] : []), ...rest].slice(0, size);
}
