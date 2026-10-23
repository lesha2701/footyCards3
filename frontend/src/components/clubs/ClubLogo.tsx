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

/** Patterns, drawn in the second colour (or a light overlay) and clipped to the shape. */
function Pattern({ kind, fill }: { kind: string; fill: string }) {
  switch (kind) {
    case "stripes":
      return <g fill={fill}>{[18, 38, 58, 78].map((x) => <rect key={x} x={x} y={0} width={10} height={100} />)}</g>;
    case "halves":
      return <rect x={50} y={0} width={50} height={100} fill={fill} />;
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
    default:
      return null;
  }
  return <g transform={t}>{body}</g>;
}

const OUTLINE_STOPS: Record<string, [string, string, string]> = {
  gold: ["#FFF3B0", "#E6B422", "#8C6A12"],
  silver: ["#FFFFFF", "#C9CED6", "#7C838D"],
  bronze: ["#F6C99A", "#C97B3C", "#6E3F17"],
  neon: ["#7CFFEA", "#22E3FF", "#B14CFF"],
};

const SPARKLES: [number, number, number, string][] = [
  [18, 16, 5, "0s"], [84, 22, 4, "0.6s"], [80, 82, 5, "1.1s"], [14, 74, 4, "0.3s"], [50, 2, 3.5, "0.9s"],
];

/** `hex` lighter (amount > 0) or darker (< 0), amount in -1…1; non-hex colours pass through. */
function shade(hex: string, amount: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const mix = (c: number) => Math.round(amount >= 0 ? c + (255 - c) * amount : c * (1 + amount));
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(mix);
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

/** The badge itself — every logo gets depth (gradient, gloss, a dark rim with a light inner
 * edge, a drop shadow); `children` are the emblem layers drawn inside the shape. */
function Badge({ uid, path, color, children }: { uid: string; path: string; color: string; children?: ReactNode }) {
  return (
    <>
      <defs>
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
      </defs>
      <path d={path} fill={shade(color, -0.5)} filter={`url(#drop-${uid})`} />
      <g clipPath={`url(#clip-${uid})`}>
        <rect x={0} y={0} width={100} height={100} fill={`url(#base-${uid})`} />
        {children}
        {/* Gloss on the upper half and a darker bottom edge. */}
        <ellipse cx={50} cy={8} rx={62} ry={40} fill={`url(#gloss-${uid})`} />
        <rect x={0} y={55} width={100} height={45} fill={`url(#shadow-${uid})`} />
        {/* Inner light edge: a stroke clipped to the shape shows only its inner half. */}
        <path d={path} fill="none" stroke="#fff" strokeOpacity={0.3} strokeWidth={5} strokeLinejoin="round" />
      </g>
      <path d={path} fill="none" stroke={shade(color, -0.55)} strokeWidth={2.2} strokeLinejoin="round" />
    </>
  );
}

export function ClubLogo({
  shape, color, size = 40, emblem,
}: { shape: ClubLogoShape; color: string; size?: number; emblem?: ClubEmblem | null }) {
  const uid = useId().replace(/:/g, "");
  const path = SHAPE_PATHS[shape];
  if (!emblem || !Object.entries(emblem).some(([k, v]) => k !== "outline_thin" && v)) {
    return (
      <svg width={size} height={size} viewBox="-6 -6 112 112" xmlns="http://www.w3.org/2000/svg" style={{ overflow: "visible" }}>
        <defs>
          <clipPath id={`clip-${uid}`}>
            <path d={path} />
          </clipPath>
        </defs>
        <Badge uid={uid} path={path} color={color} />
      </svg>
    );
  }

  const overlay = emblem.color2 ?? "rgba(255,255,255,0.32)";
  const markFill = emblem.pattern ? "#ffffff" : emblem.color2 ?? "#ffffff";
  const stops = emblem.outline ? OUTLINE_STOPS[emblem.outline] : undefined;
  const outlineWidth = emblem.outline_thin ? 2.5 : 5;
  const letters = emblem.letters;
  // Tiny logos (lists) skip the letters when a symbol is there too — unreadable at 24px.
  const showLetters = letters && (size >= 36 || !emblem.symbol);

  return (
    <svg width={size} height={size} viewBox="-8 -8 116 116" xmlns="http://www.w3.org/2000/svg" style={{ overflow: "visible" }}>
      <defs>
        <clipPath id={`clip-${uid}`}>
          <path d={path} />
        </clipPath>
        {stops && (
          <linearGradient id={`outline-${uid}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={stops[0]} />
            <stop offset="50%" stopColor={stops[1]} />
            <stop offset="100%" stopColor={stops[2]} />
          </linearGradient>
        )}
        {emblem.outline === "neon" && (
          <filter id={`glow-${uid}`} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        )}
        {emblem.effect === "shine" && (
          <linearGradient id={`shine-${uid}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#fff" stopOpacity="0" />
            <stop offset="50%" stopColor="#fff" stopOpacity="0.75" />
            <stop offset="100%" stopColor="#fff" stopOpacity="0" />
          </linearGradient>
        )}
      </defs>

      {emblem.effect === "flame" && (
        <g>
          <path className="emblem-flame" d="M22 48 C14 30 24 18 20 0 C34 12 38 24 34 40 Z" fill="#FF7A18" />
          <path className="emblem-flame-2" d="M42 30 C38 14 50 6 50 -8 C60 6 64 16 58 30 Z" fill="#FFB020" />
          <path className="emblem-flame" d="M78 48 C86 30 76 18 80 0 C66 12 62 24 66 40 Z" fill="#FF7A18" />
          <path className="emblem-flame-2" d="M28 42 C26 30 32 24 32 14 C40 24 40 32 38 42 Z" fill="#FFE066" />
          <path className="emblem-flame-2" d="M72 42 C74 30 68 24 68 14 C60 24 60 32 62 42 Z" fill="#FFE066" />
        </g>
      )}

      <defs>
        <filter id={`mark-${uid}`} x="-20%" y="-20%" width="140%" height="150%">
          <feDropShadow dx="0" dy="1.4" stdDeviation="1" floodColor="#000" floodOpacity="0.5" />
        </filter>
      </defs>

      <Badge uid={uid} path={path} color={color}>
        {emblem.pattern && <g opacity={0.92}><Pattern kind={emblem.pattern} fill={overlay} /></g>}
        {emblem.effect === "shine" && (
          <rect className="emblem-shine-band" x={-10} y={-10} width={40} height={120} fill={`url(#shine-${uid})`} transform="skewX(-15)" />
        )}
      </Badge>

      <g filter={`url(#mark-${uid})`}>
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
      </g>

      {stops && (
        <path
          d={path}
          fill="none"
          stroke={`url(#outline-${uid})`}
          strokeWidth={outlineWidth}
          strokeLinejoin="round"
          className={emblem.outline === "neon" ? "emblem-neon" : undefined}
          filter={emblem.outline === "neon" ? `url(#glow-${uid})` : undefined}
        />
      )}

      {emblem.effect === "sparkle" &&
        SPARKLES.map(([x, y, r, delay]) => (
          <path
            key={`${x}-${y}`}
            className="emblem-sparkle"
            style={{ animationDelay: delay }}
            d={`M${x} ${y - r} L${x + r * 0.28} ${y - r * 0.28} L${x + r} ${y} L${x + r * 0.28} ${y + r * 0.28} L${x} ${y + r} L${x - r * 0.28} ${y + r * 0.28} L${x - r} ${y} L${x - r * 0.28} ${y - r * 0.28} Z`}
            fill="#FFF6C2"
          />
        ))}
    </svg>
  );
}
