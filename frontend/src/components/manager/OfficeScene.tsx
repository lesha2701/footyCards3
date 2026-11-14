import { useId } from "react";

import type { ManagerItemArt } from "@/api/manager";
import { staffArt } from "@/lib/staffArt";

/** The president's car, side view, by `art.shape`. */
export function CarArt({ art, code, width = 120, className = "" }: { art?: ManagerItemArt | null; code?: string | null; width?: number; className?: string }) {
  const picture = staffArt(code);
  if (picture) {
    return <img src={picture} alt="" loading="lazy" width={width} height={(width * 2) / 3}
      className={`rounded-lg object-cover ${className}`} style={{ width, height: (width * 2) / 3 }} />;
  }
  const body = art?.body ?? "#9aa4b1";
  const shape = art?.shape ?? "hatch";
  const roof = {
    hatch: "M30 30 L44 16 L78 16 L92 30 Z",
    sedan: "M26 30 L42 16 L82 16 L100 30 Z",
    suv: "M22 30 L28 10 L92 10 L104 30 Z",
    sport: "M34 30 L54 18 L84 18 L104 30 Z",
    limo: "M22 30 L34 16 L120 16 L134 30 Z",
  }[shape];
  const long = shape === "limo";
  const w = long ? 160 : 128;
  return (
    <svg viewBox={`0 0 ${w} 52`} width={width} height={(width * 52) / w} aria-hidden>
      <ellipse cx={w / 2} cy={48} rx={w / 2 - 6} ry={3} fill="#000" opacity={0.35} />
      <path d={roof} fill={body} />
      <path d={roof} fill="#bfe6ff" opacity={0.35} transform={`translate(${w / 2} 23) scale(0.82) translate(${-w / 2} -23)`} />
      <rect x={6} y={28} width={w - 12} height={shape === "sport" ? 12 : 15} rx={7} fill={body} />
      <rect x={8} y={31} width={w - 16} height={2} rx={1} fill="#fff" opacity={0.25} />
      <rect x={w - 14} y={32} width={7} height={4} rx={2} fill="#ffe38a" />
      <rect x={7} y={32} width={5} height={4} rx={2} fill="#ff5a5a" />
      {[24, w - 26].map((x) => (
        <g key={x}>
          <circle cx={x} cy={43} r={8} fill="#111" />
          <circle cx={x} cy={43} r={3.5} fill="#cfd6de" />
        </g>
      ))}
    </svg>
  );
}

/** The office room behind the hero: the wall, a window onto the stadium,
 * the president's desk with a trophy. Colours come from the worn room. */
export default function OfficeScene({ room, code, className = "" }: { room?: ManagerItemArt | null; code?: string | null; className?: string }) {
  const uid = useId().replace(/:/g, "");
  const picture = staffArt(code);
  if (picture) return <img src={picture} alt="" loading="lazy" className={`object-cover ${className}`} />;
  const wall = room?.wall ?? "#20303f";
  const floor = room?.floor ?? "#3a2c22";
  const glow = room?.window ?? "#88a9c3";
  return (
    <svg viewBox="0 0 360 200" preserveAspectRatio="xMidYMid slice" className={className} aria-hidden>
      <defs>
        <linearGradient id={`w${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={wall} />
          <stop offset="100%" stopColor="#000" stopOpacity={0.6} />
        </linearGradient>
        <linearGradient id={`sky${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={glow} stopOpacity={0.9} />
          <stop offset="100%" stopColor={glow} stopOpacity={0.25} />
        </linearGradient>
      </defs>
      <rect width={360} height={200} fill={wall} />
      <rect width={360} height={200} fill={`url(#w${uid})`} />
      {/* the window: stands and the pitch under floodlights */}
      <rect x={150} y={18} width={196} height={112} rx={6} fill={`url(#sky${uid})`} />
      <path d="M150 96 Q248 70 346 96 L346 130 L150 130 Z" fill="#000" opacity={0.45} />
      <path d="M170 116 Q248 100 326 116 L326 130 L170 130 Z" fill="#2f9e57" opacity={0.85} />
      {[178, 318].map((x) => (
        <g key={x}>
          <rect x={x} y={30} width={3} height={60} fill="#000" opacity={0.5} />
          <circle cx={x + 1.5} cy={30} r={6} fill="#fff" opacity={0.85} />
          <circle cx={x + 1.5} cy={30} r={18} fill="#fff" opacity={0.12} />
        </g>
      ))}
      <path d="M248 18 L248 130 M150 74 L346 74" stroke={wall} strokeWidth={4} opacity={0.9} />
      <rect x={150} y={18} width={196} height={112} rx={6} fill="none" stroke="#000" strokeOpacity={0.4} strokeWidth={4} />
      {/* floor and desk */}
      <rect x={0} y={150} width={360} height={50} fill={floor} />
      <rect x={0} y={148} width={360} height={4} fill="#000" opacity={0.3} />
      <path d="M150 140 L340 140 L352 160 L138 160 Z" fill="#2a1a12" />
      <rect x={146} y={160} width={200} height={8} fill="#000" opacity={0.35} />
      {/* a trophy and a laptop on the desk */}
      <path d="M300 112 L318 112 L315 126 L303 126 Z" fill="#f2c14e" />
      <rect x={305} y={126} width={8} height={6} fill="#f2c14e" />
      <rect x={300} y={132} width={18} height={6} rx={1} fill="#6b4a1d" />
      <rect x={196} y={124} width={36} height={16} rx={2} fill="#1d2430" />
      <rect x={199} y={127} width={30} height={10} fill={glow} opacity={0.6} />
    </svg>
  );
}
