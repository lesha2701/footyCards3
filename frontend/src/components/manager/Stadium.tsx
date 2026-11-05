import type { ManagerLook } from "@/api/manager";

import { SymbolGlyph } from "./Emblem";
import { solidPaint } from "@/lib/emblemPaint";

const CSS = `
@keyframes stx-flicker { 0%,100% { opacity: .95 } 40% { opacity: .55 } 70% { opacity: .85 } }
@keyframes stx-smoke { 0% { transform: translateY(0) scale(1); opacity: .45 } 100% { transform: translateY(-26px) scale(1.8); opacity: 0 } }
@keyframes stx-sweep { 0%,100% { transform: rotate(-14deg) } 50% { transform: rotate(14deg) } }
@keyframes stx-fall { 0% { transform: translateY(-20px) rotate(0) } 100% { transform: translateY(120px) rotate(320deg) } }
@keyframes stx-wave { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-2px) } }
.stx-flare { animation: stx-flicker .9s infinite; }
.stx-smoke { animation: stx-smoke 2.4s infinite ease-out; transform-box: fill-box; transform-origin: center; }
.stx-beam { animation: stx-sweep 5s infinite ease-in-out; transform-box: fill-box; transform-origin: bottom center; }
.stx-fall { animation: stx-fall 3.2s infinite linear; }
.stx-wave { animation: stx-wave 1.6s infinite ease-in-out; }
@media (prefers-reduced-motion: reduce) { .stx-flare, .stx-smoke, .stx-beam, .stx-fall, .stx-wave { animation: none; } }
`;

/** Deterministic pseudo-random in [0, 1) — the crowd looks the same on every render. */
function rnd(i: number): number {
  const x = Math.sin(i * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

const CROWD = Array.from({ length: 120 }, (_, i) => ({
  x: 8 + (i % 40) * 7.8 + rnd(i) * 3,
  y: 36 + Math.floor(i / 40) * 12 + rnd(i + 99) * 3,
  tone: rnd(i + 7),
}));

/** The club's stands with the «Стиль» stadium skin: classic, banners,
 * flares, lights, confetti or a tifo in the club colours. Cosmetic only. */
export default function Stadium({ look, height, label }: { look: ManagerLook; height?: number; label?: string }) {
  const skin = look.stands ?? "classic";
  const a = solidPaint(look.color);
  const b = solidPaint(look.color2);
  return (
    <svg viewBox="0 0 320 112" width="100%" height={height} preserveAspectRatio="xMidYMid meet" role="img"
      style={height ? undefined : { aspectRatio: "320 / 112" }}
      aria-label={label ?? `Трибуны: ${skin}`} className="block rounded-xl" data-testid="stadium" data-skin={skin}>
      <style>{CSS}</style>
      <defs>
        <linearGradient id="stx-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0b1020" />
          <stop offset="1" stopColor="#1c2a3d" />
        </linearGradient>
        <linearGradient id="stx-beam" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff7c2" stopOpacity=".75" />
          <stop offset="1" stopColor="#fff7c2" stopOpacity="0" />
        </linearGradient>
        <radialGradient id="stx-glow">
          <stop offset="0" stopColor="#ffb347" stopOpacity=".9" />
          <stop offset="1" stopColor="#ff3d00" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="320" height="112" fill="url(#stx-sky)" />
      {skin === "lights" && [40, 160, 280].map((x, i) => (
        <polygon key={x} className="stx-beam" style={{ animationDelay: `${i * -1.3}s` }} points={`${x - 4},30 ${x + 4},30 ${x + 40},-10 ${x - 40},-10`}
          fill="url(#stx-beam)" />
      ))}
      {/* the stand */}
      <polygon points="0,28 320,28 320,80 0,80" fill="#1a2232" />
      <polygon points="0,28 320,28 320,32 0,32" fill={a} />
      {skin === "tifo" ? (
        <g>
          <rect x="6" y="33" width="154" height="44" fill={a} />
          <rect x="160" y="33" width="154" height="44" fill={b} />
          <circle cx="160" cy="55" r="17" fill={b} stroke={a} strokeWidth="4" />
          <SymbolGlyph symbol={look.symbol} fill={a} cx={160} cy={55} size={22} />
        </g>
      ) : (
        CROWD.map((p, i) => (
          <circle key={i} className={skin === "confetti" || skin === "flares" ? "stx-wave" : undefined}
            style={skin === "confetti" || skin === "flares" ? { animationDelay: `${(i % 9) * -0.18}s` } : undefined}
            cx={p.x} cy={p.y} r="2.6" fill={p.tone < 0.45 ? a : p.tone < 0.75 ? b : "#cbd5e1"} opacity={0.85} />
        ))
      )}
      {skin === "banners" && [24, 78, 132, 188, 242, 296].map((x, i) => (
        <g key={x} className="stx-wave" style={{ animationDelay: `${i * -0.3}s` }}>
          <rect x={x - 16} y="62" width="32" height="16" rx="2" fill={i % 2 ? a : b} />
          <rect x={x - 16} y="68" width="32" height="4" fill={i % 2 ? b : a} />
        </g>
      ))}
      {skin === "flares" && [30, 110, 205, 290].map((x, i) => (
        <g key={x}>
          <circle className="stx-smoke" style={{ animationDelay: `${i * -0.6}s` }} cx={x} cy="40" r="9" fill="#9ca3af" opacity=".4" />
          <circle className="stx-flare" style={{ animationDelay: `${i * -0.2}s` }} cx={x} cy="50" r="14" fill="url(#stx-glow)" />
          <circle cx={x} cy="51" r="2.5" fill="#fff4d6" />
        </g>
      ))}
      {skin === "confetti" && Array.from({ length: 26 }, (_, i) => (
        <rect key={i} className="stx-fall" style={{ animationDelay: `${-rnd(i + 3) * 3.2}s` }} x={rnd(i) * 316} y={0} width="4" height="2.5"
          fill={[a, b, "#facc15", "#f472b6", "#38bdf8"][i % 5]} />
      ))}
      {/* the pitch */}
      <rect y="80" width="320" height="32" fill="#1f7a3f" />
      {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => <rect key={i} x={i * 40} y="80" width="20" height="32" fill="#22863f" />)}
      <line x1="0" y1="84" x2="320" y2="84" stroke="#e5f5e9" strokeOpacity=".7" strokeWidth="1.2" />
      <line x1="160" y1="84" x2="160" y2="112" stroke="#e5f5e9" strokeOpacity=".6" strokeWidth="1.2" />
      <ellipse cx="160" cy="112" rx="26" ry="14" fill="none" stroke="#e5f5e9" strokeOpacity=".6" strokeWidth="1.2" />
    </svg>
  );
}
