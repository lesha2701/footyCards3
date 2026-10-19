import { staticUrl } from "@/lib/api";
import { SEAT_COLORS } from "@/lib/clubBase";
import type { ClubBaseBuilding, ClubBaseCode, ClubBaseLook, ClubBaseState } from "@/types";

import { DX, artHeight, tier } from "./artMetrics";
import { ART } from "./buildingArt";

/** «Клубная база» as an illustrated campus seen from above at an angle:
 * a meadow with contour-line hills, a pond, forest and a river with a
 * bridge, roads and a car park; the stadium in the middle and the
 * buildings around it (BaseArt.tsx — each grows with its level), a crane
 * over the one under construction, the «Академия» district and the
 * finance quarter. An admin-uploaded background / building picture
 * replaces the drawn one. Purely illustrative — the numbers are in the
 * building sheet. */

type Spot = { x: number; y: number; w: number };

// x, y = front-bottom-left corner of the building.
const SPOTS: Record<Exclude<ClubBaseCode, "stadium">, Spot> = {
  hq: { x: 152, y: 76, w: 56 },
  training: { x: 110, y: 114, w: 34 },
  media: { x: 268, y: 64, w: 42 },
  analytics: { x: 292, y: 140, w: 40 },
  hotel: { x: 290, y: 224, w: 46 },
  medical: { x: 30, y: 210, w: 44 },
  marketing: { x: 198, y: 296, w: 32 },
  shop: { x: 240, y: 296, w: 32 },
  accounting: { x: 282, y: 296, w: 30 },
};

const STADIUM = { cx: 180, cy: 184, rx: 72, ry: 46 };

const ROUND_TREES: [number, number, number][] = [
  [100, 18, 6], [116, 26, 5], [222, 16, 6], [238, 24, 5], [250, 120, 5], [262, 110, 6],
  [12, 160, 6], [22, 172, 5], [96, 222, 6], [108, 234, 5], [344, 182, 6], [350, 262, 5], [12, 252, 6],
  [138, 70, 4], [128, 78, 3.5],
];
const PINES: [number, number, number][] = [
  [8, 60, 9], [20, 70, 8], [32, 62, 7], [6, 84, 7], [334, 20, 9], [348, 36, 8], [320, 30, 7],
  [346, 94, 8], [354, 112, 7], [338, 300, 8], [352, 290, 7], [84, 252, 6], [158, 34, 6], [210, 30, 6],
];
const CARS = ["#d6443a", "#2f6fd6", "#f2c230", "#eef0ea", "#2a2d2b", "#2f9e58", "#8a4fd6", "#f08a2f"];

