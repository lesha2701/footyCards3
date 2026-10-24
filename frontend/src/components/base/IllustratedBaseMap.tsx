import { useState } from "react";

import town from "@/assets/base/town.webp";
import type { ClubBaseBuilding, ClubBaseCode, ClubBaseState } from "@/types";

/** «Клубная база» as one illustrated town (src/assets/base/town.webp) with every
 * building already drawn. Each building is a tap zone over its picture: a built
 * one opens its sheet (the «Академия» its own page) and wears a level pill; one
 * not built yet is dimmed and greyed with a «+»; the one under construction
 * pulses. Zones are in the picture's own pixels (1024×1330). */

const W = 1024;
const H = 1330;

type Box = [x0: number, y0: number, x1: number, y1: number];

const ZONES: Record<ClubBaseCode | "academy", Box> = {
  training: [195, 25, 835, 255],
  stadium: [335, 262, 830, 520],
  hq: [30, 245, 275, 420],
  shop: [835, 392, 992, 520],
  hotel: [75, 510, 300, 670],
  medical: [358, 595, 592, 732],
  analytics: [765, 563, 966, 725],
  media: [25, 688, 215, 832],
  marketing: [598, 750, 762, 872],
  accounting: [818, 772, 1002, 905],
  academy: [88, 950, 918, 1302],
};

const pct = (v: number, of: number) => `${(v / of) * 100}%`;

export default function IllustratedBaseMap({
  state, onPick, onAcademy,
}: { state: ClubBaseState; onPick: (code: ClubBaseCode) => void; onAcademy: () => void }) {
  const [hint, setHint] = useState<string | null>(null);
  const byCode = Object.fromEntries(state.buildings.map((b) => [b.code, b])) as Record<ClubBaseCode, ClubBaseBuilding>;
  const construction = state.construction;
  const underway = (code: ClubBaseCode | "academy") =>
    construction?.owner === "academy" ? code === "academy" : construction?.owner === "base" && construction.building_code === code;

  const zones = (Object.keys(ZONES) as (ClubBaseCode | "academy")[]).map((code) => {
    const isAcademy = code === "academy";
    const b = isAcademy ? null : byCode[code];
    if (!isAcademy && !b) return null;
    const level = isAcademy ? state.academy_level : b!.level;
    const max = isAcademy ? state.academy_max_level : b!.max_level;
    const name = isAcademy ? "Академия" : b!.name;
    const label = level > 0 ? `${name} · ур. ${level}` : `${name} · построить`;
    const building = underway(code);
    const [x0, y0, x1, y1] = ZONES[code];
    return (
      <button
        key={code}
        type="button"
        onClick={() => (isAcademy ? onAcademy() : onPick(code as ClubBaseCode))}
        onMouseEnter={() => setHint(label)}
        onMouseLeave={() => setHint(null)}
        onFocus={() => setHint(label)}
        onBlur={() => setHint(null)}
        aria-label={isAcademy ? "Академия" : `${name}, уровень ${level}`}
        className={`group absolute rounded-xl outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-accent-lime ${
          building ? "animate-pulse ring-2 ring-legend" : "hover:ring-2 hover:ring-white/50"
        }`}
        style={{ left: pct(x0, W), top: pct(y0, H), width: pct(x1 - x0, W), height: pct(y1 - y0, H) }}
      >
        {level === 0 && (
          // Not built yet: the drawn building fades to a grey ghost.
          <span className="absolute inset-0 rounded-xl bg-black/45 [backdrop-filter:grayscale(1)]" aria-hidden />
        )}
        {level === 0 ? (
          <span className="absolute left-1/2 top-1/2 flex h-7 min-w-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-black/70 px-1.5 text-sm font-bold text-accent-lime ring-1 ring-accent-lime/60 group-hover:scale-110">
            {building ? "🏗" : "+"}
          </span>
        ) : (
          <span
            className={`absolute left-1/2 top-1 -translate-x-1/2 whitespace-nowrap rounded-full px-1.5 font-mono text-[10px] font-bold leading-4 shadow ring-1 ${
              level >= max ? "bg-amber-400 text-bg-base ring-amber-200" : "bg-black/70 text-ink-chalk ring-white/25"
            }`}
          >
            {building ? "🏗 " : ""}{level}
          </span>
        )}
      </button>
    );
  });

  return (
    <div className="relative">
      <div
        className="relative w-full overflow-hidden rounded-2xl ring-1 ring-white/10"
        style={{ aspectRatio: `${W} / ${H}` }}
        role="img"
        aria-label={`Клубная база, уровень ${state.total_level}`}
      >
        <img src={town} alt="" className="absolute inset-0 h-full w-full object-cover" draggable={false} />
        {zones}
      </div>
      {hint && (
        <span className="pointer-events-none absolute bottom-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-bg-base/90 px-3 py-1 text-xs font-bold text-ink-chalk ring-1 ring-path/60">
          {hint}
        </span>
      )}
    </div>
  );
}
