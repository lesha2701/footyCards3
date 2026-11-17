import { useState } from "react";

import { CreatureArt } from "@/components/magic/art/creatures";
import { pngArt } from "@/components/magic/art/pngArt";
import { ROMAN } from "@/components/magic/magicMeta";
import { staticUrl } from "@/lib/api";

const TIER_RING = ["", "ring-slate-300/60", "ring-sky-400/70", "ring-fuchsia-400/70", "ring-amber-300/80", "ring-cyan-200/90"];

/** One stack: the creature itself (a painted full-body PNG when there is one,
 *  else the built-in portrait), with a strip below — the footballer whose
 *  duplicates it is made of and the head count. Foes face left. */
export default function StackToken({
  unit, tier, count, image, foe = false, size = 44, active = false, dim = false, bare = false,
}: {
  unit: string;
  tier: number;
  count: number;
  image?: string | null;
  foe?: boolean;
  size?: number;
  active?: boolean;
  dim?: boolean;
  /** No tile behind the creature (on the battle field). */
  bare?: boolean;
}) {
  const [broken, setBroken] = useState(false);
  const photo = image && !broken ? staticUrl(image) : undefined;
  const png = pngArt(`creatures/${unit}`);
  const strip = Math.max(12, Math.round(size * 0.3));
  const open = bare && !!png; // on the battle field: the figure alone, no tile or ring
  // Without a ring, the side and the turn show as a glow along the figure's outline.
  const glow = open
    ? active
      ? "drop-shadow(0 0 3px rgba(252,211,77,1)) drop-shadow(0 0 8px rgba(252,211,77,0.85))"
      : foe ? "drop-shadow(0 0 1.5px rgba(239,68,68,0.95))" : "drop-shadow(0 0 1.5px rgba(255,255,255,0.7))"
    : undefined;
  return (
    <div className={`relative ${dim ? "opacity-30 grayscale" : ""}`} style={{ width: size, height: size }}>
      <div
        className={`absolute inset-0 ${open ? "" : `overflow-hidden rounded-[28%] ring-2 ${foe ? "ring-red-500/80" : TIER_RING[tier] ?? TIER_RING[1]} ${
          active ? "shadow-[0_0_16px_rgba(252,211,77,0.95)]" : "shadow-[0_4px_10px_rgba(0,0,0,0.55)]"
        }`}`}
      >
        {png ? (
          <img src={png} alt="" draggable={false} className="h-full w-full object-contain object-bottom"
            style={{ transform: foe ? "scaleX(-1)" : undefined, filter: glow }} />
        ) : (
          <div className="h-full w-full" style={foe ? { transform: "scaleX(-1)" } : undefined}>
            <CreatureArt unit={unit} size={size} />
          </div>
        )}
      </div>
      {active && !open && <span className="pointer-events-none absolute inset-0 animate-ping rounded-[28%] ring-2 ring-amber-300/70" />}
      {/* The strip: the footballer's face and the head count. */}
      <div className="absolute inset-x-0 -bottom-1 flex items-center justify-center gap-0.5">
        {photo && (
          <img src={photo} alt="" draggable={false} onError={() => setBroken(true)}
            className="rounded-full bg-black object-cover object-top ring-1 ring-white/70" style={{ width: strip, height: strip }} />
        )}
        <span
          className={`rounded-full px-1 font-mono font-black leading-tight shadow ${foe ? "bg-red-600 text-white" : "bg-amber-300 text-black"}`}
          style={{ fontSize: Math.max(9, size * 0.22) }}
        >
          {count}
        </span>
      </div>
      <span className="absolute -left-1 -top-1 rounded bg-black/75 px-0.5 font-mono font-bold leading-none text-white/85" style={{ fontSize: Math.max(7, size * 0.17) }}>
        {ROMAN[tier]}
      </span>
    </div>
  );
}
