import { useState } from "react";

import { staticUrl } from "@/lib/api";
import { SEAT_COLORS } from "@/lib/clubBase";
import type { ClubBaseBuilding, ClubBaseCode, ClubBaseLook, ClubBaseState } from "@/types";

import { AcademyArt, GroundEllipse, IsoBox, IsoPitch, Pine, Quad, Tree } from "./BaseArt";
import { tier, topZ, visualLevel } from "./artMetrics";
import { ART } from "./buildingArt";
import { GRID, type Pt, pt, pts, shade } from "./iso";

/** «Клубная база» as an isometric island: a grass board with an earth
 * edge, contour-line hills, a pond and a river with a bridge; roads with
 * kerbs, a fountain plaza and a car park; the stadium bowl in the middle
 * and the buildings around it (BaseArt.tsx — each grows with its level),
 * a crane over the one under construction and the «Академия» with its two
 * pitches. Objects are drawn back to front. No captions — the name and
 * level show on hover / focus, a tap opens the sheet. An admin-uploaded
 * background / building picture replaces the drawn one. */

type Foot = { x: number; y: number; w: number; d: number };

const SPOTS: Record<Exclude<ClubBaseCode, "stadium">, Foot> = {
  hq: { x: 3, y: 2.5, w: 4, d: 3 },
  training: { x: 11, y: 2, w: 3, d: 3 },
  media: { x: 21, y: 5.5, w: 3, d: 2 },
  analytics: { x: 20.5, y: 9, w: 3, d: 2.6 },
  hotel: { x: 20.5, y: 16, w: 3, d: 3 },
  medical: { x: 2, y: 9, w: 3, d: 3 },
  marketing: { x: 17, y: 20.6, w: 2, d: 2 },
  shop: { x: 14, y: 20.6, w: 2, d: 2 },
  accounting: { x: 10.8, y: 20.6, w: 2, d: 2 },
};
const STADIUM: Foot = { x: 9, y: 9, w: 8, d: 7 };
const ACADEMY: Foot = { x: 2, y: 15, w: 3, d: 2 };

const ROADS: Foot[] = [
  { x: 7.5, y: 7.5, w: 11, d: 1 }, { x: 7.5, y: 16.5, w: 11, d: 1 }, { x: 7.5, y: 8.5, w: 1, d: 8 }, { x: 17.5, y: 8.5, w: 1, d: 8 },
  { x: 18.5, y: 12, w: 7.5, d: 1 }, // main avenue to the bridge
  { x: 4.5, y: 5.5, w: 1, d: 2 }, { x: 4.5, y: 7.5, w: 3, d: 1 }, // HQ
  { x: 12, y: 5, w: 1, d: 2.5 }, // training centre
  { x: 5, y: 10, w: 2.5, d: 1 }, // medical
  { x: 5, y: 15.5, w: 2.5, d: 1 }, // academy
  { x: 14.5, y: 17.5, w: 1, d: 1.9 }, { x: 11, y: 19.4, w: 8, d: 0.9 }, // finance
  { x: 18.5, y: 10, w: 2, d: 0.9 }, // analytics
  { x: 18.5, y: 7.6, w: 2.5, d: 0.9 }, // media
  { x: 18.5, y: 16.6, w: 2, d: 0.9 }, // hotel
  // district streets round the club's grounds, running off the map
  { x: -1.6, y: -30, w: 1.1, d: 90 }, { x: -30, y: -1.6, w: 54.3, d: 1.1 }, { x: -30, y: 26.6, w: 54.3, d: 1.1 },
  { x: 26.3, y: 12, w: 20, d: 1 }, // the avenue beyond the bridge
  { x: 26.3, y: -1.6, w: 20, d: 1.1 }, { x: 26.3, y: 26.6, w: 20, d: 1.1 },
];