function Terrain() {
  return (
    <g>
      <defs>
        <linearGradient id="base-land" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="rgb(var(--map-land-2))" />
          <stop offset="1" stopColor="rgb(var(--map-land))" />
        </linearGradient>
        <pattern id="base-meadow" width="9" height="9" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="3" r="0.55" fill="#ffffff" opacity="0.07" />
          <circle cx="6.5" cy="7" r="0.45" fill="#000000" opacity="0.08" />
        </pattern>
        <radialGradient id="base-vignette" cx="0.5" cy="0.5" r="0.7">
          <stop offset="0.65" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.28" />
        </radialGradient>
        <linearGradient id="base-water" x1="0" x2="1">
          <stop offset="0" stopColor="rgb(var(--map-water))" />
          <stop offset="1" stopColor="#4aa3c9" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="360" height="330" fill="url(#base-land)" />
      <rect x="0" y="0" width="360" height="330" fill="url(#base-meadow)" />
      {/* grass patches */}
      <g fill="rgb(var(--map-tree))" opacity="0.18">
        <ellipse cx="70" cy="40" rx="50" ry="22" />
        <ellipse cx="300" cy="90" rx="44" ry="30" />
        <ellipse cx="60" cy="235" rx="40" ry="18" />
        <ellipse cx="320" cy="250" rx="30" ry="40" />
      </g>
      {/* contour-line hills */}
      <g fill="none" stroke="rgb(var(--map-contour))" strokeWidth="0.6" opacity="0.4">
        {[0, 1, 2, 3, 4].map((i) => (
          <path key={`a${i}`} d={`M-10 ${100 - i * 14} C ${30 + i * 6} ${110 - i * 16}, ${80 + i * 4} ${40 - i * 8}, ${70 + i * 10} -10`} />
        ))}
        {[0, 1, 2, 3, 4].map((i) => (
          <path key={`b${i}`} d={`M370 ${120 - i * 16} C ${320 - i * 8} ${120 - i * 12}, ${300 - i * 8} ${50 - i * 8}, ${320 - i * 6} -10`} />
        ))}
        {[0, 1, 2].map((i) => <ellipse key={`c${i}`} cx="16" cy="262" rx={36 - i * 11} ry={22 - i * 6} />)}
        {[0, 1, 2].map((i) => <ellipse key={`d${i}`} cx="356" cy="214" rx={26 - i * 8} ry={40 - i * 12} />)}
      </g>
      {/* pond with reeds */}
      <ellipse cx="44" cy="28" rx="22" ry="11" fill="url(#base-water)" />
      <ellipse cx="44" cy="28" rx="22" ry="11" fill="none" stroke="#fff" strokeOpacity="0.3" strokeWidth="0.7" />
      <path d="M36 26 q 4 -2 8 0 M46 31 q 4 -2 8 0" stroke="#fff" strokeOpacity="0.35" strokeWidth="0.5" fill="none" />
      {[22, 25, 63, 66].map((x) => <line key={x} x1={x} y1={30} x2={x + 1} y2={23} stroke="#6f9a5a" strokeWidth="0.8" />)}
      {/* river with a bridge */}
      <path d="M0 316 C 60 304, 120 330, 180 318 S 300 300, 360 318 V330 H0 Z" fill="url(#base-water)" opacity="0.92" />
      <path d="M0 316 C 60 304, 120 330, 180 318 S 300 300, 360 318" fill="none" stroke="#fff" strokeOpacity="0.3" strokeWidth="0.8" />
      <path d="M20 324 q 6 -2 12 0 M120 326 q 6 -2 12 0 M250 318 q 6 -2 12 0" stroke="#fff" strokeOpacity="0.3" strokeWidth="0.5" fill="none" />
      <rect x="168" y="304" width="24" height="26" rx="2" fill="rgb(var(--map-road))" />
      <line x1="168" y1="304" x2="168" y2="330" stroke="rgb(var(--map-wall))" strokeWidth="1.4" />
      <line x1="192" y1="304" x2="192" y2="330" stroke="rgb(var(--map-wall))" strokeWidth="1.4" />
    </g>
  );
}

function Roads() {
  const r = { fill: "none", stroke: "rgb(var(--map-road))", strokeLinecap: "round" as const };
  return (
    <g>
      <ellipse cx={STADIUM.cx} cy={STADIUM.cy} rx={STADIUM.rx + 18} ry={STADIUM.ry + 16} {...r} strokeWidth="7" />
      <ellipse cx={STADIUM.cx} cy={STADIUM.cy} rx={STADIUM.rx + 18} ry={STADIUM.ry + 16} fill="none" stroke="#fff"
               strokeOpacity="0.25" strokeWidth="0.5" strokeDasharray="3 3" />
      <path d="M180 306 V246" {...r} strokeWidth="9" />
      <path d="M180 306 V246" fill="none" stroke="#fff" strokeOpacity="0.35" strokeWidth="0.6" strokeDasharray="3 3" />
      <path d="M180 122 V80" {...r} strokeWidth="6" />
      <path d="M100 166 C 72 166, 60 192, 54 210" {...r} strokeWidth="5" />
      <path d="M260 176 C 292 176, 302 204, 312 224" {...r} strokeWidth="5" />
      <path d="M250 142 C 272 120, 282 92, 290 66" {...r} strokeWidth="5" />
      <path d="M250 152 L 302 142" {...r} strokeWidth="5" />
      <path d="M180 246 C 190 272, 230 280, 270 296" {...r} strokeWidth="5" />
      <path d="M180 246 C 160 272, 120 280, 80 296" {...r} strokeWidth="5" />
      <path d="M126 142 L 130 116" {...r} strokeWidth="4" />
      {/* lamp posts along the main road */}
      {[256, 272, 288].map((y) => (
        <g key={y}>
          <circle cx="173" cy={y} r="0.9" fill="#fff7c2" />
          <circle cx="187" cy={y} r="0.9" fill="#fff7c2" />
        </g>
      ))}
    </g>
  );
}

