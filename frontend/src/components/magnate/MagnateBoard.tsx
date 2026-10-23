import { motion } from "framer-motion";
import type { ReactNode } from "react";

import type { MagnateCell, MagnateGroup, MagnatePlayer } from "@/types";

import { CellIcon, ClubCrest, PitchBackground } from "./MagnateArt";
import { SEAT_COLORS, boardSide, cellCoord, isCorner } from "./magnateMeta";

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

const SHORT_LABELS: Partial<Record<MagnateCell["type"], string>> = {
  start: "Старт", jail: "Дисквал.", break: "Перерыв", go_to_jail: "Красная", var: "VAR",
  transfer: "Трансфер", fine: "Налог", chance: "Пенальти", red_card: "Красная",
};

/** Square board around a football pitch. Clubs show a drawn crest in their
 *  colours with a band of their group's colour; owned cells take the
 *  owner's colour. Tokens share a layoutId per seat so they glide from cell
 *  to cell when the server moves them. */
export default function MagnateBoard({ cells, groups, players, selected, highlight = [], onSelect, children }: Props) {
  const total = cells.length;
  const side = boardSide(total);
  return (
    <div
      className="grid aspect-square w-full gap-[1.5px] rounded-2xl border border-white/10 bg-[#0b1f14] p-[2px] shadow-[0_8px_30px_rgba(0,0,0,0.45)]"
      style={{ gridTemplateColumns: `repeat(${side}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${side}, minmax(0, 1fr))` }}
    >
      {cells.map((cell) => {
        const { row, col } = cellCoord(cell.index, total);
        const group = cell.group !== null ? groups[cell.group] : undefined;
        const owner = cell.owner_seat !== null ? SEAT_COLORS[cell.owner_seat] : undefined;
        const here = players.filter((p) => p.pos === cell.index && !p.bankrupt);
        const corner = isCorner(cell.index, total);
        const ring = selected === cell.index
          ? "ring-2 ring-white z-10"
          : highlight.includes(cell.index) ? "ring-2 ring-accent-lime z-10 animate-pulse" : "";
        return (
          <button
            key={cell.index}
            type="button"
            onClick={() => onSelect(cell.index)}
            aria-label={cell.name}
            style={{
              gridRow: row, gridColumn: col,
              background: owner
                ? `linear-gradient(180deg, ${owner}38, ${owner}12)`
                : corner ? "linear-gradient(160deg, #1b2a22, #101a14)" : undefined,
              boxShadow: owner ? `inset 0 0 0 1.5px ${owner}` : undefined,
            }}
            className={`relative flex min-h-0 min-w-0 flex-col items-center overflow-hidden rounded-[5px] bg-[#16211b] ${ring}`}
          >
            {group && <span className="h-[4px] w-full shrink-0" style={{ background: group.color }} />}
            <span className="flex min-h-0 w-full flex-1 flex-col items-center justify-center gap-[1px]">
              {cell.type === "club" ? (
                <ClubCrest short={cell.short ?? cell.name.slice(0, 3).toUpperCase()} colors={cell.colors} size={corner ? 18 : 15} />
              ) : (
                <CellIcon type={cell.type} size={corner ? 17 : 13} />
              )}
              {/* Board-cell legends are the one exception to the 10px minimum
                  (text-micro): 32 cells share a phone-width board, and the
                  full name/price is shown in the cell panel below on tap. */}
              {cell.type !== "club" && cell.type !== "stadium" && (
                <span className="w-full truncate px-[1px] text-center text-[6.5px] font-bold uppercase leading-none tracking-tight text-white/75">
                  {SHORT_LABELS[cell.type] ?? cell.name}
                </span>
              )}
              {cell.price !== null && cell.owner_seat === null && (
                <span className="font-mono text-[6.5px] leading-none text-white/60">{cell.price}</span>
              )}
              {cell.level > 0 && (
                <span className="flex gap-[1px] leading-none">
                  {cell.level >= 4 ? (
                    <span className="text-[8px] leading-none text-amber-300">★</span>
                  ) : (
                    Array.from({ length: cell.level }, (_, i) => <span key={i} className="h-[4px] w-[4px] rounded-[1px] bg-accent-lime" />)
                  )}
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
                    className={`h-[8px] w-[8px] rounded-full border border-black/60 shadow-[0_1px_2px_rgba(0,0,0,0.6)] ${p.is_me ? "ring-1 ring-white" : ""}`}
                    style={{ background: `radial-gradient(circle at 35% 30%, #ffffffaa, ${SEAT_COLORS[p.seat]} 55%)` }}
                  />
                ))}
              </span>
            )}
          </button>
        );
      })}
      <div
        className="relative flex min-h-0 flex-col items-center justify-center gap-2 overflow-hidden rounded-xl p-3"
        style={{ gridRow: `2 / ${side}`, gridColumn: `2 / ${side}` }}
      >
        <PitchBackground />
        <div className="relative flex w-full flex-col items-center gap-2">{children}</div>
      </div>
    </div>
  );
}