const TREES: [number, number, number][] = [
  [1, 1, 0.9], [10, 0.6, 0.8], [8, 4.6, 0.9], [9.3, 5.6, 0.7], [20.8, 0.8, 0.9], [22.6, 2.6, 0.8], [1, 7, 0.8],
  [0.8, 13, 0.9], [6.6, 13.2, 0.7], [1.4, 22.8, 0.9], [9.8, 23.4, 0.8], [13, 24, 0.9], [19.6, 23.4, 0.8],
  [23, 21.2, 0.9], [23.2, 14.6, 0.8], [16.2, 6, 0.7], [6.2, 18, 0.6],
];
const PINES: [number, number, number][] = [
  [0.8, 4.4, 1], [1.8, 5.6, 0.9], [0.6, 17.4, 1], [1, 25, 0.9], [4, 24.6, 1], [21.8, 24, 0.9], [22.8, 4.4, 1],
  [16, 24.6, 0.9], [7.4, 0.8, 0.9], [18.8, 0.1, 1], [23.4, 23, 0.9], [11.6, 24.8, 0.8],
];
const CARS = ["#d6443a", "#2f6fd6", "#f2c230", "#eef0ea", "#2a2d2b", "#2f9e58", "#8a4fd6", "#f08a2f"];
const FACADES: Record<string, string> = { concrete: "#c9cbc4", brick: "#b5634b", glass: "#8fc3e8", gold: "#e2b84a" };

// The frame shows the club's grounds inside a bigger district: the map
// continues past every edge (roads, the river, neighbours' houses, fields).
const VB = { x: 18, y: 14, w: 328, h: 220 };

// Neighbourhood around the club: [x, y, w, d, h, wall, roof].
const NEIGHBOURS: [number, number, number, number, number, string, string][] = [
  [-4.5, 3, 2, 2, 1.1, "#e9e2d4", "#a5543f"], [-4.5, 7, 2, 1.6, 0.9, "#ece6da", "#5f7f9f"], [-7.5, 5, 2, 2, 1.3, "#e4dccb", "#7a8a5a"],
  [-4.5, 13, 2, 2, 1.2, "#efe8dc", "#a5543f"], [-7.5, 11, 2, 2, 0.9, "#e9e2d4", "#5f7f9f"], [-4.5, 21, 2.4, 2, 1.4, "#e4dccb", "#8a5a8a"],
  [4, -4.5, 2, 2, 1.0, "#ece6da", "#a5543f"], [8, -4.5, 2.2, 2, 1.3, "#e9e2d4", "#5f7f9f"], [13, -5, 2, 2.4, 1.1, "#efe8dc", "#7a8a5a"],
  [17, -4.5, 2, 2, 0.9, "#e4dccb", "#a5543f"], [6, -8, 2, 2, 1.0, "#ece6da", "#8a5a8a"],
  [5, 29, 2, 2, 1.1, "#e9e2d4", "#5f7f9f"], [9, 29, 2.2, 2, 1.3, "#efe8dc", "#a5543f"], [13, 29.5, 2, 2, 1.0, "#e4dccb", "#7a8a5a"],
  [28.5, 3, 2, 2, 1.2, "#ece6da", "#a5543f"], [28.5, 8, 2, 2.4, 1.4, "#e9e2d4", "#5f7f9f"], [28.5, 16, 2.2, 2, 1.1, "#efe8dc", "#8a5a8a"],
  [31.5, 14.2, 2, 2, 1.0, "#e4dccb", "#7a8a5a"],
];
const OUTER_TREES: [number, number, number][] = [
  [-2.5, 1, 0.9], [-3, 10, 0.8], [-2.6, 18, 0.9], [-6, 16, 0.8], [-3.6, 24.6, 0.9], [2, -2.6, 0.9], [11, -2.6, 0.8],
  [20, -3, 0.9], [22.6, -3.6, 0.8], [2, 28.5, 0.8], [17, 28.6, 0.9], [18.4, 31, 0.8], [27.4, 21, 0.9], [27.6, 5.6, 0.8], [31, 7, 0.8],
];
// Fields: [x, y, w, d, colour].
const FIELDS: [number, number, number, number, string][] = [
  [-9, 17, 4, 5, "#7aa35a"], [-9, 22.5, 4, 4, "#a7b85c"], [19, -9, 5, 4, "#a7b85c"], [26.8, -9, 4, 4, "#7aa35a"],
  [19.6, 28.5, 4, 4, "#7aa35a"], [29, 20.5, 4, 5, "#a7b85c"],
];

