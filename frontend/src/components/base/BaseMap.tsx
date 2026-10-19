import { useState } from "react";

import { staticUrl } from "@/lib/api";
import { SEAT_COLORS } from "@/lib/clubBase";
import type { ClubBaseBuilding, ClubBaseCode, ClubBaseLook, ClubBaseState } from "@/types";

import { DX, artHeight, tier, visualLevel } from "./artMetrics";
import { Box, Windows } from "./BaseArt";
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

const STADIUM = { cx: 180, cy: 184, rx: 60, ry: 38 };

const ROUND_TREES: [number, number, number][] = [
  [100, 18, 6], [116, 26, 5], [222, 16, 6], [238, 24, 5], [250, 120, 5], [262, 110, 6],
  [12, 160, 6], [22, 172, 5], [96, 222, 6], [108, 234, 5], [344, 182, 6], [350, 262, 5], [12, 252, 6],
  [138, 70, 4], [128, 78, 3.5],
];
const PINES: [number, number, number][] = [
  [8, 60, 9], [20, 70, 8], [32, 62, 7], [6, 84, 7], [334, 20, 9], [348, 36, 8], [320, 30, 7],
  [346, 94, 8], [354, 112, 7], [338, 300, 8], [352, 290, 7], [158, 34, 6], [210, 30, 6],
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

const ROADS: [string, number][] = [
  ["M180 306 V236", 9],
  ["M180 132 V82", 6],
  ["M104 184 C 80 184, 62 196, 56 210", 5],
  ["M256 188 C 288 188, 300 204, 312 224", 5],
  ["M246 132 C 268 112, 282 90, 290 66", 5],
  ["M256 156 L 300 144", 5],
  ["M180 262 C 200 272, 232 282, 262 296", 5],
  ["M118 236 V246", 5],
  ["M158 287 H176", 4],
  ["M128 132 L 130 116", 4],
];

function Roads() {
  const ring = {
    x: STADIUM.cx - STADIUM.rx - 16, y: STADIUM.cy - STADIUM.ry - 14,
    width: (STADIUM.rx + 16) * 2, height: (STADIUM.ry + 14) * 2, rx: 22,
  };
  return (
    <g fill="none" strokeLinecap="round">
      {/* kerbs first, asphalt on top */}
      <rect {...ring} stroke="#000" strokeOpacity="0.22" strokeWidth="9" />
      {ROADS.map(([d, w]) => <path key={`k${d}`} d={d} stroke="#000" strokeOpacity="0.22" strokeWidth={w + 2} />)}
      <rect {...ring} stroke="rgb(var(--map-road))" strokeWidth="7" />
      {ROADS.map(([d, w]) => <path key={d} d={d} stroke="rgb(var(--map-road))" strokeWidth={w} />)}
      <rect {...ring} stroke="#fff" strokeOpacity="0.22" strokeWidth="0.5" strokeDasharray="3 3" />
      <path d="M180 306 V272" stroke="#fff" strokeOpacity="0.3" strokeWidth="0.6" strokeDasharray="3 3" />
      {/* main entrance plaza with a fountain */}
      <circle cx="180" cy="262" r="12" fill="rgb(var(--map-road))" stroke="#000" strokeOpacity="0.15" />
      <circle cx="180" cy="262" r="7" fill="rgb(var(--map-wall))" />
      <circle cx="180" cy="262" r="5.6" fill="url(#base-water)" />
      <circle cx="180" cy="262" r="1.6" fill="#fff" opacity="0.8">
        <animate attributeName="r" values="1.2;2.2;1.2" dur="2.4s" repeatCount="indefinite" />
      </circle>
      {[0, 1, 2, 3, 4, 5].map((i) => {
        const a = (i / 6) * Math.PI * 2;
        return <circle key={i} cx={180 + Math.cos(a) * 10} cy={262 + Math.sin(a) * 10} r="1.4" fill="rgb(var(--map-tree))" />;
      })}
      {[280, 294].map((y) => (
        <g key={y} stroke="none">
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
      <rect x="136" y="258" width="24" height="40" rx="2.5" fill="rgb(var(--map-road))" />
      <rect x="136" y="258" width="24" height="40" rx="2.5" fill="none" stroke="#000" strokeOpacity="0.2" />
      {Array.from({ length: 6 }).map((_, i) => (
        <line key={i} x1="136" x2="146" y1={262 + i * 6} y2={262 + i * 6} stroke="#fff" strokeOpacity="0.45" strokeWidth="0.4" />
      ))}
      {Array.from({ length: 5 }).map((_, i) => (
        <rect key={i} x="137.5" y={263.2 + i * 6} width="7.5" height="3.8" rx="1.2" fill={CARS[i % CARS.length]} />
      ))}
      {Array.from({ length: 4 }).map((_, i) => (
        <rect key={`b${i}`} x="151" y={264 + i * 8} width="7.5" height="3.8" rx="1.2" fill={CARS[(i + 5) % CARS.length]} />
      ))}
      <rect x="146" y="250" width="5" height="5" rx="1" fill="#2f6fd6" />
      <rect x="148" y="251.2" width="1.2" height="2.6" fill="#fff" />
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
      <line x1={x + (w + DX) / 2 - 5} y1={y - 6} x2={x + (w + DX) / 2 - 5} y2={y - 16} stroke="#9aa59e" strokeWidth="0.8" />
      <line x1={x + (w + DX) / 2 + 5} y1={y - 6} x2={x + (w + DX) / 2 + 5} y2={y - 16} stroke="#9aa59e" strokeWidth="0.8" />
      {b.locked ? (
        <g opacity="0.8">
          <rect x={x + (w + DX) / 2 - 4} y={y - 20} width="8" height="6" rx="1" fill="#9aa59e" />
          <path d={`M${x + (w + DX) / 2 - 2.4} ${y - 20} v-2 a2.4 2.4 0 0 1 4.8 0 v2`} fill="none" stroke="#9aa59e" strokeWidth="1" />
        </g>
      ) : (
        <g>
          <rect x={x + (w + DX) / 2 - 7} y={y - 20} width="14" height="6" rx="1" fill="#f2c230" />
          {[0, 1, 2].map((i) => (
            <polygon key={i} fill="#2a2d2b"
                     points={`${x + (w + DX) / 2 - 6 + i * 5},${y - 14} ${x + (w + DX) / 2 - 3.5 + i * 5},${y - 20} ${x + (w + DX) / 2 - 1.5 + i * 5},${y - 20} ${x + (w + DX) / 2 - 4 + i * 5},${y - 14}`} />
          ))}
        </g>
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
  // The training hall sits right under the HQ: its badge goes on its left.
  if (b.code === "training") return [x - 6, y - 22];
  return [x + w + DX + 1, y - artHeight(b.code, visualLevel(b.level, b.max_level)) - 2];
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
  const vl = visualLevel(b.level, b.max_level);
  const top = y - artHeight(b.code, vl);
  return (
    <g>
      <Art x={x} y={y} w={w} level={vl} />
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
  const x0 = cx - rx;
  const y0 = cy - ry;
  const W = rx * 2;
  const H = ry * 2;
  if (b.level === 0) {
    return (
      <g>
        <rect x={x0} y={y0} width={W} height={H} rx="10" fill="#a38a5c" opacity="0.35" stroke="rgb(var(--c-ink-mist))" strokeDasharray="4 3" />
        <rect x={cx - 34} y={cy - 18} width="68" height="30" rx="2" fill="#3c9a4f" opacity="0.5" />
        {b.building && <Crane x={cx + rx - 6} top={cy - ry + 10} />}
      </g>
    );
  }
  // A rectangular football ground: four stands right up to the pitch
  // (no running track), filled corners, a membrane roof over the stands.
  const vl = visualLevel(b.level, b.max_level);
  const t = tier(vl);
  const seat = SEAT_COLORS[look.seats] ?? SEAT_COLORS.red;
  const ends = 5 + vl * 1.0; // depth of the stands behind the goals
  const sides = 4 + vl * 0.8; // depth of the long-side stands
  const px0 = x0 + ends;
  const py0 = y0 + sides;
  const pw = W - ends * 2;
  const ph = H - sides * 2;
  const pitchLine = { fill: "none", stroke: "#fff", strokeOpacity: 0.85, strokeWidth: 0.8 };
  const boxW = pw * 0.14;
  const boxH = ph * 0.5;
  // Membrane roof: the outer 60% of every covered stand.
  const rs = sides * 0.55;
  const re = ends * 0.55;
  const roofs: [number, number, number, number, "h" | "v"][] = look.roof === "none" ? [] : look.roof === "canopy"
    ? [[x0 + ends, y0, W - ends * 2, rs, "h"], [x0 + ends, y0 + H - rs, W - ends * 2, rs, "h"]]
    : [[x0, y0, W, rs, "h"], [x0, y0 + H - rs, W, rs, "h"], [x0, y0 + rs, re, H - rs * 2, "v"], [x0 + W - re, y0 + rs, re, H - rs * 2, "v"]];
  const masts: [number, number][] = [[x0 + 2, y0 + 2], [x0 + W - 2, y0 + 2], [x0 + 2, y0 + H - 2], [x0 + W - 2, y0 + H - 2]];
  return (
    <g>
      <defs>
        <pattern id="base-seat-h" width="2.4" height="1.9" patternUnits="userSpaceOnUse">
          <rect width="2.4" height="1.9" fill="#2b3036" />
          <rect x="0.25" y="0.35" width="1.9" height="1.1" rx="0.3" fill={seat} />
        </pattern>
        <pattern id="base-seat-v" width="2.4" height="1.9" patternUnits="userSpaceOnUse" patternTransform="rotate(90)">
          <rect width="2.4" height="1.9" fill="#2b3036" />
          <rect x="0.25" y="0.35" width="1.9" height="1.1" rx="0.3" fill={seat} />
        </pattern>
        <radialGradient id="base-light-glow">
          <stop offset="0" stopColor="#fff7c2" stopOpacity="0.9" />
          <stop offset="1" stopColor="#fff7c2" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect x={x0 + 3} y={y0 + 8} width={W} height={H} rx="9" fill="#000" opacity="0.28" />
      {/* facade with a little depth */}
      <rect x={x0} y={y0 + 4} width={W} height={H} rx="9" fill="rgb(var(--map-wall))" />
      <rect x={x0} y={y0 + 4} width={W} height={H} rx="9" fill="#000" opacity="0.28" />
      <rect x={x0} y={y0} width={W} height={H} rx="9" fill="rgb(var(--map-wall))" />
      {/* seats: rows of single seats on concrete terraces */}
      <polygon points={`${x0 + 2},${y0 + 2} ${x0 + W - 2},${y0 + 2} ${px0 + pw},${py0} ${px0},${py0}`} fill="url(#base-seat-h)" />
      <polygon points={`${x0 + 2},${y0 + H - 2} ${x0 + W - 2},${y0 + H - 2} ${px0 + pw},${py0 + ph} ${px0},${py0 + ph}`} fill="url(#base-seat-h)" />
      <polygon points={`${x0 + 2},${y0 + 2} ${px0},${py0} ${px0},${py0 + ph} ${x0 + 2},${y0 + H - 2}`} fill="url(#base-seat-v)" />
      <polygon points={`${x0 + W - 2},${y0 + 2} ${px0 + pw},${py0} ${px0 + pw},${py0 + ph} ${x0 + W - 2},${y0 + H - 2}`} fill="url(#base-seat-v)" />
      {/* stairways cut the stands into sectors */}
      <g stroke="#d9d6cf" strokeOpacity="0.75" strokeWidth="0.6">
        {Array.from({ length: Math.floor(pw / 16) + 1 }).map((_, i) => {
          const x = px0 + (i * pw) / Math.floor(pw / 16);
          return (
            <g key={`v${i}`}>
              <line x1={x} y1={y0 + 2} x2={x} y2={py0} />
              <line x1={x} y1={py0 + ph} x2={x} y2={y0 + H - 2} />
            </g>
          );
        })}
        {Array.from({ length: Math.floor(ph / 14) + 1 }).map((_, i) => {
          const y = py0 + (i * ph) / Math.floor(ph / 14);
          return (
            <g key={`h${i}`}>
              <line x1={x0 + 2} y1={y} x2={px0} y2={y} />
              <line x1={px0 + pw} y1={y} x2={x0 + W - 2} y2={y} />
            </g>
          );
        })}
      </g>
      {/* corner stands are separate blocks */}
      <g stroke="rgb(var(--map-wall))" strokeWidth="1">
        <line x1={px0} y1={py0} x2={x0 + 3} y2={y0 + 3} />
        <line x1={px0 + pw} y1={py0} x2={x0 + W - 3} y2={y0 + 3} />
        <line x1={px0} y1={py0 + ph} x2={x0 + 3} y2={y0 + H - 3} />
        <line x1={px0 + pw} y1={py0 + ph} x2={x0 + W - 3} y2={y0 + H - 3} />
      </g>
      {/* pitch */}
      <rect x={px0} y={py0} width={pw} height={ph} fill="#3c9a4f" />
      {Array.from({ length: 10 }).map((_, i) => (
        <rect key={i} x={px0 + (i * pw) / 10} y={py0} width={pw / 20} height={ph} fill="#fff" opacity="0.07" />
      ))}
      <g {...pitchLine}>
        <rect x={px0 + 4} y={py0 + 3.5} width={pw - 8} height={ph - 7} />
        <line x1={cx} y1={py0 + 3} x2={cx} y2={py0 + ph - 3} />
        <circle cx={cx} cy={cy} r={ph / 6} />
        <rect x={px0 + 3} y={cy - boxH / 2} width={boxW} height={boxH} />
        <rect x={px0 + pw - 3 - boxW} y={cy - boxH / 2} width={boxW} height={boxH} />
        <rect x={px0 + 3} y={cy - boxH / 4} width={boxW / 2.4} height={boxH / 2} />
        <rect x={px0 + pw - 3 - boxW / 2.4} y={cy - boxH / 4} width={boxW / 2.4} height={boxH / 2} />
      </g>
      {/* advertising boards around the pitch */}
      <rect x={px0 + 0.6} y={py0 + 0.6} width={pw - 1.2} height={ph - 1.2} fill="none" stroke="#16204a" strokeWidth="1.2" />
      <rect x={px0 + 0.6} y={py0 + 0.6} width={pw - 1.2} height={ph - 1.2} fill="none" stroke="#f2c230" strokeWidth="1.2" strokeDasharray="5 9" />
      <rect x={px0 + 1} y={cy - 3} width="2" height="6" fill="#fff" />
      <rect x={px0 + pw - 3} y={cy - 3} width="2" height="6" fill="#fff" />
      <circle cx={cx + 6} cy={cy + 3} r="1.3" fill="#fff" />
      {/* membrane roof on trusses */}
      {roofs.map(([x, y, w, h, dir]) => (
        <g key={`${x}-${y}`}>
          <rect x={x} y={y + 2} width={w} height={h} fill="#000" opacity="0.16" />
          <rect x={x} y={y} width={w} height={h} rx="2" fill="#eef1f3" opacity="0.93" stroke="#8d969c" strokeWidth="0.6" />
          {dir === "h"
            ? Array.from({ length: Math.floor(w / 8) }).map((_, i) => (
              <line key={i} x1={x + 4 + i * 8} y1={y} x2={x + 4 + i * 8} y2={y + h} stroke="#aab3b9" strokeWidth="0.5" />
            ))
            : Array.from({ length: Math.floor(h / 8) }).map((_, i) => (
              <line key={i} x1={x} y1={y + 4 + i * 8} x2={x + w} y2={y + 4 + i * 8} stroke="#aab3b9" strokeWidth="0.5" />
            ))}
        </g>
      ))}
      {look.screen && (
        <g>
          <rect x={cx - 15} y={y0 - 10} width="30" height="12" rx="1.5" fill="#101418" stroke="rgb(var(--map-wall))" strokeWidth="0.8" />
          <text x={cx} y={y0 - 1.5} textAnchor="middle" fontSize="7" fontWeight="800" fill="#7cf0b0">2 : 1</text>
        </g>
      )}
      {t >= 2 && [0.2, 0.4, 0.6, 0.8].flatMap((f) => [[x0 + W * f, y0 + H + 12], [x0 + W * f, y0 - 2]]).map(([fx, fy], i) => (
        <g key={i}>
          <line x1={fx} y1={fy} x2={fx} y2={fy - 8} stroke="#9aa59e" strokeWidth="0.6" />
          <polygon points={`${fx},${fy - 8} ${fx + 5},${fy - 6.5} ${fx},${fy - 5}`} fill={i % 2 ? seat : "#fff"} />
        </g>
      ))}
      {look.lights && masts.map(([mx, my]) => (
        <g key={`${mx}-${my}`}>
          <circle cx={mx} cy={my} r="15" fill="url(#base-light-glow)" />
          <rect x={mx - 3.5} y={my - 2.5} width="7" height="3.5" rx="0.8" fill="#fffbe0" stroke="#8a8f8b" strokeWidth="0.4" />
        </g>
      ))}
      {t >= 3 && <rect x={x0} y={y0} width={W} height={H} rx="9" fill="none" stroke="#f2c230" strokeWidth="1.4" />}
      {b.building && <Crane x={cx + rx + 4} top={cy - ry} />}
      <LevelPill x={cx + rx - 4} y={cy - ry - 2} level={b.level} />
    </g>
  );
}

function AcademyDistrict({ level, maxLevel, busy }: { level: number; maxLevel: number; busy: boolean }) {
  const vl = visualLevel(level, maxLevel);
  const floors = 1 + Math.ceil(vl / 3.4);
  const h = floors * 7 + 5;
  return (
    <g>
      <rect x="22" y="246" width="108" height="56" rx="10" fill="rgb(var(--map-tree))" opacity="0.14" />
      <Pitch x={88} y={250} w={34} h={22} />
      <Pitch x={88} y={276} w={34} h={22} />
      {vl >= 7 && [[87, 249], [123, 249], [87, 299], [123, 299]].map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="1.3" fill="#fff7c2" />
      ))}
      <ellipse cx="54" cy="299" rx="28" ry="4" fill="#000" opacity="0.2" />
      <Box x={30} y={298} w={40} h={h} front="#f1efe6" roof="rgb(var(--c-path))" />
      <Windows x={32} y={296} w={36} rows={floors} cols={5} rowH={7} seed={9} />
      <rect x={46} y={290} width="8" height="8" fill="#2d4a3c" />
      <rect x={34} y={298 - h + 1.5} width="32" height="3" rx="1" fill="rgb(var(--c-path))" />
      <circle cx={50 + DX / 2} cy={298 - h - 6} r="2.2" fill="rgb(var(--c-path))" />
      {busy && <Crane x={78} top={298 - h} />}
      {level > 0 && <LevelPill x={80} y={298 - h - 8} level={level} />}
    </g>
  );
}

export default function BaseMap({
  state, onPick, onAcademy,
}: { state: ClubBaseState; onPick: (code: ClubBaseCode) => void; onAcademy: () => void }) {
  const byCode = Object.fromEntries(state.buildings.map((b) => [b.code, b])) as Record<ClubBaseCode, ClubBaseBuilding>;
  const art = state.art ?? { background: null, buildings: {} };
  const [hint, setHint] = useState<{ x: number; y: number; text: string } | null>(null);
  const hover = (x: number, y: number, text: string) => ({
    onMouseEnter: () => setHint({ x, y, text }),
    onMouseLeave: () => setHint(null),
    onFocus: () => setHint({ x, y, text }),
    onBlur: () => setHint(null),
  });
  const anchor = (code: ClubBaseCode): [number, number] => {
    if (code === "stadium") return [STADIUM.cx, STADIUM.cy - STADIUM.ry - 14];
    const b = byCode[code];
    const spot = SPOTS[code];
    return pillAt(b, spot, art.buildings[code]) ?? [spot.x + spot.w / 2, spot.y - 26];
  };
  const interactive = (code: ClubBaseCode, label: string, node: React.ReactNode) => (
    <g
      key={code}
      role="button"
      tabIndex={0}
      aria-label={label}
      className="cursor-pointer outline-none [&:focus-visible]:opacity-80"
      onClick={() => onPick(code)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onPick(code)}
      {...hover(...anchor(code), byCode[code] ? `${byCode[code].name} · ${byCode[code].level}` : label)}
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
          <Pitch x={30} y={100} w={60} h={38} />
          <Trees />
        </>
      )}
      {order.filter((code) => SPOTS[code].y < STADIUM.cy).map(building)}
      {stadium && interactive("stadium", `Стадион, уровень ${stadium.level}`,
        <Stadium b={stadium} look={state.stadium.look} art={art.buildings.stadium} />)}
      {order.filter((code) => SPOTS[code].y >= STADIUM.cy).map(building)}
      <g role="button" tabIndex={0} aria-label="Академия" className="cursor-pointer outline-none" onClick={onAcademy}
         onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onAcademy()}
         {...hover(60, 250, `Академия · ${state.academy_level}`)}>
        <AcademyDistrict level={state.academy_level} maxLevel={state.academy_max_level} busy={academyBusy} />
      </g>
      {order.map((code) => {
        const at = byCode[code] && pillAt(byCode[code], SPOTS[code], art.buildings[code]);
        return at ? <g key={`pill-${code}`} pointerEvents="none"><LevelPill x={at[0]} y={at[1]} level={byCode[code].level} /></g> : null;
      })}

      {!art.background && <rect x="0" y="0" width="360" height="330" fill="url(#base-vignette)" pointerEvents="none" />}
      {hint && (() => {
        const w = hint.text.length * 4.4 + 12;
        const x = Math.min(356 - w, Math.max(4, hint.x - w / 2));
        const y = Math.max(4, hint.y - 22);
        return (
          <g pointerEvents="none">
            <rect x={x} y={y} width={w} height="14" rx="7" fill="rgb(var(--c-bg-base))" opacity="0.92" stroke="rgb(var(--c-path))" strokeOpacity="0.6" />
            <text x={x + w / 2} y={y + 9.6} textAnchor="middle" fontSize="7.5" fontWeight="700" fill="rgb(var(--c-ink-chalk))">{hint.text}</text>
          </g>
        );
      })()}
    </svg>
  );
}
