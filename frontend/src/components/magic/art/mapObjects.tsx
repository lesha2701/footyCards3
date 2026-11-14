// Vector art for the isometric adventure map ("Мяч и Магия").
//
// Every component returns an SVG <g> fragment in cell-local coordinates:
// (0, 0) is the centre of the 64×32 ground diamond (corners (0,−16), (32,0),
// (0,16), (−32,0)); art stands on that point and grows upward (negative y).
// Light comes from the top-left: left faces carry the base tone, right faces
// the dark tone, tops the light tone. The map renderer places and depth-sorts.
import { useId, type ReactNode } from "react";

import { pngArt, pngRatio } from "@/components/magic/art/pngArt";

export type Biome = "meadow" | "desert" | "snow" | "ash";
type Faction = "dawn" | "ash";

/* ───────────────────────── painted PNG overrides ───────────────────────── */

/** A painted picture standing on the cell: `w` wide, its bottom at `foot`. */
function Png({ k, w, foot = 10, flip = false, opacity }: { k: string; w: number; foot?: number; flip?: boolean; opacity?: number }): JSX.Element | null {
  const href = pngArt(k);
  if (!href) return null;
  const h = w * pngRatio(k);
  return (
    <g transform={flip ? "scale(-1,1)" : undefined} opacity={opacity}>
      {/* No painted shadow under it: the art stands on the ground by itself. */}
      <image href={href} x={-w / 2} y={foot - h + 1.5} width={w} height={h} />
    </g>
  );
}

const OBJECT_W: Record<string, number> = {
  chest: 28, camp: 46, market: 45, mine: 40, well: 33, tribune: 43, reinforce: 37, artifact: 27,
  training: 46, floodtower: 30, medic: 42, tunnel: 44, shrine: 46,
};

/** The painted version of a map object, or null when it has none yet. */
function objectPng(kind: string, variant: string | undefined, level: number, taken: boolean, style?: string | null): JSX.Element | null {
  const w = kind === "camp" && level >= 4 ? 76 : (OBJECT_W[kind] ?? 42) + (kind === "camp" ? (level - 1) * 4 : 0);
  // A Lost lair (level 4) wears the strong camp's art until it gets its own.
  // The two races' camps have their own tents (a Rassvet outpost, an Ash lair).
  const camp = style && pngArt(`objects/camp_${style}`) ? `camp_${style}`
    : level >= 4 && !pngArt("objects/camp_4") ? "camp_3" : `camp_${level}`;
  const own = kind === "camp" ? (taken ? "camp_taken" : camp) : kind === "artifact" ? `artifact_${variant}` : kind;
  const takenKey = `objects/${kind}_taken`;
  if (taken && kind !== "camp" && pngArt(takenKey)) return <Png k={takenKey} w={w} />;
  if (!pngArt(`objects/${own}`)) return null;
  return <Png k={`objects/${own}`} w={w} opacity={taken && kind !== "camp" ? 0.55 : undefined} />;
}

/* ───────────────────────── palette & geometry helpers ───────────────────────── */

const OL = "#1b1222";

type Pal = { base: string; dark: string; light: string };

/** Linear blend of two #rrggbb colours. */
function mix(a: string, b: string, t: number): string {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  const ch = (s: number) => Math.round(((pa >> s) & 255) * (1 - t) + ((pb >> s) & 255) * t);
  return "#" + ((1 << 24) | (ch(16) << 16) | (ch(8) << 8) | ch(0)).toString(16).slice(1);
}

/** A cel palette from one base colour: one shade, one highlight. */
function pal(base: string, dk = 0.32, lt = 0.4): Pal {
  return { base, dark: mix(base, OL, dk), light: mix(base, "#ffffff", lt) };
}

/** Washed-out version of a palette (depleted / conquered objects). */
function fade(p: Pal, t = 0.55): Pal {
  const g = "#8e8a94";
  return { base: mix(p.base, g, t), dark: mix(p.dark, g, t), light: mix(p.light, g, t) };
}

function darken(p: Pal, t: number): Pal {
  return { base: mix(p.base, OL, t), dark: mix(p.dark, OL, t), light: mix(p.light, OL, t) };
}

/** Outline props shared by every inked shape. */
function line(sw = 1.8) {
  return { stroke: OL, strokeWidth: sw, strokeLinejoin: "round" as const, strokeLinecap: "round" as const };
}

/** "x,y x,y …" from a flat list of numbers. */
function P(...n: number[]): string {
  let s = "";
  for (let i = 0; i < n.length; i += 2) s += `${n[i].toFixed(2)},${n[i + 1].toFixed(2)} `;
  return s.trim();
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const mod = (v: number, n: number) => ((Math.trunc(v) % n) + n) % n;

function useUid(): string {
  return useId().replace(/:/g, "");
}

/** Iso box: ground footprint centred at (x, y) with corners (x±w, y), (x, y±d). */
type Box = { x: number; y: number; w: number; d: number; h: number };
type Pt = [number, number];
/** Point on the front-left face: u from the left corner to the front corner, v from bottom to top. */
const lf = (b: Box, u: number, v: number): Pt => [b.x - b.w + u * b.w, b.y + u * b.d - v * b.h];
/** Point on the front-right face: u from the front corner to the right corner. */
const rf = (b: Box, u: number, v: number): Pt => [b.x + u * b.w, b.y + b.d - u * b.d - v * b.h];
type Face = typeof lf;

function quad(f: Face, b: Box, u0: number, u1: number, v0: number, v1: number): string {
  return P(...f(b, u0, v0), ...f(b, u1, v0), ...f(b, u1, v1), ...f(b, u0, v1));
}

/** Arched opening (door / window) on a box face. */
function arch(f: Face, b: Box, u0: number, u1: number, v0: number, v1: number, k = 0.22): string {
  const [ax, ay] = f(b, u0, v0);
  const [bx, by] = f(b, u1, v0);
  const [cx, cy] = f(b, u1, v1);
  const [dx, dy] = f(b, u0, v1);
  const [qx, qy] = f(b, (u0 + u1) / 2, v1 + k);
  return `M${ax},${ay} L${bx},${by} L${cx},${cy} Q${qx},${qy} ${dx},${dy} Z`;
}

/* ───────────────────────── primitive shapes ───────────────────────── */

// No ground shadows on the map at all (the art stands on the ground by itself); kept as a no-op.
function Shadow(_: { rx?: number; ry?: number; y?: number; o?: number }) {
  return null;
}

/** Four-point sparkle. */
function Glint({ x, y, s = 3, c = "#ffffff", o = 1 }: { x: number; y: number; s?: number; c?: string; o?: number }) {
  return (
    <path
      d={`M${x},${y - s} Q${x},${y} ${x + s},${y} Q${x},${y} ${x},${y + s} Q${x},${y} ${x - s},${y} Q${x},${y} ${x},${y - s} Z`}
      fill={c}
      opacity={o}
    />
  );
}

/** Soft radial glow (needs a unique id). */
function Glow({ id, x, y, r, ry, color, o = 0.85, pulse = false }: {
  id: string; x: number; y: number; r: number; ry?: number; color: string; o?: number; pulse?: boolean;
}) {
  return (
    <g>
      <defs>
        <radialGradient id={id}>
          <stop offset="0" stopColor={color} stopOpacity={o} />
          <stop offset="0.45" stopColor={color} stopOpacity={o * 0.45} />
          <stop offset="1" stopColor={color} stopOpacity={0} />
        </radialGradient>
      </defs>
      <ellipse cx={x} cy={y} rx={r} ry={ry ?? r} fill={`url(#${id})`}>
        {pulse && <animate attributeName="opacity" values="1;0.6;1" dur="2.4s" repeatCount="indefinite" />}
      </ellipse>
    </g>
  );
}

function IsoBox({ b, c, sw = 1.6, top = true }: { b: Box; c: Pal; sw?: number; top?: boolean }) {
  const { x, y, w, d, h } = b;
  const t = y - h;
  return (
    <g {...line(sw)}>
      <polygon points={P(x - w, y, x, y + d, x, t + d, x - w, t)} fill={c.base} />
      <polygon points={P(x, y + d, x + w, y, x + w, t, x, t + d)} fill={c.dark} />
      {top && <polygon points={P(x, t - d, x + w, t, x, t + d, x - w, t)} fill={c.light} />}
    </g>
  );
}

function IsoCyl({ x = 0, y = 0, r, h, c, ry = r / 2, sw = 1.6, top = true }: {
  x?: number; y?: number; r: number; h: number; c: Pal; ry?: number; sw?: number; top?: boolean;
}) {
  const t = y - h;
  const k = 0.35 * r;
  const ky = ry * 0.937;
  const body = `M${x - r},${t} L${x - r},${y} A${r},${ry} 0 0 0 ${x + r},${y} L${x + r},${t} Z`;
  return (
    <g>
      <path d={body} fill={c.base} />
      <path d={`M${x + k},${t} L${x + k},${y + ky} A${r},${ry} 0 0 0 ${x + r},${y} L${x + r},${t} Z`} fill={c.dark} />
      <path d={`M${x - 0.78 * r},${t} L${x - 0.78 * r},${y + ry * 0.62} L${x - 0.6 * r},${y + ry * 0.8} L${x - 0.6 * r},${t} Z`} fill={c.light} opacity={0.55} />
      <path d={body} fill="none" {...line(sw)} />
      {top && <ellipse cx={x} cy={t} rx={r} ry={ry} fill={c.light} {...line(sw)} />}
    </g>
  );
}

function Cone({ x = 0, y = 0, r, h, c, ry = r / 2, sw = 1.6 }: {
  x?: number; y?: number; r: number; h: number; c: Pal; ry?: number; sw?: number;
}) {
  const ay = y - h;
  const full = `M${x - r},${y} A${r},${ry} 0 0 0 ${x + r},${y} L${x},${ay} Z`;
  return (
    <g>
      <path d={full} fill={c.base} />
      <path d={`M${x},${ay} L${x + r},${y} A${r},${ry} 0 0 1 ${x + 0.25 * r},${y + ry * 0.968} Z`} fill={c.dark} />
      <polygon points={P(x, ay, x - 0.8 * r, y + 0.6 * ry, x - 0.55 * r, y + 0.83 * ry)} fill={c.light} opacity={0.7} />
      <path d={full} fill="none" {...line(sw)} />
    </g>
  );
}

/** Four-sided roof over a box footprint. */
function Pyramid({ b, h, c, o = 2, sw = 1.6 }: { b: Box; h: number; c: Pal; o?: number; sw?: number }) {
  const t = b.y - b.h;
  const L: Pt = [b.x - b.w - o, t];
  const F: Pt = [b.x, t + b.d + o / 2];
  const R: Pt = [b.x + b.w + o, t];
  const A: Pt = [b.x, t - h];
  return (
    <g {...line(sw)}>
      <polygon points={P(...L, ...F, ...A)} fill={c.base} />
      <polygon points={P(...F, ...R, ...A)} fill={c.dark} />
      <polyline points={P(L[0] + 3, L[1] - 1, A[0] - 1, A[1] + 3)} fill="none" stroke={c.light} strokeWidth={1.4} />
    </g>
  );
}

/** Path with an optional dark and light region, inked once on top. */
function Cel({ d, dd, ld, c, sw = 1.7 }: { d: string; dd?: string; ld?: string; c: Pal; sw?: number }) {
  return (
    <g>
      <path d={d} fill={c.base} />
      {dd && <path d={dd} fill={c.dark} />}
      {ld && <path d={ld} fill={c.light} />}
      <path d={d} fill="none" {...line(sw)} />
    </g>
  );
}

/** Round cel-shaded blob (foliage, sacks, bodies). */
function Blob({ x, y, r, c, sw = 1.7, ry }: { x: number; y: number; r: number; c: Pal; sw?: number; ry?: number }) {
  const k = (ry ?? r) / r;
  return (
    <g>
      <ellipse cx={x} cy={y} rx={r} ry={r * k} fill={c.dark} {...line(sw)} />
      <ellipse cx={x - r * 0.13} cy={y - r * 0.15 * k} rx={r * 0.8} ry={r * 0.8 * k} fill={c.base} />
      <ellipse
        cx={x - r * 0.38}
        cy={y - r * 0.42 * k}
        rx={r * 0.3}
        ry={r * 0.17 * k}
        transform={`rotate(-30 ${x - r * 0.38} ${y - r * 0.42 * k})`}
        fill={c.light}
      />
    </g>
  );
}

type Seg = { d: string; w: number };
/** Thick rounded strokes with an ink outline (trunks, legs, poles, cacti). */
function Limbs({ segs, c, sw = 1.7, shade = true }: { segs: Seg[]; c: Pal; sw?: number; shade?: boolean }) {
  const cap = { fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <g>
      {segs.map((s, i) => <path key={`o${i}`} d={s.d} {...cap} stroke={OL} strokeWidth={s.w + sw * 2} />)}
      {segs.map((s, i) => <path key={`b${i}`} d={s.d} {...cap} stroke={c.base} strokeWidth={s.w} />)}
      {shade && segs.map((s, i) => (
        <path key={`d${i}`} d={s.d} {...cap} stroke={c.dark} strokeWidth={s.w * 0.34} transform={`translate(${s.w * 0.24} 0)`} />
      ))}
      {shade && segs.map((s, i) => (
        <path key={`l${i}`} d={s.d} {...cap} stroke={c.light} strokeWidth={s.w * 0.22} transform={`translate(${-s.w * 0.22} 0)`} />
      ))}
    </g>
  );
}

/** Flame centred at (x, y), tip at y − 1.6r, base at y + r. */
function Flame({ x, y, r, outer = "#ff5a1f", inner = "#ffd23f", sw = 1.4 }: {
  x: number; y: number; r: number; outer?: string; inner?: string; sw?: number;
}) {
  const f = (s: number, dy: number) => {
    const R = r * s;
    const cy = y + dy;
    return `M${x},${cy - R * 1.6} C${x + R * 0.9},${cy - R * 0.6} ${x + R},${cy + R * 0.6} ${x},${cy + R} C${x - R},${cy + R * 0.6} ${x - R * 0.9},${cy - R * 0.3} ${x - R * 0.35},${cy - R * 0.8} C${x - R * 0.3},${cy - R * 0.2} ${x + R * 0.1},${cy - R * 0.4} ${x},${cy - R * 1.6} Z`;
  };
  return (
    <g>
      <path d={f(1, 0)} fill={outer} {...line(sw)} />
      <path d={f(0.62, r * 0.36)} fill={inner} />
      <path d={f(0.3, r * 0.66)} fill="#fff6c8" />
    </g>
  );
}

function SunMark({ x, y, r, c = "#ffcf3a" }: { x: number; y: number; r: number; c?: string }) {
  const rays = [];
  for (let i = 0; i < 8; i++) {
    const a = (i * Math.PI) / 4;
    const s = 0.22;
    rays.push(
      <polygon
        key={i}
        points={P(
          x + Math.cos(a - s) * r * 0.7, y + Math.sin(a - s) * r * 0.7,
          x + Math.cos(a) * r * 1.35, y + Math.sin(a) * r * 1.35,
          x + Math.cos(a + s) * r * 0.7, y + Math.sin(a + s) * r * 0.7,
        )}
      />,
    );
  }
  return (
    <g fill={c} {...line(0.9)}>
      {rays}
      <circle cx={x} cy={y} r={r * 0.68} />
      <circle cx={x - r * 0.22} cy={y - r * 0.22} r={r * 0.2} fill="#fff6c8" stroke="none" />
    </g>
  );
}

function Emblem({ kind, x, y, r }: { kind: Faction; x: number; y: number; r: number }) {
  return kind === "dawn" ? (
    <SunMark x={x} y={y} r={r} />
  ) : (
    <Flame x={x} y={y + r * 0.25} r={r * 0.62} outer="#ff6a1a" inner="#ffd23f" sw={0.9} />
  );
}

/** Pole + waving pennant. Pole base at (x, y), cloth at the top, waving to the right (dir 1) or left (−1). */
function Flag({ x, y, h, c, w = 13, fh = 8, dir = 1, swallow = false, emblem, droop = false, pole }: {
  x: number; y: number; h: number; c: Pal; w?: number; fh?: number; dir?: number; swallow?: boolean;
  emblem?: Faction; droop?: boolean; pole?: Pal;
}) {
  const t = y - h;
  const W = w * dir;
  const cloth = droop
    ? `M${x},${t + 1} Q${x + W * 0.35},${t + 2} ${x + W * 0.4},${t + fh + 6} Q${x + W * 0.2},${t + fh + 4} ${x},${t + fh} Z`
    : swallow
      ? `M${x},${t} Q${x + W * 0.5},${t - 2.5} ${x + W},${t + 1} L${x + W * 0.72},${t + fh * 0.6} L${x + W},${t + fh + 1} Q${x + W * 0.5},${t + fh - 1.5} ${x},${t + fh} Z`
      : `M${x},${t} Q${x + W * 0.5},${t - 2.5} ${x + W},${t + 1} L${x + W},${t + fh + 1} Q${x + W * 0.5},${t + fh - 1.5} ${x},${t + fh} Z`;
  const fold = droop
    ? undefined
    : `M${x + W * 0.55},${t - 0.9} Q${x + W * 0.8},${t - 0.4} ${x + W},${t + 1} L${x + W * (swallow ? 0.72 : 1)},${t + fh * 0.6} L${x + W},${t + fh + 1} Q${x + W * 0.8},${t + fh - 0.2} ${x + W * 0.55},${t + fh - 0.8} Z`;
  return (
    <g>
      <Limbs segs={[{ d: `M${x},${y} L${x},${t - 1}`, w: 1.6 }]} c={pole ?? pal("#8a5a34")} sw={1.1} shade={false} />
      <Cel d={cloth} dd={fold} c={c} sw={1.3} />
      {emblem && !droop && <Emblem kind={emblem} x={x + W * 0.45} y={t + fh / 2} r={Math.min(fh, w) * 0.28} />}
      <circle cx={x} cy={t - 1.6} r={1.5} fill="#ffd34d" {...line(0.9)} />
    </g>
  );
}

/** Six-sided crystal prism with a pointed top. */
function Shard({ x, y, w, h, c, hb = 0.62, sw = 1.5 }: { x: number; y: number; w: number; h: number; c: Pal; hb?: number; sw?: number }) {
  const d = w / 2;
  const b = h * hb;
  return (
    <g {...line(sw)}>
      <polygon points={P(x - w, y, x, y + d, x, y + d - b, x - w, y - b)} fill={c.base} />
      <polygon points={P(x, y + d, x + w, y, x + w, y - b, x, y + d - b)} fill={c.dark} />
      <polygon points={P(x - w, y - b, x, y + d - b, x, y - h)} fill={c.light} />
      <polygon points={P(x, y + d - b, x + w, y - b, x, y - h)} fill={c.base} />
      <polyline points={P(x - w * 0.55, y - b * 0.15, x - w * 0.55, y - b * 0.85)} fill="none" stroke="#ffffff" strokeWidth={1} opacity={0.8} />
    </g>
  );
}

/* ───────────────────────── trees ───────────────────────── */

const BARK = pal("#8a5530");

function Oak({ x = 0, y = 0, s = 1, fruit = false }: { x?: number; y?: number; s?: number; fruit?: boolean }) {
  const leaf = pal("#4cb83a", 0.36, 0.42);
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <Limbs
        segs={[
          { d: "M0,1 L0,-20", w: 7 },
          { d: "M0,-14 L-7,-22", w: 3.4 },
          { d: "M0,-16 L7,-24", w: 3.4 },
          { d: "M-1,1 L-6,3", w: 2.6 },
          { d: "M1,1 L6,3", w: 2.6 },
        ]}
        c={BARK}
      />
      <Blob x={0} y={-40} r={13} c={leaf} />
      <Blob x={-11} y={-29} r={10} c={leaf} />
      <Blob x={11} y={-30} r={10} c={leaf} />
      <Blob x={-3} y={-25} r={9} c={leaf} />
      <Blob x={6} y={-23} r={7.5} c={leaf} />
      {fruit && (
        <g fill="#ff4b3e" {...line(1)}>
          <circle cx={-9} cy={-31} r={2.1} />
          <circle cx={6} cy={-41} r={2.1} />
          <circle cx={11} cy={-27} r={2.1} />
          <circle cx={-2} cy={-22} r={2.1} />
        </g>
      )}
      <Glint x={-7} y={-46} s={2.4} o={0.9} />
    </g>
  );
}

