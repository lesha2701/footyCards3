import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";

import { api } from "@/lib/api";
import { IconCoin } from "@/components/icons";
import { RARITY_LABELS, RARITY_TEXT } from "@/lib/rarity";
import { hapticNotify } from "@/lib/telegram";
import type { GrantedRewards } from "@/types";

interface StreakReward {
  id: number;
  days: number;
  rewards: Partial<GrantedRewards>;
}

const BURST = ["🎉", "⚽", "🏆", "✨", "🎖️", "🎊", "⭐", "🔥"];

/** «N дней подряд»: the keepsake the server already granted
 * (streak_reward_service), celebrated once on the next app open. */
export default function StreakRewardPopup() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["streak-rewards"],
    queryFn: async () => (await api.get<StreakReward[]>("/streak-rewards/unseen")).data,
    staleTime: 60_000,
  });
  const seen = useMutation({
    mutationFn: (id: number) => api.post(`/streak-rewards/${id}/seen`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["streak-rewards"] }),
  });
  const reward = data?.[0];
  const r = reward?.rewards ?? {};

  return (
    <AnimatePresence>
      {reward && (
        <motion.div
          key={reward.id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onAnimationComplete={() => hapticNotify("success")}
          className="fixed inset-0 z-[80] flex items-center justify-center overflow-hidden bg-black/75 px-6 backdrop-blur-sm"
        >
          {BURST.flatMap((e, i) => [0, 1].map((k) => (
            <motion.span
              key={`${i}-${k}`}
              className="pointer-events-none absolute left-1/2 top-1/2 text-2xl"
              initial={{ x: 0, y: 0, opacity: 0, scale: 0.4 }}
              animate={{
                x: Math.cos(((i * 2 + k) / 16) * Math.PI * 2) * (140 + k * 40),
                y: Math.sin(((i * 2 + k) / 16) * Math.PI * 2) * (180 + k * 40),
                opacity: [0, 1, 0], scale: [0.4, 1.3, 0.8], rotate: 180,
              }}
              transition={{ duration: 1.8, delay: 0.3 + k * 0.25, repeat: 1, repeatDelay: 0.6 }}
            >
              {e}
            </motion.span>
          )))}
          <motion.div
            initial={{ scale: 0.6, y: 40 }}
            animate={{ scale: 1, y: 0 }}
            transition={{ type: "spring", damping: 14, stiffness: 180 }}
            className="relative w-full max-w-sm rounded-3xl bg-bg-surface p-6 text-center shadow-2xl ring-2 ring-amber-300/50"
          >
            <motion.p
              initial={{ scale: 0 }}
              animate={{ scale: [0, 1.25, 1] }}
              transition={{ delay: 0.2, duration: 0.7 }}
              className="bg-gradient-to-b from-amber-200 to-amber-500 bg-clip-text font-display text-7xl font-black text-transparent"
            >
              {reward.days}
            </motion.p>
            <p className="font-mono text-micro uppercase tracking-wider text-amber-300">дней подряд</p>
            <p className="mt-2 font-display text-xl font-bold leading-tight text-ink-chalk">Спасибо, что ты с нами!</p>
            <p className="mt-1 text-sm text-ink-mist">Памятный подарок уже у тебя:</p>
            <div className="mt-3 flex flex-col gap-1.5 text-sm">
              {!!r.coins && (
                <span className="flex items-center justify-center gap-1.5 rounded-xl bg-white/5 py-2 font-bold text-accent-lime">
                  +{r.coins.toLocaleString("ru-RU")} <IconCoin size={14} />
                </span>
              )}
              {(r.cards ?? []).map((c) => (
                <span key={c.id} className="rounded-xl bg-white/5 py-2">
                  <b className={RARITY_TEXT[c.player.rarity]}>{RARITY_LABELS[c.player.rarity]}</b> карта · {c.player.display_name}
                </span>
              ))}
              {r.pack_name && <span className="rounded-xl bg-white/5 py-2">Пак «{r.pack_name}»</span>}
              {r.badge && (
                <span className="rounded-xl bg-white/5 py-2">
                  {r.badge.icon} Значок «{r.badge.name}»
                </span>
              )}
              {r.cosmetic && <span className="rounded-xl bg-white/5 py-2">«{r.cosmetic.name}»</span>}
            </div>
            <button
              onClick={() => seen.mutate(reward.id)}
              disabled={seen.isPending}
              className="animate-claim-glow mt-5 w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
            >
              Ура!
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
