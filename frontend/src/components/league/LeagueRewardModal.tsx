import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

import { IconCoin, IconPack, IconTrophy } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import type { LeagueRewardClaim } from "@/types";

interface Props {
  open: boolean;
  rewards: LeagueRewardClaim[];
  collecting: boolean;
  onCollect: () => void;
  onClose: () => void;
}

export default function LeagueRewardModal({ open, rewards, collecting, onCollect, onClose }: Props) {
  // Claims come back ordered by granted_at ascending — a higher tier can
  // only ever be crossed after a lower one, so the last entry is always the
  // highest (and most recent) tier reached, the natural hero of the reveal.
  const hero = rewards[rewards.length - 1];
  const rest = rewards.slice(0, -1);

  return createPortal(
    <AnimatePresence>
      {open && hero && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="safe-bottom max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-t-3xl border border-white/10 bg-bg-surface p-7 pb-8 sm:rounded-3xl"
            initial={{ y: 80, opacity: 0, scale: 0.96 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 22, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            <motion.div
              className="flex flex-col items-center text-center"
              initial={{ scale: 0.3, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", damping: 11, stiffness: 220, delay: 0.15 }}
            >
              <motion.span
                className="flex h-32 w-32 items-center justify-center overflow-hidden rounded-full"
                style={hero.image_path ? undefined : { background: `radial-gradient(circle, ${hero.color}33, ${hero.color}08)` }}
                initial={{ rotate: -8 }}
                animate={{ rotate: 0 }}
                transition={{ type: "spring", damping: 8, stiffness: 200, delay: 0.15 }}
              >
                {hero.image_path ? (
                  <img src={staticUrl(hero.image_path) ?? undefined} className="h-full w-full object-cover" />
                ) : (
                  <IconTrophy size={68} style={{ color: hero.color }} />
                )}
              </motion.span>

              <p className="mt-4 font-display text-2xl font-bold text-ink-chalk">Поздравляем!</p>
              <p className="mt-1 text-sm text-ink-mist">
                {rewards.length > 1
                  ? `Ты поднялся сразу на ${rewards.length} лиги — теперь ты в «${hero.tier_name}»!`
                  : `Ты поднялся в лигу «${hero.tier_name}»!`}
              </p>

              {(hero.reward_coins > 0 || hero.reward_pack_name) && (
                <div className="mt-3 flex items-center gap-4">
                  {hero.reward_coins > 0 && (
                    <span className="flex items-center gap-1.5 font-mono text-lg font-bold text-accent-lime">
                      <IconCoin size={18} />+{hero.reward_coins}
                    </span>
                  )}
                  {hero.reward_pack_name && (
                    <span className="flex items-center gap-1.5 text-sm font-semibold text-accent-cyan">
                      <IconPack size={16} />
                      {hero.reward_pack_name}
                    </span>
                  )}
                </div>
              )}
            </motion.div>

            {rest.length > 0 && (
              <div className="mt-6 flex flex-col gap-2">
                <p className="text-center text-[11px] uppercase tracking-wider text-ink-mist-dim">
                  Также пройдено по пути
                </p>
                {rest.map((r) => (
                  <div key={r.id} className="flex items-center gap-3 rounded-xl bg-bg-raised px-3 py-2.5">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-bg-surface">
                      {r.image_path ? (
                        <img src={staticUrl(r.image_path) ?? undefined} className="h-full w-full object-cover" />
                      ) : (
                        <IconTrophy size={18} style={{ color: r.color }} />
                      )}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-ink-chalk">{r.tier_name}</p>
                      <div className="mt-0.5 flex items-center gap-3 text-xs text-ink-mist">
                        {r.reward_coins > 0 && (
                          <span className="flex items-center gap-1">
                            <IconCoin size={13} className="text-accent-lime" />+{r.reward_coins}
                          </span>
                        )}
                        {r.reward_pack_name && (
                          <span className="flex items-center gap-1">
                            <IconPack size={13} className="text-accent-cyan" />
                            {r.reward_pack_name}
                          </span>
                        )}
                        {r.reward_coins === 0 && !r.reward_pack_name && <span>Без награды</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={onCollect}
              disabled={collecting}
              className="mt-6 w-full rounded-2xl bg-accent py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              {collecting ? "Забираем..." : "Забрать"}
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
