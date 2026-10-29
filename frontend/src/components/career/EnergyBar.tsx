/** A player's energy (100 − fatigue) as a battery: full and green when he
 * is fresh, yellow when a bit tired, red when he is spent — the bar's
 * length and its colour say the same thing. */

import { energyLevel, energyOf } from "@/lib/careerEnergy";

const LEVEL = {
  fresh: { fill: "bg-accent-lime", text: "text-accent-lime", label: "свежий" },
  tired: { fill: "bg-amber-300", text: "text-amber-300", label: "немного устал" },
  spent: { fill: "bg-red-400", text: "text-red-400", label: "сильно устал" },
} as const;

/** `thin`: a 3 px strip for card tiles; otherwise a small battery with the
 * percentage next to it. */
export function EnergyBar({ fatigue, thin = false }: { fatigue: number; thin?: boolean }) {
  const energy = energyOf(fatigue);
  const level = LEVEL[energyLevel(energy)];
  const label = `Энергия ${energy}% — ${level.label}`;
  if (thin) {
    return (
      <span className="block h-[3px] w-full overflow-hidden rounded-full bg-white/10" title={label} aria-label={label}>
        <span className={`block h-full ${level.fill}`} style={{ width: `${energy}%` }} />
      </span>
    );
  }
  return (
    <span className="flex shrink-0 items-center gap-1" title={label} aria-label={label}>
      <span className="relative flex h-2.5 w-7 items-center rounded-[3px] border border-white/40 p-[1px]">
        <span className={`block h-full rounded-[1px] ${level.fill}`} style={{ width: `${energy}%` }} />
        <span className="absolute -right-[3px] top-1/2 h-1 w-[2px] -translate-y-1/2 rounded-r-sm bg-white/40" />
      </span>
      <span className={`w-7 text-right font-mono text-micro ${level.text}`}>{energy}%</span>
    </span>
  );
}
