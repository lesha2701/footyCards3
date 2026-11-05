/** A player's energy (100 − fatigue) as a battery: full and green when he
 * is fresh, yellow when a bit tired, red when he is spent — the bar's
 * length and its colour say the same thing. */

import { energyLevel, energyOf } from "@/lib/careerEnergy";

const LEVEL = {
  fresh: { fill: "bg-accent-lime", text: "text-accent-lime", label: "свежий" },
  tired: { fill: "bg-amber-300", text: "text-amber-300", label: "немного устал" },
  spent: { fill: "bg-red-400", text: "text-red-400", label: "сильно устал" },
} as const;

/** The pitch battery: the percentage sits inside it, the fill behind the digits. */
export function EnergyBattery({ fatigue }: { fatigue: number }) {
  const energy = energyOf(fatigue);
  const level = LEVEL[energyLevel(energy)];
  return (
    <span
      role="img"
      className="relative block h-[13px] w-[calc(100%-3px)] rounded-[3px] border border-white/50 bg-black/60"
      title={`Энергия ${energy}%`}
      aria-label={`Энергия ${energy}% — ${level.label}`}
    >
      <span className={`absolute inset-y-0 left-0 rounded-[2px] opacity-80 ${level.fill}`} style={{ width: `${Math.max(6, energy)}%` }} />
      <span className="absolute inset-0 flex items-center justify-center font-mono text-[9px] font-bold leading-none text-white [text-shadow:0_0_2px_#000,0_0_2px_#000]">
        {energy}%
      </span>
      <span className="absolute -right-[3px] top-1/2 h-[5px] w-[2px] -translate-y-1/2 rounded-r-sm bg-white/50" />
    </span>
  );
}

/** `thin`: a 3 px strip; `card`: a tiny battery with its % under a card
 * tile; otherwise a small battery with the percentage next to it. */
export function EnergyBar({ fatigue, thin = false, card = false }: { fatigue: number; thin?: boolean; card?: boolean }) {
  const energy = energyOf(fatigue);
  const level = LEVEL[energyLevel(energy)];
  const label = `Энергия ${energy}% — ${level.label}`;
  if (card) {
    return (
      <span className="flex items-center justify-center gap-[3px]" title={label} aria-label={label}>
        <span className="relative flex h-[9px] w-[17px] items-center rounded-[2.5px] border border-white/45 p-[1px]">
          <span className={`block h-full rounded-[1px] ${level.fill}`} style={{ width: `${Math.max(8, energy)}%` }} />
          <span className="absolute -right-[3px] top-1/2 h-[4px] w-[2px] -translate-y-1/2 rounded-r-sm bg-white/45" />
        </span>
        <span className={`font-mono text-[10px] font-bold leading-none ${level.text}`}>{energy}%</span>
      </span>
    );
  }
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
