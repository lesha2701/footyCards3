import { motion } from "framer-motion";

import { staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_LABELS } from "@/lib/rarity";
import type { OpenedCard } from "@/types";

export type Stage = "position" | "rarity" | "country" | "club" | "silhouette" | "reveal";
export const STAGES: Stage[] = ["position", "rarity", "country", "club", "silhouette", "reveal"];
export const STAGE_DURATION_MS = 900;

export function RevealStage({
  opened,
  stage,
  index,
  total,
  onTap,
}: {
  opened: OpenedCard;
  stage: Stage;
  index: number;
  total: number;
  onTap: () => void;
}) {
  const player = opened.card.player;
  const showFrom = (s: Stage) => STAGES.indexOf(stage) >= STAGES.indexOf(s);

  return (
    <div
      onClick={onTap}
      role="button"
      tabIndex={0}
      className="flex flex-1 cursor-pointer flex-col items-center justify-center gap-5 px-6 text-center"
    >
      {total > 1 && <p className="text-xs text-slate-500">Карточка {index + 1} / {total}</p>}

      <motion.div
        initial={{ scale: 0.85, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className={`relative flex h-72 w-52 flex-col items-center justify-center overflow-hidden rounded-3xl bg-gradient-to-b ${
          showFrom("rarity") ? RARITY_GRADIENTS[player.rarity] : "from-slate-700 to-slate-900"
        } p-[3px] ${showFrom("rarity") ? RARITY_GLOW[player.rarity] : ""}`}
      >
        <div className="flex h-full w-full flex-col items-center justify-center rounded-[22px] bg-bg-surface">
          {showFrom("reveal") ? (
            <motion.img
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              src={staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
              alt={player.display_name}
              className="h-full w-full object-cover"
            />
          ) : showFrom("silhouette") ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="h-32 w-32 rounded-full bg-black/60" />
          ) : (
            <span className="text-5xl">❓</span>
          )}
        </div>

        {showFrom("position") && (
          <span className="absolute left-2 top-2 rounded-md bg-black/70 px-2 py-1 text-[11px] font-bold text-white">
            {player.position}
          </span>
        )}
        {showFrom("rarity") && (
          <span className="absolute right-2 top-2 rounded-md bg-black/70 px-2 py-1 text-[11px] font-bold text-white">
            {RARITY_LABELS[player.rarity]}
          </span>
        )}
      </motion.div>

      <div className="min-h-[70px] space-y-1">
        {showFrom("country") && <p className="text-sm text-slate-300">🌍 {player.country}</p>}
        {showFrom("club") && <p className="text-sm text-slate-300">🏟️ {player.club}</p>}
        {showFrom("reveal") && (
          <>
            <p className="font-display text-xl font-bold text-slate-100">{player.display_name}</p>
            <p className="font-display text-lg font-bold text-amber-300">Рейтинг {player.rating}</p>
            {player.collection_name && (
              <p className="text-xs font-semibold text-amber-400">🏷️ {player.collection_name}</p>
            )}
            {opened.is_new && <span className="inline-block rounded-full bg-emerald-500 px-2 py-0.5 text-[11px] font-bold text-white">Новая!</span>}
            {opened.duplicate_count > 1 && (
              <span className="ml-1 inline-block rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-slate-300">
                ×{opened.duplicate_count} в коллекции
              </span>
            )}
          </>
        )}
      </div>

      {stage !== "reveal" && <p className="text-xs text-slate-500">Нажми, чтобы продолжить</p>}
    </div>
  );
}
