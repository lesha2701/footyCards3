import type { StrategoPiece } from "@/types";

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

/** Square N×N pitch sized to the container width — ~42px cells on a 375px
 *  phone for the default 8×8 board. Own pieces are always at the bottom. */
export default function StrategoBoard({ size, pieces, selectedId, targets = [], lastMove, onCellClick, homeRows = [], lakes = [] }: Props) {
  const water = new Set(lakes.map(([r, c]) => `${r}:${c}`));
  const byCell = new Map(pieces.map((p) => [`${p.row}:${p.col}`, p]));
  const isTarget = (r: number, c: number) => targets.some(([tr, tc]) => tr === r && tc === c);
  const isLast = (r: number, c: number) =>
    !!lastMove && ((lastMove.from[0] === r && lastMove.from[1] === c) || (lastMove.to[0] === r && lastMove.to[1] === c));

  return (
    <div
      className={`grid w-full rounded-2xl bg-accent-green/15 p-1 ${size >= 8 ? "gap-0.5" : "gap-1"}`}
      style={{ gridTemplateColumns: `repeat(${size}, minmax(0, 1fr))` }}
    >
      {Array.from({ length: size * size }, (_, i) => {
        const r = Math.floor(i / size);
        const c = i % size;
        const piece = byCell.get(`${r}:${c}`);
        const target = isTarget(r, c);
        const home = homeRows.includes(r);
        if (water.has(`${r}:${c}`)) {
          return (
            <div
              key={i}
              aria-label="Лужа"
              className="flex aspect-square items-center justify-center rounded-lg bg-sky-500/35 text-xs"
            >
              💧
            </div>
          );
        }
        return (
          <button
            key={i}
            type="button"
            onClick={() => onCellClick?.(r, c)}
            className={[
              "relative flex aspect-square items-center justify-center rounded-lg text-center transition-transform active:scale-95",
              (r + c) % 2 === 0 ? "bg-accent-green/25" : "bg-accent-green/15",
              home ? "ring-1 ring-inset ring-accent-lime/40" : "",
              isLast(r, c) ? "outline outline-2 outline-accent-cyan/60" : "",
              target ? "ring-2 ring-inset ring-accent-lime" : "",
            ].join(" ")}
          >
            {piece && <PieceChip piece={piece} selected={piece.id === selectedId} attackable={target && !piece.mine} />}
            {!piece && target && <span className="h-2 w-2 rounded-full bg-accent-lime/80" />}
          </button>
        );
      })}
    </div>
  );
}

export function PieceChip({ piece, selected, attackable }: { piece: StrategoPiece; selected?: boolean; attackable?: boolean }) {
  const base = "flex h-[88%] w-[88%] flex-col items-center justify-center rounded-md leading-none shadow";
  if (piece.hidden || !piece.role) {
    return (
      <span className={`${base} bg-red-500/70 text-white ${attackable ? "ring-2 ring-accent-lime" : ""}`}>
        <span className="text-sm font-bold">?</span>
        {piece.moved && <span className="mt-0.5 text-[8px] opacity-80">ходил</span>}
      </span>
    );
  }
  const meta = ROLE_META[piece.role];
  const tone = piece.mine ? "bg-accent-cyan text-bg-base" : "bg-red-500/80 text-white";
  return (
    <span
      className={`${base} ${tone} ${selected ? "ring-2 ring-accent-lime scale-105" : ""} ${attackable ? "ring-2 ring-accent-lime" : ""}`}
      title={piece.card ? `${meta.label}: ${piece.card.display_name}` : meta.label}
    >
      <span className="text-sm leading-none">{meta.glyph}</span>
      {piece.power ? <span className="mt-0.5 font-mono text-[9px] font-bold">{piece.power}</span> : null}
      {piece.mine && piece.revealed && <span className="absolute right-0.5 top-0.5 text-[8px]">👁</span>}
    </span>
  );
}
