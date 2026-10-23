import type { ReactNode } from "react";

import type { MagnateCell, MagnateGroup, MagnatePlayer } from "@/types";

import { CellIcon, ClubCrest } from "./MagnateArt";
import { CELL_TYPE_LABELS, SEAT_COLORS, formatMoney, levelLabel } from "./magnateMeta";

/** A "property card" for a cell: club colours, crest, group, rents. Used for
 *  the purchase offer and when the player taps a cell on the board. */
export default function MagnateClubCard({
  cell, group, owner, stadiumRents, compact = false, children,
}: {
  cell: MagnateCell;
  group?: MagnateGroup | null;
  owner?: MagnatePlayer | null;
  stadiumRents?: number[];
  compact?: boolean;
  children?: ReactNode;
}) {
  const primary = cell.colors?.[0] ?? group?.color ?? "#1e293b";
  const secondary = cell.colors?.[1] ?? "#0f172a";
  const isClub = cell.type === "club";
  const rentRows: [string, number][] = cell.rent
    ? [["Аренда", cell.rent[0]], ["Вся группа", cell.rent[0] * 2], ["Трибуны ×1", cell.rent[1]], ["Трибуны ×2", cell.rent[2]], ["Трибуны ×3", cell.rent[3]], ["Арена", cell.rent[4]]]
    : (stadiumRents ?? []).map((r, i) => [`${i + 1} стадион${i ? "а" : ""}`, r] as [string, number]);

  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-bg-surface shadow-lg">
      <div
        className="relative flex items-center gap-3 px-3 py-2.5"
        style={{ background: `linear-gradient(120deg, ${primary} 0%, ${primary}cc 45%, ${secondary}aa 100%)` }}
      >
        <span className="absolute inset-0 bg-gradient-to-b from-white/10 to-black/30" />
        {group && <span className="absolute inset-x-0 top-0 h-1" style={{ background: group.color }} />}
        <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-black/25 backdrop-blur-sm">
          {isClub ? <ClubCrest short={cell.short} colors={cell.colors} size={28} /> : <CellIcon type={cell.type} size={26} />}
        </span>
        <span className="relative min-w-0 flex-1">
          <span className="block truncate font-display text-base font-bold text-white drop-shadow">{cell.name}</span>
          <span className="block text-caption text-white/80 drop-shadow">
            {isClub && group ? group.name : CELL_TYPE_LABELS[cell.type]}
            {cell.price !== null && ` · ${formatMoney(cell.price)}`}
          </span>
        </span>
        {owner && (
          <span className="relative rounded-full bg-black/35 px-2 py-0.5 text-micro font-semibold" style={{ color: SEAT_COLORS[owner.seat] }}>
            {owner.is_me ? "твой" : owner.name}
          </span>
        )}
      </div>
      {!compact && (
        <div className="px-3 py-2">
          {cell.price !== null && (
            <p className="mb-1.5 text-caption text-ink-mist">
              {owner
                ? `${cell.level > 0 ? `${levelLabel(cell.level)} · ` : ""}аренда сейчас ${formatMoney(cell.current_rent)}`
                : "Свободен — можно купить"}
            </p>
          )}
          {cell.type === "fine" && cell.amount !== null && <p className="text-caption text-ink-mist">Платёж: {formatMoney(cell.amount)}</p>}
          {rentRows.length > 0 && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-caption">
              {rentRows.map(([label, value]) => (
                <div key={label} className="contents">
                  <span className="text-ink-mist">{label}</span>
                  <span className="text-right font-mono text-ink-chalk">{formatMoney(value)}</span>
                </div>
              ))}
              {cell.build_cost !== null && (
                <>
                  <span className="text-ink-mist">Постройка</span>
                  <span className="text-right font-mono text-accent-lime">{formatMoney(cell.build_cost)}</span>
                </>
              )}
            </div>
          )}
        </div>
      )}
      {children && <div className="border-t border-white/5 px-3 py-2.5">{children}</div>}
    </div>
  );
}
