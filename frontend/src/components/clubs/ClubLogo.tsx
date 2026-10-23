import { useId, type ReactNode } from "react";

import type { ClubEmblem, ClubLogoShape } from "@/types";

const SHAPE_PATHS: Record<ClubLogoShape, string> = {
  shield: "M50 5 L90 20 V50 C90 75 70 90 50 95 C30 90 10 75 10 50 V20 Z",
  circle: "M50 5 A45 45 0 1 1 49.99 5 Z",
  hexagon: "M50 5 L90 27.5 V72.5 L50 95 L10 72.5 V27.5 Z",
  star: "M50 5 L61 38 H96 L67 59 L78 92 L50 71 L22 92 L33 59 L4 38 H39 Z",
  diamond: "M50 5 L90 50 L50 95 L10 50 Z",
  banner: "M15 5 H85 V80 L50 65 L15 80 Z",
  crest: "M50 5 C70 5 88 15 88 35 C88 60 70 85 50 95 C30 85 12 60 12 35 C12 15 30 5 50 5 Z",
  chevron: "M10 30 L50 5 L90 30 L90 60 L50 35 L10 60 Z M10 65 L50 40 L90 65 L90 95 L50 70 L10 95 Z",
};

function starPath(cx: number, cy: number, points: number, outer: number, inner: number): string {
  const parts: string[] = [];
  for (let i = 0; i < points * 2; i++) {
    const r = i % 2 === 0 ? outer : inner;
    const a = (Math.PI * i) / points - Math.PI / 2;
    parts.push(`${i === 0 ? "M" : "L"}${(cx + r * Math.cos(a)).toFixed(1)} ${(cy + r * Math.sin(a)).toFixed(1)}`);
  }
  return `${parts.join(" ")} Z`;
}

const LION_MANE = starPath(50, 50, 14, 21, 15);
const STAR = starPath(50, 51, 5, 21, 9);
const SUNBURST = Array.from({ length: 12 }, (_, i) => {
  const a = (Math.PI * 2 * i) / 12;
  const b = a + Math.PI / 12;
  const p = (t: number) => `${(50 + 90 * Math.cos(t)).toFixed(1)} ${(50 + 90 * Math.sin(t)).toFixed(1)}`;
  return `M50 50 L${p(a)} L${p(b)} Z`;
}).join(" ");

