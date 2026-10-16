import { memo } from "react";

import PathCardMark from "@/components/path/PathCardMark";
import { staticUrl } from "@/lib/api";
import { pathFrameClass } from "@/lib/pathCards";
import { prestigeMarks, prestigeStyle } from "@/lib/prestige";
import { RARITY_GLOW_STATIC, RARITY_GRADIENTS, RARITY_LABELS } from "@/lib/rarity";
import type { Player } from "@/types";

interface Props {
  player: Player;
  size?: "sm" | "md" | "lg";
  badge?: React.ReactNode;
  footer?: React.ReactNode;
  onClick?: () => void;
  selected?: boolean;
  dimmed?: boolean;
  /** «Звёзды» of this specific copy (its rating already includes them). */
  stars?: number;
  /** «Академия»: stage of this specific copy (omit for a design). */
  pathStage?: number;
  /** «Академия» prestige tier of this copy (◆ marks; it also tints the frame). */
  prestige?: number;
  /** Talent picked in a prestige reforge (overrides the design's). */
  talentOverride?: string | null;
  /** The card is the focus (pack reveal, detail): adds the GPU shine. */
  animated?: boolean;
}

// One corner = one meaning: top-left rating + status (★ stars / ◆ prestige),
// top-right position, bottom-left skill (badge slot), bottom-right «Академия».
// The footer keeps only the name (+ club and attack/defence from md up):
// rarity and «Академия» are already said by the frame, so no repeated text.
const RATING_TEXT = { sm: "text-[12px]", md: "text-sm", lg: "text-base" } as const;
const NAME_TEXT = { sm: "text-caption", md: "text-xs", lg: "text-sm" } as const;

function PlayerCard({
  player, size = "md", badge, footer, onClick, selected, dimmed, stars = 0, pathStage, prestige = 0, talentOverride,
  animated = false,
}: Props) {
  const isPath = !!player.path_talent_code;
  const frame = isPath
    ? pathFrameClass(pathStage, prestige, animated || selected)
    : `${RARITY_GRADIENTS[player.rarity]} ${RARITY_GLOW_STATIC[player.rarity]}${
        (animated || selected) && (player.rarity === "diamond" || player.rarity === "legendary") ? " card-shine" : ""
      }`;
  const imageUrl = staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp");

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      aria-label={`${player.display_name}, ${player.position}, рейтинг ${player.rating}, ${RARITY_LABELS[player.rarity]}${
        isPath ? ", Академия" : ""
      }`}
      className={`group relative flex aspect-[3/4] w-full flex-col overflow-hidden rounded-2xl bg-gradient-to-b ${frame} ${
        isPath ? "p-[3px]" : "p-[2px]"
      } transition-transform active:scale-[0.97] ${
        selected ? (player.rarity === "diamond" ? "ring-4 ring-rarity-diamond" : "ring-4 ring-accent-lime") : ""
      } ${dimmed ? "opacity-40 grayscale" : ""} ${onClick ? "cursor-pointer" : "cursor-default"}`}
    >
      <div className="flex h-full w-full flex-col overflow-hidden rounded-[14px] bg-bg-surface">
        <div className="relative flex-1 overflow-hidden bg-black/20">
          <img
            src={imageUrl}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
            decoding="async"
            draggable={false}
          />
          <div className="absolute left-1 top-1 rounded-md bg-black/70 px-1.5 py-0.5 text-center font-display font-bold leading-none text-white">
            <span className={RATING_TEXT[size]}>{player.rating}</span>
            {prestige > 0 && (
              <span className={`mt-0.5 block text-micro leading-none ${prestigeStyle(prestige).mark}`} aria-label={`Престиж: ${prestige}`}>
                {prestigeMarks(prestige)}
              </span>
            )}
            {stars > 0 && (
              <span className="mt-0.5 block text-micro leading-none text-amber-300" aria-label={`Звёзд: ${stars}`}>
                {"★".repeat(stars)}
              </span>
            )}
          </div>
          <div className="absolute right-1 top-1 rounded-md bg-black/70 px-1.5 py-0.5 font-display font-semibold leading-none text-white">
            <span className={size === "sm" ? "text-micro" : "text-caption"}>{player.position}</span>
          </div>
          {badge && <div className="absolute bottom-1 left-1">{badge}</div>}
          {isPath && (
            <div className="absolute bottom-1 right-1">
              <PathCardMark talentCode={talentOverride || player.path_talent_code!} stage={pathStage} size={size} />
            </div>
          )}
        </div>
        <div className="border-t border-white/10 bg-black/30 px-1.5 py-1 text-center">
          <p className={`truncate font-display font-semibold leading-tight text-ink-chalk ${NAME_TEXT[size]}`}>{player.display_name}</p>
          {size !== "sm" && (
            <p className="mt-0.5 truncate text-micro leading-tight text-ink-mist">
              {player.club} · <span className="font-mono text-accent-cyan">{player.attack_rating}/{player.defense_rating}</span>
            </p>
          )}
        </div>
        {footer}
      </div>
    </button>
  );
}

export default memo(PlayerCard);
