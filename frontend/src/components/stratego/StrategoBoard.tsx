import { useId } from "react";

import type { StrategoPiece } from "@/types";

import { CELL_LINES, GRASS_STYLE } from "./boardStyle";
import RoleIcon from "./RoleIcon";
import { ROLE_META } from "./strategoMeta";

interface Props {
  size: number;
  pieces: StrategoPiece[];
  selectedId?: number | null;
  targets?: [number, number][];
  lastMove?: { from: [number, number]; to: [number, number] } | null;
  onCellClick?: (row: number, col: number) => void;
  /** Rows to tint as the viewer's home rows (placement editor). */
  homeRows?: number[];
  lakes?: [number, number][];
}

type Rect = { r: number; c: number; h: number; w: number };

/** Groups lake cells into connected rectangles (each puddle is drawn once). */
function lakeRects(lakes: [number, number][]): Rect[] {
  const left = new Set(lakes.map(([r, c]) => `${r}:${c}`));
  const rects: Rect[] = [];
  for (const [r, c] of [...lakes].sort((a, b) => a[0] - b[0] || a[1] - b[1])) {
    if (!left.has(`${r}:${c}`)) continue;
    let w = 1;
    while (left.has(`${r}:${c + w}`)) w++;
    let h = 1;
    while (Array.from({ length: w }, (_, i) => left.has(`${r + h}:${c + i}`)).every(Boolean)) h++;
    for (let dr = 0; dr < h; dr++) for (let dc = 0; dc < w; dc++) left.delete(`${r + dr}:${c + dc}`);
    rects.push({ r, c, h, w });
  }
  return rects;
}

/** Square N×N pitch sized to the container width — ~45px cells on a 375px
 *  phone for the default 8×8 board. Own pieces are always at the bottom. */