function Bush({ x, y, s = 1 }: { x: number; y: number; s?: number }) {
  const leaf = pal("#3fa63a", 0.36, 0.42);
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <Blob x={-4} y={-5} r={6} c={leaf} />
      <Blob x={4} y={-4} r={5.5} c={leaf} />
      <circle cx={-5} cy={-6} r={1.3} fill="#ffe35c" {...line(0.8)} />
      <circle cx={3} cy={-5} r={1.3} fill="#ff7ab0" {...line(0.8)} />
    </g>
  );
}

function Pine({ x = 0, y = 0, s = 1, snow = false }: { x?: number; y?: number; s?: number; snow?: boolean }) {
  const g = pal(snow ? "#2f8a62" : "#2f9a4e", 0.38, 0.4);
  const tiers = [0, 1, 2].map((i) => {
    const hw = 15 - i * 3.6;
    const b = -6 - i * 11;
    const top = b - 21;
    const H = b - top;
    return (
      <g key={i}>
        <Cel
          d={`M${-hw},${b} Q0,${b + 5} ${hw},${b} L0,${top} Z`}
          dd={`M0,${top} L${hw},${b} Q${hw * 0.5},${b + 2.5} 0,${b + 2.5} Z`}
          c={g}
          sw={1.6}
        />
        {snow && (
          <g>
            <path
              d={`M0,${top} L${hw * 0.42},${top + H * 0.42} L${hw * 0.2},${top + H * 0.36} L0,${top + H * 0.48} L${-hw * 0.22},${top + H * 0.36} L${-hw * 0.42},${top + H * 0.42} Z`}
              fill="#f4fbff"
              {...line(1.2)}
            />
            <path
              d={`M${-hw},${b} Q${-hw * 0.5},${b + 3.6} 0,${b + 2.6} L${-hw * 0.15},${b} Q${-hw * 0.5},${b + 0.6} ${-hw * 0.88},${b - 2.2} Z`}
              fill="#f4fbff"
              {...line(1.1)}
            />
          </g>
        )}
      </g>
    );
  });
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <Limbs segs={[{ d: "M0,2 L0,-8", w: 5 }]} c={BARK} />
      {tiers}
    </g>
  );
}

function Palm({ x = 0, y = 0, s = 1, lean = 1 }: { x?: number; y?: number; s?: number; lean?: number }) {
  const trunk = pal("#b07a43");
  const leaf = pal("#44b24a", 0.36, 0.42);
  const tx = 7 * lean;
  const ty = -40;
  const cx = 2 * lean;
  const rings = [0.2, 0.38, 0.56, 0.74].map((t) => {
    const px = 2 * (1 - t) * t * cx + t * t * tx;
    const py = 2 * (1 - t) * t * -22 + t * t * ty;
    return <path key={t} d={`M${px - 3},${py - 0.6} L${px + 3},${py + 0.6}`} stroke={trunk.dark} strokeWidth={1.3} strokeLinecap="round" />;
  });
  const frond = (dx: number, dy: number, k: number) => (
    <Cel
      key={`${dx},${dy}`}
      d={`M${tx},${ty} Q${tx + dx * 0.4},${ty + dy * 0.4 - 7} ${tx + dx},${ty + dy} Q${tx + dx * 0.55},${ty + dy * 0.55 + 1.5} ${tx},${ty + 2} Z`}
      dd={`M${tx},${ty + 2} Q${tx + dx * 0.55},${ty + dy * 0.55 + 1.5} ${tx + dx},${ty + dy} Q${tx + dx * 0.5},${ty + dy * 0.5 - 1.5} ${tx},${ty + 0.5} Z`}
      c={k ? leaf : darken(leaf, 0.12)}
      sw={1.5}
    />
  );
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <Limbs segs={[{ d: `M0,1 Q${cx},-22 ${tx},${ty}`, w: 6 }]} c={trunk} />
      {rings}
      {frond(-4 * lean, -10, 0)}
      {frond(13 * lean, -7, 0)}
      {frond(-16 * lean, -2, 0)}
      {frond(-20 * lean, 11, 1)}
      {frond(20 * lean, 7, 1)}
      {frond(5 * lean, 13, 1)}
      <g fill="#7a4a26" {...line(1)}>
        <circle cx={tx - 2.4} cy={ty + 3} r={2.5} />
        <circle cx={tx + 2.2} cy={ty + 3.8} r={2.5} />
      </g>
    </g>
  );
}

function Cactus({ x = 0, y = 0, s = 1, flower = true }: { x?: number; y?: number; s?: number; flower?: boolean }) {
  const g = pal("#3fae58", 0.36, 0.42);
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <Limbs
        segs={[
          { d: "M0,0 L0,-31", w: 9 },
          { d: "M-2,-12 L-8,-12 Q-10,-12 -10,-15 L-10,-23", w: 5.4 },
          { d: "M2,-17 L7,-17 Q9,-17 9,-20 L9,-27", w: 5.4 },
        ]}
        c={g}
      />
      <g stroke="#f4f0d0" strokeWidth={0.9} strokeLinecap="round">
        <path d="M-5,-20 L-6.8,-20.6 M-5,-8 L-6.8,-8.6 M5,-6 L6.8,-6.6 M5,-24 L6.8,-24.6 M-12.4,-19 L-13.8,-19.6 M11.4,-23 L12.8,-23.6" />
      </g>
      {flower && (
        <g {...line(0.9)}>
          <circle cx={-2} cy={-35} r={2} fill="#ff6fa8" />
          <circle cx={2} cy={-35.5} r={2} fill="#ff6fa8" />
          <circle cx={0} cy={-37} r={2} fill="#ff8fbe" />
          <circle cx={0} cy={-35.3} r={1} fill="#ffe35c" stroke="none" />
        </g>
      )}
    </g>
  );
}

function DeadTree({ x = 0, y = 0, s = 1, v = 0 }: { x?: number; y?: number; s?: number; v?: number }) {
  const bark = pal("#4a3732", 0.4, 0.28);
  const sets: Seg[][] = [
    [
      { d: "M0,1 L1,-22 L-2,-38", w: 6 },
      { d: "M1,-19 L10,-29 L15,-30", w: 3 },
      { d: "M0,-27 L-9,-35 L-11,-41", w: 2.8 },
      { d: "M-2,-38 L2,-46", w: 2.2 },
      { d: "M10,-29 L11,-36", w: 1.8 },
    ],
    [
      { d: "M0,1 Q-2,-18 6,-34", w: 6 },
      { d: "M-1,-14 L-12,-24 L-13,-31", w: 3 },
      { d: "M3,-26 L13,-30", w: 2.6 },
      { d: "M6,-34 L4,-43 M6,-34 L11,-40", w: 2 },
    ],
    [
      { d: "M-6,1 L-5,-24 L-9,-33", w: 6 },
      { d: "M-5,-17 L3,-25", w: 2.6 },
      { d: "M-9,-33 L-4,-39", w: 2 },
      { d: "M10,5 L10,-6 L12,-10", w: 5 },
    ],
  ];
  const embers: Pt[] = [
    [[1, -12], [-1, -30], [9, -28]],
    [[-1, -8], [4, -28], [-10, -22]],
    [[-5, -10], [10, -2], [-8, -30]],
  ][v] as Pt[];
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <ellipse cx={0} cy={2} rx={12} ry={4.5} fill="#6b6470" {...line(1.3)} />
      <ellipse cx={-2} cy={1} rx={6} ry={2} fill="#8a8390" />
      <Limbs segs={sets[v]} c={bark} />
      {embers.map(([ex, ey], i) => (
        <g key={i}>
          <circle cx={ex} cy={ey} r={3.2} fill="#ff7a1a" opacity={0.35} />
          <circle cx={ex} cy={ey} r={1.3} fill="#ffc23a" />
        </g>
      ))}
    </g>
  );
}

function TreeArt({ biome, v }: { biome: Biome; v: number }) {
  let art: ReactNode;
  if (biome === "meadow") {
    art = [
      <Oak key="a" s={1.05} />,
      <g key="b"><Oak x={-6} y={-2} s={0.92} /><Oak x={13} y={6} s={0.56} /></g>,
      <g key="c"><Oak x={3} y={-1} s={0.98} fruit /><Bush x={-13} y={7} /></g>,
    ][v];
  } else if (biome === "desert") {
    art = [
      <g key="a"><ellipse cx={0} cy={2} rx={14} ry={5} fill="#e7b870" {...line(1.3)} /><Palm s={1.05} /></g>,
      <Cactus key="b" s={1.15} />,
      <g key="c"><Palm x={-6} y={-1} s={0.9} lean={-1} /><Cactus x={12} y={7} s={0.62} flower={false} /></g>,
    ][v];
  } else if (biome === "snow") {
    art = [
      <g key="a"><ellipse cx={0} cy={2} rx={15} ry={5.5} fill="#f4fbff" {...line(1.3)} /><Pine s={1.18} snow /></g>,
      <g key="b"><Pine x={-7} y={-2} s={1.02} snow /><Pine x={11} y={6} s={0.7} snow /></g>,
      <g key="c"><Pine x={-11} y={-2} s={0.78} snow /><Pine x={9} y={-5} s={0.9} snow /><Pine x={0} y={8} s={0.62} snow /></g>,
    ][v];
  } else {
    art = <DeadTree v={v} s={1.05} />;
  }
  return (
    <g>
      <Shadow rx={19} ry={8} />
      {art}
    </g>
  );
}

/* ───────────────────────── rocks ───────────────────────── */

type RockShape = { o: number[][]; t: number[][]; r: number[][] };
const ROCK_SHAPES: RockShape[] = [
  {
    o: [[-1, 0], [-0.9, -0.5], [-0.5, -0.9], [0.15, -1], [0.7, -0.75], [1, -0.2], [0.85, 0.2], [0.2, 0.35], [-0.6, 0.3]],
    t: [[-0.9, -0.5], [-0.5, -0.9], [0.15, -1], [0.7, -0.75], [0.25, -0.45], [-0.4, -0.4]],
    r: [[0.7, -0.75], [1, -0.2], [0.85, 0.2], [0.2, 0.35], [0.15, -0.05], [0.25, -0.45]],
  },
  {
    o: [[-1, 0.05], [-0.95, -0.6], [-0.45, -0.85], [0.35, -0.95], [0.95, -0.55], [1, 0.05], [0.4, 0.35], [-0.5, 0.3]],
    t: [[-0.95, -0.6], [-0.45, -0.85], [0.35, -0.95], [0.95, -0.55], [0.35, -0.4], [-0.4, -0.45]],
    r: [[0.95, -0.55], [1, 0.05], [0.4, 0.35], [0.35, -0.4]],
  },
  {
    o: [[-1, 0.1], [-0.7, -0.5], [-0.35, -1], [0.15, -0.95], [0.55, -0.45], [1, 0.05], [0.3, 0.3], [-0.5, 0.3]],
    t: [[-0.7, -0.5], [-0.35, -1], [0.15, -0.95], [-0.05, -0.55]],
    r: [[0.15, -0.95], [0.55, -0.45], [1, 0.05], [0.3, 0.3], [0.05, -0.1], [-0.05, -0.55]],
  },
];

const ROCK_PAL: Record<Biome, Pal> = {
  meadow: pal("#a3acb7", 0.34, 0.42),
  desert: pal("#e09f5c", 0.34, 0.38),
  snow: pal("#94a6bd", 0.34, 0.42),
  ash: { base: "#3e3349", dark: "#241c2c", light: "#6c5c82" },
};

