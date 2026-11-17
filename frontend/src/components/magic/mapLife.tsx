// Cheap ambient life for the adventure map: CSS keyframe animations only
// (no JS timers), all switched off under prefers-reduced-motion.
import type { CSSProperties } from "react";

import type { MagicBiome } from "@/types";

const CSS = `
.mm-sway { transform-box: fill-box; transform-origin: 50% 100%; animation: mm-sway 4.6s ease-in-out infinite; }
@keyframes mm-sway { 0%, 100% { transform: rotate(-1.4deg) skewX(0.6deg); } 50% { transform: rotate(1.4deg) skewX(-0.6deg); } }
.mm-smoke { transform-box: fill-box; transform-origin: 50% 50%; opacity: 0; animation: mm-smoke 3.6s ease-out infinite; }
@keyframes mm-smoke { 0% { transform: translate(0, 0) scale(0.5); opacity: 0; } 20% { opacity: 0.5; } 100% { transform: translate(7px, -28px) scale(1.7); opacity: 0; } }
.mm-glint { transform-box: fill-box; transform-origin: 50% 50%; opacity: 0; animation: mm-glint 4s ease-in-out infinite; }
@keyframes mm-glint { 0%, 62%, 100% { opacity: 0; transform: scale(0.3); } 76% { opacity: 0.95; transform: scale(1); } }
.mm-flag { transform-box: fill-box; transform-origin: 0% 50%; animation: mm-flag 1.5s ease-in-out infinite; }
@keyframes mm-flag { 0%, 100% { transform: skewY(0deg) scaleX(1); } 50% { transform: skewY(-9deg) scaleX(0.84); } }
.mm-cloud { animation: mm-cloud 46s ease-in-out infinite alternate; }
@keyframes mm-cloud { from { transform: translateX(-70px); } to { transform: translateX(70px); } }
.mm-fly { animation: mm-fly 6s ease-in-out infinite; }
@keyframes mm-fly { 0%, 100% { transform: translate(0, 0); opacity: 0.1; } 25% { opacity: 0.95; } 50% { transform: translate(18px, -14px); opacity: 0.3; } 75% { transform: translate(-10px, -24px); opacity: 0.9; } }
.mm-fall { animation: mm-fall 11s linear infinite; }
@keyframes mm-fall { 0% { transform: translate(0, 0); } 50% { transform: translate(14px, calc(var(--fall) * 0.5)); } 100% { transform: translate(-6px, var(--fall)); } }
.mm-rise { animation: mm-rise 9s ease-out infinite; }
@keyframes mm-rise { 0% { transform: translate(0, 0); opacity: 0; } 10% { opacity: 0.95; } 100% { transform: translate(24px, calc(var(--fall) * -0.7)); opacity: 0; } }
.mm-dust { animation: mm-dust 12s ease-in-out infinite; }
@keyframes mm-dust { 0%, 100% { transform: translate(0, 0); opacity: 0; } 30%, 70% { opacity: 0.55; } 50% { transform: translate(70px, -16px); } }
/* Phones: an animation inside the map's SVG repaints the whole (huge) SVG layer
   every frame, which flickers on mid-range Android GPUs. Keep only the HTML
   particles (snow, sparks), which the compositor moves for free. */
@media (pointer: coarse) {
  .mm-sway, .mm-flag, .mm-cloud { animation: none !important; }
  .mm-smoke, .mm-glint { display: none !important; }
}
@media (prefers-reduced-motion: reduce) {
  .mm-sway, .mm-flag, .mm-cloud { animation: none !important; }
  .mm-smoke, .mm-glint, .mm-particles { display: none !important; }
}
`;

/** The keyframes for everything in this file (render once, anywhere). */
export function MapLifeStyle(): JSX.Element {
  return <style>{CSS}</style>;
}

/** De-synced animation start for a cell. */
const delay = (h: number, dur: number): CSSProperties => ({ animationDelay: `${-((h % 1000) / 1000) * dur}s` });

/** A tree that sways around its base. */
export function Sway({ seed, children }: { seed: number; children: JSX.Element }): JSX.Element {
  return <g className="mm-sway" style={{ ...delay(seed, 4.6), animationDuration: `${4 + (seed % 7) * 0.2}s` }}>{children}</g>;
}

/** Smoke curling up from a camp's fire (cell-local coordinates). */
export function CampSmoke({ seed }: { seed: number }): JSX.Element {
  return (
    <g pointerEvents="none">
      {[0, 1, 2].map((i) => (
        <circle key={i} className="mm-smoke" cx={-3 + i} cy={-24} r={4.5} fill="#d9d4cf"
          style={{ animationDelay: `${-(i * 1.2 + (seed % 10) * 0.11)}s` }} />
      ))}
    </g>
  );
}

/** A small waving pennant over a castle (cell-local coordinates). */
export function CastlePennant({ color, seed }: { color: string; seed: number }): JSX.Element {
  return (
    <g pointerEvents="none">
      <line x1={0} y1={-70} x2={0} y2={-96} stroke="#1b1222" strokeWidth={1.8} strokeLinecap="round" />
      <circle cx={0} cy={-97} r={1.8} fill="#fde68a" stroke="#1b1222" strokeWidth={0.8} />
      <path className="mm-flag" style={delay(seed, 1.5)} d="M1,-95 Q8,-93 15,-90 Q8,-87 1,-84 Z" fill={color} stroke="#1b1222" strokeWidth={1.2} strokeLinejoin="round" />
    </g>
  );
}