function Parking() {
  return (
    <g>
      <rect x="146" y="254" width="24" height="42" rx="2" fill="rgb(var(--map-road))" opacity="0.9" />
      {Array.from({ length: 6 }).map((_, i) => (
        <line key={i} x1="146" x2="158" y1={258 + i * 6.5} y2={258 + i * 6.5} stroke="#fff" strokeOpacity="0.5" strokeWidth="0.4" />
      ))}
      {Array.from({ length: 5 }).map((_, i) => (
        <rect key={i} x="148" y={259.5 + i * 6.5} width="8" height="4" rx="1.2" fill={CARS[i % CARS.length]} />
      ))}
      {Array.from({ length: 4 }).map((_, i) => (
        <rect key={`b${i}`} x="160" y={262 + i * 8} width="8" height="4" rx="1.2" fill={CARS[(i + 5) % CARS.length]} />
      ))}
      <text x="158" y="252" textAnchor="middle" fontSize="5" fontWeight="800" fill="#fff" opacity="0.7">P</text>
    </g>
  );
}

function Trees() {
  return (
    <g>
      {ROUND_TREES.map(([x, y, s]) => (
        <g key={`r${x}-${y}`}>
          <ellipse cx={x + 1.5} cy={y + s * 0.85} rx={s * 0.95} ry={s * 0.35} fill="#000" opacity="0.2" />
          <circle cx={x} cy={y} r={s} fill="rgb(var(--map-tree))" />
          <circle cx={x + s * 0.35} cy={y + s * 0.2} r={s * 0.7} fill="#000" opacity="0.12" />
          <circle cx={x - s * 0.3} cy={y - s * 0.3} r={s * 0.45} fill="#fff" opacity="0.14" />
        </g>
      ))}
      {PINES.map(([x, y, s]) => (
        <g key={`p${x}-${y}`}>
          <ellipse cx={x + 1.5} cy={y + 1} rx={s * 0.5} ry={s * 0.18} fill="#000" opacity="0.2" />
          <polygon points={`${x},${y - s * 1.4} ${x + s * 0.55},${y} ${x - s * 0.55},${y}`} fill="rgb(var(--map-tree))" />
          <polygon points={`${x},${y - s * 1.4} ${x + s * 0.55},${y} ${x},${y}`} fill="#000" opacity="0.18" />
          <polygon points={`${x},${y - s * 1.75} ${x + s * 0.4},${y - s * 0.7} ${x - s * 0.4},${y - s * 0.7}`} fill="rgb(var(--map-tree))" />
        </g>
      ))}
    </g>
  );
}