function Ground() {
  const n = GRID;
  return (
    <g>
      <defs>
        <linearGradient id="base-land" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="rgb(var(--map-land-2))" />
          <stop offset="1" stopColor="rgb(var(--map-land))" />
        </linearGradient>
        <linearGradient id="base-water" x1="0" x2="1">
          <stop offset="0" stopColor="rgb(var(--map-water))" />
          <stop offset="1" stopColor="#4aa3c9" />
        </linearGradient>
      </defs>
      {/* the whole district */}
      <rect x={VB.x - 2} y={VB.y - 2} width={VB.w + 4} height={VB.h + 4} fill="url(#base-land)" />
      {FIELDS.map(([x, y, w, d, c]) => (
        <g key={`${x}-${y}`}>
          <Quad x={x} y={y} w={w} d={d} fill={c} opacity={0.35} />
          {Array.from({ length: 5 }).map((_, i) => (
            <polyline key={i} points={pts([pt(x + 0.3, y + ((i + 0.5) * d) / 5), pt(x + w - 0.3, y + ((i + 0.5) * d) / 5)])}
                      stroke="#000" strokeOpacity="0.12" strokeWidth="0.4" fill="none" />
          ))}
        </g>
      ))}
      {[1.4, 2.4, 3.4].map((r) => <GroundEllipse key={`a${r}`} cx={-8} cy={2} r={r} fill="none" stroke="rgb(var(--map-contour))" opacity={0.4} />)}
      {[1.2, 2.2, 3.2].map((r) => <GroundEllipse key={`b${r}`} cx={31} cy={28} r={r} fill="none" stroke="rgb(var(--map-contour))" opacity={0.4} />)}
      {/* the club's grounds: lighter grass inside a hedge */}
      <polygon points={pts([pt(0, 0), pt(n, 0), pt(n, n), pt(0, n)])} fill="rgb(var(--map-land-2))" opacity="0.55" />
      <polygon points={pts([pt(0, 0), pt(24, 0), pt(24, n), pt(0, n)])} fill="none" stroke="rgb(var(--map-tree))" strokeWidth="1.6" strokeLinejoin="round" />
      <GroundEllipse cx={5} cy={4} r={3.5} fill="rgb(var(--map-tree))" opacity={0.12} />
      <GroundEllipse cx={22} cy={20} r={3.5} fill="rgb(var(--map-tree))" opacity={0.12} />
      {/* pond */}
      <GroundEllipse cx={8.4} cy={1.6} r={1.1} fill="url(#base-water)" stroke="#ffffff" />
      {/* the river runs through the whole district */}
      <polygon points={pts([pt(24.3, -30), pt(26.3, -30), pt(26.3, 60), pt(24.3, 60)])} fill="url(#base-water)" />
      <polyline points={pts([pt(24.3, -30), pt(24.3, 60)])} stroke="#e9e2cf" strokeOpacity="0.5" strokeWidth="0.8" fill="none" />
      <polyline points={pts([pt(26.3, -30), pt(26.3, 60)])} stroke="#e9e2cf" strokeOpacity="0.5" strokeWidth="0.8" fill="none" />
      {[-6, 3, 9, 17, 22, 30].map((y) => (
        <polyline key={y} points={pts([pt(24.9, y), pt(25.6, y + 1)])} stroke="#fff" strokeOpacity="0.35" strokeWidth="0.5" fill="none" />
      ))}
    </g>
  );
}

function Roads() {
  return (
    <g>
      {ROADS.map((r) => <Quad key={`k${r.x}-${r.y}`} x={r.x - 0.08} y={r.y - 0.08} w={r.w + 0.16} d={r.d + 0.16} fill="#000" opacity={0.2} />)}
      {ROADS.map((r) => <Quad key={`${r.x}-${r.y}`} x={r.x} y={r.y} w={r.w} d={r.d} fill="rgb(var(--map-road))" />)}
      {/* dashed centre line on the avenue and the bridge */}
      <polyline points={pts([pt(18.6, 12.5), pt(46, 12.5)])} stroke="#fff" strokeOpacity="0.35" strokeWidth="0.5" strokeDasharray="2 2" fill="none" />
      {[-1.05, 27.15].map((y) => (
        <IsoBox key={y} x={24.2} y={y - 0.6} w={2.2} d={1.2} h={0.25} color="#b8b0a0" top="rgb(var(--map-road))" />
      ))}
      <IsoBox x={24.2} y={11.8} w={2.2} d={1.4} h={0.25} color="#b8b0a0" top="rgb(var(--map-road))" />
      {/* fountain plaza on the avenue */}
      <GroundEllipse cx={21.2} cy={12.5} r={1.15} fill="rgb(var(--map-road))" stroke="#000" />
      <GroundEllipse cx={21.2} cy={12.5} r={0.75} fill="#d9d4c7" />
      <GroundEllipse cx={21.2} cy={12.5} r={0.6} fill="url(#base-water)" />
      {(() => { const [fx, fy] = pt(21.2, 12.5, 0.4); return (
        <circle cx={fx} cy={fy} r="1.2" fill="#fff" opacity="0.8">
          <animate attributeName="r" values="0.8;1.8;0.8" dur="2.4s" repeatCount="indefinite" />
        </circle>
      ); })()}
    </g>
  );
}