/** `hex` lighter (amount > 0) or darker (< 0), amount in -1…1; non-hex colours pass through. */
function shade(hex: string, amount: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const mix = (c: number) => Math.round(amount >= 0 ? c + (255 - c) * amount : c * (1 + amount));
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(mix);
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

/** Patterns, drawn in the second colour (or a light overlay) and clipped to the shape. */
function Pattern({ kind, fill }: { kind: string; fill: string }) {
  switch (kind) {
    case "stripes":
      return <g fill={fill}>{[18, 38, 58, 78].map((x) => <rect key={x} x={x} y={0} width={10} height={100} />)}</g>;
    case "hoops":
      return <g fill={fill}>{[14, 36, 58, 80].map((y) => <rect key={y} x={0} y={y} width={100} height={11} />)}</g>;
    case "halves":
      return <rect x={50} y={0} width={50} height={100} fill={fill} />;
    case "quarters":
      return <g fill={fill}><rect x={50} y={0} width={50} height={50} /><rect x={0} y={50} width={50} height={50} /></g>;
    case "sash":
      return <path d="M-5 25 L25 -5 L105 75 L75 105 Z" fill={fill} />;
    case "checker": {
      const cells = [];
      for (let r = 0; r < 5; r++) for (let c = 0; c < 5; c++) if ((r + c) % 2 === 0) cells.push(<rect key={`${r}-${c}`} x={c * 20} y={r * 20} width={20} height={20} />);
      return <g fill={fill}>{cells}</g>;
    }
    case "chevron":
      return <path d="M0 40 L50 70 L100 40 L100 58 L50 88 L0 58 Z" fill={fill} />;
    case "diamonds":
      return (
        <g fill={fill}>
          {[[25, 25], [75, 25], [50, 50], [25, 75], [75, 75]].map(([x, y]) => (
            <path key={`${x}-${y}`} d={`M${x} ${y - 11} L${x + 11} ${y} L${x} ${y + 11} L${x - 11} ${y} Z`} />
          ))}
        </g>
      );
    case "sunburst":
      return <path d={SUNBURST} fill={fill} opacity={0.85} />;
    case "waves":
      return (
        <g fill="none" stroke={fill} strokeWidth={7}>
          {[22, 46, 70, 94].map((y) => (
            <path key={y} d={`M-5 ${y} Q 7.5 ${y - 9} 20 ${y} T 45 ${y} T 70 ${y} T 95 ${y} T 120 ${y}`} />
          ))}
        </g>
      );
    default:
      return null;
  }
}

/** Symbols in the middle, 100×100 space. `base` is the club colour (for cut-outs). */
function SymbolMark({ kind, fill, base, y = 0, scale = 1 }: { kind: string; fill: string; base: string; y?: number; scale?: number }) {
  const t = `translate(50 ${50 + y}) scale(${scale}) translate(-50 -50)`;
  const stroke = { stroke: "rgba(0,0,0,0.35)", strokeWidth: 1.5, strokeLinejoin: "round" as const };
  let body: JSX.Element | null = null;
  switch (kind) {
    case "ball":
      body = (
        <g>
          <circle cx={50} cy={50} r={17} fill={fill} {...stroke} />
          <path d="M50 42 L57.6 47.5 L54.7 56.5 L45.3 56.5 L42.4 47.5 Z" fill="#1b1b1b" />
          <path d="M50 42 V33.5 M57.6 47.5 L65.5 44.5 M54.7 56.5 L59.5 64 M45.3 56.5 L40.5 64 M42.4 47.5 L34.5 44.5" stroke="#1b1b1b" strokeWidth={1.6} />
        </g>
      );
      break;
    case "crown":
      body = (
        <g fill={fill} {...stroke}>
          <path d="M29 63 L29 39 L40 50 L50 32 L60 50 L71 39 L71 63 Z" />
          <rect x={29} y={65} width={42} height={6} rx={1.5} />
        </g>
      );
      break;
    case "lion":
      body = (
        <g>
          <path d={LION_MANE} fill={fill} {...stroke} />
          <circle cx={50} cy={51} r={11.5} fill={base} />
          <circle cx={45.5} cy={48} r={1.8} fill={fill} />
          <circle cx={54.5} cy={48} r={1.8} fill={fill} />
          <path d="M46.5 54 L50 57.5 L53.5 54 Z" fill={fill} />
        </g>
      );
      break;
    case "eagle":
      body = <path d="M50 34 L56 45 L76 37 L67 51 L58 54 L55 67 L50 63 L45 67 L42 54 L33 51 L24 37 L44 45 Z" fill={fill} {...stroke} />;
      break;
    case "lightning":
      body = <path d="M56 28 L37 55 L49 55 L43 74 L64 45 L52 45 Z" fill={fill} {...stroke} />;
      break;
    case "castle":
      body = (
        <path
          d="M32 70 V44 H37 V38 H42 V44 H47 V38 H53 V44 H58 V38 H63 V44 H68 V70 H57 V60 A7 7 0 0 0 43 60 V70 Z"
          fill={fill}
          {...stroke}
        />
      );
      break;
    case "star":
      body = <path d={STAR} fill={fill} {...stroke} />;
      break;
    case "trophy":
      body = (
        <g fill={fill} {...stroke}>
          <path d="M34 50 C26 50 24 36 33 36 M66 50 C74 50 76 36 67 36" fill="none" stroke={fill} strokeWidth={3.5} />
          <path d="M35 31 H65 V40 C65 52 58 59 50 59 C42 59 35 52 35 40 Z" />
          <rect x={46.5} y={58} width={7} height={7} />
          <rect x={38} y={65} width={24} height={6} rx={1.5} />
        </g>
      );
      break;
    case "wings":
      body = (
        <g fill={fill} {...stroke}>
          <path d="M47 52 C40 41 30 36 18 37 C24 41 27 43 29 46 C23 46 18 48 16 53 C24 52 29 53 32 55 C27 57 25 60 24 64 C33 62 41 58 47 55 Z" />
          <path d="M53 52 C60 41 70 36 82 37 C76 41 73 43 71 46 C77 46 82 48 84 53 C76 52 71 53 68 55 C73 57 75 60 76 64 C67 62 59 58 53 55 Z" />
          <circle cx={50} cy={53} r={5} />
        </g>
      );
      break;
    case "anchor":
      body = (
        <g fill="none" stroke={fill} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round">
          <circle cx={50} cy={31} r={4.5} />
          <path d="M50 36 V69 M40 44 H60 M31 56 C33 66 41 70 50 70 C59 70 67 66 69 56" />
          <path d="M27 58 L31 54 L35 59 M73 58 L69 54 L65 59" />
        </g>
      );
      break;
    case "wolf":
      body = (
        <g>
          <path d="M31 30 L39 44 L45 42 L50 46 L55 42 L61 44 L69 30 L69 52 L61 65 L50 72 L39 65 L31 52 Z" fill={fill} {...stroke} />
          <path d="M40 51 L46 53 L43 56 Z M60 51 L54 53 L57 56 Z" fill={base} />
          <path d="M46.5 62 L50 66 L53.5 62 Z" fill={base} />
        </g>
      );
      break;
    case "swords":
      body = (
        <g stroke={fill} strokeLinecap="round">
          <path d="M33 31 L65 63 M67 31 L35 63" strokeWidth={5} />
          <path d="M58 67 L69 56 M42 67 L31 56" strokeWidth={5} />
          <path d="M66 65 L71 70 M34 65 L29 70" strokeWidth={6} />
        </g>
      );
      break;
    default:
      return null;
  }
  return <g transform={t}>{body}</g>;
}

/** Outline gradients (top-left → bottom-right). */
const OUTLINE_STOPS: Record<string, string[]> = {
  gold: ["#FFF3B0", "#E6B422", "#8C6A12"],
  silver: ["#FFFFFF", "#C9CED6", "#7C838D"],
  bronze: ["#F6C99A", "#C97B3C", "#6E3F17"],
  neon: ["#7CFFEA", "#22E3FF", "#B14CFF"],
  ruby: ["#FFC1CF", "#E0115F", "#6E0A2C"],
  emerald: ["#C8FFE0", "#10B981", "#064E3B"],
  diamond: ["#FFFFFF", "#CFF4FF", "#8CC8F0", "#FFFFFF"],
  rainbow: ["#FF5E5E", "#FFC14D", "#5CE17C", "#45C8FF", "#A86BFF", "#FF5EC8"],
};
/** Outlines that animate (CSS in index.css) and the ones drawn with a glow. */
const OUTLINE_CLASS: Record<string, string> = { neon: "emblem-neon", diamond: "emblem-diamond", rainbow: "emblem-rainbow" };
const GLOW_OUTLINES = new Set(["neon", "diamond", "rainbow"]);

const SPARKLES: [number, number, number, string][] = [
  [18, 16, 5, "0s"], [84, 22, 4, "0.6s"], [80, 82, 5, "1.1s"], [14, 74, 4, "0.3s"], [50, 2, 3.5, "0.9s"],
];

function sparklePath(x: number, y: number, r: number): string {
  return `M${x} ${y - r} L${x + r * 0.28} ${y - r * 0.28} L${x + r} ${y} L${x + r * 0.28} ${y + r * 0.28} L${x} ${y + r} L${x - r * 0.28} ${y + r * 0.28} L${x - r} ${y} L${x - r * 0.28} ${y - r * 0.28} Z`;
}

/** Laurel leaves along an arc on the left; the right branch is its mirror. */
const LAUREL_LEAVES = Array.from({ length: 7 }, (_, i) => {
  const a = ((200 - i * 13) * Math.PI) / 180;
  const x = 50 + 56 * Math.cos(a);
  const y = 54 - 50 * Math.sin(a);
  const deg = (-(200 - i * 13) + 90 + 360) % 360;
  return { x, y, deg };
});

/** Effects drawn behind the badge (aura, rays, flames). */
function EffectBehind({ effect, uid, glow }: { effect: string | null | undefined; uid: string; glow: string }) {
  switch (effect) {
    case "flame":
      return (
        <g>
          <path className="emblem-flame" d="M22 48 C14 30 24 18 20 0 C34 12 38 24 34 40 Z" fill="#FF7A18" />
          <path className="emblem-flame-2" d="M42 30 C38 14 50 6 50 -8 C60 6 64 16 58 30 Z" fill="#FFB020" />
          <path className="emblem-flame" d="M78 48 C86 30 76 18 80 0 C66 12 62 24 66 40 Z" fill="#FF7A18" />
          <path className="emblem-flame-2" d="M28 42 C26 30 32 24 32 14 C40 24 40 32 38 42 Z" fill="#FFE066" />
          <path className="emblem-flame-2" d="M72 42 C74 30 68 24 68 14 C60 24 60 32 62 42 Z" fill="#FFE066" />
        </g>
      );
    case "aura":
      return (
        <g className="emblem-aura">
          <defs>
            <radialGradient id={`aura-${uid}`}>
              <stop offset="40%" stopColor={glow} stopOpacity="0.85" />
              <stop offset="100%" stopColor={glow} stopOpacity="0" />
            </radialGradient>
          </defs>
          <rect x={-16} y={-16} width={132} height={132} fill="none" />
          <circle cx={50} cy={50} r={60} fill={`url(#aura-${uid})`} />
        </g>
      );
    case "rays":
      return (
        <g className="emblem-rays" opacity={0.85}>
          <defs>
            <radialGradient id={`rays-${uid}`}>
              <stop offset="20%" stopColor="#FFF3B0" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#FFC93C" stopOpacity="0" />
            </radialGradient>
          </defs>
          <rect x={-16} y={-16} width={132} height={132} fill="none" />
          <path d={SUNBURST} fill={`url(#rays-${uid})`} transform="translate(50 50) scale(0.7) translate(-50 -50)" />
        </g>
      );
    case "laurel":
      return (
        <g>
          <defs>
            <linearGradient id={`laurel-${uid}`} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#FFF3B0" />
              <stop offset="60%" stopColor="#E6B422" />
              <stop offset="100%" stopColor="#8C6A12" />
            </linearGradient>
          </defs>
          {[1, -1].map((dir) => (
            <g key={dir} transform={dir === -1 ? "translate(100 0) scale(-1 1)" : undefined}>
              <path d="M30 96 C8 84 -2 56 8 26" fill="none" stroke={`url(#laurel-${uid})`} strokeWidth={2} />
              {LAUREL_LEAVES.map((l, i) => (
                <ellipse key={i} cx={l.x} cy={l.y} rx={7} ry={3} transform={`rotate(${l.deg} ${l.x} ${l.y})`}
                  fill={`url(#laurel-${uid})`} stroke="rgba(0,0,0,0.3)" strokeWidth={0.6} />
              ))}
            </g>
          ))}
        </g>
      );
    default:
      return null;
  }
}

/** Effects drawn over the badge (shine is inside the shape, see EmblemArt). */
function EffectFront({ effect, path }: { effect: string | null | undefined; path: string }) {
  switch (effect) {
    case "sparkle":
      return (
        <>
          {SPARKLES.map(([x, y, r, delay]) => (
            <path key={`${x}-${y}`} className="emblem-sparkle" style={{ animationDelay: delay }} d={sparklePath(x, y, r)} fill="#FFF6C2" />
          ))}
        </>
      );
    case "orbit":
      return (
        <g className="emblem-orbit">
          <rect x={-16} y={-16} width={132} height={132} fill="none" />
          <ellipse cx={50} cy={50} rx={58} ry={58} fill="none" stroke="#fff" strokeOpacity={0.18} strokeDasharray="2 5" />
          <g transform="translate(50 -8)">
            <circle r={6.5} fill="#fff" stroke="#1b1b1b" strokeWidth={1} />
            <path d="M0 -2.6 L2.5 -0.8 L1.5 2.1 L-1.5 2.1 L-2.5 -0.8 Z" fill="#1b1b1b" />
          </g>
          <circle cx={50} cy={108} r={3} fill="#C6E63A" />
        </g>
      );
    case "lightning":
      return (
        <g>
          <path d={path} fill="none" stroke="#9EF0FF" strokeWidth={2.5} strokeDasharray="7 9" strokeLinecap="round" className="emblem-electric" />
          <path className="emblem-bolt" d="M6 18 L14 30 L9 31 L17 46 L4 32 L9 31 Z" fill="#E6FBFF" stroke="#45C8FF" strokeWidth={1} />
          <path className="emblem-bolt" style={{ animationDelay: "0.35s" }} d="M94 52 L86 64 L91 65 L83 80 L96 66 L91 65 Z" fill="#E6FBFF" stroke="#45C8FF" strokeWidth={1} />
        </g>
      );
    default:
      return null;
  }
}

/** A club emblem in any shape: depth for every logo (gradient, gloss, a dark rim with a
 * light inner edge, a drop shadow) plus the optional layers — `inside` (patterns, clipped
 * to the shape), `mark` (symbol / letters / emoji on top), an outline and an effect.
 * Shared by the clubs (ClubLogo) and «Менеджер» (manager/Emblem). */
export function EmblemArt({
  path, color, size, inside, mark, outline, outlineThin, effect, glow,
}: {
  path: string; color: string; size: number; inside?: ReactNode; mark?: ReactNode;
  outline?: string | null; outlineThin?: boolean; effect?: string | null; glow?: string;
}) {
  const uid = useId().replace(/:/g, "");
  const stops = outline ? OUTLINE_STOPS[outline] : undefined;
  const outlineWidth = outlineThin ? 2.5 : 5;
  return (
    <svg width={size} height={size} viewBox="-8 -8 116 116" xmlns="http://www.w3.org/2000/svg" style={{ overflow: "visible" }}>
      <defs>
        <clipPath id={`clip-${uid}`}>
          <path d={path} />
        </clipPath>
        <linearGradient id={`base-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={shade(color, 0.22)} />
          <stop offset="55%" stopColor={color} />
          <stop offset="100%" stopColor={shade(color, -0.28)} />
        </linearGradient>
        <linearGradient id={`gloss-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.38" />
          <stop offset="100%" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`shadow-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#000" stopOpacity="0" />
          <stop offset="100%" stopColor="#000" stopOpacity="0.22" />
        </linearGradient>
        <filter id={`drop-${uid}`} x="-20%" y="-20%" width="140%" height="150%">
          <feDropShadow dx="0" dy="2.5" stdDeviation="2.2" floodColor="#000" floodOpacity="0.45" />
        </filter>
        <filter id={`mark-${uid}`} x="-20%" y="-20%" width="140%" height="150%">
          <feDropShadow dx="0" dy="1.4" stdDeviation="1" floodColor="#000" floodOpacity="0.5" />
        </filter>
        {stops && (
          <linearGradient id={`outline-${uid}`} x1="0" y1="0" x2="1" y2="1">
            {stops.map((c, i) => <stop key={i} offset={`${(i / (stops.length - 1)) * 100}%`} stopColor={c} />)}
          </linearGradient>
        )}
        {outline && GLOW_OUTLINES.has(outline) && (
          <filter id={`glow-${uid}`} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        )}
        {effect === "shine" && (
          <linearGradient id={`shine-${uid}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#fff" stopOpacity="0" />
            <stop offset="50%" stopColor="#fff" stopOpacity="0.75" />
            <stop offset="100%" stopColor="#fff" stopOpacity="0" />
          </linearGradient>
        )}
      </defs>

      <EffectBehind effect={effect} uid={uid} glow={glow ?? shade(color, 0.35)} />

      <path d={path} fill={shade(color, -0.5)} filter={`url(#drop-${uid})`} />
      <g clipPath={`url(#clip-${uid})`}>
        <rect x={0} y={0} width={100} height={100} fill={`url(#base-${uid})`} />
        {inside}
        {effect === "shine" && (
          <rect className="emblem-shine-band" x={-10} y={-10} width={40} height={120} fill={`url(#shine-${uid})`} transform="skewX(-15)" />
        )}
        <ellipse cx={50} cy={8} rx={62} ry={40} fill={`url(#gloss-${uid})`} />
        <rect x={0} y={55} width={100} height={45} fill={`url(#shadow-${uid})`} />
        {/* Inner light edge: a stroke clipped to the shape shows only its inner half. */}
        <path d={path} fill="none" stroke="#fff" strokeOpacity={0.3} strokeWidth={5} strokeLinejoin="round" />
      </g>
      <path d={path} fill="none" stroke={shade(color, -0.55)} strokeWidth={2.2} strokeLinejoin="round" />

      {mark && <g filter={`url(#mark-${uid})`}>{mark}</g>}

      {stops && outline && (
        <path
          d={path}
          fill="none"
          stroke={`url(#outline-${uid})`}
          strokeWidth={outlineWidth}
          strokeLinejoin="round"
          className={OUTLINE_CLASS[outline]}
          filter={GLOW_OUTLINES.has(outline) ? `url(#glow-${uid})` : undefined}
        />
      )}

      <EffectFront effect={effect} path={path} />
    </svg>
  );
}