function Rock({ x, y, w, h, shape, biome }: { x: number; y: number; w: number; h: number; shape: number; biome: Biome }) {
  const S = ROCK_SHAPES[shape];
  const c = ROCK_PAL[biome];
  const m = (p: number[]) => [x + p[0] * w, y + p[1] * h];
  const pts = (a: number[][]) => P(...a.flatMap(m));
  const M = (px: number, py: number) => m([px, py]);
  const outline = pts(S.o);
  return (
    <g>
      <polygon points={outline} fill={c.base} />
      <polygon points={pts(S.t)} fill={c.light} />
      <polygon points={pts(S.r)} fill={c.dark} />
      <polygon points={outline} fill="none" {...line(1.7)} />
      <polyline points={P(...M(-0.35, -0.2), ...M(-0.15, 0.05), ...M(-0.2, 0.22))} fill="none" stroke={c.dark} strokeWidth={1.3} strokeLinecap="round" />
      {biome === "meadow" && (
        <g>
          <path
            d={`M${M(-0.88, -0.5).join(",")} Q${M(-0.6, -0.95).join(",")} ${M(-0.1, -0.93).join(",")} Q${M(-0.15, -0.65).join(",")} ${M(-0.45, -0.6).join(",")} Q${M(-0.7, -0.38).join(",")} ${M(-0.88, -0.5).join(",")} Z`}
            fill="#5fbf47"
            {...line(1.2)}
          />
          <Glint x={M(0.3, -0.7)[0]} y={M(0.3, -0.7)[1]} s={2} o={0.8} />
        </g>
      )}
      {biome === "desert" && (
        <g fill="none" strokeLinecap="round">
          <polyline points={P(...M(-0.85, -0.35), ...M(-0.1, -0.25), ...M(0.85, -0.35))} stroke="#f6c98a" strokeWidth={1.6} />
          <polyline points={P(...M(-0.88, -0.05), ...M(0, 0.05), ...M(0.9, -0.05))} stroke={c.dark} strokeWidth={1.6} />
        </g>
      )}
      {biome === "snow" && (
        <g>
          <polygon
            points={P(
              ...M(-0.95, -0.45), ...M(-0.5, -0.94), ...M(0.15, -1.04), ...M(0.75, -0.76), ...M(0.62, -0.52), ...M(0.42, -0.62),
              ...M(0.22, -0.42), ...M(-0.08, -0.52), ...M(-0.38, -0.36), ...M(-0.7, -0.46),
            )}
            fill="#f4fbff"
            {...line(1.3)}
          />
          <polygon points={P(...M(0.15, -1.04), ...M(0.75, -0.76), ...M(0.62, -0.52), ...M(0.3, -0.7))} fill="#c9def2" />
          <Shard x={M(0.85, 0.15)[0]} y={M(0.85, 0.15)[1]} w={2.6} h={9} c={pal("#9fdcff", 0.3, 0.5)} sw={1.1} />
        </g>
      )}
      {biome === "ash" && (
        <g fill="none" strokeLinecap="round" strokeLinejoin="round">
          {[
            [M(-0.6, -0.55), M(-0.25, -0.2), M(-0.3, 0.1), M(0.05, 0.28)],
            [M(0.25, -0.8), M(0.5, -0.35), M(0.4, -0.05)],
          ].map((cr, i) => (
            <g key={i}>
              <polyline points={P(...cr.flat())} stroke="#ff6a1a" strokeWidth={4} opacity={0.35} />
              <polyline points={P(...cr.flat())} stroke="#ff8a24" strokeWidth={1.9} />
              <polyline points={P(...cr.flat())} stroke="#ffe08a" strokeWidth={0.7} />
            </g>
          ))}
          <Glint x={M(-0.45, -0.75)[0]} y={M(-0.45, -0.75)[1]} s={2} c="#d9c6ff" o={0.85} />
        </g>
      )}
    </g>
  );
}

function RockArt({ biome, v }: { biome: Biome; v: number }) {
  return (
    <g>
      <Shadow rx={22} ry={9} />
      {v === 0 && <Rock x={0} y={1} w={20} h={25} shape={0} biome={biome} />}
      {v === 1 && (
        <g>
          <Rock x={-6} y={-1} w={16} h={21} shape={1} biome={biome} />
          <Rock x={11} y={6} w={9} h={11} shape={0} biome={biome} />
        </g>
      )}
      {v === 2 && (
        <g>
          <Rock x={3} y={0} w={13} h={38} shape={2} biome={biome} />
          <Rock x={-13} y={5} w={8} h={9} shape={0} biome={biome} />
          <Rock x={15} y={6} w={6} h={7} shape={1} biome={biome} />
        </g>
      )}
    </g>
  );
}

/* ───────────────────────── mountains ───────────────────────── */

type Peak = { x: number; top: number; hw: number; base: number };
const PEAKS: Peak[][] = [
  [
    { x: -12, top: -56, hw: 19, base: 0 },
    { x: 8, top: -80, hw: 25, base: 4 },
    { x: -6, top: -34, hw: 16, base: 12 },
  ],
  [
    { x: -10, top: -74, hw: 22, base: 2 },
    { x: 12, top: -62, hw: 20, base: 4 },
    { x: 14, top: -30, hw: 13, base: 12 },
  ],
  [
    { x: 0, top: -82, hw: 30, base: 8 },
    { x: -15, top: -30, hw: 14, base: 12 },
    { x: 17, top: -24, hw: 11, base: 12 },
  ],
];

const MOUNT_PAL: Record<"meadow" | "snow" | "ash", Pal> = {
  meadow: pal("#8d9f88", 0.36, 0.38),
  snow: { base: "#e4eefb", dark: "#a2bfe2", light: "#ffffff" },
  ash: pal("#4d3b48", 0.42, 0.25),
};

function MountainPeak({ p, biome, gid }: { p: Peak; biome: "meadow" | "snow" | "ash"; gid: string }) {
  const c = MOUNT_PAL[biome];
  const { x, top, hw, base } = p;
  const H = base - top;
  const big = H > 60;
  const capF = biome === "meadow" ? 0.3 : 0;
  const tri = P(x - hw, base, x, top, x + hw, base);
  const cap = (f: number) =>
    P(
      x, top,
      x + hw * f, top + H * f,
      x + hw * f * 0.45, top + H * f * 0.8,
      x + hw * f * 0.1, top + H * f * 1.08,
      x - hw * f * 0.35, top + H * f * 0.78,
      x - hw * f * 0.7, top + H * f * 1.02,
      x - hw * f, top + H * f,
    );
  return (
    <g>
      <polygon points={tri} fill={c.base} />
      <polygon points={P(x, top, x + hw, base, x + hw * 0.12, base)} fill={c.dark} />
      <polyline points={P(x - 2, top + 5, x - hw * 0.45, top + H * 0.5)} fill="none" stroke={c.light} strokeWidth={2} strokeLinecap="round" opacity={0.8} />
      <polyline points={P(x + hw * 0.35, top + H * 0.42, x + hw * 0.28, top + H * 0.62, x + hw * 0.4, top + H * 0.8)} fill="none" stroke={mix(c.dark, OL, 0.3)} strokeWidth={1.3} strokeLinecap="round" />
      {biome === "snow" && (
        <g>
          <polygon
            points={P(x - hw, base, x + hw, base, x + hw * 0.78, base - H * 0.22, x + hw * 0.45, base - H * 0.14, x + hw * 0.2, base - H * 0.3, x - hw * 0.15, base - H * 0.17, x - hw * 0.45, base - H * 0.32, x - hw * 0.72, base - H * 0.24)}
            fill="#7f8ea6"
          />
          <polygon points={P(x + hw * 0.12, base, x + hw, base, x + hw * 0.78, base - H * 0.22, x + hw * 0.45, base - H * 0.14, x + hw * 0.2, base - H * 0.3, x + hw * 0.1, base - H * 0.27)} fill="#5d6a80" />
          <polyline points={P(x - hw * 0.72, base - H * 0.24, x - hw * 0.45, base - H * 0.32, x - hw * 0.15, base - H * 0.17, x + hw * 0.2, base - H * 0.3, x + hw * 0.45, base - H * 0.14, x + hw * 0.78, base - H * 0.22)} fill="none" {...line(1.1)} />
        </g>
      )}
      {capF > 0 && (
        <g>
          <polygon points={cap(capF)} fill="#f6fbff" {...line(1.3)} />
          <polygon points={P(x, top, x + hw * capF, top + H * capF, x + hw * capF * 0.45, top + H * capF * 0.8, x + hw * 0.04, top + H * capF * 0.95)} fill="#c7dcf0" />
        </g>
      )}
      {biome === "ash" && big && (
        <g>
          <Glow id={gid} x={x} y={top + 2} r={14} ry={9} color="#ff6a1a" pulse />
          <path
            d={`M${x},${top + 2} Q${x - 4},${top + H * 0.25} ${x - hw * 0.15},${top + H * 0.45} T${x - hw * 0.4},${base - 3}`}
            fill="none" stroke="#ff5a14" strokeWidth={3.6} strokeLinecap="round"
          />
          <path
            d={`M${x},${top + 2} Q${x - 4},${top + H * 0.25} ${x - hw * 0.15},${top + H * 0.45} T${x - hw * 0.4},${base - 3}`}
            fill="none" stroke="#ffd04a" strokeWidth={1.3} strokeLinecap="round"
          />
          <path
            d={`M${x + 1},${top + 3} Q${x + 5},${top + H * 0.3} ${x + hw * 0.25},${top + H * 0.6}`}
            fill="none" stroke="#e8431a" strokeWidth={2.6} strokeLinecap="round"
          />
          <ellipse cx={x} cy={top + 2} rx={4} ry={1.8} fill="#ffd04a" {...line(1.1)} />
        </g>
      )}
      <polygon points={tri} fill="none" {...line(1.8)} />
    </g>
  );
}

type Butte = { x: number; base: number; bw: number; tw: number; top: number };
const BUTTES: Butte[][] = [
  [{ x: 0, base: 0, bw: 28, tw: 22, top: -42 }],
  [
    { x: -8, base: -3, bw: 16, tw: 11, top: -66 },
    { x: 12, base: 5, bw: 16, tw: 13, top: -30 },
  ],
  [
    { x: -5, base: 2, bw: 24, tw: 18, top: -50 },
    { x: 17, base: 8, bw: 8, tw: 4, top: -68 },
  ],
];

function ButteArt({ b }: { b: Butte }) {
  const { x, base, bw, tw, top } = b;
  const c = pal("#e39a55", 0.32, 0.38);
  const L0: Pt = [x - bw, base];
  const F0: Pt = [x, base + bw / 2];
  const R0: Pt = [x + bw, base];
  const L1: Pt = [x - tw, top];
  const F1: Pt = [x, top + tw / 2];
  const R1: Pt = [x + tw, top];
  const lp = (a: Pt, z: Pt, t: number): Pt => [lerp(a[0], z[0], t), lerp(a[1], z[1], t)];
  return (
    <g>
      <polygon points={P(...L0, ...F0, ...F1, ...L1)} fill={c.base} />
      <polygon points={P(...F0, ...R0, ...R1, ...F1)} fill={c.dark} />
      {[0.28, 0.52, 0.76].map((f, i) => (
        <polyline
          key={f}
          points={P(...lp(L0, L1, f), ...lp(F0, F1, f), ...lp(R0, R1, f))}
          fill="none"
          stroke={i % 2 ? "#f4c084" : "#b8642f"}
          strokeWidth={2.2}
        />
      ))}
      <polygon points={P(...L0, ...F0, ...F1, ...L1)} fill="none" {...line(1.7)} />
      <polygon points={P(...F0, ...R0, ...R1, ...F1)} fill="none" {...line(1.7)} />
      <polygon points={P(x - tw, top, x, top - tw / 2, x + tw, top, x, top + tw / 2)} fill={c.light} {...line(1.7)} />
      <polyline points={P(x - tw * 0.6, top, x - tw * 0.1, top - tw * 0.2)} fill="none" stroke="#fff0cf" strokeWidth={1.4} strokeLinecap="round" />
    </g>
  );
}

function MountainArt({ biome, v }: { biome: Biome; v: number }) {
  const uid = useUid();
  if (biome === "desert") {
    return (
      <g>
        <Shadow rx={30} ry={13} y={4} />
        {BUTTES[v].map((b, i) => <ButteArt key={i} b={b} />)}
        <Rock x={-20} y={8} w={6} h={6} shape={0} biome="desert" />
      </g>
    );
  }
  const peaks = PEAKS[v];
  const main = peaks.reduce((a, p) => (p.base - p.top > a.base - a.top ? p : a), peaks[0]);
  return (
    <g>
      <Shadow rx={30} ry={13} y={4} />
      {peaks.map((p, i) => <MountainPeak key={i} p={p} biome={biome} gid={`${uid}m${i}`} />)}
      {biome === "meadow" && (
        <g>
          <Blob x={-22} y={4} r={4.5} c={pal("#4cb83a")} />
          <Blob x={20} y={7} r={4} c={pal("#4cb83a")} />
          <Blob x={2} y={13} r={3.6} c={pal("#4cb83a")} />
        </g>
      )}
      {biome === "snow" && <Shard x={-20} y={8} w={3} h={11} c={pal("#9fdcff", 0.3, 0.5)} sw={1.2} />}
      {biome === "ash" && (
        <g fill="#8a8290" opacity={0.78} {...line(1.1)}>
          <circle cx={main.x + 3} cy={main.top - 6} r={4} />
          <circle cx={main.x + 7} cy={main.top - 10} r={3.2} />
          <circle cx={main.x + 4} cy={main.top - 13} r={2.4} />
        </g>
      )}
    </g>
  );
}

// [x, y, scale, mirrored] of each copy, sorted back (small y) to front; within one cell diamond.
const CLUSTERS: [number, number, number, boolean][][] = [
  [[0, 0, 1.08, false]],
  [[-8, -3, 0.9, true], [7, 3, 0.98, false]],
  [[2, -6, 0.82, false], [-11, 1, 0.86, true], [9, 4, 0.94, true]],
];

export function ObstacleArt({ kind, biome, variant }: { kind: "tree" | "rock" | "mountain"; biome: Biome; variant: number }): JSX.Element {
  const v = mod(variant, 3);
  const png = pngArt(`terrain/${biome}_${kind}`);
  if (png) {
    const k = `terrain/${biome}_${kind}`;
    if (kind === "mountain") {
      // Volcanoes of several sizes and shapes: a dormant cone, a broken one, lava vents, a spire.
      const SHAPES: [string, number][] = [[k, 64], [`${k}_2`, 46], [`${k}_3`, 56], [`${k}_4`, 50], [`${k}_5`, 28]];
      const shapes = SHAPES.filter(([key]) => pngArt(key));
      if (shapes.length > 1) {
        const [key, w] = shapes[mod(variant, shapes.length)];
        return <Png k={key} w={w} flip={mod(variant, 2) === 1} />;
      }
      return <g transform={`scale(${(v % 2 ? -1 : 1) * (0.88 + v * 0.05)},${0.88 + v * 0.05})`}><Png k={k} w={64} /></g>;
    }
    // A painted grove / heap when there is one (the third variant).
    const many = `terrain/${biome}_${kind === "tree" ? "grove" : "rocks"}`;
    if (v === 2 && pngArt(many)) return <Png k={many} w={kind === "tree" ? 50 : 40} />;
    // Else a lone one, a pair or a little grove / heap, back to front; a second shape mixed in.
    const alt = pngArt(`${k}_2`) ? `${k}_2` : k;
    const w = kind === "tree" ? 34 : 26;
    return (
      <g>
        {CLUSTERS[v].map(([x, y, s, flip], i) => {
          const key = (i + v) % 2 ? alt : k;
          // A tall slim shape keeps its height, not its width.
          const kw = key === k ? w : w * Math.sqrt(pngRatio(k) / pngRatio(key));
          return (
            <g key={i} transform={`translate(${x},${y}) scale(${s})`}>
              <Png k={key} w={kw} flip={flip} />
            </g>
          );
        })}
      </g>
    );
  }
  if (kind === "tree") return <TreeArt biome={biome} v={v} />;
  if (kind === "rock") return <RockArt biome={biome} v={v} />;
  return <MountainArt biome={biome} v={v} />;
}