function Parking() {
  const p = { x: 19.6, y: 13.6, w: 3.2, d: 2.1 };
  return (
    <g>
      <Quad {...p} fill="rgb(var(--map-road))" stroke="#000" strokeWidth={0.3} />
      {Array.from({ length: 5 }).map((_, i) => (
        <polyline key={i} points={pts([pt(p.x + 0.2 + i * 0.6, p.y + 0.1), pt(p.x + 0.2 + i * 0.6, p.y + 0.9)])} stroke="#fff" strokeOpacity="0.5" strokeWidth="0.35" fill="none" />
      ))}
      {Array.from({ length: 4 }).map((_, i) => (
        <IsoBox key={i} x={p.x + 0.3 + i * 0.6} y={p.y + 0.2} w={0.4} d={0.6} h={0.28} color={CARS[i % CARS.length]} edge={false} />
      ))}
      {Array.from({ length: 4 }).map((_, i) => (
        <IsoBox key={`b${i}`} x={p.x + 0.3 + i * 0.7} y={p.y + 1.25} w={0.4} d={0.6} h={0.28} color={CARS[(i + 4) % CARS.length]} edge={false} />
      ))}
    </g>
  );
}

function Crane({ at, topPx }: { at: Pt; topPx: number }) {
  const [x, base] = at;
  const top = Math.min(topPx, base - 20);
  return (
    <g stroke="rgb(var(--c-legend))" strokeWidth="1.2" fill="none">
      <line x1={x} y1={base} x2={x} y2={top - 10} />
      {Array.from({ length: Math.floor((base - top) / 8) }).map((_, i) => (
        <line key={i} x1={x - 1.4} y1={base - i * 8} x2={x + 1.4} y2={base - i * 8 - 5} strokeWidth="0.45" />
      ))}
      <line x1={x - 22} y1={top - 8} x2={x + 7} y2={top - 8} />
      <line x1={x} y1={top - 10} x2={x - 15} y2={top - 8} />
      <line x1={x - 19} y1={top - 8} x2={x - 19} y2={top + 6} strokeDasharray="2 1.5" />
      <rect x={x - 21.5} y={top + 6} width="5" height="3.5" fill="rgb(var(--c-legend))" stroke="none" />
      <rect x={x + 2.5} y={top - 11} width="4.5" height="3.5" fill="rgb(var(--c-legend))" stroke="none" />
      <circle cx={x} cy={top - 12} r="1.4" fill="#ff5a4e" stroke="none">
        <animate attributeName="opacity" values="1;0.2;1" dur="1.2s" repeatCount="indefinite" />
      </circle>
    </g>
  );
}

function LevelPill({ at, level, gold }: { at: Pt; level: number; gold: boolean }) {
  const [x, y] = at;
  return (
    <g pointerEvents="none">
      <circle cx={x} cy={y} r="6.3" fill={gold ? "#f2c230" : "rgb(var(--c-bg-base))"} stroke={gold ? "#b8862f" : "rgb(var(--c-path))"} strokeWidth="1" />
      <text x={x} y={y + 2.5} textAnchor="middle" fontSize={level >= 10 ? 6 : 7} fontWeight="800" fill={gold ? "#3a2a00" : "rgb(var(--c-ink-chalk))"}>{level}</text>
    </g>
  );
}

