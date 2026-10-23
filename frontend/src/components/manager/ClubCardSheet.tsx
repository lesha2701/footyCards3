import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";

import { buyManagerMerch, fetchManagerClubCard, type ManagerClubCard } from "@/api/manager";
import { IconCoin } from "@/components/icons";
import { themeClass } from "@/lib/managerLook";
import { eur } from "@/lib/managerMoney";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

import Emblem, { KitShirt } from "./Emblem";

/** Another club's card (opened from the league table): style, division,
 * fans and its merchandise — buying it burns coins and brings that club
 * euros. */
export default function ClubCardSheet({ clubId, onClose, onError }: { clubId: number | null; onClose: () => void; onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data } = useQuery({ queryKey: ["manager", "club", clubId], queryFn: () => fetchManagerClubCard(clubId!), enabled: clubId != null });
  const buy = useMutation({
    mutationFn: (code: string) => buyManagerMerch(clubId!, code),
    onSuccess: (card: ManagerClubCard, code: string) => {
      hapticNotify("success");
      queryClient.setQueryData(["manager", "club", clubId], card);
      const item = card.merch.find((m) => m.code === code);
      if (user && item) updateBalance(user.balance - item.coins);
      void queryClient.invalidateQueries({ queryKey: ["manager"], exact: true });
    },
    onError,
  });
  return (
    <AnimatePresence>
      {clubId != null && (
        <motion.div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm" initial={{ opacity: 0 }}
          animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div className={`w-full max-w-lg rounded-t-3xl bg-bg-surface bg-gradient-to-br p-4 pb-8 ${data ? themeClass(data.look.theme) : ""}`} initial={{ y: 60 }} animate={{ y: 0 }} exit={{ y: 60 }}
            onClick={(e) => e.stopPropagation()} data-testid="club-card">
            {!data ? <p className="py-8 text-center text-sm text-ink-mist">Загрузка…</p> : (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-3">
                  <Emblem look={data.look} size={60} />
                  <KitShirt look={data.look} size={44} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-display text-lg font-bold text-ink-chalk">
                      {data.name}
                      {data.pro && <span className="ml-1.5 rounded bg-amber-400 px-1.5 py-0.5 align-middle text-micro font-black text-bg-base">PRO</span>}
                    </span>
                    <span className="block truncate text-xs text-ink-mist">
                      {data.owner_name} · {data.division_name}{data.titles > 0 && ` · 🏆 ${data.titles}`}
                    </span>
                    {data.stadium_name && <span className="block truncate text-xs text-ink-mist">🏟 {data.stadium_name}</span>}
                  </span>
                </div>
                <p className="text-xs text-ink-mist">Рейтинг состава <b className="text-ink-chalk">{data.rating}</b> · болельщиков <b className="text-ink-chalk">{data.fans}</b></p>
                <div className="flex flex-wrap gap-1">
                  {data.xi.map((p) => (
                    <span key={p.slot} className={`rounded px-1.5 py-0.5 text-micro ${p.kind === "own" || p.kind === "live" ? "bg-accent-cyan/20 text-ink-chalk" : "bg-bg-raised text-ink-mist"}`}>
                      {p.position} {p.name} {p.rating}
                    </span>
                  ))}
                </div>
                {!data.is_mine && (
                  <div className="flex flex-col gap-2">
                    <p className="text-xs font-bold text-ink-chalk">Стань болельщиком — купи мерч</p>
                    <div className="grid grid-cols-3 gap-2">
                      {data.merch.map((m) => (
                        <button key={m.code} disabled={m.bought || buy.isPending} onClick={() => buy.mutate(m.code)}
                          className={`flex flex-col items-center gap-0.5 rounded-xl p-2 ${m.bought ? "bg-accent-lime/15 ring-1 ring-accent-lime" : "bg-bg-raised"}`}>
                          <span className="text-2xl">{m.emoji}</span>
                          <span className="text-micro text-ink-chalk">{m.name}</span>
                          {m.bought ? <span className="text-micro text-accent-lime">куплено</span> : (
                            <span className="flex items-center gap-0.5 text-micro font-bold text-ink-chalk">{m.coins} <IconCoin className="h-3 w-3" /></span>
                          )}
                          <span className="text-[9px] text-ink-mist">клубу +{eur(m.eur)}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
