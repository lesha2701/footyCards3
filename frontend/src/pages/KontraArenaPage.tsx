import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  fetchKontraArena, fetchKontraDefense, fetchKontraHub, kontraRevenge, markKontraDefenseSeen, refreshKontraArena,
  setKontraTactic, startKontraArena,
} from "@/api/kontra";
import { IconChevronLeft, IconCoin, IconTrophy } from "@/components/icons";
import FighterCard from "@/components/kontra/FighterCard";
import LeagueCard from "@/components/kontra/LeagueCard";
import TacticPicker from "@/components/kontra/TacticPicker";
import { tacticVerdict } from "@/components/kontra/kontraMeta";
import { formatGameError } from "@/lib/errors";
import { hapticSelection } from "@/lib/telegram";
import type { KontraArena, KontraBattle, KontraTacticCode } from "@/types";

/** Arena: your tactic, the weekly league, three defence squads to attack
 *  (players near your rating, bots when there aren't enough) and the
 *  defence log — whoever beat your squad can be paid back once. */
export default function KontraArenaPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const { data: arena } = useQuery({ queryKey: ["kontra-arena"], queryFn: fetchKontraArena });
  const { data: hub } = useQuery({ queryKey: ["kontra-hub"], queryFn: fetchKontraHub });
  const { data: log } = useQuery({ queryKey: ["kontra-defense"], queryFn: fetchKontraDefense, enabled: logOpen });

  const apply = (a: KontraArena) => queryClient.setQueryData(["kontra-arena"], a);
  const refresh = useMutation({ mutationFn: refreshKontraArena, onSuccess: apply });
  const tactic = useMutation({
    mutationFn: (code: KontraTacticCode | null) => setKontraTactic(code),
    onSuccess: (squad) => {
      queryClient.setQueryData(["kontra-squad"], squad);
      queryClient.invalidateQueries({ queryKey: ["kontra-arena"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось сменить тактику")),
  });
  const revenge = useMutation({
    mutationFn: (battleId: number) => kontraRevenge(battleId),
    onSuccess: (a) => {
      apply(a);
      setLogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["kontra-defense"] });
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    onError: (err) => setError(formatGameError(err, "Реванш недоступен")),
  });
  const start = useMutation({
    mutationFn: ({ offer, manual }: { offer: number; manual: boolean }) => startKontraArena(offer, manual),
    onSuccess: (b: KontraBattle) => {
      queryClient.invalidateQueries({ queryKey: ["kontra-arena"] });
      queryClient.invalidateQueries({ queryKey: ["kontra-hub"] });
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      queryClient.setQueryData(["kontra-battle", b.id], b);
      navigate(`/play/kontra/battles/${b.id}`, { state: { play: true } });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось начать бой")),
  });

  const openLog = () => {
    hapticSelection();
    setLogOpen(true);
    if (arena?.defense_unread) {
      markKontraDefenseSeen().then(() => {
        queryClient.invalidateQueries({ queryKey: ["kontra-hub"] });
        queryClient.setQueryData<KontraArena>(["kontra-arena"], (a) => (a ? { ...a, defense_unread: 0 } : a));
      }).catch(() => undefined);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <button onClick={() => navigate("/play/kontra")} className="flex items-center gap-1 self-start text-xs text-ink-mist">
        <IconChevronLeft size={16} /> Контратака
      </button>
      <div className="flex items-center justify-between gap-2">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Арена</h1>
        <div className="flex items-center gap-1.5">
          <button onClick={openLog} className="relative rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-ink-chalk active:scale-95">
            🛡 Защита
            {arena?.defense_unread ? (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-black text-white">{arena.defense_unread}</span>
            ) : null}
          </button>
          <button onClick={() => navigate("/ranking?metric=kontra_rating")} className="flex items-center gap-1 rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-amber-300">
            <IconTrophy size={13} /> {arena?.rating ?? "—"}{arena?.rank ? ` · #${arena.rank}` : ""}
          </button>
        </div>
      </div>

      {hub?.active_battle_id && (
        <button onClick={() => navigate(`/play/kontra/battles/${hub.active_battle_id}`)}
          className="rounded-2xl bg-amber-400 px-3 py-2.5 text-sm font-black text-bg-base active:scale-95">
          ⚔ У тебя незаконченный бой — доиграть
        </button>
      )}

      {arena?.league && <LeagueCard league={arena.league} />}

      {arena && (
        <TacticPicker
          tactics={arena.tactics} current={arena.tactic?.code ?? null} edge={arena.tactic_edge_pct}
          busy={tactic.isPending} onPick={(code) => tactic.mutate(code)}
        />
      )}

      {arena && (
        <p className="text-caption text-ink-mist-dim">
          Победа +{arena.rating_win} рейтинга и {arena.reward_win} <IconCoin size={10} className="inline" />, поражение −{arena.rating_loss}.
          Наградных боёв сегодня {arena.rewarded_today}/{arena.daily_limit}. Твой отряд и тактика — это и твоя защита.
        </p>
      )}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {arena?.offers.map((o) => {
        const verdict = tacticVerdict(arena.tactic, o.tactic);
        return (
          <motion.section key={`${o.index}-${o.name}`} layout
            className={`rounded-2xl p-3 ${o.revenge ? "bg-gradient-to-br from-red-950/80 to-bg-surface ring-2 ring-red-500/60" : "bg-bg-surface"}`}>
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="min-w-0 truncate font-display text-sm font-bold text-ink-chalk">
                {o.revenge && <span className="mr-1 text-red-300">⚔ Реванш ·</span>}{o.name}{o.is_bot ? " · бот" : ""}
              </span>
              <span className="shrink-0 font-mono text-xs text-ink-mist">⚡ {o.power.toLocaleString("ru-RU")} · ★ {o.rating}</span>
            </div>
            <div className="grid grid-cols-5 gap-1">
              {o.cards.map((c, i) => <FighterCard key={c.card_id} card={c} foe edge={i === 0 ? "left" : i === o.cards.length - 1 ? "right" : undefined} />)}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-micro">
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-ink-mist">Тактика: <b className="text-ink-chalk">{o.tactic?.name ?? "без схемы"}</b></span>
              {verdict === "win" && <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 font-bold text-emerald-300">твоя бьёт · +{arena.tactic_edge_pct}% урона</span>}
              {verdict === "lose" && <span className="rounded-full bg-red-500/15 px-2 py-0.5 font-bold text-red-300">их тактика бьёт твою</span>}
              {o.revenge && <span className="rounded-full bg-red-500/15 px-2 py-0.5 font-bold text-red-200">победа ×1.5 рейтинга</span>}
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button onClick={() => start.mutate({ offer: o.index, manual: false })} disabled={start.isPending} className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-chalk active:scale-95 disabled:opacity-50">
                🤖 Автобой
              </button>
              <button onClick={() => start.mutate({ offer: o.index, manual: true })} disabled={start.isPending} className="rounded-xl bg-amber-400 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-50">
                ⚔ Вручную
              </button>
            </div>
          </motion.section>
        );
      })}
      <button onClick={() => refresh.mutate()} disabled={refresh.isPending} className="rounded-2xl bg-white/5 py-2.5 text-xs font-semibold text-ink-mist active:scale-95">
        Других соперников
      </button>

      <AnimatePresence>
        {logOpen && (
          <motion.div className="fixed inset-0 z-50 flex items-end bg-black/60" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setLogOpen(false)}>
            <motion.div className="max-h-[80vh] w-full overflow-y-auto rounded-t-3xl bg-bg-surface p-4 pb-8"
              initial={{ y: 400 }} animate={{ y: 0 }} exit={{ y: 400 }} transition={{ type: "spring", damping: 26, stiffness: 260 }}
              onClick={(e) => e.stopPropagation()}>
              <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/20" />
              <p className="font-display text-lg font-black text-ink-chalk">🛡 Журнал защиты</p>
              <p className="mb-3 text-caption text-ink-mist">
                Кто атаковал твой отряд за неделю.{log ? ` Отбился: ${log.wins}, пропустил: ${log.losses}.` : ""} Обидчику можно ответить реваншем — один раз за каждое поражение.
              </p>
              {!log && <p className="py-6 text-center text-xs text-ink-mist">Загрузка…</p>}
              {log && !log.items.length && <p className="py-6 text-center text-xs text-ink-mist">Пока никто не нападал — твой отряд в безопасности.</p>}
              <div className="flex flex-col gap-1.5">
                {log?.items.map((it) => (
                  <div key={it.battle_id} className={`flex items-center gap-2 rounded-2xl px-3 py-2 ${it.result === "win" ? "bg-emerald-500/10" : "bg-red-500/10"}`}>
                    <span className="text-xl">{it.result === "win" ? "🛡️" : "💥"}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-bold text-ink-chalk">
                        {it.attacker_name} <span className="font-mono font-normal text-ink-mist">★ {it.attacker_rating}</span>
                        {it.is_new && <span className="ml-1 rounded-full bg-red-500 px-1.5 text-[9px] font-black text-white">новое</span>}
                      </p>
                      <p className="text-micro text-ink-mist">
                        {it.result === "win" ? `Отбился${it.survivors ? ` · в строю ${it.survivors}` : ""}` : "Твой отряд проиграл"} · {timeAgo(it.created_at)}
                      </p>
                    </div>
                    {it.can_revenge && (
                      <button onClick={() => revenge.mutate(it.battle_id)} disabled={revenge.isPending}
                        className="shrink-0 rounded-xl bg-red-500 px-3 py-1.5 text-xs font-black text-white active:scale-95 disabled:opacity-50">
                        Реванш
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function timeAgo(iso: string): string {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (min < 1) return "только что";
  if (min < 60) return `${min} мин назад`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h} ч назад`;
  return `${Math.round(h / 24)} дн назад`;
}
