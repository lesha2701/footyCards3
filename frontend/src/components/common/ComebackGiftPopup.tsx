import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";

import { IconCoin, IconGift } from "@/components/icons";
import { api } from "@/lib/api";
import { hapticNotify } from "@/lib/telegram";
import type { GrantedRewards } from "@/types";

interface ComebackGift {
  id: number;
  days_away: number;
  rewards: Partial<GrantedRewards>;
}

/** «Подарок за возвращение»: what the server already granted on this visit
 * (comeback_gift_service), shown once. */
export default function ComebackGiftPopup() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["comeback-gifts"],
    queryFn: async () => (await api.get<ComebackGift[]>("/comeback-gifts/unseen")).data,
    staleTime: 60_000,
  });
  const seen = useMutation({
    mutationFn: (id: number) => api.post(`/comeback-gifts/${id}/seen`),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["comeback-gifts"] });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
  const gift = data?.[0];
  const r = gift?.rewards ?? {};

  return (
    <AnimatePresence>
      {gift && (
        <motion.div
          key={gift.id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onAnimationComplete={() => hapticNotify("success")}
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/75 px-6 backdrop-blur-sm"
        >
          <motion.div
            initial={{ scale: 0.6, y: 40 }}
            animate={{ scale: 1, y: 0 }}
            transition={{ type: "spring", damping: 14, stiffness: 180 }}
            className="w-full max-w-sm rounded-3xl bg-bg-surface p-6 text-center shadow-2xl ring-2 ring-accent-lime/40"
          >
            <span className="mx-auto flex h-20 w-20 items-center justify-center rounded-3xl bg-accent-lime/15 text-accent-lime">
              <IconGift size={40} />
            </span>
            <p className="mt-4 font-display text-xl font-bold leading-tight text-ink-chalk">С возвращением!</p>
            <p className="mt-1 text-sm text-ink-mist">Тебя не было {gift.days_away} дн. Мы скучали — держи подарок:</p>
            <div className="mt-3 flex flex-col gap-1.5 text-sm">
              {!!r.coins && (
                <span className="flex items-center justify-center gap-1.5 rounded-xl bg-white/5 py-2 font-bold text-accent-lime">
                  +{r.coins.toLocaleString("ru-RU")} <IconCoin size={14} />
                </span>
              )}
              {r.pack_name && <span className="rounded-xl bg-white/5 py-2 text-ink-chalk">Пак «{r.pack_name}»</span>}
            </div>
            <button
              onClick={() => seen.mutate(gift.id)}
              disabled={seen.isPending}
              className="animate-claim-glow mt-5 w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
            >
              Забрать
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
