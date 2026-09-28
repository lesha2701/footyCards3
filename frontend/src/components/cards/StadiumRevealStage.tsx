import { motion } from "framer-motion";

import { staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_LABELS } from "@/lib/rarity";
import type { EquippedStadium } from "@/types";

// A stadium-appropriate reveal, mirroring CoachRevealStage.tsx exactly but
// substituting boost_pct display for the coach's boosts list — kept as its
// own component for the same reason CoachRevealStage isn't folded into
// CardRevealStage.tsx: the stage set (position/country/club) there assumes
// Player-shaped data neither a Coach nor a Stadium has.
export type StadiumStage = "rarity" | "silhouette" | "reveal";
export const STADIUM_STAGES: StadiumStage[] = ["rarity", "silhouette", "reveal"];
export const STADIUM_STAGE_DURATION_MS = 900;

export interface RevealableOpenedStadiumCard {
  card: { stadium: EquippedStadium };
  is_new: boolean;
}

export function StadiumRevealStage({
  opened,
  stage,
  index,
  total,
  onTap,
}: {
  opened: RevealableOpenedStadiumCard;
  stage: StadiumStage;
  index: number;
  total: number;
  onTap: () => void;
}) {
  const stadium = opened.card.stadium;
  const showFrom = (s: StadiumStage) => STADIUM_STAGES.indexOf(stage) >= STADIUM_STAGES.indexOf(s);
  const revealed = showFrom("reveal");

  return (
    <div
      onClick={onTap}
      role="button"
      tabIndex={0}
      className="flex flex-1 cursor-pointer flex-col items-center justify-center gap-5 px-6 text-center"
    >
      {total > 1 && <p className="font-mono text-xs text-ink-mist-dim">Стадион {index + 1} / {total}</p>}

      <div className="relative">
        <motion.div
          initial={{ scale: 0.85, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className={`relative flex aspect-square w-64 flex-col items-center justify-center overflow-hidden rounded-3xl bg-gradient-to-b ${
            showFrom("rarity") ? RARITY_GRADIENTS[stadium.rarity] : "from-bg-raised to-bg-surface"
          } p-[3px] ${showFrom("rarity") ? RARITY_GLOW[stadium.rarity] : ""}`}
        >
          <div className="flex h-full w-full flex-col items-center justify-center rounded-[22px] bg-bg-surface">
            {revealed ? (
              <motion.img
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                src={staticUrl(stadium.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt={stadium.display_name}
                className="h-full w-full object-cover"
              />
            ) : showFrom("silhouette") ? (
              <img
                src={staticUrl(stadium.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt=""
                className="h-full w-full object-cover opacity-30 blur-sm"
              />
            ) : null}
          </div>

          {showFrom("rarity") && (
            <span className="absolute right-2 top-2 rounded-md bg-black/70 px-2 py-1 text-[11px] font-bold text-ink-chalk">
              {RARITY_LABELS[stadium.rarity]}
            </span>
          )}
        </motion.div>
      </div>

      <div className="min-h-[70px] space-y-1">
        {revealed && (
          <>
            <p className="font-display text-lg font-bold text-ink-chalk">{stadium.display_name}</p>
            <p className="font-mono text-xs text-ink-mist">+{Math.round(stadium.boost_pct * 100)}% к силе</p>
            {opened.is_new && (
              <span className="inline-block rounded-full bg-accent-green px-2 py-0.5 text-[11px] font-bold text-bg-base">Новый!</span>
            )}
          </>
        )}
      </div>

      {stage !== "reveal" && <p className="text-xs text-ink-mist-dim">Нажми, чтобы продолжить</p>}
    </div>
  );
}