/* ───────────────────────── ground decor ───────────────────────── */

function Pebbles({ c, snow = false }: { c: Pal; snow?: boolean }) {
  const ps: [number, number, number, number][] = [[-4, 0, 4, 2.6], [4, 2, 3, 2], [5, -2.5, 2.2, 1.6]];
  return (
    <g>
      {ps.map(([x, y, rx, ry], i) => (
        <g key={i}>
          <ellipse cx={x} cy={y} rx={rx} ry={ry} fill={c.base} {...line(1.1)} />
          <ellipse cx={x - rx * 0.25} cy={y - ry * 0.35} rx={rx * 0.5} ry={ry * 0.4} fill={snow ? "#f4fbff" : c.light} />
        </g>
      ))}
    </g>
  );
}

function Tuft({ c, x = 0, y = 0 }: { c: Pal; x?: number; y?: number }) {
  return (
    <g transform={`translate(${x} ${y})`} {...line(1.1)}>
      <path d="M-6,1 Q-6,-5 -9,-9 Q-4,-5 -2,1 Z" fill={c.dark} />
      <path d="M-3,1 Q-2,-7 -1,-12 Q2,-6 2,1 Z" fill={c.base} />
      <path d="M1,1 Q4,-5 8,-8 Q5,-3 5,1 Z" fill={c.base} />
      <path d="M-1.6,-1 Q-1.2,-6 -0.8,-9" fill="none" stroke={c.light} strokeWidth={0.9} />
    </g>
  );
}

export function DecorArt({ biome, variant }: { biome: Biome; variant: number }): JSX.Element {
  const v = mod(variant, 4);
  // A painted ground decal (flowers, a skull, a snow drift, an ember crack …), lying on the cell.
  const decal = `decals/${biome}_decal_${v + 1}`;
  const href = pngArt(decal);
  if (href) {
    const ratio = pngRatio(decal);
    const w = ratio > 1 ? 16 : 26;
    const h = w * ratio;
    return <image href={href} x={-w / 2} y={ratio > 1 ? 4 - h : -h / 2 + 1} width={w} height={h} />;
  }
  let art: ReactNode = null;
  if (biome === "meadow") {
    if (v === 0) {
      art = (
        <g>
          <g stroke="#2e7d2a" strokeWidth={1.3} strokeLinecap="round">
            <path d="M-4,1 L-4,-6 M1,1 L1,-9 M5,1 L5,-5" />
          </g>
          <path d="M1,-3 Q4,-5 5,-3 Q3,-2 1,-3 Z" fill="#4cb83a" {...line(0.8)} />
          {([[-4, -7, "#ff5d8f"], [1, -10, "#ffd23f"], [5, -6, "#ffffff"]] as [number, number, string][]).map(([x, y, c]) => (
            <g key={x}>
              <circle cx={x} cy={y} r={2.3} fill={c} {...line(1)} />
              <circle cx={x} cy={y} r={0.8} fill="#ff9d1c" />
            </g>
          ))}
        </g>
      );
    } else if (v === 1) art = <Tuft c={pal("#4cb83a")} />;
    else if (v === 2) art = <Pebbles c={ROCK_PAL.meadow} />;
    else {
      art = (
        <g>
          <path d="M-1.5,1 L-1,-6 L2,-6 L2.5,1 Z" fill="#f4ead6" {...line(1.1)} />
          <path d="M-6,-5 Q-6,-12 0.5,-12 Q7,-12 7,-5 Z" fill="#e8413c" {...line(1.2)} />
          <g fill="#ffffff">
            <circle cx={-2.5} cy={-8.5} r={1.2} />
            <circle cx={2.5} cy={-9.5} r={1} />
            <circle cx={4.6} cy={-6.6} r={0.8} />
          </g>
          <Tuft c={pal("#4cb83a")} x={7} y={1} />
        </g>
      );
    }
  } else if (biome === "desert") {
    if (v === 0) {
      art = <Limbs segs={[{ d: "M0,1 L0,-9", w: 4 }, { d: "M0,-4 L-3.5,-4 L-3.5,-7", w: 2.4 }]} c={pal("#3fae58")} sw={1.1} />;
    } else if (v === 1) {
      const bone = pal("#f1e6cf");
      art = (
        <g>
          <Limbs segs={[{ d: "M-6,-1 L5,2", w: 1.8 }, { d: "M-4,3 L4,-3", w: 1.8 }]} c={bone} sw={1} shade={false} />
          {[[-6, -1], [5, 2], [-4, 3], [4, -3]].map(([x, y]) => <circle key={`${x}${y}`} cx={x} cy={y} r={1.6} fill={bone.base} {...line(0.9)} />)}
          <path d="M6,-7 Q6,-11 10,-11 Q13,-11 13,-7 L12,-5 L7,-5 Z" fill={bone.base} {...line(1)} />
          <circle cx={8.6} cy={-8} r={0.9} fill={OL} />
          <circle cx={11} cy={-8} r={0.9} fill={OL} />
        </g>
      );
    } else if (v === 2) art = <Pebbles c={ROCK_PAL.desert} />;
    else art = <Tuft c={pal("#c9a34a", 0.32, 0.35)} />;
  } else if (biome === "snow") {
    if (v === 0) {
      art = (
        <g>
          <Tuft c={pal("#8fa36a")} y={-2} />
          <path d="M-9,2 Q-8,-3 -2,-3 Q3,-5 7,-2 Q10,0 9,2 Z" fill="#f4fbff" {...line(1.1)} />
        </g>
      );
    } else if (v === 1) {
      const ice = pal("#9fdcff", 0.3, 0.5);
      art = (
        <g>
          <Shard x={-1} y={1} w={3} h={12} c={ice} sw={1.1} />
          <Shard x={4} y={2.5} w={2} h={7} c={ice} sw={1} />
          <Glint x={-3} y={-9} s={2} />
        </g>
      );
    } else if (v === 2) art = <Pebbles c={ROCK_PAL.snow} snow />;
    else {
      art = (
        <g>
          <path d="M-8,2 Q-7,-4 0,-4 Q7,-4 8,2 Z" fill="#f4fbff" {...line(1.1)} />
          <path d="M-1,-2 L2,-10 M0.5,-6 L-2,-9" stroke="#5a4033" strokeWidth={1.4} strokeLinecap="round" />
        </g>
      );
    }
  } else {
    const crack = (
      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="-8,0 -3,-1 0,1.5 5,0 8,1" stroke={OL} strokeWidth={3.4} />
        <polyline points="-8,0 -3,-1 0,1.5 5,0 8,1" stroke="#ff7a1a" strokeWidth={1.8} />
        <polyline points="-3,-1 -2,-3.5" stroke="#ff7a1a" strokeWidth={1.2} />
        <ellipse cx={0} cy={0} rx={8} ry={3} fill="#ff6a1a" opacity={0.22} stroke="none" />
      </g>
    );
    if (v === 0) art = crack;
    else if (v === 1) {
      art = <Limbs segs={[{ d: "M-6,1 L1,-5 L2,-10 M1,-5 L6,-7", w: 1.8 }]} c={pal("#4a3732", 0.4, 0.28)} sw={1} />;
    } else if (v === 2) {
      const ob = ROCK_PAL.ash;
      art = (
        <g>
          <Shard x={-2} y={1} w={3} h={10} c={ob} sw={1.1} />
          <Shard x={4} y={2.5} w={2.2} h={6} c={ob} sw={1} />
          <Glint x={-3.4} y={-6} s={1.6} c="#d9c6ff" />
        </g>
      );
    } else {
      art = (
        <g>
          {crack}
          <path d="M3,-1 Q4,-5 8,-5 Q12,-5 12,-1 Z" fill="#6b6470" {...line(1)} />
        </g>
      );
    }
  }
  return (
    <g>
      <ellipse cx={0} cy={2} rx={9} ry={3.4} fill="#0b0610" opacity={0.16} />
      {art}
    </g>
  );
}

/* ───────────────────────── map objects ───────────────────────── */

const WOOD = pal("#b0672e", 0.34, 0.36);
const GOLD = pal("#f6c343", 0.3, 0.5);
const STONE = pal("#a9b0bb", 0.32, 0.42);

const FACTION_CLOTH: Record<Faction, Pal> = {
  dawn: pal("#3aa0ff", 0.32, 0.4),
  ash: pal("#6a2a8c", 0.34, 0.35),
};
const FACTION_ACCENT: Record<Faction, Pal> = {
  dawn: GOLD,
  ash: pal("#d8323a", 0.32, 0.38),
};

function ChestArt({ taken }: { taken: boolean }) {
  const body: Box = { x: 0, y: 5, w: 14, d: 7, h: 10 };
  const lid: Box = { x: 0, y: -5, w: 15, d: 7.5, h: 6 };
  const bands = (b: Box) => (
    <g {...line(1.1)} fill={GOLD.base}>
      <polygon points={quad(lf, b, 0.18, 0.3, 0, 1)} />
      <polygon points={quad(lf, b, 0.7, 0.82, 0, 1)} />
      <polygon points={quad(rf, b, 0.25, 0.38, 0, 1)} fill={GOLD.dark} />
      <polygon points={quad(rf, b, 0.68, 0.81, 0, 1)} fill={GOLD.dark} />
    </g>
  );
  if (taken) {
    const top = body.y - body.h;
    return (
      <g>
        <Shadow rx={20} ry={8} y={4} />
        <polygon points={P(0, top - 7, 14, top, 15, top - 11, 1, top - 19)} fill={WOOD.dark} {...line(1.6)} />
        <polygon points={P(2.4, top - 7.5, 12.6, top - 2.4, 13.3, top - 9.6, 3.1, top - 15.2)} fill={mix(WOOD.dark, OL, 0.25)} />
        <IsoBox b={body} c={WOOD} />
        <polygon points={P(-11.5, top, 0, top - 5.6, 11.5, top, 0, top + 5.6)} fill="#2c1a12" {...line(1.1)} />
        <polygon points={P(-11.5, top, 0, top - 5.6, 0, top - 3, -8, top + 1)} fill="#3e2518" />
        {bands(body)}
        <polygon points={quad(lf, body, 0.42, 0.58, 0.45, 0.95)} fill={GOLD.base} {...line(1.1)} />
        <circle cx={lf(body, 0.5, 0.68)[0]} cy={lf(body, 0.5, 0.68)[1]} r={1.1} fill={OL} />
      </g>
    );
  }
  const lt = lid.y - lid.h;
  return (
    <g>
      <Shadow rx={20} ry={8} y={4} />
      <IsoBox b={body} c={WOOD} />
      {bands(body)}
      <polygon points={P(-14.5, -5.2, 0, 2.2, 14.5, -5.2, 0, -12.6)} fill="#ffd34d" opacity={0.9} />
      <IsoBox b={lid} c={pal("#c2552c", 0.34, 0.36)} />
      <path d={`M${-15},${lt} Q${-8},${lt - 7} 0,${lt - 7.5} Q8,${lt - 7} 15,${lt} L0,${lt + 7.5} Z`} fill={mix("#c2552c", "#ffffff", 0.2)} {...line(1.5)} />
      <path d={`M${-12},${lt - 1} Q${-7},${lt - 5.5} ${-1},${lt - 6}`} fill="none" stroke="#ffffff" strokeWidth={1.4} strokeLinecap="round" opacity={0.7} />
      {bands(lid)}
      <polygon points={quad(lf, body, 0.42, 0.58, 0.4, 1.1)} fill={GOLD.base} {...line(1.1)} />
      <circle cx={lf(body, 0.5, 0.72)[0]} cy={lf(body, 0.5, 0.72)[1]} r={1.1} fill={OL} />
      <g fill={GOLD.base} {...line(1)}>
        <ellipse cx={-6} cy={lt - 2} rx={2.6} ry={1.4} />
        <ellipse cx={-3} cy={lt - 4} rx={2.6} ry={1.4} />
      </g>
      <Glint x={-9} y={lt - 8} s={3.2} c="#fff6c8" />
      <Glint x={9} y={-14} s={2.6} c="#fff6c8" />
      <Glint x={-12} y={-1} s={2} c="#fff6c8" />
    </g>
  );
}

function WellArt({ taken, uid }: { taken: boolean; uid: string }) {
  const ring = taken ? fade(STONE, 0.3) : STONE;
  const top = -5;
  return (
    <g>
      <Shadow rx={22} ry={9} y={4} />
      {!taken && <Glow id={`${uid}wg`} x={0} y={top} r={26} ry={18} color="#4fd6ff" o={0.55} pulse />}
      <IsoCyl x={0} y={4} r={16} ry={8} h={9} c={ring} top={false} />
      {[-11, -4, 4, 11].map((sx) => (
        <path key={sx} d={`M${sx},${4 + 8 * Math.sqrt(1 - (sx / 16) ** 2) - 9} L${sx},${4 + 8 * Math.sqrt(1 - (sx / 16) ** 2) - 4.5}`} stroke={ring.dark} strokeWidth={1.2} />
      ))}
      <path d="M-16,0 Q0,7 16,0" fill="none" stroke={ring.dark} strokeWidth={1.1} />
      <ellipse cx={0} cy={top} rx={16} ry={8} fill={ring.light} {...line(1.6)} />
      <ellipse cx={0} cy={top + 0.6} rx={11.5} ry={5.6} fill={taken ? "#56606e" : "#2b7fe0"} {...line(1.3)} />
      {!taken ? (
        <g>
          <ellipse cx={-1} cy={top + 0.2} rx={8} ry={3.6} fill="#6fe3ff" />
          <ellipse cx={-3} cy={top - 0.6} rx={3.4} ry={1.4} fill="#e6fbff" />
          <path d="M-5,-6 L-4,-30 L4,-30 L5,-6 Z" fill="#8ff0ff" opacity={0.28} />
          <g transform="translate(0 -38)">
            <polygon points={P(0, -9, 5, -1, 0, 7, -5, -1)} fill="#5fd2ff" {...line(1.4)} />
            <polygon points={P(0, -9, 5, -1, 0, 7)} fill="#2c8fe6" />
            <polygon points={P(0, -9, -2.2, -1, 0, 3, -5, -1)} fill="#c9f6ff" />
            <polygon points={P(0, -9, 5, -1, 0, 7, -5, -1)} fill="none" {...line(1.4)} />
            <animateTransform attributeName="transform" type="translate" values="0 -38;0 -41;0 -38" dur="2.6s" repeatCount="indefinite" />
          </g>
          <Glint x={-9} y={-24} s={2.6} c="#c9f6ff" />
          <Glint x={10} y={-30} s={2.2} c="#c9f6ff" />
          <Glint x={7} y={-14} s={1.8} c="#ffffff" />
        </g>
      ) : (
        <g>
          <ellipse cx={-2} cy={top} rx={4} ry={1.4} fill="#7a8492" />
          <g transform="translate(9 -2)">
            <polygon points={P(0, -7, 4, -1, 0, 4, -4, -1)} fill="#8a96a6" {...line(1.2)} />
            <polygon points={P(0, -7, 4, -1, 0, 4)} fill="#6b7686" />
          </g>
        </g>
      )}
      <g fill={ring.base} {...line(1.2)}>
        <rect x={-19} y={0} width={5} height={4} rx={1.2} />
        <rect x={14} y={1} width={5} height={4} rx={1.2} />
      </g>
    </g>
  );
}

