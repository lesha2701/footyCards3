import { useId } from "react";

/** Animated overlay over the whole «Мой игрок» card for the «Эффект»
 * cosmetic slot (codes from backend my_player_service.COSMETICS). SMIL
 * animations, so no extra CSS; pointer-events off. */
export default function CardEffect({ effect, className = "" }: { effect?: string | null; className?: string }) {
  const id = useId().replace(/:/g, "");
  if (!effect) return null;
  return (
    <svg
      viewBox="0 0 300 400"
      preserveAspectRatio="none"
      className={`pointer-events-none absolute inset-0 h-full w-full ${className}`}
      aria-hidden="true"
      data-testid={`card-effect-${effect}`}
    >
      {effect === "fx_sparkle" && <Sparkles />}
      {effect === "fx_fire" && <Fire id={id} />}
      {effect === "fx_lightning" && <Lightning id={id} />}
    </svg>
  );
}

const SPARKS = [
  [40, 60, 9, 0], [250, 48, 7, 0.6], [270, 170, 10, 1.2], [26, 210, 8, 0.3], [150, 26, 6, 1.6], [70, 330, 9, 0.9],
  [232, 300, 8, 1.9], [120, 120, 5, 2.3], [200, 368, 7, 0.4], [16, 360, 6, 1.4], [284, 380, 6, 2.1], [180, 90, 5, 2.6],
];

function Sparkles() {
  return (
    <g fill="#fff8d6">
      {SPARKS.map(([x, y, r, begin]) => (
        <path
          key={`${x}-${y}`}
          d={`M${x} ${y - r} Q${x} ${y} ${x + r} ${y} Q${x} ${y} ${x} ${y + r} Q${x} ${y} ${x - r} ${y} Q${x} ${y} ${x} ${y - r}Z`}
          opacity="0"
        >
          <animate attributeName="opacity" values="0;1;0" dur="2.4s" begin={`${begin}s`} repeatCount="indefinite" />
          <animateTransform
            attributeName="transform" type="rotate" from={`0 ${x} ${y}`} to={`90 ${x} ${y}`}
            dur="2.4s" begin={`${begin}s`} repeatCount="indefinite"
          />
        </path>
      ))}
    </g>
  );
}

const FLAMES = [
  [30, 46, 0], [80, 60, 0.35], [130, 52, 0.7], [170, 64, 0.15], [220, 54, 0.5], [270, 48, 0.85],
];

function Fire({ id }: { id: string }) {
  return (
    <>
      <defs>
        <radialGradient id={`flame${id}`} cx="50%" cy="80%" r="70%">
          <stop offset="0" stopColor="#fff7c2" stopOpacity="0.95" />
          <stop offset="0.35" stopColor="#fb923c" stopOpacity="0.8" />
          <stop offset="1" stopColor="#dc2626" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`heat${id}`} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#f97316" stopOpacity="0.45" />
          <stop offset="0.5" stopColor="#f97316" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="0" y="200" width="300" height="200" fill={`url(#heat${id})`} />
      {FLAMES.map(([x, h, begin]) => (
        <ellipse key={x} cx={x} cy="400" rx="34" ry={h} fill={`url(#flame${id})`}>
          <animate attributeName="ry" values={`${h};${h * 1.7};${h * 1.1};${h * 1.5};${h}`} dur="1.3s" begin={`${begin}s`} repeatCount="indefinite" />
          <animate attributeName="rx" values="34;28;36;30;34" dur="1.3s" begin={`${begin}s`} repeatCount="indefinite" />
        </ellipse>
      ))}
      {[[60, 0.2], [150, 0.9], [240, 0.5]].map(([x, begin]) => (
        <circle key={x} cx={x} cy="380" r="2.5" fill="#fde68a">
          <animate attributeName="cy" values="380;250" dur="1.8s" begin={`${begin}s`} repeatCount="indefinite" />
          <animate attributeName="opacity" values="1;0" dur="1.8s" begin={`${begin}s`} repeatCount="indefinite" />
        </circle>
      ))}
    </>
  );
}

function Lightning({ id }: { id: string }) {
  const bolt = (d: string, begin: string) => (
    <path d={d} fill="none" stroke="#e0f2fe" strokeWidth="3" strokeLinejoin="round" filter={`url(#glow${id})`} opacity="0">
      <animate attributeName="opacity" values="0;0;1;0.2;1;0;0" keyTimes="0;0.55;0.6;0.65;0.7;0.78;1" dur="3s" begin={begin} repeatCount="indefinite" />
    </path>
  );
  return (
    <>
      <defs>
        <filter id={`glow${id}`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect x="2" y="2" width="296" height="396" rx="16" fill="none" stroke="#38bdf8" strokeWidth="3" opacity="0.5">
        <animate attributeName="opacity" values="0.25;0.7;0.25" dur="1.6s" repeatCount="indefinite" />
      </rect>
      {bolt("M24 30 L44 92 L28 96 L56 170", "0s")}
      {bolt("M276 210 L254 268 L272 272 L240 352", "1.4s")}
      {bolt("M150 4 L138 40 L152 44 L136 80", "0.7s")}
    </>
  );
}