function Plot({ b, f }: { b: ClubBaseBuilding; f: Foot }) {
  const [sx, sy] = pt(f.x + f.w / 2, f.y + f.d / 2, 0);
  return (
    <g>
      <Quad {...f} fill="#a38a5c" opacity={0.45} />
      <Quad {...f} fill="none" stroke="rgb(var(--c-ink-mist))" dash="2 1.5" strokeWidth={0.6} />
      <line x1={sx - 4} y1={sy} x2={sx - 4} y2={sy - 10} stroke="#9aa59e" strokeWidth="0.7" />
      <line x1={sx + 4} y1={sy} x2={sx + 4} y2={sy - 10} stroke="#9aa59e" strokeWidth="0.7" />
      {b.locked ? (
        <g opacity="0.85">
          <rect x={sx - 3.5} y={sy - 15} width="7" height="5.5" rx="1" fill="#9aa59e" />
          <path d={`M${sx - 2} ${sy - 15} v-1.8 a2 2 0 0 1 4 0 v1.8`} fill="none" stroke="#9aa59e" strokeWidth="1" />
        </g>
      ) : (
        <g>
          <rect x={sx - 6} y={sy - 14} width="12" height="5" rx="1" fill="#f2c230" />
          {[0, 1, 2].map((i) => (
            <polygon key={i} fill="#2a2d2b" points={`${sx - 5 + i * 4},${sy - 9} ${sx - 3 + i * 4},${sy - 14} ${sx - 1.5 + i * 4},${sy - 14} ${sx - 3.5 + i * 4},${sy - 9}`} />
          ))}
        </g>
      )}
    </g>
  );
}

function Uploaded({ f, href }: { f: Foot; href: string }) {
  const left = pt(f.x, f.y + f.d)[0];
  const right = pt(f.x + f.w, f.y)[0];
  const bottom = pt(f.x + f.w, f.y + f.d)[1];
  const width = right - left;
  return <image href={staticUrl(href)} x={left} y={bottom - width} width={width} height={width} preserveAspectRatio="xMidYMax meet" />;
}