function Pitch({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  return (
    <g>
      <rect x={x - 1.5} y={y - 1.5} width={w + 3} height={h + 3} rx="3" fill="#000" opacity="0.15" />
      <rect x={x} y={y} width={w} height={h} rx="2" fill="#3c9a4f" />
      {Array.from({ length: 6 }).map((_, i) => (
        <rect key={i} x={x + (i * w) / 6} y={y} width={w / 12} height={h} fill="#fff" opacity="0.07" />
      ))}
      <g fill="none" stroke="#fff" strokeOpacity="0.75" strokeWidth="0.7">
        <rect x={x + 2} y={y + 2} width={w - 4} height={h - 4} />
        <line x1={x + w / 2} y1={y + 2} x2={x + w / 2} y2={y + h - 2} />
        <circle cx={x + w / 2} cy={y + h / 2} r={h / 6} />
        <rect x={x + 2} y={y + h / 2 - h / 5} width={w / 9} height={(h * 2) / 5} />
        <rect x={x + w - 2 - w / 9} y={y + h / 2 - h / 5} width={w / 9} height={(h * 2) / 5} />
      </g>
      {/* training cones */}
      {[0.3, 0.4, 0.5, 0.6].map((f) => (
        <polygon key={f} points={`${x + w * f},${y + h * 0.78} ${x + w * f + 1},${y + h * 0.78 + 2} ${x + w * f - 1},${y + h * 0.78 + 2}`} fill="#f08a2f" />
      ))}
    </g>
  );
}

function Crane({ x, top }: { x: number; top: number }) {
  return (
    <g stroke="rgb(var(--c-legend))" strokeWidth="1.3" fill="none">
      <line x1={x} y1={top + 40} x2={x} y2={top - 14} />
      {[0, 1, 2, 3, 4].map((i) => (
        <line key={i} x1={x - 1.5} y1={top + 36 - i * 10} x2={x + 1.5} y2={top + 31 - i * 10} strokeWidth="0.5" />
      ))}
      <line x1={x - 26} y1={top - 12} x2={x + 8} y2={top - 12} />
      <line x1={x} y1={top - 14} x2={x - 18} y2={top - 12} />
      <line x1={x - 22} y1={top - 12} x2={x - 22} y2={top + 4} strokeDasharray="2 1.5" />
      <rect x={x - 25} y={top + 4} width="6" height="4" fill="rgb(var(--c-legend))" stroke="none" />
      <rect x={x + 3} y={top - 15} width="5" height="4" fill="rgb(var(--c-legend))" stroke="none" />
      <circle cx={x} cy={top - 16} r="1.6" fill="#ff5a4e" stroke="none">
        <animate attributeName="opacity" values="1;0.2;1" dur="1.2s" repeatCount="indefinite" />
      </circle>
    </g>
  );
}

function LevelPill({ x, y, level }: { x: number; y: number; level: number }) {
  const gold = level >= 10;
  return (
    <g>
      <circle cx={x} cy={y} r="6.5" fill={gold ? "#f2c230" : "rgb(var(--c-bg-base))"} stroke={gold ? "#b8862f" : "rgb(var(--c-path))"} strokeWidth="1" />
      <text x={x} y={y + 2.6} textAnchor="middle" fontSize={level >= 10 ? 6 : 7} fontWeight="800"
            fill={gold ? "#3a2a00" : "rgb(var(--c-ink-chalk))"}>{level}</text>
    </g>
  );
}

function Plot({ b, spot }: { b: ClubBaseBuilding; spot: Spot }) {
  const { x, y, w } = spot;
  return (
    <g>
      <rect x={x} y={y - 12} width={w + DX} height="12" rx="2" fill="#a38a5c" opacity="0.4" />
      <rect x={x} y={y - 12} width={w + DX} height="12" rx="2" fill="none" stroke="rgb(var(--c-ink-mist))" strokeDasharray="3 2" strokeWidth="0.8" />
      {/* fence posts and a sign */}
      {Array.from({ length: Math.floor((w + DX) / 6) + 1 }).map((_, i) => (
        <line key={i} x1={x + i * 6} y1={y} x2={x + i * 6} y2={y - 3} stroke="#c9b48a" strokeWidth="0.6" />
      ))}
      <rect x={x + (w + DX) / 2 - 9} y={y - 26} width="18" height="10" rx="1.5" fill="rgb(var(--c-bg-base))" opacity="0.85" />
      <line x1={x + (w + DX) / 2} y1={y - 16} x2={x + (w + DX) / 2} y2={y - 8} stroke="#9aa59e" strokeWidth="0.8" />
      <text x={x + (w + DX) / 2} y={y - 18.5} textAnchor="middle" fontSize="7" opacity={b.locked ? 0.5 : 1}>{b.locked ? "🔒" : b.emoji}</text>
      {!b.building && !b.locked && (
        <text x={x + (w + DX) / 2} y={y - 3} textAnchor="middle" fontSize="7" fontWeight="800" fill="rgb(var(--c-path))">+</text>
      )}
      {b.building && <Crane x={x + w + DX + 4} top={y - 34} />}
    </g>
  );
}

/** Where a building's level badge goes (drawn on a top layer, so a
 * neighbour never hides it). */
function pillAt(b: ClubBaseBuilding, spot: Spot, art?: string): [number, number] | null {
  if (b.level <= 0) return null;
  const { x, y, w } = spot;
  if (art) return [x + w + DX, y - w - 6];
  return [x + w + DX + 1, y - artHeight(b.code, b.level) - 2];
}

function Building({ b, spot, art }: { b: ClubBaseBuilding; spot: Spot; art?: string }) {
  const { x, y, w } = spot;
  if (art) {
    return (
      <g>
        <image href={staticUrl(art)} x={x - 6} y={y - w - 14} width={w + DX + 12} height={w + 14} preserveAspectRatio="xMidYMax meet" />
        {b.building && <Crane x={x + w + DX + 5} top={y - w} />}
      </g>
    );
  }
  if (b.level === 0) return <Plot b={b} spot={spot} />;
  const Art = ART[b.code];
  const top = y - artHeight(b.code, b.level);
  return (
    <g>
      <Art x={x} y={y} w={w} level={b.level} />
      {b.building && (
        <>
          <g stroke="rgb(var(--c-legend))" strokeWidth="0.6" opacity="0.85">
            {[0, 1, 2, 3].map((i) => (
              <line key={i} x1={x - 2} x2={x + w + DX + 2} y1={y - 4 - i * ((y - top) / 4)} y2={y - 4 - i * ((y - top) / 4)} />
            ))}
            <line x1={x - 2} x2={x - 2} y1={y} y2={top} />
            <line x1={x + w + DX + 2} x2={x + w + DX + 2} y1={y} y2={top} />
          </g>
          <Crane x={x + w + DX + 6} top={top} />
        </>
      )}
    </g>
  );
}

function Stadium({ b, look, art }: { b: ClubBaseBuilding; look: ClubBaseLook; art?: string }) {
  const { cx, cy, rx, ry } = STADIUM;
  if (art) {
    return (
      <g>
        <image href={staticUrl(art)} x={cx - rx - 6} y={cy - ry - 18} width={(rx + 6) * 2} height={(ry + 14) * 2}
               preserveAspectRatio="xMidYMid meet" />
        {b.building && <Crane x={cx + rx} top={cy - ry} />}
        {b.level > 0 && <LevelPill x={cx + rx - 4} y={cy - ry - 2} level={b.level} />}
      </g>
    );
  }
  if (b.level === 0) {
    return (
      <g>
        <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="#a38a5c" opacity="0.35" stroke="rgb(var(--c-ink-mist))" strokeDasharray="4 3" />
        <rect x={cx - 34} y={cy - 18} width="68" height="30" rx="2" fill="#3c9a4f" opacity="0.5" />
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize="16">🏟️</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize="8" fill="rgb(var(--c-ink-chalk))">
          {b.building ? "строится" : "участок под стадион"}
        </text>
        {b.building && <Crane x={cx + rx - 6} top={cy - ry + 10} />}
      </g>
    );
  }
  const t = tier(b.level);
  const stand = 6 + b.level * 1.8;
  const seat = SEAT_COLORS[look.seats] ?? SEAT_COLORS.red;
  const irx = rx - stand;
  const iry = ry - stand * 0.66;
  const masts: [number, number][] = [[cx - rx + 6, cy - ry + 8], [cx + rx - 6, cy - ry + 8], [cx - rx + 6, cy + ry - 8], [cx + rx - 6, cy + ry - 8]];
  const ribs = 28;
  return (
    <g>
      <defs>
        <clipPath id="base-pitch-clip"><ellipse cx={cx} cy={cy} rx={irx} ry={iry} /></clipPath>
        <radialGradient id="base-light-glow">
          <stop offset="0" stopColor="#fff7c2" stopOpacity="0.9" />
          <stop offset="1" stopColor="#fff7c2" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="base-seats" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0.6" stopColor={seat} />
          <stop offset="1" stopColor="#000" stopOpacity="0.35" />
        </radialGradient>
      </defs>
      <ellipse cx={cx + 3} cy={cy + 8} rx={rx + 3} ry={ry + 3} fill="#000" opacity="0.28" />
      {/* outer facade */}
      <ellipse cx={cx} cy={cy + 4} rx={rx} ry={ry} fill="rgb(var(--map-wall))" />
      <ellipse cx={cx} cy={cy + 4} rx={rx} ry={ry} fill="#000" opacity="0.25" />
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="rgb(var(--map-wall))" />
      {t >= 1 && Array.from({ length: ribs }).map((_, i) => {
        const a = (i / ribs) * Math.PI * 2;
        return <line key={i} x1={cx + Math.cos(a) * rx} y1={cy + Math.sin(a) * ry} x2={cx + Math.cos(a) * rx} y2={cy + Math.sin(a) * ry + 4}
                     stroke="#000" strokeOpacity="0.25" strokeWidth="0.6" />;
      })}
      <ellipse cx={cx} cy={cy} rx={rx - 2} ry={ry - 2} fill={seat} />
      <ellipse cx={cx} cy={cy} rx={rx - 2} ry={ry - 2} fill="url(#base-seats)" opacity="0.5" />
      {Array.from({ length: Math.min(9, b.level + 1) }).map((_, i) => (
        <ellipse key={i} cx={cx} cy={cy} rx={rx - 4 - i * (stand / 9)} ry={ry - 4 - i * (stand / 13)} fill="none" stroke="#000" strokeOpacity="0.15" strokeWidth="0.6" />
      ))}
      {/* vomitories */}
      {[0.25, 0.75, 1.25, 1.75].map((f) => (
        <rect key={f} x={cx + Math.cos(f * Math.PI) * (rx - stand / 2) - 1.5} y={cy + Math.sin(f * Math.PI) * (ry - stand / 3) - 1.5}
              width="3" height="3" fill="#000" opacity="0.4" />
      ))}
      <g clipPath="url(#base-pitch-clip)">
        <rect x={cx - irx} y={cy - iry} width={irx * 2} height={iry * 2} fill="#3c9a4f" />
        {Array.from({ length: 10 }).map((_, i) => (
          <rect key={i} x={cx - irx + (i * irx) / 5} y={cy - iry} width={irx / 10} height={iry * 2} fill="#fff" opacity="0.07" />
        ))}
        <g fill="none" stroke="#fff" strokeOpacity="0.8" strokeWidth="0.8">
          <rect x={cx - irx + 7} y={cy - iry + 5} width={irx * 2 - 14} height={iry * 2 - 10} />
          <line x1={cx} y1={cy - iry + 5} x2={cx} y2={cy + iry - 5} />
          <circle cx={cx} cy={cy} r={iry / 3.2} />
          <rect x={cx - irx + 7} y={cy - iry / 2.4} width={irx / 5} height={iry / 1.2} />
          <rect x={cx + irx - 7 - irx / 5} y={cy - iry / 2.4} width={irx / 5} height={iry / 1.2} />
        </g>
        <circle cx={cx + 6} cy={cy + 3} r="1.3" fill="#fff" />
      </g>
      {look.roof === "canopy" && (
        <g fill="none" stroke="rgb(var(--map-roof))" strokeOpacity="0.85" strokeWidth={stand * 0.8}>
          <path d={`M ${cx - rx * 0.7} ${cy - ry * 0.74} A ${rx - stand / 2} ${ry - stand / 3} 0 0 1 ${cx + rx * 0.7} ${cy - ry * 0.74}`} />
          <path d={`M ${cx - rx * 0.7} ${cy + ry * 0.74} A ${rx - stand / 2} ${ry - stand / 3} 0 0 0 ${cx + rx * 0.7} ${cy + ry * 0.74}`} />
        </g>
      )}
      {look.roof === "full" && (
        <g>
          <ellipse cx={cx} cy={cy} rx={rx - stand * 0.32} ry={ry - stand * 0.22} fill="none" stroke="rgb(var(--map-roof))"
                   strokeOpacity="0.7" strokeWidth={stand * 0.55} />
          <ellipse cx={cx} cy={cy} rx={rx - stand * 0.32} ry={ry - stand * 0.22} fill="none" stroke="#fff" strokeOpacity="0.25"
                   strokeWidth="0.6" strokeDasharray="2 3" />
        </g>
      )}
      {look.screen && (
        <g>
          <rect x={cx - 15} y={cy - ry - 10} width="30" height="12" rx="1.5" fill="#101418" stroke="rgb(var(--map-wall))" strokeWidth="0.8" />
          <text x={cx} y={cy - ry - 1.5} textAnchor="middle" fontSize="7" fontWeight="800" fill="#7cf0b0">2 : 1</text>
        </g>
      )}
      {t >= 2 && Array.from({ length: 8 }).map((_, i) => {
        const a = (i / 8) * Math.PI * 2 + 0.2;
        const fx = cx + Math.cos(a) * (rx + 6);
        const fy = cy + Math.sin(a) * (ry + 5);
        return (
          <g key={i}>
            <line x1={fx} y1={fy} x2={fx} y2={fy - 8} stroke="#9aa59e" strokeWidth="0.6" />
            <polygon points={`${fx},${fy - 8} ${fx + 5},${fy - 6.5} ${fx},${fy - 5}`} fill={i % 2 ? seat : "#fff"} />
          </g>
        );
      })}
      {look.lights && masts.map(([mx, my]) => (
        <g key={`${mx}-${my}`}>
          <circle cx={mx} cy={my} r="15" fill="url(#base-light-glow)" />
          <rect x={mx - 3.5} y={my - 2.5} width="7" height="3.5" rx="0.8" fill="#fffbe0" stroke="#8a8f8b" strokeWidth="0.4" />
        </g>
      ))}
      {t >= 3 && <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke="#f2c230" strokeWidth="1.4" />}
      {b.building && <Crane x={cx + rx + 4} top={cy - ry} />}
      <LevelPill x={cx + rx - 4} y={cy - ry - 2} level={b.level} />
    </g>
  );
}

function AcademyDistrict({ level, maxLevel, busy }: { level: number; maxLevel: number; busy: boolean }) {
  const houses = 5;
  const lit = maxLevel ? Math.round((level / maxLevel) * houses * 3) : 0;
  return (
    <g>
      <rect x="24" y="252" width="118" height="54" rx="8" fill="rgb(var(--c-path))" opacity="0.12"
            stroke="rgb(var(--c-path))" strokeOpacity="0.45" strokeDasharray="3 2" />
      <rect x="30" y="296" width="106" height="4" rx="2" fill="#3c9a4f" opacity="0.7" />
      {Array.from({ length: houses }).map((_, i) => {
        const x = 30 + i * 22;
        const h = 14 + ((i * 7) % 3) * 4;
        return (
          <g key={i}>
            <rect x={x} y={296 - h} width="16" height={h} fill="rgb(var(--map-wall))" />
            <rect x={x + 16} y={296 - h} width="3" height={h} fill="#000" opacity="0.2" />
            <polygon points={`${x - 2},${296 - h} ${x + 9},${287 - h} ${x + 20},${296 - h}`} fill="rgb(var(--c-path))" opacity="0.9" />
            {[0, 1, 2].map((r) => (
              <rect key={r} x={x + 4} y={292 - h + 6 + r * 4} width="8" height="2" rx="0.5"
                    fill="rgb(var(--c-legend))" opacity={i * 3 + r < lit ? 0.9 : 0.15} />
            ))}
          </g>
        );
      })}
      <rect x="44" y="255" width="86" height="11" rx="5.5" fill="rgb(var(--c-bg-base))" opacity="0.75" />
      <text x="87" y="263" textAnchor="middle" fontSize="7.5" fontWeight="800" fill="rgb(var(--c-path))">🌱 Академия · {level}</text>
      {busy && <Crane x={142} top={262} />}
    </g>
  );
}

export default function BaseMap({
  state, onPick, onAcademy,
}: { state: ClubBaseState; onPick: (code: ClubBaseCode) => void; onAcademy: () => void }) {
  const byCode = Object.fromEntries(state.buildings.map((b) => [b.code, b])) as Record<ClubBaseCode, ClubBaseBuilding>;
  const art = state.art ?? { background: null, buildings: {} };
  const interactive = (code: ClubBaseCode, label: string, node: React.ReactNode) => (
    <g
      key={code}
      role="button"
      tabIndex={0}
      aria-label={label}
      className="cursor-pointer outline-none [&:focus-visible]:opacity-80"
      onClick={() => onPick(code)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onPick(code)}
    >
      {node}
    </g>
  );
  const stadium = byCode.stadium;
  const academyBusy = state.construction?.owner === "academy";
  // Back to front, so nearer buildings overlap farther ones.
  const order = (Object.keys(SPOTS) as Exclude<ClubBaseCode, "stadium">[]).sort((a, b) => SPOTS[a].y - SPOTS[b].y);
  const building = (code: Exclude<ClubBaseCode, "stadium">) =>
    byCode[code] && interactive(code, `${byCode[code].name}, уровень ${byCode[code].level}`,
      <Building b={byCode[code]} spot={SPOTS[code]} art={art.buildings[code]} />);
  return (
    <svg viewBox="0 0 360 330" className="w-full rounded-2xl" role="img"
         aria-label={`Клубная база, уровень ${state.total_level}`}>
      {art.background ? (
        <image href={staticUrl(art.background)} x="0" y="0" width="360" height="330" preserveAspectRatio="xMidYMid slice" />
      ) : (
        <>
          <Terrain />
          <Roads />
          <Parking />
          <Pitch x={20} y={96} w={78} h={44} />
          <Pitch x={60} y={44} w={40} h={22} />
          <Trees />
        </>
      )}
      {order.filter((code) => SPOTS[code].y < STADIUM.cy).map(building)}
      {stadium && interactive("stadium", `Стадион, уровень ${stadium.level}`,
        <Stadium b={stadium} look={state.stadium.look} art={art.buildings.stadium} />)}
      {order.filter((code) => SPOTS[code].y >= STADIUM.cy).map(building)}
      <g role="button" tabIndex={0} aria-label="Академия" className="cursor-pointer outline-none" onClick={onAcademy}
         onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onAcademy()}>
        <AcademyDistrict level={state.academy_level} maxLevel={state.academy_max_level} busy={academyBusy} />
      </g>
      {order.map((code) => {
        const at = byCode[code] && pillAt(byCode[code], SPOTS[code], art.buildings[code]);
        return at ? <g key={`pill-${code}`} pointerEvents="none"><LevelPill x={at[0]} y={at[1]} level={byCode[code].level} /></g> : null;
      })}
      <rect x="198" y="300" width="114" height="12" rx="6" fill="rgb(var(--c-bg-base))" opacity="0.75" />
      <text x="255" y="308.5" textAnchor="middle" fontSize="7.5" fontWeight="800" fill="rgb(var(--c-ink-chalk))">
        💼 Финансовый департамент
      </text>
      {!art.background && <rect x="0" y="0" width="360" height="330" fill="url(#base-vignette)" pointerEvents="none" />}
    </svg>
  );
}
