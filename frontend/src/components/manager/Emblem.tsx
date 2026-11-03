import { useId } from "react";

import type { ManagerLook } from "@/api/manager";
import { EmblemArt, ImageSymbol } from "@/components/clubs/ClubLogo";
import { isImageSymbol } from "@/lib/emblemSymbols";

const SHAPES: Record<string, string> = {
  shield: "M50 4 L92 16 L88 62 Q82 86 50 98 Q18 86 12 62 L8 16 Z",
  circle: "M50 4 A46 46 0 1 1 49.9 4 Z",
  crown: "M8 34 L24 12 L38 30 L50 6 L62 30 L76 12 L92 34 L86 92 L14 92 Z",
  star: "M50 4 L62 36 L96 38 L69 59 L79 94 L50 74 L21 94 L31 59 L4 38 L38 36 Z",
  hexagon: "M50 4 L90 27 L90 73 L50 96 L10 73 L10 27 Z",
  crest: "M10 6 Q50 22 90 6 V44 Q90 80 50 96 Q10 80 10 44 Z",
  diamond: "M50 4 L94 50 L50 96 L6 50 Z",
  castle: "M10 92 V30 H22 V16 H34 V30 H44 V10 H56 V30 H66 V16 H78 V30 H90 V92 Z",
};

/** The club emblem drawn from its look: shape and colours (the second colour is the inner
 * band), the symbol, and the «Обводка» / «Эффект» bought in «Стиль» (shared drawing with
 * the clubs' ClubLogo). */
export default function Emblem({ look, size = 48, className = "" }: {
  look: Pick<ManagerLook, "shape" | "symbol" | "color" | "color2"> & Partial<Pick<ManagerLook, "rim" | "fx">>;
  size?: number;
  className?: string;
}) {
  const path = SHAPES[look.shape] ?? SHAPES.shield;
  const rim = look.rim && look.rim !== "none" ? look.rim : null;
  const fx = look.fx && look.fx !== "none" ? look.fx : null;
  return (
    <span className={`inline-flex shrink-0 ${className}`} aria-hidden="true">
      <EmblemArt
        path={path}
        color={look.color}
        size={size}
        outline={rim}
        effect={fx}
        glow={look.color2}
        inside={<path d={path} fill="none" stroke={look.color2} strokeWidth={12} strokeLinejoin="round" />}
        mark={<SymbolGlyph symbol={look.symbol} fill={look.color2} cx={50} cy={52} size={54} />}
      />
    </span>
  );
}

/** The emblem symbol in SVG space: a picture symbol tinted with `fill`
 * («img_<key>», see ClubLogo.ImageSymbol), an emoji (the older symbols) or nothing («none»). */
export function SymbolGlyph({ symbol, fill, cx, cy, size }: { symbol: string; fill: string; cx: number; cy: number; size: number }) {
  if (!symbol || symbol === "none") return null;
  if (isImageSymbol(symbol)) return <ImageSymbol symbol={symbol} fill={fill} x={cx - size / 2} y={cy - size / 2} size={size} />;
  return <text x={cx} y={cy + size * 0.06} textAnchor="middle" dominantBaseline="middle" fontSize={size * 0.83}>{symbol}</text>;
}

// Shirt in a 100×100 box: short sleeves, the neckline dips at the front.
const SHIRT = "M37 7 Q50 {neck} 63 7 L81 12 L98 31 L87 44 L79 38 L79 93 Q50 98 21 93 L21 38 L13 44 L2 31 L19 12 Z";
const SLEEVES = "M19 12 L2 31 L13 44 L21 38 L21 18 Z M81 12 L98 31 L87 44 L79 38 L79 18 Z";

/** The kit pattern in the shirt's box over the main colour, drawn in the second colour `b`. */
function KitPattern({ kit, b, uid }: { kit: string; b: string; uid: string }) {
  const bands = (horizontal: boolean, step: number, width: number) =>
    Array.from({ length: Math.ceil(100 / step) }, (_, i) => (horizontal
      ? <rect key={i} x={0} y={i * step + (step - width) / 2} width={100} height={width} fill={b} />
      : <rect key={i} x={i * step + (step - width) / 2} y={0} width={width} height={100} fill={b} />));
  switch (kit) {
    case "stripes": return <>{bands(false, 14, 7)}</>;
    case "hoops": return <>{bands(true, 14, 7)}</>;
    case "pinstripes": return <>{bands(false, 7, 1.4)}</>;
    case "halves": return <rect x={50} y={0} width={50} height={100} fill={b} />;
    case "quarters": return <path d="M50 0 H100 V50 H50 Z M0 50 H50 V100 H0 Z" fill={b} />;
    case "sash": return <path d="M14 4 L32 4 L96 82 L96 100 L84 100 Z" fill={b} />;
    case "chevron": return <path d="M10 22 L50 52 L90 22 L90 36 L50 66 L10 36 Z" fill={b} />;
    case "checks":
      return (
        <>
          {Array.from({ length: 64 }, (_, i) => ((i % 8) + Math.floor(i / 8)) % 2 === 0 && (
            <rect key={i} x={(i % 8) * 12.5} y={Math.floor(i / 8) * 12.5} width={12.5} height={12.5} fill={b} />
          ))}
        </>
      );
    case "gradient": return <rect width={100} height={100} fill={`url(#kit-grad-${uid})`} />;
    case "sleeves": return <path d={SLEEVES} fill={b} />;
    case "band": return <rect x={0} y={44} width={100} height={14} fill={b} />;
    case "yoke": return <path d="M0 0 H100 V30 Q50 40 0 30 Z" fill={b} />;
    default: return null;
  }
}