function Stadium({ b, look, art }: { b: ClubBaseBuilding; look: ClubBaseLook; art?: string }) {
  const { x, y, w: W, d: D } = STADIUM;
  if (art) return <Uploaded f={STADIUM} href={art} />;
  if (b.level === 0) return <Plot b={b} f={STADIUM} />;
  const vl = visualLevel(b.level, b.max_level);
  const t = tier(vl);
  const seat = SEAT_COLORS[look.seats] ?? SEAT_COLORS.red;
  const facade = FACADES[look.facade] ?? FACADES.concrete;
  const H = 1.0 + vl * 0.14;
  const e = 0.8 + vl * 0.1;
  const s = 0.7 + vl * 0.08;
  const z0 = 0.3;
  const px = x + e;
  const py = y + s;
  const pw = W - 2 * e;
  const pd = D - 2 * s;
  // Stands: outer top edge (z = H) down to the pitch edge (z = z0).
  const standA = [pt(x, y, H), pt(x, y + D, H), pt(px, py + pd, z0), pt(px, py, z0)];
  const standB = [pt(x, y, H), pt(x + W, y, H), pt(px + pw, py, z0), pt(px, py, z0)];
  const lerp = (a: number, bb: number, f: number) => a + (bb - a) * f;
  const rows = Math.min(7, 2 + Math.ceil(vl / 2));
  const rowLines = [];
  for (let k = 1; k <= rows; k += 1) {
    const f = k / (rows + 1);
    const zz = lerp(H, z0, f);
    rowLines.push(<polyline key={`ra${k}`} points={pts([pt(lerp(x, px, f), lerp(y, py, f), zz), pt(lerp(x, px, f), lerp(y + D, py + pd, f), zz)])} />);
    rowLines.push(<polyline key={`rb${k}`} points={pts([pt(lerp(x, px, f), lerp(y, py, f), zz), pt(lerp(x + W, px + pw, f), lerp(y, py, f), zz)])} />);
  }
  const aisles = [];
  for (let i = 1; i < 5; i += 1) {
    const fy = i / 5;
    aisles.push(<polyline key={`aa${i}`} points={pts([pt(x, lerp(y, y + D, fy), H), pt(px, lerp(py, py + pd, fy), z0)])} />);
    aisles.push(<polyline key={`ab${i}`} points={pts([pt(lerp(x, x + W, fy), y, H), pt(lerp(px, px + pw, fy), py, z0)])} />);
  }
  // Membrane roof over the outer part of the stands (flat, above them).
  const Hr = H + 0.4;
  const k = 0.55;
  const inner = (side: "A" | "B" | "C" | "D"): Pt[] => {
    const ix0 = x + e * k;
    const iy0 = y + s * k;
    const ix1 = x + W - e * k;
    const iy1 = y + D - s * k;
    if (side === "A") return [pt(x, y, Hr), pt(x, y + D, Hr), pt(ix0, iy1, Hr), pt(ix0, iy0, Hr)];
    if (side === "B") return [pt(x, y, Hr), pt(x + W, y, Hr), pt(ix1, iy0, Hr), pt(ix0, iy0, Hr)];
    if (side === "C") return [pt(x + W, y, Hr), pt(x + W, y + D, Hr), pt(ix1, iy1, Hr), pt(ix1, iy0, Hr)];
    return [pt(x, y + D, Hr), pt(x + W, y + D, Hr), pt(ix1, iy1, Hr), pt(ix0, iy1, Hr)];
  };
  const roofSides: ("A" | "B" | "C" | "D")[] = look.roof === "full" ? ["A", "B", "C", "D"] : look.roof === "canopy" ? ["B", "D"] : [];
  const corners: Pt[] = [pt(x, y, 0), pt(x + W, y, 0), pt(x, y + D, 0), pt(x + W, y + D, 0)];
  return (
    <g>
      <defs>
        <radialGradient id="base-light-glow">
          <stop offset="0" stopColor="#fff7c2" stopOpacity="0.9" />
          <stop offset="1" stopColor="#fff7c2" stopOpacity="0" />
        </radialGradient>
      </defs>
      {/* back stands */}
      <polygon points={pts(standA)} fill={shade(seat, 0.9)} />
      <polygon points={pts(standB)} fill={seat} />
      <g stroke="#000" strokeOpacity="0.18" strokeWidth="0.35" fill="none">{rowLines}</g>
      <g stroke="#f4f1ea" strokeOpacity="0.7" strokeWidth="0.55" fill="none">{aisles}</g>
      <polyline points={pts([pt(px, py + pd, z0), pt(px, py, z0), pt(px + pw, py, z0)])} stroke="#3a3f44" strokeWidth="0.6" fill="none" />
      {/* the pitch */}
      <IsoPitch x={px} y={py} w={pw} d={pd} z={z0} pattern={look.pitch} />
      {/* front walls (the facade) and the rim on top */}
      <polygon points={pts([pt(x, y + D, 0), pt(x + W, y + D, 0), pt(x + W, y + D, H), pt(x, y + D, H)])} fill={facade} stroke={shade(facade, 0.6)} strokeWidth="0.35" />
      <polygon points={pts([pt(x + W, y, 0), pt(x + W, y + D, 0), pt(x + W, y + D, H), pt(x + W, y, H)])} fill={shade(facade, 0.72)} stroke={shade(facade, 0.5)} strokeWidth="0.35" />
      {Array.from({ length: 9 }).map((_, i) => {
        const u = ((i + 0.5) * W) / 9;
        return <polyline key={`fl${i}`} points={pts([pt(x + u, y + D, 0.15), pt(x + u, y + D, H - 0.2)])} stroke={shade(facade, 0.62)} strokeWidth="0.45" fill="none" />;
      })}
      {Array.from({ length: 7 }).map((_, i) => {
        const u = ((i + 0.5) * D) / 7;
        return <polyline key={`fr${i}`} points={pts([pt(x + W, y + u, 0.15), pt(x + W, y + u, H - 0.2)])} stroke={shade(facade, 0.48)} strokeWidth="0.45" fill="none" />;
      })}
      <polyline points={pts([pt(x, y + D, H), pt(x + W, y + D, H), pt(x + W, y, H)])} stroke={shade(facade, 1.25)} strokeWidth="1.1" fill="none" />
      {/* membrane roof on trusses */}
      {roofSides.map((side) => (
        <g key={side}>
          <polygon points={pts(inner(side))} fill="#eef1f3" opacity="0.93" stroke="#8d969c" strokeWidth="0.45" />
        </g>
      ))}
      {look.screen === "on" && (
        <IsoBox x={x + W / 2 - 1.3} y={y - 0.3} w={2.6} d={0.3} h={1.3} z={H} color="#1b2228" left="#101418" />
      )}
      {t >= 2 && [0.15, 0.38, 0.62, 0.85].map((f) => {
        const [fx, fy] = pt(x + W * f, y + D, H);
        return (
          <g key={f}>
            <line x1={fx} y1={fy} x2={fx} y2={fy - 9} stroke="#9aa59e" strokeWidth="0.6" />
            <polygon points={`${fx},${fy - 9} ${fx + 4.5},${fy - 7.6} ${fx},${fy - 6.2}`} fill={seat} />
          </g>
        );
      })}
      {look.lights === "on" && corners.map(([cx, cy], i) => {
        const top = cy - (H + 3) * 5.2;
        return (
          <g key={i}>
            <line x1={cx} y1={cy} x2={cx} y2={top} stroke="#8a8f8b" strokeWidth="0.9" />
            <circle cx={cx} cy={top} r="8" fill="url(#base-light-glow)" opacity="0.7" />
            <rect x={cx - 3.2} y={top - 2} width="6.4" height="3.2" rx="0.6" fill="#fffbe0" stroke="#8a8f8b" strokeWidth="0.35" />
          </g>
        );
      })}
      {t >= 3 && <polygon points={pts([pt(x, y, H), pt(x + W, y, H), pt(x + W, y + D, H), pt(x, y + D, H)])} fill="none" stroke="#f2c230" strokeWidth="0.9" />}
    </g>
  );
}

