import { motion } from "framer-motion";
import type { ReactNode } from "react";

import type { MagnateCell, MagnateGroup, MagnatePlayer } from "@/types";

import { BOARD_SIDE, CELL_BADGE, SEAT_COLORS, cellCoord } from "./magnateMeta";

interface Props {
  cells: MagnateCell[];
  groups: MagnateGroup[];
  players: MagnatePlayer[];
  selected: number | null;
  /** Cells to outline (the one on offer / where building is possible). */
  highlight?: number[];
  onSelect: (index: number) => void;
  children?: ReactNode;
}

/** Square board: 24 cells around a 7×7 grid, the centre holds `children`
 *  (dice, current event). Tokens use a shared layoutId so they glide from
 *  cell to cell when the server moves them. */
export default function MagnateBoard({ cells, groups, players, selected, highlight = [], onSelect, children }: Props) {
  return (
    <div
      className="grid aspect-square w-full gap-[2px] rounded-2xl bg-white/5 p-[2px]"
      style={{ gridTemplateColumns: `repeat(${BOARD_SIDE}, 1fr)`, gridTemplateRows: `repeat(${BOARD_SIDE}, 1fr)` }}
    >
      {cells.map((cell) => {
        const { row, col } = cellCoord(cell.index);
        const group = cell.group !== null ? groups[cell.group] : undefined;
        const owner = cell.owner_seat !== null ? SEAT_COLORS[cell.owner_seat] : undefined;
        const here = players.filter((p) => p.pos === cell.index && !p.bankrupt);
        const isCorner = cell.index % (BOARD_SIDE - 1) === 0;
        return (
          <button
            key={cell.index}
            type="button"
            onClick={() => onSelect(cell.index)}
            aria-label={cell.name}
            style={{ gridRow: row, gridColumn: col, boxShadow: owner ? `inset 0 0 0 2px ${owner}` : undefined }}
            className={`relative flex min-w-0 flex-col overflow-hidden rounded-md text-left ${
              isCorner ? "bg-bg-raised" : "bg-bg-surface"
            } ${selected === cell.index ? "ring-2 ring-white" : highlight.includes(cell.index) ? "ring-2 ring-accent-lime" : ""}`}
          >
            {group && <span className="h-[5px] w-full shrink-0" style={{ background: group.color }} />}
            <span className="flex min-h-0 flex-1 flex-col items-center justify-center px-[1px] text-center">
              {CELL_BADGE[cell.type] && (
                <span className={`leading-none ${cell.type === "var" ? "font-mono text-[8px] font-bold text-accent-cyan" : "text-[11px]"}`}>
                  {CELL_BADGE[cell.type]}
                </span>
              )}
              {cell.name !== CELL_BADGE[cell.type] && (
                <span className="line-clamp-2 w-full break-words text-[7px] font-semibold leading-[1.1] text-ink-chalk">
                  {cell.name.replace(/^Стадион /, "")}
                </span>
              )}
              {cell.price !== null && cell.owner_seat === null && (
                <span className="font-mono text-[7px] leading-none text-ink-mist">{cell.price}</span>
              )}
              {cell.level > 0 && (
                <span className="font-mono text-[7px] leading-none text-accent-lime">
                  {cell.level >= 4 ? "★" : "▮".repeat(cell.level)}
                </span>
              )}
            </span>
            {here.length > 0 && (
              <span className="pointer-events-none absolute inset-x-0 bottom-[1px] flex justify-center gap-[1px]">
                {here.map((p) => (
                  <motion.span
                    key={p.seat}
                    layoutId={`magnate-token-${p.seat}`}
                    transition={{ type: "spring", stiffness: 260, damping: 26 }}
                    className={`h-[9px] w-[9px] rounded-full border border-black/40 ${p.is_me ? "ring-1 ring-white" : ""}`}
                    style={{ background: SEAT_COLORS[p.seat] }}
                  />
                ))}
              </span>
            )}
          </button>
        );
      })}
      <div
        className="flex min-h-0 flex-col items-center justify-center gap-2 overflow-hidden rounded-xl p-2"
        style={{ gridRow: `2 / ${BOARD_SIDE}`, gridColumn: `2 / ${BOARD_SIDE}` }}
      >
        {children}
      </div>
    </div>
  );
}
