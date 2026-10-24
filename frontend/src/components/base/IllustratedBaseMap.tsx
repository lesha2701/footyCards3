import { useState } from "react";

import bg from "@/assets/base/bg.webp";
import type { ClubBaseBuilding, ClubBaseCode, ClubBaseState } from "@/types";

/** «Клубная база» as an illustrated town: a full-bleed evening background with
 * eleven empty plots (src/assets/base/bg.webp) and a picture of each building
 * standing on its plot. A building appears from level 1; an empty plot offers
 * to build. Tap a building — its sheet; the «Академия» opens its own page.
 * Coordinates are in the background's own pixels (1536×1024). */

const ART = import.meta.glob<string>("@/assets/base/*.webp", { eager: true, import: "default" });
const art = (code: string): string | undefined => ART[`/src/assets/base/${code}.webp`];

const W = 1536;
const H = 1024;

type Box = [x0: number, y0: number, x1: number, y1: number];
type Spot = { plot: Box; size: [number, number]; scale?: number };

// Plot bounding boxes measured on the background; size = the trimmed picture (w×h).
const SPOTS: Record<ClubBaseCode | "academy", Spot> = {
  // Smaller than its plot: the stands rise high and would hide the three plots behind it.
  stadium: { plot: [416, 264, 1120, 628], size: [760, 645], scale: 0.86 },
  training: { plot: [952, 128, 1440, 368], size: [560, 330] },
  academy: { plot: [140, 64, 556, 284], size: [480, 295] },
  hq: { plot: [96, 384, 340, 540], size: [400, 241] },
  hotel: { plot: [340, 580, 608, 760], size: [400, 314] },
  medical: { plot: [824, 684, 1148, 864], size: [400, 237] },
  analytics: { plot: [1216, 404, 1444, 536], size: [360, 302] },
  media: { plot: [1084, 528, 1364, 696], size: [400, 265] },
  shop: { plot: [632, 144, 752, 220], size: [240, 174] },
  marketing: { plot: [728, 172, 848, 252], size: [240, 185] },
  accounting: { plot: [828, 204, 956, 292], size: [240, 161] },
};

/** Where a building's picture goes: as wide as its plot, its base on the plot's bottom edge. */
function place({ plot: [x0, y0, x1, y1], size: [w, h], scale = 1.04 }: Spot) {
  const width = (x1 - x0) * scale;
  const height = (width * h) / w;
  const cx = (x0 + x1) / 2;
  const bottom = y1 + (y1 - y0) * 0.04;
  return { left: cx - width / 2, top: bottom - height, width, height, cx, plotMid: (y0 + y1) / 2 };
}

const pct = (v: number, of: number) => `${(v / of) * 100}%`;

export default function IllustratedBaseMap({
  state, onPick, onAcademy,
}: { state: ClubBaseState; onPick: (code: ClubBaseCode) => void; onAcademy: () => void }) {
  const [hint, setHint] = useState<string | null>(null);
  const byCode = Object.fromEntries(state.buildings.map((b) => [b.code, b])) as Record<ClubBaseCode, ClubBaseBuilding>;
  const construction = state.construction;
  const building = (code: ClubBaseCode | "academy") =>
    construction?.owner === "academy" ? code === "academy" : construction?.owner === "base" && construction.building_code === code;

  // Back to front: what stands lower on the picture is drawn later.
  const codes = (Object.keys(SPOTS) as (ClubBaseCode | "academy")[]).sort((a, b) => SPOTS[a].plot[3] - SPOTS[b].plot[3]);

  const tiles = codes.map((code) => {
    const spot = SPOTS[code];
    const p = place(spot);
    const isAcademy = code === "academy";
    const b = isAcademy ? null : byCode[code];
    if (!isAcademy && !b) return null;
    const level = isAcademy ? state.academy_level : b!.level;
    const max = isAcademy ? state.academy_max_level : b!.max_level;
    const name = isAcademy ? "Академия" : b!.name;
    const picture = art(code);
    const open = () => (isAcademy ? onAcademy() : onPick(code as ClubBaseCode));
    const label = level > 0 ? `${name} · ур. ${level}` : `${name} · построить`;
    const [x0, y0, x1, y1] = spot.plot;
    return (
      <button
        key={code}
        type="button"
        onClick={open}
        onMouseEnter={() => setHint(label)}
        onMouseLeave={() => setHint(null)}
        onFocus={() => setHint(label)}
        onBlur={() => setHint(null)}
        aria-label={level > 0 ? `${name}, уровень ${level}` : `${name}, не построено`}
        className="group absolute outline-none"
        style={level > 0 && picture
          ? { left: pct(p.left, W), top: pct(p.top, H), width: pct(p.width, W), height: pct(p.height, H) }
          : { left: pct(x0, W), top: pct(y0, H), width: pct(x1 - x0, W), height: pct(y1 - y0, H) }}
      >
        {level > 0 && picture ? (
          <img
            src={picture}
            alt=""
            draggable={false}
            className={`h-full w-full object-contain drop-shadow-[0_6px_6px_rgba(0,0,0,0.45)] transition-[filter,transform] duration-200 group-hover:brightness-110 group-active:scale-[0.98] ${
              building(code) ? "animate-pulse" : ""
            }`}
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center">
            <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-black/55 px-1.5 text-xs font-bold text-accent-lime ring-1 ring-accent-lime/50 group-hover:scale-110">
              {building(code) ? "🏗" : "+"}
            </span>
          </span>
        )}
        {level > 0 && (
          <span
            className={`absolute left-1/2 top-0 -translate-x-1/2 rounded-full px-1.5 font-mono text-[9px] font-bold leading-4 ring-1 ${
              level >= max ? "bg-amber-400 text-bg-base ring-amber-200" : "bg-black/65 text-ink-chalk ring-white/20"
            }`}
          >
            {building(code) ? "🏗 " : ""}{level}
          </span>
        )}
      </button>
    );
  });

  return (
    <div className="relative">
      {/* On a phone the town is wider than the screen — swipe sideways; it opens on the stadium. */}
      <div
        ref={(el) => {
          if (el && !el.dataset.centered) {
            el.dataset.centered = "1";
            el.scrollLeft = (el.scrollWidth - el.clientWidth) / 2;
          }
        }}
        className="w-full overflow-x-auto overflow-y-hidden rounded-2xl ring-1 ring-white/10 [scrollbar-width:none]"
      >
        <div
          className="relative"
          style={{ width: "max(100%, 620px)", aspectRatio: `${W} / ${H}` }}
          role="img"
          aria-label={`Клубная база, уровень ${state.total_level}`}
        >
          <img src={bg} alt="" className="absolute inset-0 h-full w-full object-cover" draggable={false} />
          {tiles}
        </div>
      </div>
      {hint && (
        <span className="pointer-events-none absolute bottom-2 left-1/2 -translate-x-1/2 rounded-full bg-bg-base/90 px-3 py-1 text-xs font-bold text-ink-chalk ring-1 ring-path/60">
          {hint}
        </span>
      )}
    </div>
  );
}