type Item = { key: string; depth: number; node: React.ReactNode };

export default function BaseMap({
  state, onPick, onAcademy,
}: { state: ClubBaseState; onPick: (code: ClubBaseCode) => void; onAcademy: () => void }) {
  const byCode = Object.fromEntries(state.buildings.map((b) => [b.code, b])) as Record<ClubBaseCode, ClubBaseBuilding>;
  const art = state.art ?? { background: null, buildings: {} };
  const [hint, setHint] = useState<{ x: number; y: number; text: string } | null>(null);
  const hover = (at: Pt, text: string) => ({
    onMouseEnter: () => setHint({ x: at[0], y: at[1], text }),
    onMouseLeave: () => setHint(null),
    onFocus: () => setHint({ x: at[0], y: at[1], text }),
    onBlur: () => setHint(null),
  });
  const footOf = (code: ClubBaseCode): Foot => (code === "stadium" ? STADIUM : SPOTS[code]);
  const topOf = (code: ClubBaseCode, b: ClubBaseBuilding): Pt => {
    const f = footOf(code);
    const vl = visualLevel(b.level, b.max_level);
    if (code === "stadium") {
      // On the stadium's far right corner, clear of the stands.
      const [sx, sy] = pt(f.x + f.w, f.y, 1.0 + vl * 0.14 + 0.6);
      return [sx, sy - 6];
    }
    const z = b.level > 0 ? topZ(code, vl) : 1.5;
    const [px, py] = pt(f.x + f.w / 2, f.y + f.d / 2, z);
    return [px, py - 6];
  };
  const interactive = (code: ClubBaseCode, node: React.ReactNode) => {
    const b = byCode[code];
    return (
      <g
        role="button"
        tabIndex={0}
        aria-label={`${b.name}, уровень ${b.level}`}
        className="cursor-pointer outline-none [&:focus-visible]:opacity-80"
        onClick={() => onPick(code)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onPick(code)}
        {...hover(topOf(code, b), `${b.name} · ${b.level}`)}
      >
        {node}
      </g>
    );
  };

  const items: Item[] = [];
  (Object.keys(SPOTS) as Exclude<ClubBaseCode, "stadium">[]).forEach((code) => {
    const b = byCode[code];
    if (!b) return;
    const f = SPOTS[code];
    const vl = visualLevel(b.level, b.max_level);
    const Art = ART[code];
    const upload = art.buildings[code];
    items.push({
      key: code,
      depth: f.x + f.w + f.y + f.d,
      node: interactive(code, upload ? <Uploaded f={f} href={upload} /> : b.level > 0 ? <Art {...f} vl={vl} /> : <Plot b={b} f={f} />),
    });
  });
  if (byCode.stadium) {
    items.push({
      key: "stadium", depth: STADIUM.x + STADIUM.w + STADIUM.y + STADIUM.d,
      node: interactive("stadium", <Stadium b={byCode.stadium} look={state.stadium.look} art={art.buildings.stadium} />),
    });
  }
  const academyVl = visualLevel(state.academy_level, state.academy_max_level);
  const academyTop = pt(ACADEMY.x + ACADEMY.w / 2, ACADEMY.y + ACADEMY.d / 2, topZ("academy", academyVl));
  items.push({
    key: "academy", depth: ACADEMY.x + ACADEMY.w + ACADEMY.y + ACADEMY.d,
    node: (
      <g role="button" tabIndex={0} aria-label="Академия" className="cursor-pointer outline-none" onClick={onAcademy}
         onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onAcademy()}
         {...hover([academyTop[0], academyTop[1] - 6], `Академия · ${state.academy_level}`)}>
        <AcademyArt {...ACADEMY} vl={Math.max(1, academyVl)} />
      </g>
    ),
  });
  if (!art.background) {
    NEIGHBOURS.forEach(([x, y, w, d, h, wall, roof]) => items.push({
      key: `n${x}-${y}`, depth: x + w + y + d,
      node: (
        <g>
          <IsoBox x={x} y={y} w={w} d={d} h={h} color={wall} />
          <polygon points={pts([pt(x, y + d, h), pt(x + w, y + d, h), pt(x + w, y + d / 2, h + 0.7), pt(x, y + d / 2, h + 0.7)])} fill={roof} />
          <polygon points={pts([pt(x + w, y, h), pt(x + w, y + d, h), pt(x + w, y + d / 2, h + 0.7)])} fill={shade(roof, 0.7)} />
        </g>
      ),
    }));
    OUTER_TREES.forEach(([x, y, sz]) => items.push({ key: `o${x}-${y}`, depth: x + y + 0.2, node: <Tree x={x} y={y} s={sz} /> }));
    TREES.forEach(([x, y, s]) => items.push({ key: `t${x}-${y}`, depth: x + y + 0.2, node: <Tree x={x} y={y} s={s} /> }));
    PINES.forEach(([x, y, s]) => items.push({ key: `p${x}-${y}`, depth: x + y + 0.2, node: <Pine x={x} y={y} s={s} /> }));
  }
  items.sort((a, b) => a.depth - b.depth);

  const construction = state.construction;
  let crane: React.ReactNode = null;
  if (construction?.owner === "base") {
    const code = construction.building_code as ClubBaseCode;
    const b = byCode[code];
    if (b) {
      const f = footOf(code);
      crane = <Crane at={pt(f.x + f.w + 0.3, f.y + 0.2, 0)} topPx={topOf(code, b)[1] - 4} />;
    }
  } else if (construction?.owner === "academy") {
    crane = <Crane at={pt(ACADEMY.x + ACADEMY.w + 0.3, ACADEMY.y + 0.2, 0)} topPx={academyTop[1] - 10} />;
  }

  return (
    <svg viewBox={`${VB.x} ${VB.y} ${VB.w} ${VB.h}`} className="w-full rounded-2xl" role="img"
         aria-label={`Клубная база, уровень ${state.total_level}`}>
      <defs>
        <radialGradient id="base-vignette" cx="0.5" cy="0.5" r="0.75">
          <stop offset="0.7" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.25" />
        </radialGradient>
      </defs>
      {art.background ? (
        <image href={staticUrl(art.background)} x={VB.x} y={VB.y} width={VB.w} height={VB.h} preserveAspectRatio="xMidYMid slice" />
      ) : (
        <>
          <Ground />
          <Roads />
          <Parking />
          <IsoPitch x={14.6} y={1.2} w={5.4} d={3.4} />
          <IsoPitch x={2} y={18.6} w={3.4} d={2.3} />
          <IsoPitch x={6} y={18.6} w={3.4} d={2.3} />
        </>
      )}
      {items.map((it) => <g key={it.key}>{it.node}</g>)}
      {crane}
      {(Object.keys(SPOTS) as ClubBaseCode[]).concat("stadium").map((code) => {
        const b = byCode[code];
        return b && b.level > 0
          ? <LevelPill key={`pill-${code}`} at={topOf(code, b)} level={b.level} gold={b.level >= b.max_level} /> : null;
      })}
      {state.academy_level > 0 && (
        <LevelPill at={[academyTop[0], academyTop[1] - 6]} level={state.academy_level} gold={state.academy_level >= state.academy_max_level} />
      )}
      {!art.background && <rect x={VB.x} y={VB.y} width={VB.w} height={VB.h} fill="url(#base-vignette)" pointerEvents="none" />}
      {hint && (() => {
        const w = hint.text.length * 4.4 + 12;
        const hx = Math.min(VB.x + VB.w - 4 - w, Math.max(VB.x + 4, hint.x - w / 2));
        const hy = Math.max(VB.y + 4, hint.y - 24);
        return (
          <g pointerEvents="none">
            <rect x={hx} y={hy} width={w} height="14" rx="7" fill="rgb(var(--c-bg-base))" opacity="0.92" stroke="rgb(var(--c-path))" strokeOpacity="0.6" />
            <text x={hx + w / 2} y={hy + 9.6} textAnchor="middle" fontSize="7.5" fontWeight="700" fill="rgb(var(--c-ink-chalk))">{hint.text}</text>
          </g>
        );
      })()}
    </svg>
  );
}

