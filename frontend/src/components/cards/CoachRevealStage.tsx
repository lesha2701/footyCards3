import { motion } from "framer-motion";

import { staticUrl } from "@/lib/api";
import { BOOST_TYPE_LABELS } from "@/lib/coaches";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_LABELS } from "@/lib/rarity";
import type { EquippedCoach } from "@/types";

// A simpler, coach-appropriate reveal — NOT a modification of the shared
// CardRevealStage.tsx, whose stage set (position/country/club) assumes
// Player-shaped data a Coach doesn't have. Keeping this separate avoids
// touching a component the two existing player-pack flows already depend on.
export type CoachStage = "rarity" | "silhouette" | "reveal";
export const COACH_STAGES: CoachStage[] = ["rarity", "silhouette", "reveal"];
export const COACH_STAGE_DURATION_MS = 900;

export interface RevealableOpenedCoachCard {
  card: { coach: EquippedCoach };
  is_new: boolean;
}

export function CoachRevealStage({
  opened,
  stage,
  index,
  total,
  onTap,
}: {
  opened: RevealableOpenedCoachCard;
  stage: CoachStage;
  index: number;
  total: number;
  onTap: () => void;
}) {
  const coach = opened.card.coach;
  const showFrom = (s: CoachStage) => COACH_STAGES.indexOf(stage) >= COACH_STAGES.indexOf(s);
  const revealed = showFrom("reveal");

  return (
    <div
      onClick={onTap}
      role="button"
      tabIndex={0}
      className="flex flex-1 cursor-pointer flex-col items-center justify-center gap-5 px-6 text-center"
    >
      {total > 1 && <p className="font-mono text-xs text-ink-mist-dim">Тренер {index + 1} / {total}</p>}

      <div className="relative">
        <motion.div
          initial={{ scale: 0.85, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className={`relative flex aspect-square w-64 flex-col items-center justify-center overflow-hidden rounded-3xl bg-gradient-to-b ${
            showFrom("rarity") ? RARITY_GRADIENTS[coach.rarity] : "from-bg-raised to-bg-surface"
          } p-[3px] ${showFrom("rarity") ? RARITY_GLOW[coach.rarity] : ""}`}
        >
          <div className="flex h-full w-full flex-col items-center justify-center rounded-[22px] bg-bg-surface">
            {revealed ? (
              <motion.img
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                src={staticUrl(coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt={coach.display_name}
                className="h-full w-full object-cover"
              />
            ) : showFrom("silhouette") ? (
              <img
                src={staticUrl(coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt=""
                className="h-full w-full object-cover opacity-30 blur-sm"
              />
            ) : null}
          </div>

          {showFrom("rarity") && (
            <span className="absolute right-2 top-2 rounded-md bg-black/70 px-2 py-1 text-[11px] font-bold text-ink-chalk">
              {RARITY_LABELS[coach.rarity]}
            </span>
          )}
        </motion.div>
      </div>

      <div className="min-h-[70px] space-y-1">
        {revealed && (
          <>
            <p className="font-display text-lg font-bold text-ink-chalk">{coach.display_name}</p>
            {coach.boosts.length > 0 && (
              <p className="font-mono text-xs text-ink-mist">
                {coach.boosts.map((b) => `${BOOST_TYPE_LABELS[b.boost_type]} +${b.magnitude}`).join(" · ")}
              </p>
            )}
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