export default function StrategoBoard({ size, pieces, selectedId, targets = [], lastMove, onCellClick, homeRows = [], lakes = [] }: Props) {
  const water = new Set(lakes.map(([r, c]) => `${r}:${c}`));
  const byCell = new Map(pieces.map((p) => [`${p.row}:${p.col}`, p]));
  const isTarget = (r: number, c: number) => targets.some(([tr, tc]) => tr === r && tc === c);
  const isLast = (r: number, c: number) =>
    !!lastMove && ((lastMove.from[0] === r && lastMove.from[1] === c) || (lastMove.to[0] === r && lastMove.to[1] === c));

  return (
    <div className="w-full overflow-hidden rounded-2xl border border-white/10 p-1 shadow-glow" style={GRASS_STYLE}>
      <div className="relative grid w-full rounded-xl" style={{ gridTemplateColumns: `repeat(${size}, minmax(0, 1fr))` }}>
        <PitchMarkings size={size} />
        {Array.from({ length: size * size }, (_, i) => {
          const r = Math.floor(i / size);
          const c = i % size;
          if (water.has(`${r}:${c}`)) return <div key={i} aria-label="Лужа" className="aspect-square" />;
          const piece = byCell.get(`${r}:${c}`);
          const target = isTarget(r, c);
          return (
            <button
              key={i}
              type="button"
              onClick={() => onCellClick?.(r, c)}
              className={[
                "relative flex aspect-square items-center justify-center text-center transition-transform active:scale-95",
                CELL_LINES,
                homeRows.includes(r) ? "bg-white/[0.05]" : "",
                isLast(r, c) ? "bg-accent-cyan/20" : "",
                target ? "bg-accent-lime/20 ring-2 ring-inset ring-accent-lime" : "",
              ].join(" ")}
            >
              {piece && <PieceChip piece={piece} selected={piece.id === selectedId} attackable={target && !piece.mine} />}
              {!piece && target && <span className="h-2 w-2 rounded-full bg-accent-lime shadow" />}
            </button>
          );
        })}
        {lakeRects(lakes).map((rect) => (
          <div
            key={`${rect.r}:${rect.c}`}
            className="pointer-events-none absolute"
            style={{
              top: `${(rect.r / size) * 100}%`, left: `${(rect.c / size) * 100}%`,
              width: `${(rect.w / size) * 100}%`, height: `${(rect.h / size) * 100}%`,
            }}
          >
            <Puddle w={rect.w} h={rect.h} />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Smooth closed blob (Catmull-Rom → cubic Bézier) on a superellipse with a
 *  fixed wobble: full and rounded rather than pointy, hand-drawn looking, yet
 *  identical on every render. */
function blobPath(cx: number, cy: number, rx: number, ry: number, wobble: number[]): string {
  const e = 2 / 2.6; // superellipse exponent — between an ellipse and a rounded rect
  const pts = wobble.map((k, i) => {
    const a = (i / wobble.length) * Math.PI * 2;
    const cos = Math.cos(a), sin = Math.sin(a);
    return [
      cx + Math.sign(cos) * Math.abs(cos) ** e * rx * k,
      cy + Math.sign(sin) * Math.abs(sin) ** e * ry * k,
    ] as const;
  });
  const n = pts.length;
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n], p1 = pts[i], p2 = pts[(i + 1) % n], p3 = pts[(i + 2) % n];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return `${d} Z`;
}

const WOBBLE = [1, 0.97, 1.02, 0.95, 0.99, 1.03, 0.96, 1, 0.97, 1.02, 0.94, 1, 1.03, 0.96, 0.99, 1.02];

export function Puddle({ w, h }: { w: number; h: number }) {
  const uid = useId().replace(/:/g, "");
  const W = w * 100, H = h * 100, cx = W / 2, cy = H / 2;
  const rx = W / 2 - 9, ry = H / 2 - 9;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full drop-shadow-[0_2px_3px_rgba(0,0,0,0.35)]" aria-hidden>
      <defs>
        <radialGradient id={`water-${uid}`} cx="42%" cy="38%" r="70%">
          <stop offset="0%" stopColor="#a6e6ff" />
          <stop offset="45%" stopColor="#3fa9e6" />
          <stop offset="100%" stopColor="#14609f" />
        </radialGradient>
        <radialGradient id={`shallow-${uid}`} cx="50%" cy="50%" r="50%">
          <stop offset="78%" stopColor="#7fd3c8" stopOpacity="0" />
          <stop offset="100%" stopColor="#8fdcc4" stopOpacity="0.75" />
        </radialGradient>
        <linearGradient id={`mud-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6b5332" />
          <stop offset="100%" stopColor="#3f2f1a" />
        </linearGradient>
      </defs>
      {/* wet soil rim */}
      <path d={blobPath(cx, cy, rx + 6, ry + 6, WOBBLE)} fill={`url(#mud-${uid})`} opacity="0.55" />
      {/* water, then a pale shallow band along the shore */}
      <path d={blobPath(cx, cy, rx, ry, WOBBLE)} fill={`url(#water-${uid})`} stroke="#0e4677" strokeOpacity="0.35" strokeWidth="1.5" />
      <path d={blobPath(cx, cy, rx, ry, WOBBLE)} fill={`url(#shallow-${uid})`} />
      {/* sky reflection and ripples */}
      <ellipse cx={cx - rx * 0.28} cy={cy - ry * 0.45} rx={rx * 0.32} ry={ry * 0.1} fill="#fff" opacity="0.45" transform={`rotate(-18 ${cx} ${cy})`} />
      <ellipse cx={cx + rx * 0.2} cy={cy + ry * 0.35} rx={rx * 0.42} ry={ry * 0.12} fill="none" stroke="#fff" strokeOpacity="0.3" strokeWidth="1.5" />
      <ellipse cx={cx + rx * 0.2} cy={cy + ry * 0.35} rx={rx * 0.24} ry={ry * 0.06} fill="none" stroke="#fff" strokeOpacity="0.35" strokeWidth="1.2" />
      <circle cx={cx - rx * 0.35} cy={cy + ry * 0.05} r="2.2" fill="#fff" opacity="0.5" />
      {/* grass tufts hugging the edge */}
      <g stroke="#2c6b2b" strokeWidth="2.2" strokeLinecap="round" fill="none">
        <path d={`M${cx - rx * 0.85},${cy - ry * 0.55} l-4,-9 M${cx - rx * 0.8},${cy - ry * 0.52} l1,-11 M${cx - rx * 0.74},${cy - ry * 0.55} l5,-8`} />
        <path d={`M${cx + rx * 0.78},${cy + ry * 0.62} l-4,-9 M${cx + rx * 0.84},${cy + ry * 0.6} l1,-11 M${cx + rx * 0.9},${cy + ry * 0.63} l5,-8`} />
      </g>
    </svg>
  );
}

/** Chalk markings under the pieces: touchlines, halfway line, centre circle
 *  and spot, and a penalty box in front of each home zone. */
function PitchMarkings({ size }: { size: number }) {
  const cell = 100 / size;
  const box = { w: cell * 4, h: cell * 1.5 };
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
      <g fill="none" stroke="#fff" strokeOpacity="0.32" strokeWidth="0.45" vectorEffect="non-scaling-stroke">
        <rect x="0.6" y="0.6" width="98.8" height="98.8" rx="1.5" />
        <line x1="0" y1="50" x2="100" y2="50" />
        <circle cx="50" cy="50" r={cell * 0.85} />
        <rect x={50 - box.w / 2} y="0.6" width={box.w} height={box.h} />
        <rect x={50 - box.w / 2} y={99.4 - box.h} width={box.w} height={box.h} />
      </g>
      <circle cx="50" cy="50" r="0.9" fill="#fff" fillOpacity="0.45" />
    </svg>
  );
}

/** VICTOR FC crest mark (the gradient pill + ball from /brand/victor-fc-crest)
 *  drawn as vector so it stays crisp on a 40px token — the card back of every
 *  unrevealed opponent piece. */
function BrandMark({ className }: { className?: string }) {
  const uid = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <defs>
        <linearGradient id={`vfc-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#22d3e6" />
          <stop offset="55%" stopColor="#5fd38a" />
          <stop offset="100%" stopColor="#d4e01a" />
        </linearGradient>
      </defs>
      <circle cx="12" cy="12" r="10.6" fill="#0b0d0f" stroke={`url(#vfc-${uid})`} strokeWidth="1.5" />
      <line x1="8.6" y1="8.4" x2="11.9" y2="15.4" stroke={`url(#vfc-${uid})`} strokeWidth="3.6" strokeLinecap="round" />
      <circle cx="15.3" cy="8.9" r="2" fill={`url(#vfc-${uid})`} />
    </svg>
  );
}

const RARITY_BORDER: Record<string, string> = {
  common: "border-rarity-common",
  rare: "border-rarity-rare",
  epic: "border-rarity-epic",
  legendary: "border-rarity-legendary",
  diamond: "border-rarity-diamond",
};

/** One piece token. Own pieces: dark chip framed in the card's rarity colour
 *  with a lime role icon (same language as the app's cards); the cup and
 *  walls get a floodlight frame. Opponent: deep red chip, "?" until revealed. */
export function PieceChip({ piece, selected, attackable }: { piece: StrategoPiece; selected?: boolean; attackable?: boolean }) {
  const base =
    "relative flex h-[86%] w-[86%] flex-col items-center justify-center gap-px rounded-lg leading-none shadow-[0_2px_4px_rgba(0,0,0,0.45)] transition-transform";
  const focus = `${selected ? "scale-110 ring-2 ring-accent-lime shadow-glow" : ""} ${attackable ? "ring-2 ring-accent-lime animate-pulse" : ""}`;
  const enemyTone = "border border-red-400/50 bg-gradient-to-b from-[#7a1f26] to-[#3d0d12] text-red-100";
  if (piece.hidden || !piece.role) {
    return (
      <span className={`${base} ${enemyTone} ${focus}`} title={piece.moved ? "Фишка уже ходила" : "Неизвестная фишка"}>
        <BrandMark className="h-[74%] w-[74%] drop-shadow-[0_1px_2px_rgba(0,0,0,0.5)]" />
        {piece.moved && <span className="absolute bottom-0.5 h-1 w-1 rounded-full bg-red-200/80" />}
      </span>
    );
  }
  const meta = ROLE_META[piece.role];
  const rarity = piece.card?.rarity;
  const mineTone = rarity
    ? `border-[1.5px] ${RARITY_BORDER[rarity] ?? "border-white/30"} bg-gradient-to-b from-bg-raised to-bg-base text-accent-lime`
    : "border-[1.5px] border-accent-lime/70 bg-gradient-to-b from-bg-raised to-bg-base text-accent-lime";
  return (
    <span
      className={`${base} ${piece.mine ? mineTone : enemyTone} ${focus}`}
      title={piece.card ? `${meta.label}: ${piece.card.display_name}` : meta.label}
    >
      <RoleIcon role={piece.role} size={15} strokeWidth={2} />
      {piece.power ? (
        <span className={`font-mono text-[9px] font-bold ${piece.mine ? "text-ink-chalk" : "text-red-50"}`}>{piece.power}</span>
      ) : null}
      {piece.mine && piece.revealed && (
        <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-red-400 ring-1 ring-bg-base" title="Соперник знает эту фишку" />
      )}
      {piece.card?.is_my_player && (
        <span className="absolute -left-0.5 -top-0.5 rounded-full bg-accent-lime p-[1px] text-bg-base" title="Мой игрок">
          <RoleIcon role="star" size={7} strokeWidth={3} />
        </span>
      )}
    </span>
  );
}