function ArtifactItem({ variant }: { variant?: string }) {
  switch (variant) {
    case "boots": {
      const boot = (dx: number, c: Pal) => (
        <g transform={`translate(${dx} 0)`}>
          <path d="M-8,-21 Q-9,-30 -5,-31 L-1,-31 L0,-27 Q6,-26.5 9,-23.5 Q10.5,-21 8,-20 L-8,-20 Z" fill={c.base} {...line(1.4)} />
          <path d="M0,-27 Q6,-26.5 9,-23.5 Q10.5,-21 8,-20 L2,-20 Q5,-23 0,-27 Z" fill={c.dark} />
          <path d="M-8,-20 L8,-20 L8,-18.6 L-8,-18.6 Z" fill="#2b2230" {...line(1)} />
          <g fill="#f4f4f4">
            <circle cx={-5} cy={-17.6} r={0.9} />
            <circle cx={1} cy={-17.6} r={0.9} />
            <circle cx={6} cy={-17.6} r={0.9} />
          </g>
          <path d="M-3,-28 L1,-26 M-3.5,-25.5 L1.5,-24" stroke="#ffffff" strokeWidth={1} strokeLinecap="round" />
          <path d="M-6,-29 Q-7,-24 -5,-22" fill="none" stroke={c.light} strokeWidth={1.3} strokeLinecap="round" />
        </g>
      );
      return (
        <g>
          {boot(4, darken(GOLD, 0.12))}
          {boot(-3, GOLD)}
        </g>
      );
    }
    case "armband":
      return (
        <g>
          <path d="M-9,-26 A9,4.5 0 0 1 9,-26" fill="none" stroke={OL} strokeWidth={8} />
          <path d="M-9,-26 A9,4.5 0 0 1 9,-26" fill="none" stroke="#c98d1c" strokeWidth={4.8} />
          <path d="M-9,-26 A9,4.5 0 0 0 9,-26" fill="none" stroke={OL} strokeWidth={8} />
          <path d="M-9,-26 A9,4.5 0 0 0 9,-26" fill="none" stroke="#ffd23f" strokeWidth={4.8} />
          <path d="M-6,-23.6 A9,4.5 0 0 0 -1,-21.8" fill="none" stroke="#fff6c8" strokeWidth={1.3} strokeLinecap="round" />
          <path d="M4.2,-23.2 A2.3,2.3 0 1 0 4.2,-19.6" fill="none" stroke="#1e3a8a" strokeWidth={1.5} strokeLinecap="round" transform="translate(-2.6 0)" />
        </g>
      );
    case "shinguards": {
      const guard = (dx: number, rot: number) => (
        <g transform={`translate(${dx} 0) rotate(${rot} 0 -26)`}>
          <path d="M-4.5,-35 Q0,-37.5 4.5,-35 L4.5,-22 Q0,-15.5 -4.5,-22 Z" fill="#f4f7fb" {...line(1.4)} />
          <path d="M1.5,-36.3 Q3.5,-36 4.5,-35 L4.5,-22 Q3,-19.5 1.5,-18.5 Z" fill="#c3cfdf" />
          <path d="M-4.5,-30 L4.5,-30 L4.5,-27 L-4.5,-27 Z" fill="#3aa0ff" />
          <circle cx={0} cy={-23} r={1.6} fill="#ffd23f" {...line(0.8)} />
          <path d="M-4.5,-35 Q0,-37.5 4.5,-35 L4.5,-22 Q0,-15.5 -4.5,-22 Z" fill="none" {...line(1.4)} />
        </g>
      );
      return (
        <g>
          {guard(5, 10)}
          {guard(-4, -8)}
        </g>
      );
    }
    case "whistle": {
      const s = pal("#d9e2ec", 0.34, 0.5);
      return (
        <g>
          <path d="M-6,-28 Q-12,-24 -10,-16 Q-6,-10 2,-14" fill="none" stroke="#e8413c" strokeWidth={1.6} strokeLinecap="round" />
          <path d="M1,-31 L11,-31 L11,-26 L4,-26 Z" fill={s.base} {...line(1.3)} />
          <circle cx={-1} cy={-25} r={6.5} fill={s.base} {...line(1.4)} />
          <path d="M2,-30.6 A6.5,6.5 0 0 1 4,-21 A5,5 0 0 0 2,-30.6 Z" fill={s.dark} />
          <circle cx={-3} cy={-27} r={1.8} fill="#ffffff" />
          <circle cx={-6.5} cy={-29.5} r={2} fill="none" {...line(1.2)} />
          <rect x={3} y={-30} width={4} height={2.2} rx={0.6} fill="#2b2230" />
        </g>
      );
    }
    case "flag":
      return (
        <g>
          <Limbs segs={[{ d: "M-4,-14 L-4,-46", w: 1.8 }]} c={pal("#8a5a34")} sw={1.1} shade={false} />
          <path d="M-4,-46 Q4,-49 12,-45 L12,-33 Q4,-37 -4,-34 Z" fill="#ffd23f" {...line(1.4)} />
          <path d="M-4,-42 Q4,-45 12,-41 L12,-37 Q4,-41 -4,-38 Z" fill="#3aa0ff" />
          <path d="M4,-47.2 Q8,-47 12,-45 L12,-33 Q8,-35 4,-35.7 Z" fill="#000" opacity={0.15} />
          <path d="M-4,-46 Q4,-49 12,-45 L12,-33 Q4,-37 -4,-34 Z" fill="none" {...line(1.4)} />
          <circle cx={-4} cy={-47.5} r={1.6} fill="#ffd34d" {...line(0.9)} />
        </g>
      );
    default:
      return (
        <g>
          <circle cx={0} cy={-27} r={7.5} fill="#9a4dff" {...line(1.5)} />
          <path d="M3,-33.5 A7.5,7.5 0 0 1 3,-20.5 A6.5,6.5 0 0 0 3,-33.5 Z" fill="#5a22b5" />
          <circle cx={-2.5} cy={-29.5} r={3} fill="#d8b8ff" />
          <circle cx={-3.3} cy={-30.4} r={1.2} fill="#ffffff" />
        </g>
      );
  }
}

function ArtifactArt({ variant, taken, uid }: { variant?: string; taken: boolean; uid: string }) {
  const st = taken ? fade(STONE, 0.3) : STONE;
  const isFlag = variant === "flag";
  return (
    <g>
      <Shadow rx={18} ry={8} y={4} />
      {!taken && <Glow id={`${uid}ag`} x={0} y={isFlag ? -34 : -26} r={18} color="#ffe27a" o={0.75} pulse />}
      <IsoBox b={{ x: 0, y: 5, w: 13, d: 6.5, h: 4 }} c={st} />
      <IsoCyl x={0} y={1} r={6} ry={3} h={12} c={st} top={false} />
      <IsoBox b={{ x: 0, y: -10, w: 10, d: 5, h: 3 }} c={st} />
      <polygon points={P(-6, -13, 0, -16, 6, -13, 0, -10)} fill={taken ? st.base : "#8a6bff"} opacity={taken ? 0.6 : 0.85} />
      {!taken && (
        <g>
          <ArtifactItem variant={variant} />
          <Glint x={-11} y={-34} s={3} c="#fff6c8" />
          <Glint x={11} y={-24} s={2.4} c="#fff6c8" />
          <Glint x={7} y={-40} s={1.8} c="#ffffff" />
        </g>
      )}
    </g>
  );
}

function TribuneArt({ taken, faction }: { taken: boolean; faction: Faction }) {
  const wood = taken ? fade(WOOD, 0.35) : WOOD;
  const cloth = FACTION_CLOTH[faction];
  const accent = FACTION_ACCENT[faction];
  const steps: Box[] = [
    { x: 8, y: 0, w: 10, d: 5, h: 15 },
    { x: 3, y: 2.5, w: 15, d: 7.5, h: 10 },
    { x: -2, y: 5, w: 20, d: 10, h: 5 },
  ];
  const fans: [number, number, string][] = [
    [-15, 2.5, cloth.base], [-9, 5.5, accent.base], [-3, 8.5, cloth.base],
    [-7, -5.5, accent.base], [-1, -2.5, cloth.base], [5, 0.5, accent.base],
  ];
  const front = steps[2];
  return (
    <g>
      <Shadow rx={25} ry={11} y={4} />
      <Flag x={-2} y={-15} h={24} c={taken ? fade(cloth) : cloth} droop={taken} emblem={faction} w={13} fh={8} dir={-1} />
      <Flag x={18} y={-15} h={22} c={taken ? fade(accent) : accent} droop={taken} w={11} fh={7} />
      {steps.map((b, i) => (
        <g key={i}>
          <IsoBox b={b} c={wood} />
          <polyline points={P(...lf(b, 0, 0.5), ...lf(b, 1, 0.5), ...rf(b, 1, 0.5))} fill="none" stroke={wood.dark} strokeWidth={1} />
        </g>
      ))}
      {!taken &&
        fans.map(([x, y, c], i) => (
          <g key={i}>
            <path d={`M${x - 2.6},${y} Q${x - 2.6},${y - 4} ${x},${y - 4} Q${x + 2.6},${y - 4} ${x + 2.6},${y} Z`} fill={c} {...line(1)} />
            <circle cx={x} cy={y - 6} r={2.3} fill="#f1c69b" {...line(1)} />
            {i % 2 === 0 && <path d={`M${x + 2},${y - 3} L${x + 4.5},${y - 9}`} stroke={accent.base} strokeWidth={1.6} strokeLinecap="round" />}
          </g>
        ))}
      {[0.12, 0.42, 0.72].map((u, i) => {
        const c = i % 2 ? accent : cloth;
        return (
          <g key={u}>
            <polygon points={quad(lf, front, u, u + 0.14, 0.1, 1)} fill={taken ? fade(c).base : c.base} {...line(1)} />
            <polygon points={quad(lf, front, u, u + 0.14, 0.42, 0.62)} fill="#ffffff" opacity={taken ? 0.5 : 1} />
          </g>
        );
      })}
    </g>
  );
}

function ReinforceArt({ taken, faction }: { taken: boolean; faction: Faction }) {
  const cloth = taken ? fade(FACTION_CLOTH[faction]) : FACTION_CLOTH[faction];
  const trim = taken ? fade(GOLD) : GOLD;
  const crate: Box = { x: 9, y: 7, w: 10, d: 5, h: 9 };
  const planks = (f: Face) => (
    <g stroke={WOOD.dark} strokeWidth={1.5} strokeLinecap="round">
      <line x1={f(crate, 0.1, 0.12)[0]} y1={f(crate, 0.1, 0.12)[1]} x2={f(crate, 0.9, 0.88)[0]} y2={f(crate, 0.9, 0.88)[1]} />
      <line x1={f(crate, 0.1, 0.88)[0]} y1={f(crate, 0.1, 0.88)[1]} x2={f(crate, 0.9, 0.12)[0]} y2={f(crate, 0.9, 0.12)[1]} />
    </g>
  );
  const ct = crate.y - crate.h;
  return (
    <g>
      <Shadow rx={22} ry={9} y={4} />
      <g transform={taken ? "rotate(-14 -10 3)" : undefined}>
        <Limbs segs={[{ d: "M-10,3 L-10,-52", w: 2.4 }, { d: "M-17.5,-48 L-2.5,-48", w: 1.8 }]} c={pal("#8a5a34")} sw={1.2} />
        <polygon points={P(-10, -61, -12, -54, -8, -54)} fill="#d9e2ec" {...line(1.1)} />
        <Cel
          d={taken ? "M-16.5,-48 L-3.5,-48 L-4.5,-38 L-10,-40 L-15.5,-38 Z" : "M-16.5,-48 L-3.5,-48 L-3.5,-26 L-10,-31 L-16.5,-26 Z"}
          dd={taken ? "M-8,-48 L-3.5,-48 L-4.5,-38 L-8,-39.3 Z" : "M-8,-48 L-3.5,-48 L-3.5,-26 L-8,-29.7 Z"}
          c={cloth}
          sw={1.4}
        />
        <path d="M-16.5,-45.5 L-3.5,-45.5" stroke={trim.base} strokeWidth={1.6} />
        {!taken && <Emblem kind={faction} x={-10} y={-37.5} r={3.6} />}
      </g>
      {!taken && <Blob x={18} y={-2} r={5.5} ry={6.5} c={pal("#d9b98a")} />}
      <IsoBox b={crate} c={WOOD} />
      {planks(lf)}
      {planks(rf)}
      {taken ? (
        <polygon points={P(crate.x - 8, ct, crate.x, ct - 4, crate.x + 8, ct, crate.x, ct + 4)} fill="#2c1a12" {...line(1)} />
      ) : (
        <g>
          <IsoBox b={{ x: 6, y: ct + 1, w: 5, d: 2.5, h: 5 }} c={pal("#7c8a3a", 0.34, 0.36)} />
          <Limbs segs={[{ d: "M-2,9 L13,-25", w: 1.5 }, { d: "M1,10 L16,-22", w: 1.5 }]} c={pal("#8a5a34")} sw={1} shade={false} />
          <polygon points={P(13, -25, 12.2, -30, 15, -27)} fill="#d9e2ec" {...line(1)} />
          <polygon points={P(16, -22, 15.4, -27, 18, -23.6)} fill="#d9e2ec" {...line(1)} />
          <Glint x={-14} y={-56} s={2.4} c="#fff6c8" />
        </g>
      )}
      {taken && <IsoBox b={{ x: -14, y: 11, w: 6, d: 3, h: 1.6 }} c={WOOD} sw={1.2} />}
    </g>
  );
}

function MarketArt({ taken }: { taken: boolean }) {
  const f = (c: string) => (taken ? mix(c, "#8e8a94", 0.55) : c);
  const stripes = [f("#e8413c"), f("#fff3d6"), f("#3aa0ff"), f("#fff3d6")];
  const A: Pt = [0, -48];
  const L: Pt = [-23, -28];
  const F: Pt = [0, -17];
  const R: Pt = [23, -28];
  const n = 4;
  const wedge = (a: Pt, b: Pt, dark: boolean) =>
    Array.from({ length: n }, (_, i) => {
      const p0: Pt = [lerp(a[0], b[0], i / n), lerp(a[1], b[1], i / n)];
      const p1: Pt = [lerp(a[0], b[0], (i + 1) / n), lerp(a[1], b[1], (i + 1) / n)];
      const col = stripes[(i + (dark ? 1 : 0)) % stripes.length];
      const c = dark ? mix(col, OL, 0.25) : col;
      return (
        <g key={`${dark}${i}`}>
          <polygon points={P(...A, ...p0, ...p1)} fill={c} />
          <path d={`M${p0[0]},${p0[1]} Q${(p0[0] + p1[0]) / 2},${(p0[1] + p1[1]) / 2 + 5} ${p1[0]},${p1[1]} Z`} fill={c} {...line(1.2)} />
        </g>
      );
    });
  const counter: Box = { x: 0, y: 6, w: 18, d: 9, h: 9 };
  const wood = taken ? fade(WOOD, 0.4) : WOOD;
  const gold = taken ? fade(GOLD, 0.5) : GOLD;
  return (
    <g>
      <Shadow rx={25} ry={11} y={4} />
      <IsoBox b={counter} c={wood} />
      <polygon points={quad(lf, counter, 0.06, 0.94, 0.2, 0.92)} fill={f("#3aa0ff")} {...line(1.1)} />
      <polygon points={quad(lf, counter, 0.06, 0.94, 0.78, 0.92)} fill={gold.base} />
      <polygon points={quad(rf, counter, 0.06, 0.94, 0.2, 0.92)} fill={f("#2a74c0")} {...line(1.1)} />
      {!taken && (
        <g>
          <ellipse cx={-6} cy={-2} rx={3.5} ry={1.6} fill={gold.dark} {...line(1)} />
          <Limbs segs={[{ d: "M-6,-2.5 L-6,-17", w: 1.4 }, { d: "M-13,-15.5 L1,-17.5", w: 1.3 }]} c={gold} sw={0.9} shade={false} />
          <path d="M-13,-15.5 L-15,-9.5 M-13,-15.5 L-11,-9.5 M1,-17.5 L-1,-11.5 M1,-17.5 L3,-11.5" stroke={OL} strokeWidth={0.8} />
          <path d="M-16,-9.5 Q-13,-7 -10,-9.5 Z" fill={gold.base} {...line(1)} />
          <path d="M-2,-11.5 Q1,-9 4,-11.5 Z" fill={gold.base} {...line(1)} />
          <g transform="rotate(-24 9 -1)">
            <rect x={3} y={-3} width={12} height={5} fill="#fff1d0" {...line(1.1)} />
            <rect x={1.6} y={-4} width={2.6} height={7} rx={1.2} fill="#ecd6a6" {...line(1)} />
            <rect x={13.8} y={-4} width={2.6} height={7} rx={1.2} fill="#ecd6a6" {...line(1)} />
            <path d="M6,-1.5 L12,-1.5 M6,0.4 L10.5,0.4" stroke="#8a6a4a" strokeWidth={0.7} />
          </g>
          <circle cx={11.5} cy={3.5} r={2} fill="#d32b2b" {...line(0.9)} />
          <g fill={gold.base} {...line(0.9)}>
            <ellipse cx={14} cy={-6} rx={2.4} ry={1.2} />
            <ellipse cx={14} cy={-7.6} rx={2.4} ry={1.2} />
          </g>
          <Glint x={-6} y={-21} s={2.8} c="#fff6c8" />
        </g>
      )}
      <Limbs segs={[{ d: "M-20,-27 L-18,7", w: 2 }, { d: "M20,-27 L18,7", w: 2 }]} c={wood} sw={1.1} />
      {wedge(L, F, false)}
      {wedge(F, R, true)}
      <polygon points={P(...L, ...F, ...R, ...A)} fill="none" {...line(1.6)} />
      <polyline points={P(...A, ...F)} fill="none" {...line(1.2)} />
      <Flag x={0} y={-48} h={10} c={taken ? fade(GOLD) : pal("#ffd23f")} w={8} fh={5} droop={taken} />
    </g>
  );
}

