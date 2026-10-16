import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchMyPlayerDuels, playMyPlayerDuel, type MyPlayerDuel } from "@/api/myPlayer";
import { ListSkeleton } from "@/components/common/Skeleton";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

import PlayerAvatar from "./PlayerAvatar";

const RESULT_TEXT = { win: "Победа", draw: "Ничья", loss: "Поражение" } as const;
const RESULT_COLOR = { win: "text-accent-lime", draw: "text-ink-mist", loss: "text-red-400" } as const;

/** «Дуэли»: your footballer against a friend's — 5 attacks each, attack vs
 * defense, played on the server at once. Daily limit; only the challenger
 * earns coins and XP, the friend gets a notification to answer. */
export default function MyPlayerDuels() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data, isLoading } = useQuery({ queryKey: ["my-player", "duels"], queryFn: fetchMyPlayerDuels });
  const [shown, setShown] = useState<MyPlayerDuel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const play = useMutation({
    mutationFn: (opponentUserId: number) => playMyPlayerDuel(opponentUserId),
    onSuccess: (res) => {
      setError(null);
      queryClient.setQueryData(["my-player", "duels"], res.duels);
      updateBalance(res.balance);
      void queryClient.invalidateQueries({ queryKey: ["my-player"], exact: true });
      setShown(res.duel);
    },
    onError: (err) => setError(formatGameError(err, "Не получилось начать дуэль")),
  });

  if (isLoading || !data) return <ListSkeleton />;
  if (!data.enabled) return <p className="rounded-2xl bg-bg-surface p-6 text-center text-sm text-ink-mist">Дуэли сейчас выключены</p>;

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl bg-gradient-to-br from-accent-cyan/20 to-bg-surface p-4">
        <p className="font-display text-base font-bold text-ink-chalk">Дуэль игроков</p>
        <p className="mt-1 text-caption text-ink-mist">
          {data.attacks} атак у каждого: твоя атака против защиты друга и наоборот. Победа +{data.reward_win} монет, ничья +
          {data.reward_draw}, и +{data.xp} опыта. Усталость тоже играет.
        </p>
        <p className="mt-2 text-xs font-semibold text-ink-chalk">Сегодня осталось: {data.left_today} из {data.per_day}</p>
      </section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      <section className="rounded-2xl bg-bg-surface p-4">
        <h2 className="font-display text-base font-bold text-ink-chalk">Друзья</h2>
        {data.friends.length === 0 ? (
          <div className="mt-2 text-center">
            <p className="text-sm text-ink-mist">Ни у кого из друзей пока нет своего игрока.</p>
            <button onClick={() => navigate("/friends")} className="mt-2 rounded-xl bg-bg-raised px-4 py-2 text-xs font-semibold text-ink-chalk">
              Позвать друзей
            </button>
          </div>
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            {data.friends.map((f) => (
              <div key={f.user_id} className="flex items-center gap-3 rounded-xl bg-bg-raised p-2.5">
                <span className="h-11 w-11 shrink-0 overflow-hidden rounded-lg">
                  <PlayerAvatar appearance={f.player.appearance} accessory={f.player.accessory} backdrop={f.player.background} className="h-full w-full" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-ink-chalk">{f.player.name} · {f.player.rating}</span>
                  <span className="block truncate text-caption text-ink-mist">
                    {f.user_name} · {f.player.position} · АТК {f.player.attack_rating} / ЗЩТ {f.player.defense_rating}
                  </span>
                </span>
                <button
                  disabled={play.isPending || data.left_today <= 0}
                  onClick={() => { haptic("medium"); play.mutate(f.user_id); }}
                  className="shrink-0 rounded-lg bg-floodlight px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
                >
                  Вызвать
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {data.recent.length > 0 && (
        <section className="rounded-2xl bg-bg-surface p-4">
          <h2 className="font-display text-base font-bold text-ink-chalk">Последние дуэли</h2>
          <div className="mt-2 flex flex-col divide-y divide-white/5">
            {data.recent.map((d) => (
              <button key={d.id} onClick={() => setShown(d)} className="flex items-center gap-3 py-2 text-left">
                <span className={`w-20 shrink-0 text-xs font-bold ${RESULT_COLOR[d.result]}`}>{RESULT_TEXT[d.result]}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink-chalk">
                  {d.as_challenger ? "ты → " : "← "}{d.opponent_name}
                </span>
                <span className="font-mono text-sm font-bold text-ink-chalk">{d.my_goals}:{d.opp_goals}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <AnimatePresence>{shown && <DuelReplay duel={shown} onClose={() => setShown(null)} />}</AnimatePresence>
    </div>
  );
}

const OUTCOME = { goal: "⚽ Гол!", save: "🧤 Сейв", miss: "↗ Мимо" } as const;

/** Plays the duel's attacks back one by one, then the score and reward. */
function DuelReplay({ duel, onClose }: { duel: MyPlayerDuel; onClose: () => void }) {
  const [step, setStep] = useState(0);
  const total = duel.events.length;
  useEffect(() => {
    if (step >= total) {
      hapticNotify(duel.result === "loss" ? "warning" : "success");
      return;
    }
    const timer = setTimeout(() => {
      if (duel.events[step].outcome === "goal") haptic("medium");
      setStep((s) => s + 1);
    }, 550);
    return () => clearTimeout(timer);
  }, [step, total, duel]);
  const seen = duel.events.slice(0, step);
  const mine = seen.filter((e) => e.side === "me" && e.outcome === "goal").length;
  const theirs = seen.filter((e) => e.side === "opp" && e.outcome === "goal").length;
  const finished = step >= total;

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/75"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={finished ? onClose : () => setStep(total)}
    >
      <motion.div
        className="w-full max-w-lg rounded-t-3xl bg-bg-surface p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))]"
        initial={{ y: 80 }} animate={{ y: 0 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="grid grid-cols-3 items-center">
          {[duel.me, null, duel.opp].map((side, i) =>
            i === 1 ? (
              <p key="score" className="text-center font-display text-4xl font-black text-ink-chalk" data-testid="duel-score">
                {mine}:{theirs}
              </p>
            ) : (
              <div key={i} className="flex flex-col items-center gap-1">
                <span className="h-16 w-16 overflow-hidden rounded-2xl">
                  {side && <PlayerAvatar appearance={side.appearance} accessory={side.accessory} backdrop={side.background} className="h-full w-full" />}
                </span>
                <span className="max-w-full truncate text-xs font-semibold text-ink-chalk">{side?.name}</span>
                <span className="font-mono text-micro text-ink-mist">{side?.match_rating ?? side?.rating}</span>
              </div>
            ),
          )}
        </div>
        <div className="mt-4 grid max-h-48 grid-cols-2 gap-x-3 gap-y-1 overflow-y-auto text-xs">
          {seen.map((e, i) => (
            <span
              key={i}
              className={`${e.side === "me" ? "col-start-1" : "col-start-2 text-right"} ${e.outcome === "goal" ? "font-bold text-accent-lime" : "text-ink-mist"}`}
            >
              {e.n}. {OUTCOME[e.outcome]}
            </span>
          ))}
        </div>
        {finished ? (
          <div className="mt-4 text-center">
            <p className={`font-display text-2xl font-black ${RESULT_COLOR[duel.result]}`}>{RESULT_TEXT[duel.result]}</p>
            {duel.reward_coins > 0 && <p className="text-sm text-ink-mist">+{duel.reward_coins} монет</p>}
            <button onClick={onClose} className="mt-3 w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base">Готово</button>
          </div>
        ) : (
          <p className="mt-4 text-center text-caption text-ink-mist">Нажми, чтобы пропустить</p>
        )}
      </motion.div>
    </motion.div>
  );
}