/** The club shirt: kit pattern and colours, collar and cuffs in the second colour, the
 * club emblem on the chest and the shirt sponsor. `back` shows the back instead: the
 * club name and a number. */
export function KitShirt({ look, size = 40, sponsor, back }: {
  look: Pick<ManagerLook, "kit" | "kit_color" | "kit_color2"> & Partial<Pick<ManagerLook, "shape" | "symbol" | "color" | "color2">>;
  size?: number;
  /** A shirt sponsor's brand across the chest («Кабинет президента»). */
  sponsor?: string | null;
  back?: { name: string; number: number };
}) {
  const uid = useId().replace(/:/g, "");
  const a = look.kit_color;
  const b = look.kit_color2;
  const shirt = SHIRT.replace("{neck}", back ? "11" : "19");
  const emblem = !back && size >= 40 && look.shape && look.symbol && look.color && look.color2;
  return (
    <span className="relative inline-flex shrink-0" style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 100 100" width={size} height={size} className="overflow-visible">
        <defs>
          <clipPath id={`kit-clip-${uid}`}><path d={shirt} /></clipPath>
          <linearGradient id={`kit-grad-${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={a} /><stop offset="1" stopColor={b} />
          </linearGradient>
          <linearGradient id={`kit-light-${uid}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#fff" stopOpacity={0.22} />
            <stop offset="0.45" stopColor="#fff" stopOpacity={0} />
            <stop offset="1" stopColor="#000" stopOpacity={0.28} />
          </linearGradient>
        </defs>
        <g clipPath={`url(#kit-clip-${uid})`}>
          <rect width={100} height={100} fill={a} />
          <KitPattern kit={look.kit} b={b} uid={uid} />
          {/* cuffs, side seams and the fold under the arms */}
          <path d="M3.6 32.6 L14.2 45 M96.4 32.6 L85.8 45" stroke={b} strokeWidth={5} />
          <path d="M21 38 V93 M79 38 V93" stroke="#000" strokeOpacity={0.18} strokeWidth={1.2} />
          <path d="M21 93 Q50 98 79 93" fill="none" stroke="#000" strokeOpacity={0.2} strokeWidth={3} />
          <rect width={100} height={100} fill={`url(#kit-light-${uid})`} />
        </g>
        {/* collar */}
        <path d={back ? "M37 7 Q50 11 63 7" : "M37 7 Q50 19 63 7"} fill="none" stroke={b} strokeWidth={4.5} strokeLinecap="round" />
        {!back && <path d="M40 8.5 Q50 15 60 8.5" fill="none" stroke="#000" strokeOpacity={0.35} strokeWidth={1.2} />}
        <path d={shirt} fill="none" stroke="#000" strokeOpacity={0.4} strokeWidth={1.4} strokeLinejoin="round" />
        {back && (
          <>
            <text x={50} y={28} textAnchor="middle" fontSize={8.5} fontWeight={900} fill={b} stroke="#0b0f14" strokeOpacity={0.85}
              strokeWidth={1.6} strokeLinejoin="round" paintOrder="stroke" letterSpacing={0.6} style={{ textTransform: "uppercase" }}>
              {back.name.slice(0, 12)}
            </text>
            <text x={50} y={70} textAnchor="middle" fontSize={38} fontWeight={900} fill={b} stroke="#0b0f14" strokeOpacity={0.85}
              strokeWidth={3.2} strokeLinejoin="round" paintOrder="stroke">
              {back.number}
            </text>
          </>
        )}
      </svg>
      {emblem && (
        <span className="absolute" style={{ left: size * 0.57, top: size * 0.22 }}>
          <Emblem look={{ shape: look.shape!, symbol: look.symbol!, color: look.color!, color2: look.color2! }} size={Math.round(size * 0.17)} />
        </span>
      )}
      {sponsor && !back && (
        <span
          className="absolute inset-x-0 flex justify-center"
          style={{ top: size * 0.46 }}
        >
          <span
            className="max-w-[54%] truncate rounded-sm bg-white/90 px-0.5 text-center font-black uppercase leading-none text-slate-900"
            style={{ fontSize: Math.max(5, size * 0.11) }}
          >
            {sponsor.split(" ")[0]}
          </span>
        </span>
      )}
    </span>
  );
}
