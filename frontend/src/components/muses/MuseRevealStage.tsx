import { motion } from "framer-motion";

import MuseArt from "@/components/muses/MuseArt";
import { type TokenStage } from "@/components/cards/revealStages";
import { RARITY_LABELS } from "@/lib/rarity";
import type { OpenedMuse } from "@/types";

/** Reveal for a pack slot that dropped a «Муза» — the same two-beat rhythm
 * as the skill-token reveal (glow, then the reveal). */
export function MuseRevealStage({
  opened,
  stage,
  index,
  total,
  onTap,
}: {
  opened: OpenedMuse;
  stage: TokenStage;
  index: number;
  total: number;
  onTap: () => void;
}) {
  const revealed = stage === "reveal";
  const { muse } = opened;
  return (
    <div
      onClick={onTap}
      role="button"
      tabIndex={0}
      className="flex flex-1 cursor-pointer flex-col items-center justify-center gap-5 px-6 text-center"
    >
      {total > 1 && <p className="font-mono text-xs text-ink-mist-dim">Карта {index + 1} / {total}</p>}

      <motion.div
        initial={{ scale: 0.7, opacity: 0, rotate: -6 }}
        animate={{ scale: revealed ? 1 : 0.9, opacity: 1, rotate: 0 }}
        transition={{ type: "spring", damping: 14, stiffness: 180 }}
        className="relative w-52 rounded-2xl shadow-[0_0_60px_-10px] shadow-pink-400/60"
      >
        {revealed ? (
          <MuseArt muse={muse} className="aspect-[3/4] w-full rounded-2xl" iconClass="text-8xl" />
        ) : (
          <motion.span
            animate={{ opacity: [0.4, 1, 0.4] }}
            transition={{ repeat: Infinity, duration: 1.2 }}
            className="flex aspect-[3/4] w-full items-center justify-center rounded-2xl bg-gradient-to-b from-pink-500/30 to-fuchsia-500/10 text-7xl"
            aria-hidden
          >
            💖
          </motion.span>
        )}
        {revealed && opened.is_new && (
          <span className="absolute left-2 top-2 rounded-full bg-accent-green px-2 py-0.5 text-micro font-bold text-bg-base">NEW</span>
        )}
      </motion.div>

      <div className="min-h-[70px] space-y-1">
        {revealed ? (
          <>
            <p className="font-display text-lg font-bold text-ink-chalk">{muse.name}</p>
            <p className="text-xs text-ink-mist">
              {muse.title ? `${muse.title} · ` : ""}{RARITY_LABELS[muse.rarity]}
            </p>
            <p className="text-sm font-semibold text-pink-300">{muse.effect_label}</p>
            {!opened.is_new && <p className="text-caption text-ink-mist-dim">Уже в альбоме — копий: {opened.copies}</p>}
          </>
        ) : (
          <p className="font-display text-base font-semibold text-pink-300">Муза!</p>
        )}
      </div>

      {!revealed && <p className="text-xs text-ink-mist-dim">Нажми, чтобы продолжить</p>}
    </div>
  );
}
