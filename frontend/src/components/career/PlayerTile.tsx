/** The one player card of «Карьера тренера»: the pitch, the bench strip
 * and the season squad sheet all draw this face, so a player looks the
 * same wherever the coach meets him. */
import type { ReactNode } from "react";

import type { CareerSquadCard } from "@/api/career";
import type { PlayerInfo } from "@/lib/careerPlayer";
import { RARITY_GLOW_STATIC, RARITY_GRADIENTS } from "@/lib/rarity";

function StatusBadge({ entry }: { entry: CareerSquadCard }) {
  if (entry.suspended_rounds > 0) {
    return <span className="rounded bg-red-500 px-1 text-micro font-bold leading-tight text-white">🟥 {entry.suspended_rounds}</span>;
  }
  if (entry.injured_rounds > 0) {
    return <span className="rounded bg-red-500 px-1 text-micro font-bold leading-tight text-white">✚ {entry.injured_rounds}</span>;
  }
  if (entry.form > 0) return <span className="rounded bg-accent-lime px-1 text-micro font-bold leading-tight text-bg-base">▲{entry.form}</span>;
  if (entry.form < 0) return <span className="rounded bg-red-400 px-1 text-micro font-bold leading-tight text-white">▼</span>;
  return null;
}

/** A player card in a rarity frame: photo, rating, position, surname.
 * `entry` adds the status (cards, injury, form) in the corner; `corner`
 * replaces the «Я» mark top right (e.g. ✓ «в заявке»). */
export function PlayerTile({ info, entry, width = "w-full", children, offPosition = false, corner }: {
  info: PlayerInfo; entry?: CareerSquadCard; width?: string; children?: ReactNode;
  offPosition?: boolean; corner?: ReactNode;
}) {
  return (
    <div className={`${width} rounded-[11px] bg-gradient-to-b p-[1.5px] ${RARITY_GRADIENTS[info.rarity]} ${RARITY_GLOW_STATIC[info.rarity]}`}>
      <div className="flex flex-col items-center gap-0.5 rounded-[10px] bg-bg-surface/95 p-0.5">
        <div className="relative aspect-[5/4] w-full overflow-hidden rounded-lg bg-gradient-to-b from-white/10 to-black/40">
          <img decoding="async" src={info.image} alt="" className="h-full w-full object-cover" loading="lazy" />
          <span className="absolute left-0.5 top-0.5 rounded-md bg-black/75 px-1 font-mono text-micro font-bold leading-tight text-accent-lime">
            {info.rating}
          </span>
          {corner ?? (info.mine && <span className="absolute right-0.5 top-0.5 rounded bg-accent-lime px-0.5 text-micro font-black text-bg-base">Я</span>)}
          {entry && <span className="absolute bottom-0.5 left-0.5"><StatusBadge entry={entry} /></span>}
          <span className={`absolute bottom-0.5 right-0.5 rounded px-0.5 font-mono text-micro font-bold leading-tight ${
            offPosition ? "bg-red-500/90 text-white" : "bg-black/75 text-accent-cyan"
          }`}>
            {info.position}
          </span>
        </div>
        <span className="w-full truncate text-center text-micro font-semibold leading-tight text-ink-chalk">{info.short}</span>
        {children}
      </div>
    </div>
  );
}