function Tent({ x, y, s = 1, c, eyes }: { x: number; y: number; s?: number; c: Pal; eyes: boolean }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s * 1.25})`}>
      <path d="M0,-19 L-4,-26 M0,-19 L4,-25.5 M0,-19 L1,-27" stroke="#5a3a22" strokeWidth={2.2} strokeLinecap="round" />
      <Cone r={12} ry={6} h={20} c={c} />
      <polygon points={P(-4.4, -9, -9.2, 3.6, -2.9, 5.6)} fill="#20120c" {...line(1.3)} />
      {eyes && (
        <g fill="#ff3b2f">
          <circle cx={-6.2} cy={0.2} r={0.95} />
          <circle cx={-4.2} cy={0.9} r={0.95} />
        </g>
      )}
      <path d="M-1,-12 L3,-11 L3.5,-6 L-0.5,-6.8 Z" fill={c.light} {...line(1)} />
      <path d="M0.2,-11 L0.4,-7.4 M2,-10.6 L2.2,-7" stroke={c.dark} strokeWidth={0.7} />
    </g>
  );
}

function Campfire({ x, y, lit, gid }: { x: number; y: number; lit: boolean; gid: string }) {
  const logs = lit ? pal("#7a4a26") : pal("#4a4040", 0.35, 0.25);
  return (
    <g transform={`translate(${x} ${y})`}>
      {lit && <Glow id={gid} x={0} y={-4} r={16} ry={11} color="#ff8a24" o={0.7} pulse />}
      {[[-7, 0], [-4, 3], [1, 3.8], [6, 2], [7, -1], [0, -3]].map(([sx, sy]) => (
        <ellipse key={`${sx}${sy}`} cx={sx} cy={sy} rx={2.6} ry={1.7} fill="#8d939d" {...line(1)} />
      ))}
      <Limbs segs={[{ d: "M-5,2 L5,-2", w: 2.6 }, { d: "M-5,-2 L5,2", w: 2.6 }]} c={logs} sw={1.1} />
      {lit ? (
        <g>
          <Flame x={0} y={-7} r={5.5} />
          <circle cx={-3} cy={-20} r={0.9} fill="#ffd23f" />
          <circle cx={3} cy={-23} r={0.7} fill="#ffb03a" />
        </g>
      ) : (
        <path d="M0,-2 Q-4,-8 0,-13 Q4,-18 0,-24" fill="none" stroke="#d6d9df" strokeWidth={2.6} strokeLinecap="round" opacity={0.75} />
      )}
    </g>
  );
}

function Totem({ x, y, h, horns, cloth }: { x: number; y: number; h: number; horns: boolean; cloth?: Pal }) {
  const bone = pal("#efe6d2", 0.3, 0.5);
  const t = y - h;
  return (
    <g>
      <Limbs segs={[{ d: `M${x},${y} L${x},${t}`, w: 3.6 }]} c={pal("#7a4a26")} />
      <Limbs segs={[{ d: `M${x - 6},${t + 16} L${x + 6},${t + 5}`, w: 2.6 }]} c={pal("#9a6a3a")} sw={1.1} />
      <circle cx={x + 6.5} cy={t + 4.5} r={3.2} fill="#9a6a3a" {...line(1.2)} />
      <path d={`M${x + 8},${t + 2} L${x + 10},${t + 0.6} M${x + 9.5},${t + 5} L${x + 11.4},${t + 5.4}`} stroke={OL} strokeWidth={1.3} strokeLinecap="round" />
      {cloth && <path d={`M${x - 1},${t + 9} L${x - 7},${t + 11} L${x - 5},${t + 20} L${x - 1},${t + 15} Z`} fill={cloth.base} {...line(1.1)} />}
      {horns && (
        <g fill={bone.light} {...line(1.2)}>
          <path d={`M${x - 4},${t - 6} Q${x - 11},${t - 7} ${x - 10},${t - 15} Q${x - 8},${t - 10} ${x - 3.5},${t - 9} Z`} />
          <path d={`M${x + 4},${t - 6} Q${x + 11},${t - 7} ${x + 10},${t - 15} Q${x + 8},${t - 10} ${x + 3.5},${t - 9} Z`} />
        </g>
      )}
      <path d={`M${x - 5},${t - 5} Q${x - 5},${t - 12} ${x},${t - 12} Q${x + 5},${t - 12} ${x + 5},${t - 5} L${x + 3.5},${t - 2} L${x + 3},${t + 1} L${x - 3},${t + 1} L${x - 3.5},${t - 2} Z`} fill={bone.base} {...line(1.3)} />
      <path d={`M${x + 2},${t - 11.6} Q${x + 5},${t - 11} ${x + 5},${t - 5} L${x + 3.5},${t - 2} L${x + 3},${t + 1} L${x + 1.5},${t + 1} Q${x + 4},${t - 5} ${x + 2},${t - 11.6} Z`} fill={bone.dark} />
      <ellipse cx={x - 2} cy={t - 5.5} rx={1.6} ry={1.9} fill={OL} />
      <ellipse cx={x + 2} cy={t - 5.5} rx={1.6} ry={1.9} fill={OL} />
      <circle cx={x - 2} cy={t - 5.5} r={0.6} fill="#ff3b2f" />
      <circle cx={x + 2} cy={t - 5.5} r={0.6} fill="#ff3b2f" />
      <path d={`M${x - 1.5},${t - 1} L${x - 1.5},${t + 0.8} M${x},${t - 1} L${x},${t + 0.8} M${x + 1.5},${t - 1} L${x + 1.5},${t + 0.8}`} stroke={OL} strokeWidth={0.7} />
    </g>
  );
}

function Stake({ x, y, h, lean, c }: { x: number; y: number; h: number; lean: number; c: Pal }) {
  const tx = x + lean;
  return (
    <g>
      <polygon points={P(x - 2, y, x + 2, y + 0.6, tx + 2, y - h + 3, tx, y - h, tx - 2, y - h + 3)} fill={c.base} {...line(1.2)} />
      <polygon points={P(x + 0.3, y + 0.3, x + 2, y + 0.6, tx + 2, y - h + 3, tx, y - h, tx + 0.3, y - h + 3)} fill={c.dark} />
      <polygon points={P(tx + 2, y - h + 3, tx, y - h, tx - 2, y - h + 3)} fill="#e9dcc0" />
      <polygon points={P(x - 2, y, x + 2, y + 0.6, tx + 2, y - h + 3, tx, y - h, tx - 2, y - h + 3)} fill="none" {...line(1.2)} />
    </g>
  );
}

function CampArt({ level, taken, uid }: { level: number; taken: boolean; uid: string }) {
  const lv = Math.min(3, Math.max(1, Math.round(level)));
  const hide = lv === 3 ? pal("#9a4a38", 0.34, 0.34) : pal("#b07b4f", 0.34, 0.36);
  const tc = taken ? fade(hide, 0.45) : hide;
  const eyes = !taken && lv >= 2;
  const red = taken ? fade(pal("#d32b2b"), 0.6) : pal("#d32b2b", 0.32, 0.38);
  type Part = { y: number; el: ReactNode };
  const parts: Part[] = [];
  const add = (y: number, el: ReactNode) => parts.push({ y, el });
  if (lv === 1) {
    add(-3, <Tent x={-8} y={-3} s={0.95} c={tc} eyes={eyes} />);
    add(-6, <Totem x={15} y={-6} h={18} horns={false} />);
    add(5, <Campfire x={8} y={5} lit={!taken} gid={`${uid}cf`} />);
  } else if (lv === 2) {
    add(-9, <Tent x={7} y={-9} s={0.86} c={tc} eyes={false} />);
    add(-2, <Tent x={-11} y={-2} s={1} c={tc} eyes={eyes} />);
    add(4, <Totem x={20} y={4} h={22} horns />);
    add(6, <Campfire x={3} y={6} lit={!taken} gid={`${uid}cf`} />);
  } else {
    add(-12, <Totem x={1} y={-12} h={28} horns cloth={red} />);
    add(-11, <Flag x={-20} y={-4} h={36} c={red} swallow droop={taken} w={12} fh={8} />);
    add(-10, <Flag x={22} y={-4} h={34} c={red} swallow droop={taken} w={11} fh={7} dir={-1} />);
    add(-8, <Tent x={10} y={-7} s={0.92} c={tc} eyes={false} />);
    add(-3, <Tent x={-13} y={-3} s={1.05} c={tc} eyes={eyes} />);
    add(1, <Tent x={17} y={3} s={0.75} c={tc} eyes={eyes} />);
    add(6, <Campfire x={-1} y={5} lit={!taken} gid={`${uid}cf`} />);
  }
  if (taken) add(7, <Flag x={4} y={9} h={34} c={pal("#f6f4ee", 0.22, 0.5)} w={13} fh={8} />);
  parts.sort((a, b) => a.y - b.y);
  const stakeC = taken ? fade(pal("#9a6a3a"), 0.4) : pal("#9a6a3a");
  const stakes: ReactNode[] = [];
  if (lv === 3) {
    for (let i = 0; i < 4; i++) {
      const t = i / 3;
      stakes.push(<Stake key={`l${i}`} x={lerp(-29, -10, t)} y={lerp(3, 12.5, t)} h={11 - i * 0.5} lean={-1.5} c={stakeC} />);
      stakes.push(<Stake key={`r${i}`} x={lerp(10, 29, t)} y={lerp(12.5, 3, t)} h={9.5 + i * 0.5} lean={1.5} c={stakeC} />);
    }
  } else if (lv === 2) {
    stakes.push(<Stake key="a" x={-24} y={6} h={9} lean={-1.5} c={stakeC} />);
    stakes.push(<Stake key="b" x={-18} y={9} h={10} lean={-1} c={stakeC} />);
  }
  return (
    <g>
      <Shadow rx={26} ry={11} y={3} />
      <ellipse cx={0} cy={3} rx={22} ry={9} fill={taken ? "#7d7468" : "#8a6a48"} opacity={0.35} />
      {parts.map((p, i) => <g key={i}>{p.el}</g>)}
      {stakes}
    </g>
  );
}

function MineArt({ taken, uid }: { taken: boolean; uid: string }) {
  const rock = pal("#8f7c6c", 0.34, 0.36);
  const cart: Box = { x: 12, y: 8, w: 8, d: 4, h: 6 };
  const ct = cart.y - cart.h;
  const metal = pal("#6f7884", 0.34, 0.4);
  return (
    <g>
      <Shadow rx={26} ry={11} y={4} />
      <Cel
        d="M-27,6 Q-29,-10 -17,-23 Q-6,-35 7,-31 Q19,-27 23,-13 Q27,0 21,8 Q0,14 -27,6 Z"
        dd="M7,-31 Q19,-27 23,-13 Q27,0 21,8 Q12,11 5,10 Q13,-6 7,-31 Z"
        ld="M-22,-6 Q-20,-18 -11,-24 Q-14,-14 -18,-4 Z"
        c={rock}
        sw={1.8}
      />
      <g fill={rock.dark} {...line(1.1)}>
        <ellipse cx={-20} cy={2} rx={3} ry={2} />
        <ellipse cx={15} cy={-18} rx={2.6} ry={1.8} />
      </g>
      <circle cx={-3} cy={-26} r={1.6} fill={GOLD.base} {...line(0.8)} />
      <path d="M-15,8 L-15,-7 Q-8,-17 -1,-7 L-1,10 Z" fill="#170d12" />
      <Limbs segs={[{ d: "M-16,9 L-16,-9", w: 3.2 }, { d: "M0,11 L0,-8", w: 3.2 }, { d: "M-18,-10 L2,-9", w: 3.2 }]} c={WOOD} sw={1.2} />
      <g stroke="#5c5f66" strokeWidth={1.4} strokeLinecap="round">
        <path d="M-11,10 L9,17 M-5,8 L15,14" />
        <path d="M-9,10.5 L-4,8.6 M-3,12.6 L2,10.8 M3,14.6 L8,12.8" stroke={WOOD.dark} strokeWidth={1.8} />
      </g>
      {!taken && <Glow id={`${uid}ml`} x={-20} y={-12} r={7} color="#ffd34d" o={0.8} />}
      <Limbs segs={[{ d: "M-20,6 L-20,-9", w: 1.8 }]} c={WOOD} sw={1} shade={false} />
      <rect x={-22.5} y={-14} width={5} height={5.5} rx={1.2} fill={taken ? "#6f6a5a" : "#ffd34d"} {...line(1.1)} />
      <IsoBox b={cart} c={metal} />
      <g fill="#3a3f47" {...line(1.1)}>
        <circle cx={lf(cart, 0.25, 0)[0]} cy={lf(cart, 0.25, 0)[1] + 0.5} r={2.3} />
        <circle cx={lf(cart, 0.8, 0)[0]} cy={lf(cart, 0.8, 0)[1] + 0.5} r={2.3} />
      </g>
      {taken ? (
        <polygon points={P(cart.x - 6.5, ct, cart.x, ct - 3.2, cart.x + 6.5, ct, cart.x, ct + 3.2)} fill="#2a2a30" {...line(1)} />
      ) : (
        <g fill={GOLD.base} {...line(1)}>
          <circle cx={cart.x - 4} cy={ct - 0.5} r={2.6} />
          <circle cx={cart.x + 3.5} cy={ct - 0.5} r={2.6} />
          <circle cx={cart.x} cy={ct - 2.5} r={3} />
          <circle cx={cart.x - 1} cy={ct + 1.6} r={2.2} />
          <Glint x={cart.x - 1} y={ct - 8} s={2.8} c="#fff6c8" />
          <Glint x={cart.x + 7} y={ct - 4} s={2} c="#fff6c8" />
        </g>
      )}
    </g>
  );
}

export function MapObjectArt({ kind, variant, level = 1, taken = false, faction = "dawn", style }: {
  kind: string; variant?: string; level?: number; taken?: boolean; faction?: Faction; style?: string | null;
}): JSX.Element {
  const uid = useUid();
  const painted = objectPng(kind, variant, level, taken, style);
  if (painted) return painted;
  switch (kind) {
    case "chest":
      return <g transform="scale(1.15)"><ChestArt taken={taken} /></g>;
    case "well":
      return <WellArt taken={taken} uid={uid} />;
    case "artifact":
      return <ArtifactArt variant={variant} taken={taken} uid={uid} />;
    case "tribune":
      return <TribuneArt taken={taken} faction={faction} />;
    case "reinforce":
      return <ReinforceArt taken={taken} faction={faction} />;
    case "market":
      return <MarketArt taken={taken} />;
    case "camp":
      return <CampArt level={level} taken={taken} uid={uid} />;
    case "mine":
      return <MineArt taken={taken} uid={uid} />;
    default:
      return <ArtifactArt taken={taken} uid={uid} />;
  }
}

/* ───────────────────────── hero ───────────────────────── */

type HeadKind = "plume" | "horned" | "laurel" | "hood" | "crystal";
type HeroLook = {
  horse: Pal; mane: Pal; armor: Pal; cape: Pal; barding: Pal; trim: Pal; head: HeadKind; eye: string; aura?: string; armband?: boolean;
};

function heroLook(faction: Faction, skin?: string): HeroLook {
  const dawn = faction === "dawn";
  const barding = FACTION_CLOTH[faction];
  switch (skin) {
    case "gold":
      return {
        horse: pal("#f6f1e6", 0.26, 0.5), mane: pal("#e2b13c"), armor: pal("#f2bf2e", 0.32, 0.5), cape: dawn ? pal("#3aa0ff") : pal("#b3202f"),
        barding: pal("#f2bf2e", 0.32, 0.5), trim: pal("#ffffff", 0.2, 0.2), head: "laurel", eye: OL, armband: true,
      };
    case "shadow":
      return {
        horse: pal("#2b2533", 0.4, 0.22), mane: pal("#8a4dff", 0.35, 0.4), armor: pal("#3b2a55", 0.4, 0.28), cape: pal("#24183a", 0.4, 0.25),
        barding: pal("#4a2a7a", 0.36, 0.3), trim: pal("#b07bff"), head: "hood", eye: "#c58bff", aura: "#9a4dff",
      };
    case "ember":
      return {
        horse: pal("#3a2622", 0.4, 0.25), mane: pal("#ff7a1a", 0.34, 0.45), armor: pal("#b3202f", 0.34, 0.36), cape: pal("#7a1420", 0.36, 0.3),
        barding: pal("#ff9a2e", 0.32, 0.45), trim: GOLD, head: "hood", eye: "#ffb347", aura: "#ff7a1a",
      };
    case "mage":
      return {
        horse: dawn ? pal("#f3ead8", 0.26, 0.5) : pal("#4a3b40", 0.4, 0.25), mane: pal("#6c8cff", 0.34, 0.4),
        armor: dawn ? pal("#3d5fd6", 0.34, 0.36) : pal("#5a2a6a", 0.36, 0.3), cape: dawn ? pal("#2a3f9a", 0.36, 0.3) : pal("#3a1a4a", 0.36, 0.3),
        barding, trim: GOLD, head: "hood", eye: "#bfe0ff", aura: dawn ? "#8fb8ff" : "#c06bff",
      };
    case "grove":
    case "ranger":
      return {
        horse: pal("#8a5a34", 0.34, 0.36), mane: pal("#4a3218", 0.36, 0.3), armor: pal("#4f8a3a", 0.34, 0.4), cape: pal("#2f6a2a", 0.36, 0.34),
        barding: skin === "grove" ? pal("#6fbf4a", 0.32, 0.45) : barding, trim: pal("#c9a46a"), head: "hood", eye: OL,
        aura: skin === "grove" ? "#9fe86a" : undefined,
      };
    case "night":
      return {
        horse: pal("#26242c", 0.4, 0.22), mane: pal("#cfd6e0", 0.3, 0.45), armor: pal("#2e3138", 0.4, 0.26), cape: pal("#15161b", 0.4, 0.22),
        barding: pal("#3a3f4a", 0.36, 0.3), trim: pal("#cfd6e0"), head: "hood", eye: "#d6e4ff", aura: "#a9b8d6",
      };
    case "frost":
      return {
        horse: pal("#dfe9f3", 0.28, 0.5), mane: pal("#9fd3ff", 0.3, 0.45), armor: pal("#bfe6ff", 0.3, 0.5), cape: pal("#5fb8ee", 0.32, 0.4),
        barding: pal("#7cc8f0", 0.32, 0.45), trim: pal("#ffffff", 0.2, 0.2), head: "crystal", eye: "#2a6fb0", aura: "#bfe9ff",
      };
    default:
      return dawn
        ? {
            horse: pal("#f3ead8", 0.26, 0.5), mane: pal("#d9a441"), armor: pal("#e6ecf4", 0.3, 0.5), cape: pal("#4fb3ff", 0.32, 0.4),
            barding: barding, trim: GOLD, head: "plume", eye: OL,
          }
        : {
            horse: pal("#4a3b40", 0.4, 0.25), mane: pal("#c2321f", 0.34, 0.36), armor: pal("#4b4558", 0.38, 0.3), cape: pal("#b3202f", 0.34, 0.36),
            barding: barding, trim: pal("#d8323a"), head: "horned", eye: "#ff5a2a",
          };
  }
}

function HeroHead({ look }: { look: HeroLook }) {
  const a = look.armor;
  const skinTone = "#f1c69b";
  switch (look.head) {
    case "hood":
      return (
        <g>
          <Cel d="M-7,-41 Q-9,-53 -1,-55 Q6,-53 5,-43 L3,-41 Z" dd="M1,-54.6 Q6,-53 5,-43 L3,-41 L1,-41 Q4,-48 1,-54.6 Z" c={look.cape} sw={1.5} />
          <ellipse cx={0} cy={-46} rx={3.4} ry={3.8} fill="#120a1c" />
          <circle cx={-1.2} cy={-46.5} r={0.9} fill={look.eye} />
          <circle cx={1.6} cy={-46.5} r={0.9} fill={look.eye} />
          <circle cx={0.2} cy={-46.5} r={4} fill={look.eye} opacity={0.18} />
        </g>
      );
    case "laurel":
      return (
        <g>
          <circle cx={-1} cy={-46} r={4.6} fill={skinTone} {...line(1.4)} />
          <path d="M-5.6,-46 Q-6,-51.5 -1,-51.6 Q4,-51.5 3.6,-46.5 Q1,-49 -5.6,-46 Z" fill="#b8742a" {...line(1.1)} />
          {[-5.6, -4.2, -2.4, -0.4, 1.6, 3.2].map((lx, i) => (
            <ellipse key={lx} cx={lx} cy={-49.5 + Math.abs(i - 2.5) * 0.9} rx={1.5} ry={0.8} transform={`rotate(${-30 + i * 12} ${lx} ${-49.5 + Math.abs(i - 2.5) * 0.9})`} fill="#7cc242" {...line(0.7)} />
          ))}
          <circle cx={1.6} cy={-46.4} r={0.7} fill={OL} />
        </g>
      );
    case "crystal":
      return (
        <g>
          <circle cx={-1} cy={-46} r={4.6} fill={skinTone} {...line(1.4)} />
          <polygon points={P(-5, -50, -6, -58, -3, -52)} fill={a.light} {...line(1)} />
          <polygon points={P(-2, -52, -1, -62, 1.5, -52)} fill="#e6f8ff" {...line(1)} />
          <polygon points={P(2, -51, 5, -57, 4, -49)} fill={a.light} {...line(1)} />
          <Cel d="M-6,-45 Q-6.5,-53 -1,-53 Q4.5,-53 4,-45 L4,-43.5 L-6,-43.5 Z" dd="M1,-52.8 Q4.5,-53 4,-45 L4,-43.5 L1.5,-43.5 Z" c={a} sw={1.4} />
          <path d="M-0.5,-47 L4,-47" stroke="#2a6fb0" strokeWidth={1.4} strokeLinecap="round" />
        </g>
      );
    case "horned":
      return (
        <g>
          <path d="M-5,-50 Q-11,-52 -10,-58 Q-8,-54 -4,-53 Z" fill="#e9dcc0" {...line(1.1)} />
          <path d="M3,-50 Q8,-53 7,-58 Q5.5,-54 2,-53 Z" fill="#e9dcc0" {...line(1.1)} />
          <Cel d="M-6,-44 Q-6.5,-53 -1,-53 Q4.5,-53 4,-44 L4,-42 L-6,-42 Z" dd="M1,-52.8 Q4.5,-53 4,-44 L4,-42 L1.5,-42 Z" c={a} sw={1.4} />
          <path d="M-0.5,-47 L4,-47" stroke={look.eye} strokeWidth={1.5} strokeLinecap="round" />
        </g>
      );
    default:
      return (
        <g>
          <path d="M-1,-53 Q-7,-61 -14,-56 Q-8,-56 -5,-51 Z" fill={look.trim.base} {...line(1.2)} />
          <path d="M-2,-53 Q-8,-58 -12,-56" fill="none" stroke={look.trim.light} strokeWidth={1} strokeLinecap="round" />
          <Cel d="M-6,-44 Q-6.5,-53 -1,-53 Q4.5,-53 4,-44 L4,-42 L-6,-42 Z" dd="M1,-52.8 Q4.5,-53 4,-44 L4,-42 L1.5,-42 Z" c={a} sw={1.4} />
          <path d="M-0.5,-47 L4,-47" stroke={OL} strokeWidth={1.4} strokeLinecap="round" />
          <path d="M-1,-53 L-1,-42" stroke={look.trim.base} strokeWidth={1.2} />
        </g>
      );
  }
}

export function HeroArt({ faction, skin, heroClass = "knight", rival = false }: {
  faction: Faction; skin?: string; heroClass?: string; rival?: boolean;
}): JSX.Element {
  const uid = useUid();
  const skinned = skin && skin !== "default";
  // A skin's painting, else the class's (per faction), else the faction's knight.
  const keys = skinned ? [`objects/hero_${skin}`] : heroClass === "knight" ? [`objects/hero_${faction}`] : [`objects/hero_${heroClass}_${faction}`];
  const heroKey = keys.find((k) => pngArt(k));
  // Taller paintings get a little narrower, so every rider stands about the same height.
  if (heroKey) return <Png k={heroKey} w={46 / Math.sqrt(Math.max(1, pngRatio(heroKey) / 1.025))} foot={8} flip={rival} />;
  const look = heroLook(faction, skinned ? skin : heroClass === "knight" ? undefined : heroClass);
  const { horse, mane, armor, cape, barding, trim } = look;
  const farHorse = darken(horse, 0.2);
  const banner = FACTION_CLOTH[faction];
  return (
    <g>
      <Shadow rx={22} ry={9} y={2} />
      {rival && (
        <g>
          <ellipse cx={0} cy={2} rx={25} ry={11.5} fill="none" stroke="#ff2d3d" strokeWidth={5} opacity={0.3} />
          <ellipse cx={0} cy={2} rx={25} ry={11.5} fill="none" stroke="#ff2d3d" strokeWidth={2.2} />
        </g>
      )}
      {look.aura && <Glow id={`${uid}au`} x={0} y={-32} r={30} ry={36} color={look.aura} o={0.45} pulse />}
      {/* far legs */}
      <Limbs segs={[{ d: "M-6,-16 L-6,-7 L-4,-1", w: 3.6 }, { d: "M12,-16 L14,-8 L15,-1", w: 3.6 }]} c={farHorse} sw={1.4} />
      {/* tail */}
      <Limbs segs={[{ d: "M-14,-22 Q-22,-20 -20,-6", w: 4.2 }]} c={mane} sw={1.4} />
      {/* body */}
      <Blob x={0} y={-20} r={15} ry={8.4} c={horse} sw={1.8} />
      {/* neck + head */}
      <Cel d="M5,-26 L13,-40 L20,-38 L15,-21 Z" dd="M16,-38.6 L20,-38 L15,-21 L12,-22 Z" c={horse} sw={1.6} />
      <Cel
        d="M12.5,-42 Q15.5,-47 20,-44 L27.5,-35.5 Q28.6,-31 24.4,-31 L17,-34 Q12.5,-36 12.5,-42 Z"
        dd="M27.5,-35.5 Q28.6,-31 24.4,-31 L19,-33 Q24,-33 27.5,-35.5 Z"
        c={horse}
        sw={1.6}
      />
      <polygon points={P(14.5, -43, 14.6, -49, 18, -44.5)} fill={horse.base} {...line(1.3)} />
      <circle cx={18.4} cy={-40} r={1.1} fill={look.eye === OL ? OL : look.eye} />
      {look.aura && look.head === "hood" && <circle cx={18.4} cy={-40} r={2.6} fill={look.eye} opacity={0.35} />}
      <circle cx={25.2} cy={-33} r={0.6} fill={OL} />
      <path d="M13,-38 L19,-37 L24,-33" fill="none" stroke={trim.base} strokeWidth={1.1} />
      {/* mane */}
      <Cel d="M12.5,-45 Q8,-41 7,-35 Q5.4,-30 3.6,-25.6 L8,-27.6 Q9,-33 13.5,-38 Z" c={mane} sw={1.3} />
      {/* near legs */}
      <Limbs segs={[{ d: "M-10,-16 L-12,-7 L-11,0", w: 4 }, { d: "M9,-16 L10,-7 L11,0", w: 4 }]} c={horse} sw={1.5} />
      <g fill="#2b2230">
        <ellipse cx={-11} cy={0.6} rx={2.6} ry={1.4} />
        <ellipse cx={11} cy={0.6} rx={2.6} ry={1.4} />
      </g>
      {/* saddle cloth */}
      <Cel d="M-9,-27 L5,-27 L6,-15 Q-2,-12 -10,-15 Z" dd="M1,-27 L5,-27 L6,-15 Q3,-13.6 1,-13.4 Z" c={barding} sw={1.4} />
      <path d="M-10,-15.6 Q-2,-12.4 6,-15.6" fill="none" stroke={trim.base} strokeWidth={1.6} />
      {/* cape */}
      <Cel d="M-4,-41 Q-14,-37 -18,-22 Q-12,-25 -6,-23.5 Z" dd="M-10.4,-31 Q-14,-26 -18,-22 Q-12,-25 -6,-23.5 L-7,-28 Z" c={cape} sw={1.4} />
      {/* rider */}
      <Limbs segs={[{ d: "M-1,-26 L2.5,-19 L1.5,-13", w: 4.2 }]} c={armor} sw={1.4} />
      <ellipse cx={1.6} cy={-12.6} rx={2.8} ry={1.6} fill="#2b2230" {...line(1)} />
      <Cel d="M-6,-26 L4,-26 L3,-40 Q-1,-43.5 -5,-40 Z" dd="M0.5,-42 Q2,-41.6 3,-40 L4,-26 L0.5,-26 Z" c={armor} sw={1.5} />
      <path d="M-6,-29 L4,-29" stroke={trim.base} strokeWidth={1.8} />
      <HeroHead look={look} />
      {/* banner */}
      <Limbs segs={[{ d: "M7,-16 L7,-72", w: 2 }]} c={pal("#8a5a34")} sw={1.2} shade={false} />
      <polygon points={P(7, -78, 5.4, -72.5, 8.6, -72.5)} fill={trim.base} {...line(1)} />
      <Cel
        d="M7,-71 Q16,-74 26,-69 L22,-62 L26,-54.5 Q16,-58.5 7,-55.5 Z"
        dd="M17,-72.4 Q22,-71.4 26,-69 L22,-62 L26,-54.5 Q21,-56.6 17,-57 Z"
        c={banner}
        sw={1.5}
      />
      <path d="M7,-69 Q16,-72 25,-67.4" fill="none" stroke={trim.base} strokeWidth={1.3} />
      <Emblem kind={faction} x={14.5} y={-63} r={4.4} />
      {/* near arm */}
      <circle cx={-1} cy={-39} r={3.2} fill={armor.light} {...line(1.3)} />
      <Limbs segs={[{ d: "M0,-38 L4,-33 L7,-35", w: 3.4 }]} c={armor} sw={1.3} />
      {look.armband && <path d="M1.6,-36.6 L3.4,-34.2" stroke="#ffd23f" strokeWidth={3.2} />}
      <circle cx={7} cy={-35} r={2.1} fill={armor.dark} {...line(1.1)} />
      {skin === "gold" && <Glint x={-7} y={-36} s={2.6} c="#fff6c8" />}
      {skin === "frost" && <Glint x={-4} y={-30} s={2.4} />}
    </g>
  );
}

/* ───────────────────────── castle ───────────────────────── */

type CastleLook = { stone: Pal; roof: Pal; window: string; ember: boolean; banner: Pal; emblem: Faction; trim: Pal };

function castleLook(faction: Faction, rival: boolean): CastleLook {
  const base: CastleLook =
    faction === "dawn"
      ? { stone: pal("#efe9dc", 0.28, 0.5), roof: pal("#f2b92b", 0.32, 0.45), window: "#3b6ea8", ember: false, banner: FACTION_CLOTH.dawn, emblem: "dawn", trim: GOLD }
      : { stone: pal("#4b4553", 0.4, 0.28), roof: pal("#8e1f2e", 0.36, 0.34), window: "#ff8a24", ember: true, banner: FACTION_CLOTH.ash, emblem: "ash", trim: pal("#d8323a") };
  if (!rival) return base;
  return { ...base, stone: darken(base.stone, 0.18), roof: darken(base.roof, 0.18), banner: pal("#d7263d", 0.32, 0.38) };
}

function Window({ d, look }: { d: string; look: CastleLook }) {
  return (
    <g>
      {look.ember && <path d={d} fill="#ff6a1a" opacity={0.45} stroke="#ff6a1a" strokeWidth={3} />}
      <path d={d} fill={look.window} {...line(1.1)} />
    </g>
  );
}

function Tower({ x, y, r, h, look, roofH, pennant = true }: { x: number; y: number; r: number; h: number; look: CastleLook; roofH: number; pennant?: boolean }) {
  const t = y - h;
  const rr = r + 2;
  return (
    <g>
      <IsoCyl x={x} y={y} r={r} h={h} c={look.stone} />
      <Window d={`M${x - 2},${t + 13} L${x - 2},${t + 8.5} Q${x - 0.5},${t + 6} ${x + 1},${t + 8.5} L${x + 1},${t + 13} Z`} look={look} />
      {pennant && <Flag x={x} y={t - roofH + 2} h={7} c={look.banner} w={7} fh={4} />}
      <Cone x={x} y={t + 1} r={rr} ry={rr / 2} h={roofH} c={look.roof} />
    </g>
  );
}

function Merlons({ a, b, n, c }: { a: Pt; b: Pt; n: number; c: Pal }) {
  return (
    <g>
      {Array.from({ length: n }, (_, i) => {
        const t = (i + 0.5) / n;
        return <IsoBox key={i} b={{ x: lerp(a[0], b[0], t), y: lerp(a[1], b[1], t), w: 2.4, d: 1.2, h: 3.2 }} c={c} sw={1.1} />;
      })}
    </g>
  );
}

/** The classic home castle; footprint fills the cell, top ≈ −92. */
function Fortress({ look }: { look: CastleLook }) {
  const block: Box = { x: 0, y: 4, w: 25, d: 12.5, h: 16 };
  const bt = block.y - block.h;
  const keep: Box = { x: 0, y: bt, w: 11, d: 5.5, h: 36 };
  const kt = keep.y - keep.h;
  const L: Pt = [block.x - block.w, bt];
  const F: Pt = [block.x, bt + block.d];
  const R: Pt = [block.x + block.w, bt];
  const K: Pt = [block.x, bt - block.d];
  return (
    <g>
      <Tower x={0} y={-8.5} r={6} h={26} look={look} roofH={14} />
      <IsoBox b={block} c={look.stone} />
      <polyline points={P(...lf(block, 0, 0.4), ...lf(block, 1, 0.4), ...rf(block, 1, 0.4))} fill="none" stroke={look.stone.dark} strokeWidth={1} />
      <Merlons a={L} b={K} n={4} c={look.stone} />
      <Merlons a={K} b={R} n={4} c={look.stone} />
      <IsoBox b={keep} c={look.stone} />
      <Window d={arch(lf, keep, 0.22, 0.42, 0.55, 0.75)} look={look} />
      <Window d={arch(lf, keep, 0.6, 0.8, 0.55, 0.75)} look={look} />
      <Window d={arch(rf, keep, 0.4, 0.6, 0.55, 0.75)} look={look} />
      <path
        d={`M${lf(keep, 0.35, 0.42).join(",")} L${lf(keep, 0.65, 0.42).join(",")} L${lf(keep, 0.65, 0.1).join(",")} L${lf(keep, 0.5, 0.02).join(",")} L${lf(keep, 0.35, 0.1).join(",")} Z`}
        fill={look.banner.base}
        {...line(1.2)}
      />
      <Emblem kind={look.emblem} x={lf(keep, 0.5, 0.27)[0]} y={lf(keep, 0.5, 0.27)[1]} r={2.6} />
      <Flag x={0} y={kt - 22} h={18} c={look.banner} w={16} fh={10} swallow emblem={look.emblem} />
      <Pyramid b={keep} h={24} c={look.roof} />
      <Merlons a={L} b={F} n={5} c={look.stone} />
      <Merlons a={F} b={R} n={5} c={look.stone} />
      <path d={arch(lf, block, 0.42, 0.66, 0, 0.62, 0.25)} fill="#2a1d2a" {...line(1.4)} />
      <path d={arch(lf, block, 0.42, 0.66, 0, 0.62, 0.25)} fill="none" stroke={look.trim.base} strokeWidth={1.2} transform="translate(0 -0.6)" />
      <g stroke={look.trim.dark} strokeWidth={0.9}>
        {[0.48, 0.54, 0.6].map((u) => (
          <line key={u} x1={lf(block, u, 0)[0]} y1={lf(block, u, 0)[1]} x2={lf(block, u, 0.6)[0]} y2={lf(block, u, 0.6)[1]} />
        ))}
      </g>
      <Window d={arch(rf, block, 0.3, 0.42, 0.45, 0.72)} look={look} />
      <Window d={arch(rf, block, 0.6, 0.72, 0.45, 0.72)} look={look} />
      <Tower x={-25} y={4} r={6.5} h={28} look={look} roofH={15} />
      <Tower x={25} y={4} r={6.5} h={28} look={look} roofH={15} />
      <Tower x={0} y={16.5} r={6.5} h={25} look={look} roofH={14} pennant={false} />
      {!look.ember && <Glint x={-8} y={kt - 10} s={2.6} c="#fff6c8" />}
    </g>
  );
}

function StadiumCastle({ look, uid }: { look: CastleLook; uid: string }) {
  const seat = look.banner;
  const top = -9;
  const masts: [number, number, number][] = [[-19, -18, -72], [19, -18, -72], [-22, -1.5, -58], [22, -1.5, -58]];
  const arches = [];
  for (let a = 20; a <= 160; a += 20) {
    const rad = (a * Math.PI) / 180;
    const px = 27 * Math.cos(rad) * 0.92;
    const py = 6 + 13 * Math.sin(rad) * 0.92;
    arches.push(<path key={a} d={`M${px - 2},${py - 1} L${px - 2},${py - 7} Q${px},${py - 10} ${px + 2},${py - 7} L${px + 2},${py - 1} Z`} fill={look.ember ? "#ff8a24" : "#2a3a5a"} {...line(1)} />);
  }
  const keep: Box = { x: 0, y: -16, w: 9, d: 4.5, h: 40 };
  return (
    <g>
      <IsoBox b={keep} c={look.stone} />
      <Window d={arch(lf, keep, 0.3, 0.7, 0.7, 0.85)} look={look} />
      <Flag x={0} y={keep.y - keep.h - 20} h={18} c={look.banner} w={15} fh={9} swallow emblem={look.emblem} />
      <Pyramid b={keep} h={20} c={look.roof} />
      <IsoCyl x={0} y={6} r={27} ry={13} h={15} c={look.stone} />
      {arches}
      <path d={`M-27,${6 - 9} A27,13 0 0 0 27,${6 - 9}`} fill="none" stroke={look.trim.base} strokeWidth={1.6} />
      <ellipse cx={0} cy={top} rx={23} ry={10.6} fill={seat.base} {...line(1.3)} />
      <ellipse cx={0} cy={top} rx={19.5} ry={8.8} fill={seat.dark} />
      <ellipse cx={0} cy={top + 0.4} rx={17} ry={7.6} fill="#3fae4a" {...line(1.2)} />
      <path d={`M-12,${top - 4.5} L12,${top + 5} M-6,${top - 6.6} L17,${top + 2.6} M-17,${top - 2} L6,${top + 7.2}`} stroke="#5fc85f" strokeWidth={2.6} opacity={0.6} />
      <g fill="none" stroke="#ffffff" strokeWidth={0.9}>
        <ellipse cx={0} cy={top + 0.4} rx={4} ry={1.9} />
        <path d={`M-6,${top - 6} L6,${top + 6.8}`} />
      </g>
      <circle cx={-1} cy={top + 1} r={1.2} fill="#ffffff" {...line(0.6)} />
      {masts.map(([mx, my, mt], i) => (
        <g key={i}>
          <Glow id={`${uid}fl${i}`} x={mx} y={mt + 2} r={12} color="#fff3b0" o={0.7} />
          <Limbs segs={[{ d: `M${mx},${my} L${mx},${mt + 4}`, w: 1.8 }]} c={pal("#9aa3ae")} sw={1.1} shade={false} />
          <rect x={mx - 5} y={mt - 1} width={10} height={6} rx={1} fill="#4a5058" {...line(1.1)} />
          <g fill="#fff7c2">
            {[-3, 0, 3].map((dx) => (
              <g key={dx}>
                <circle cx={mx + dx} cy={mt + 1} r={1} />
                <circle cx={mx + dx} cy={mt + 3.2} r={1} />
              </g>
            ))}
          </g>
        </g>
      ))}
      <Flag x={-27} y={-3} h={10} c={look.banner} w={7} fh={4} dir={-1} />
      <Flag x={27} y={-3} h={10} c={look.banner} w={7} fh={4} />
    </g>
  );
}

function IceCastle({ look }: { look: CastleLook }) {
  const ice = pal("#a8dcf7", 0.3, 0.5);
  const deep = pal("#7cc4ef", 0.32, 0.45);
  const plat: Box = { x: 0, y: 6, w: 27, d: 13.5, h: 7 };
  const pt = plat.y - plat.h;
  return (
    <g>
      <IsoBox b={plat} c={deep} />
      <path d="M-27,-1 Q-24,3 -20,2 Q-17,6 -13,5 Q-10,9 -6,8 Q-3,11 0,12.5" fill="none" stroke="#f4fbff" strokeWidth={2.2} strokeLinecap="round" />
      <Shard x={-13} y={pt - 6} w={5} h={46} c={ice} />
      <Shard x={13} y={pt - 6} w={5} h={42} c={ice} />
      <Flag x={0} y={pt - 76} h={14} c={look.banner} w={14} fh={8} swallow emblem={look.emblem} />
      <Shard x={0} y={pt - 1} w={9} h={76} c={ice} hb={0.66} />
      <g fill="#eafcff" {...line(1)}>
        <polygon points={P(-4.5, pt - 30, -2.5, pt - 34, -0.5, pt - 30, -2.5, pt - 26)} />
        <polygon points={P(-4.5, pt - 44, -2.5, pt - 48, -0.5, pt - 44, -2.5, pt - 40)} />
        <polygon points={P(3, pt - 35, 5, pt - 39, 7, pt - 35, 5, pt - 31)} fill={deep.base} />
      </g>
      <path d={arch(lf, { x: 0, y: pt + 5.5, w: 9, d: 4.5, h: 20 }, 0.25, 0.85, 0.05, 0.7, 0.2)} fill="#1f4a7a" {...line(1.3)} />
      <Shard x={-20} y={pt + 4} w={4} h={28} c={ice} />
      <Shard x={20} y={pt + 4} w={4} h={25} c={ice} />
      <Shard x={-8} y={pt + 10} w={3} h={15} c={ice} />
      <Shard x={9} y={pt + 10} w={3} h={13} c={ice} />
      <Glint x={-6} y={pt - 62} s={3} />
      <Glint x={-16} y={pt - 30} s={2.4} />
      <Glint x={17} y={pt - 14} s={2} />
    </g>
  );
}

function VolcanoCastle({ look, uid }: { look: CastleLook; uid: string }) {
  const rock = pal("#3b2f36", 0.4, 0.22);
  const top = -22;
  const bw = 31;
  const tw = 20;
  const base = 4;
  const L0: Pt = [-bw, base];
  const F0: Pt = [0, base + bw / 2];
  const R0: Pt = [bw, base];
  const L1: Pt = [-tw, top];
  const F1: Pt = [0, top + tw / 2];
  const R1: Pt = [tw, top];
  const lava = (d: string, k: string) => (
    <g key={k} fill="none" strokeLinecap="round">
      <path d={d} stroke="#ff5a14" strokeWidth={5} opacity={0.35} />
      <path d={d} stroke="#ff6a1a" strokeWidth={2.6} />
      <path d={d} stroke="#ffd04a" strokeWidth={1} />
    </g>
  );
  return (
    <g>
      <Glow id={`${uid}vg`} x={0} y={12} r={34} ry={12} color="#ff6a1a" o={0.6} pulse />
      <polygon points={P(...L0, ...F0, ...F1, ...L1)} fill={rock.base} {...line(1.8)} />
      <polygon points={P(...F0, ...R0, ...R1, ...F1)} fill={rock.dark} {...line(1.8)} />
      <polygon points={P(-tw, top, 0, top - tw / 2, tw, top, 0, top + tw / 2)} fill={rock.light} {...line(1.6)} />
      {lava(`M-12,${top + 6} Q-14,${top + 14} -19,${top + 18} T-22,${base + 4}`, "a")}
      {lava(`M-3,${top + 10} Q-6,${top + 20} -3,${top + 26} T-6,${base + 14}`, "b")}
      {lava(`M8,${top + 7} Q12,${top + 16} 16,${top + 21} T21,${base + 6}`, "c")}
      <ellipse cx={-6} cy={base + 13} rx={6} ry={2.4} fill="#ff8a24" {...line(1.2)} />
      <g transform={`translate(0 ${top}) scale(0.62)`}>
        <Fortress look={look} />
      </g>
      <g fill="#ffc23a">
        <circle cx={-24} cy={-14} r={1} />
        <circle cx={25} cy={-24} r={0.9} />
        <circle cx={-18} cy={-34} r={0.8} />
      </g>
    </g>
  );
}

export function CastleArt({ faction, skin, rival = false }: { faction: Faction; skin?: string; rival?: boolean }): JSX.Element {
  const uid = useUid();
  const castleKey = `objects/castle_${skin && skin !== "default" ? skin : faction}`;
  if (pngArt(castleKey)) return <Png k={castleKey} w={72} foot={12} flip={rival} />;
  const look = castleLook(faction, rival);
  let art: ReactNode;
  if (skin === "stadium") art = <StadiumCastle look={look} uid={uid} />;
  else if (skin === "ice") art = <IceCastle look={look} />;
  else if (skin === "volcano") art = <VolcanoCastle look={look} uid={uid} />;
  else art = <Fortress look={look} />;
  return (
    <g>
      <Shadow rx={31} ry={14} y={5} o={0.32} />
      {art}
    </g>
  );
}

/* ───────────────────────── HTML wrapper ───────────────────────── */

/** Shows a map-art fragment as a standalone icon (popups, lists). */
export function ArtIcon({ children, size = 48, className, tight = false }: { children: ReactNode; size?: number; className?: string; tight?: boolean }): JSX.Element {
  return (
    <svg viewBox={tight ? "-36 -62 72 76" : "-48 -100 96 112"} width={size} height={size} className={className} xmlns="http://www.w3.org/2000/svg">
      {children}
    </svg>
  );
}