/** A sparkle glinting on water (map coordinates). */
export function WaterGlint({ x, y, seed, color }: { x: number; y: number; seed: number; color: string }): JSX.Element {
  const s = 3.2;
  return (
    <path className="mm-glint" style={{ ...delay(seed, 4), animationDuration: `${3.4 + (seed % 5) * 0.4}s` }} fill={color}
      d={`M${x},${y - s} Q${x},${y} ${x + s},${y} Q${x},${y} ${x},${y + s} Q${x},${y} ${x - s},${y} Q${x},${y} ${x},${y - s} Z`} />
  );
}

const STAR = "M0,-3.6 L1.06,-1.15 L3.42,-1.11 L1.7,0.62 L2.12,3.0 L0,1.8 L-2.12,3.0 L-1.7,0.62 L-3.42,-1.11 L-1.06,-1.15 Z";
const DANGER: Record<string, string> = { easy: "#22c55e", even: "#facc15", hard: "#ef4444" };

/** The camp's strength over its sprite: colour by danger, stars by level (cell-local coordinates). */
export function CampBadge({ level, danger }: { level: number; danger?: string | null }): JSX.Element {
  const lv = Math.min(3, Math.max(1, Math.round(level)));
  const fill = (danger && DANGER[danger]) || "#94a3b8";
  const stars: [number, number][] = lv === 1 ? [[0, 0]] : lv === 2 ? [[-3.6, 0.4], [3.6, 0.4]] : [[0, -3.2], [-3.9, 2.6], [3.9, 2.6]];
  return (
    <g transform="translate(17,-50)" pointerEvents="none">
      <circle r={10.5} fill="#1b1222" opacity={0.35} cy={1.5} />
      <circle r={10} fill={fill} stroke="#1b1222" strokeWidth={1.8} />
      <circle r={7.6} fill="none" stroke="#fff" strokeOpacity={0.45} strokeWidth={1} />
      {stars.map(([sx, sy], i) => (
        <path key={i} d={STAR} transform={`translate(${sx},${sy}) scale(${lv === 1 ? 1.35 : 1})`} fill="#fff" stroke="#1b1222" strokeWidth={0.7} strokeLinejoin="round" />
      ))}
    </g>
  );
}

/** A slow cloud drifting over the fog (HTML, map coordinates). */
export function Cloud({ x, y, seed }: { x: number; y: number; seed: number }): JSX.Element {
  const w = 150 + (seed % 5) * 30;
  return (
    <div className="mm-cloud pointer-events-none absolute" style={{
      left: x - w / 2, top: y - w * 0.2, width: w, height: w * 0.4, borderRadius: "50%",
      background: "radial-gradient(ellipse at 50% 50%, rgba(190,200,225,0.22) 0%, rgba(190,200,225,0.1) 45%, rgba(190,200,225,0) 70%)",
      ...delay(seed, 46), animationDuration: `${38 + (seed % 9) * 3}s`,
    }} />
  );
}

type Kind = { cls: string; color: string; size: [number, number]; dur: [number, number]; glow: boolean; from: "any" | "top" | "bottom" };
const PARTICLES: Record<MagicBiome, Kind> = {
  meadow: { cls: "mm-fly", color: "#fef08a", size: [2.5, 4], dur: [5, 9], glow: true, from: "any" },
  snow: { cls: "mm-fall", color: "#ffffff", size: [2.5, 5], dur: [9, 15], glow: false, from: "top" },
  ash: { cls: "mm-rise", color: "#fb923c", size: [2, 3.5], dur: [7, 11], glow: true, from: "bottom" },
  desert: { cls: "mm-dust", color: "#fde7b0", size: [1.5, 3], dur: [10, 16], glow: false, from: "any" },
};

/** A fixed handful of biome particles over the screen (fireflies, snow, embers, dust). */
export function AmbientParticles({ biome, height, count = 24 }: { biome: MagicBiome; height: number; count?: number }): JSX.Element {
  const k = PARTICLES[biome] ?? PARTICLES.meadow;
  const rnd = (i: number, s: number) => (((i + 1) * 2654435761 + s * 40503) % 10007) / 10007;
  return (
    <div className="mm-particles pointer-events-none absolute inset-0 overflow-hidden" style={{ "--fall": `${height + 30}px` } as CSSProperties}>
      {Array.from({ length: count }, (_, i) => {
        const size = k.size[0] + rnd(i, 1) * (k.size[1] - k.size[0]);
        const dur = k.dur[0] + rnd(i, 2) * (k.dur[1] - k.dur[0]);
        const top = k.from === "top" ? "-12px" : k.from === "bottom" ? "100%" : `${8 + rnd(i, 3) * 84}%`;
        return (
          <span key={i} className={`${k.cls} absolute rounded-full`} style={{
            left: `${rnd(i, 4) * 100}%`, top, width: size, height: size, background: k.color,
            opacity: k.from === "top" ? 0.5 + rnd(i, 5) * 0.4 : undefined,
            boxShadow: k.glow ? `0 0 ${size * 2.5}px ${size * 0.8}px ${k.color}` : undefined,
            animationDuration: `${dur}s`, animationDelay: `${-rnd(i, 6) * dur}s`,
          }} />
        );
      })}
    </div>
  );
}