export function ClubLogo({
  shape, color, size = 40, emblem,
}: { shape: ClubLogoShape; color: string; size?: number; emblem?: ClubEmblem | null }) {
  const path = SHAPE_PATHS[shape];
  if (!emblem || !Object.entries(emblem).some(([k, v]) => k !== "outline_thin" && v)) {
    return <EmblemArt path={path} color={color} size={size} />;
  }

  const overlay = emblem.color2 ?? "rgba(255,255,255,0.32)";
  const markFill = emblem.pattern ? "#ffffff" : emblem.color2 ?? "#ffffff";
  const letters = emblem.letters;
  // Tiny logos (lists) skip the letters when a symbol is there too — unreadable at 24px.
  const showLetters = letters && (size >= 36 || !emblem.symbol);

  return (
    <EmblemArt
      path={path}
      color={color}
      size={size}
      outline={emblem.outline}
      outlineThin={emblem.outline_thin}
      effect={emblem.effect}
      glow={emblem.color2 ?? undefined}
      inside={emblem.pattern ? <g opacity={0.92}><Pattern kind={emblem.pattern} fill={overlay} /></g> : undefined}
      mark={
        emblem.symbol || showLetters ? (
          <>
            {emblem.symbol && (
              <SymbolMark kind={emblem.symbol} fill={markFill} base={color} y={showLetters ? -7 : 0} scale={showLetters ? 0.85 : 1} />
            )}
            {showLetters && (
              <text
                x={50}
                y={emblem.symbol ? 84 : 50}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={emblem.symbol ? 14 : letters.length > 2 ? 26 : 32}
                fontWeight={900}
                fontFamily="inherit"
                fill={markFill}
                stroke="rgba(0,0,0,0.25)"
                strokeWidth={emblem.symbol ? 0.6 : 0.9}
                paintOrder="stroke"
              >
                {letters}
              </text>
            )}
          </>
        ) : undefined
      }
    />
  );
}
