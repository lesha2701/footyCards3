/** The one player card of «Карьера тренера»: the pitch, the bench strip
 * and the season squad sheet all draw this face, so a player looks the
 * same wherever the coach meets him. */
import type { ReactNode } from "react";

import type { CareerSquadCard } from "@/api/career";
import { EnergyBattery } from "@/components/career/EnergyBar";
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

/** Form as a triangle with its number inside: up and green-lime when the
 * player is on the rise, down and red when he is off it. */
export function FormTriangle({ form }: { form: number }) {
  if (!form) return null;
  const up = form > 0;
  return (
    <svg viewBox="0 0 18 16" width="18" height="16" role="img" aria-label={`Форма ${up ? "+" : ""}${form}`} className="block">
      <title>{`Форма ${up ? "+" : ""}${form}`}</title>
      <path
        d={up ? "M9 1.5 17 14.5H1z" : "M1 1.5h16L9 14.5z"}
        fill={up ? "#c6e63a" : "#f87171"} stroke="#04130c" strokeWidth={1.2} strokeLinejoin="round"
      />
      <text
        x="9" y={up ? 13 : 9.5} textAnchor="middle" fontSize="9" fontWeight="800" fontFamily="ui-monospace, monospace"
        fill={up ? "#04130c" : "#ffffff"}
      >
        {Math.abs(form)}
      </text>
    </svg>
  );
}

/** The compact card of the pitch and the bench: a clean square photo with
 * only the rating and position on it; everything else stands around it — the
 * chemistry flask and icons (`side`) to the right, the battery under it. The
 * name opens on tap. `anchor` marks the square for the chemistry lines. */
export function PitchTile({ info, entry, chemistry, side, offPosition = false, anchor }: {
  info: PlayerInfo; entry?: CareerSquadCard; chemistry?: ReactNode; side?: ReactNode; offPosition?: boolean; anchor?: string;
}) {
  return (
    <div className="grid w-fit grid-cols-[auto_18px] gap-x-0.5 gap-y-[3px]">
      <div
        data-chem-slot={anchor}
        className={`relative aspect-square w-[40px] rounded-[9px] bg-gradient-to-b p-[1.5px] min-[400px]:w-[44px] ${RARITY_GRADIENTS[info.rarity]} ${RARITY_GLOW_STATIC[info.rarity]}`}
      >
        <div className="relative h-full w-full overflow-hidden rounded-[8px] bg-bg-surface">
          <img decoding="async" src={info.image} alt="" className="h-full w-full object-cover object-top" loading="lazy" />
          {info.mine && <span className="absolute right-0 top-0 rounded-bl bg-accent-lime px-0.5 text-[9px] font-black leading-tight text-bg-base">Я</span>}
          {entry && (
            <span className="absolute left-0 top-0 [&>span]:!text-[9px]">
              {entry.injured_rounds > 0 || entry.suspended_rounds > 0 ? <StatusBadge entry={entry} /> : <FormTriangle form={entry.form} />}
            </span>
          )}
          <span className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-[3px] bg-black/80 font-mono text-[9px] font-bold leading-[12px]">
            <span className="text-accent-lime">{info.rating}</span>
            <span className={offPosition ? "text-red-400" : "text-accent-cyan"}>{info.position}</span>
          </span>
        </div>
      </div>
      <div className="row-span-2 flex flex-col items-center gap-[2px]">
        {chemistry}
        {side}
      </div>
      {entry && <EnergyBattery fatigue={entry.fatigue} />}
    </div>
  );
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
