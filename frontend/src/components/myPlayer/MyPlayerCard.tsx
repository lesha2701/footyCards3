import type { MyPlayer } from "@/api/myPlayer";
import { ATTR_ORDER, ATTR_SHORT, TIER_FRAMES, TIER_TEXT } from "@/lib/myPlayer";

import PlayerAvatar from "./PlayerAvatar";

interface Props {
  player: MyPlayer;
  level?: number | null;
  size?: "sm" | "md";
}

/** «Мой игрок» as a collectible-style card; the frame follows the tier. */
export default function MyPlayerCard({ player, level, size = "md" }: Props) {
  const small = size === "sm";
  return (
    <div
      className={`relative aspect-[3/4] w-full overflow-hidden rounded-2xl bg-gradient-to-b p-[3px] ${TIER_FRAMES[player.tier]}`}
      data-testid="my-player-card"
    >
      <div className="flex h-full w-full flex-col overflow-hidden rounded-[13px] bg-gradient-to-b from-bg-raised to-bg-surface">
        <div className="relative flex-1">
          <div className="absolute left-2 top-2 z-10 flex flex-col items-center leading-none drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]">
            <span className={`font-display font-black text-ink-chalk ${small ? "text-lg" : "text-3xl"}`}>{player.rating}</span>
            <span className={`font-display font-bold text-ink-mist ${small ? "text-micro" : "text-xs"}`}>{player.position}</span>
          </div>
          <div className="absolute right-2 top-2 z-10 text-right leading-tight drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]">
            <span className={`block font-display font-bold ${TIER_TEXT[player.tier]} ${small ? "text-micro" : "text-micro"}`}>
              {player.tier_label.toUpperCase()}
            </span>
            {level != null && (
              <span className={`block font-mono text-ink-mist ${small ? "text-micro" : "text-micro"}`}>ур. {level}</span>
            )}
          </div>
          <PlayerAvatar
            appearance={player.appearance} number={player.number} accessory={player.accessory} backdrop={player.background}
            className="absolute inset-0 h-full w-full"
          />
        </div>
        <div className="border-t border-white/10 bg-black/30 px-2 py-1.5 text-center">
          <p className={`truncate font-display font-bold text-ink-chalk ${small ? "text-micro" : "text-sm"}`}>
            {player.name} <span className="text-ink-mist">#{player.number}</span>
          </p>
          {!small && (
            <p className="mt-0.5 flex items-center justify-center gap-3 font-mono text-micro text-ink-mist">
              {ATTR_ORDER.map((a) => (
                <span key={a}>
                  {ATTR_SHORT[a]} <b className="text-accent-cyan">{player.attributes[a]}</b>
                </span>
              ))}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
