import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  acceptMordoboiChallenge,
  cancelMordoboiChallenge,
  createMordoboiBotMatch,
  createMordoboiChallenge,
  declineMordoboiChallenge,
  fetchMordoboiMatch,
  forfeitMordoboiMatch,
  pickMordoboiAction,
} from "@/api/mordoboi";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import BoxingRing from "@/components/mordoboi/BoxingRing";
import { ACTION_META, ACTION_ORDER, WIN_REASON_LABELS, describeExchange } from "@/components/mordoboi/mordoboiMeta";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { MordoboiAction, MordoboiExchange, MordoboiMatch } from "@/types";

const RESULT_TITLES: Record<string, string> = { win: "Победа!", draw: "Ничья", loss: "Поражение" };
const OPPONENT_LABELS: Record<string, string> = { bot: "Бот", friend: "Друг", online: "Онлайн" };

export default function MordoboiMatchPage() {
  const { matchId } = useParams();
  const id = Number(matchId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [hit, setHit] = useState<MordoboiExchange | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [confirmForfeit, setConfirmForfeit] = useState(false);
  const seenN = useRef<number | null>(null);
  const seenStatus = useRef<string | null>(null);

  const { data: match, isLoading, isError } = useQuery({
    queryKey: ["mordoboi-match", id],
    queryFn: () => fetchMordoboiMatch(id),
    // Polling while waiting on the other side also keeps the server's lazy
    // deadline sweep running (see mordoboi_service._sweep).
    refetchInterval: (q) => {
      const m = q.state.data as MordoboiMatch | undefined;
      if (!m) return false;
      if (m.status === "pending_accept") return 5000;
      if (m.status !== "in_progress" || m.can_pick) return false;
      return m.live ? 1500 : 4000;
    },
  });

  // Animate exchanges we haven't shown yet; open the result when the bout ends here.
  useEffect(() => {
    if (!match) return;
    const lastN = match.log.length ? match.log[match.log.length - 1].n : 0;
    if (seenN.current === null) {
      seenN.current = lastN;
      seenStatus.current = match.status;
      if (match.status === "finished") setShowResult(true);
      return;
    }
    if (lastN > seenN.current) {
      const latest = match.log[match.log.length - 1];
      setHit(latest);
      if (latest.opponent_damage > latest.my_damage) hapticNotify("error");
      else haptic(latest.my_damage > 0 ? "heavy" : "light");
      seenN.current = lastN;
    }
    if (seenStatus.current !== "finished" && match.status === "finished") {
      const t = setTimeout(() => setShowResult(true), 900);
      hapticNotify(match.result === "win" ? "success" : match.result === "loss" ? "error" : "warning");
      seenStatus.current = match.status;
      return () => clearTimeout(t);
    }
    seenStatus.current = match.status;
  }, [match]);

  useEffect(() => {
    if (!hit) return;
    const t = setTimeout(() => setHit(null), 1600);
    return () => clearTimeout(t);
  }, [hit]);

  const setMatch = (m: MordoboiMatch) => {
    queryClient.setQueryData(["mordoboi-match", id], m);
    queryClient.invalidateQueries({ queryKey: ["mordoboi-matches"] });
    if (m.status === "finished") {
      queryClient.invalidateQueries({ queryKey: ["mordoboi-info"] });
      queryClient.invalidateQueries({ queryKey: ["mordoboi-stats"] });
    }
  };
  const pick = useMutation({
    mutationFn: ({ action, version }: { action: MordoboiAction; version: number }) => pickMordoboiAction(id, action, version),
    onSuccess: (m) => { setError(null); setMatch(m); },
    onError: (err) => {
      hapticNotify("error");
      setError(formatGameError(err, "Удар не принят"));
      queryClient.invalidateQueries({ queryKey: ["mordoboi-match", id] });
    },
  });
  const action = useMutation({
    mutationFn: (kind: "accept" | "decline" | "cancel" | "forfeit") =>
      ({ accept: acceptMordoboiChallenge, decline: declineMordoboiChallenge, cancel: cancelMordoboiChallenge, forfeit: forfeitMordoboiMatch })[kind](id),
    onSuccess: (m) => { setError(null); setMatch(m); queryClient.invalidateQueries({ queryKey: ["game-limits"] }); },
    onError: (err) => setError(formatGameError(err, "Не получилось")),
  });
  const rematch = useMutation({
    mutationFn: (m: MordoboiMatch) =>
      m.opponent_type === "friend" && m.opponent_user_id
        ? createMordoboiChallenge(m.opponent_user_id)
        : createMordoboiBotMatch(m.difficulty === "easy" ? "easy" : "hard"),
    onSuccess: (m) => {
      setShowResult(false);
      seenN.current = null;
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      navigate(`/play/mordoboi/matches/${m.id}`, { replace: true });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось начать бой")),
  });

  if (isLoading) return <LoadingScreen />;
  if (isError || !match || !match.me) return <ErrorScreen message="Бой не найден" />;

  const inPlay = match.status === "in_progress";
  const pending = match.status === "pending_accept";
  const totals = match.scorecards.reduce((a, c) => ({ mine: a.mine + c.mine, opponent: a.opponent + c.opponent }), { mine: 0, opponent: 0 });
  const recent = [...match.log].reverse().slice(0, 6);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate("/play/mordoboi")} className="flex items-center gap-1 text-xs text-ink-mist active:scale-95">
          <IconChevronLeft size={16} />
          Мордобой
        </button>
        <span className="rounded-full bg-white/5 px-2.5 py-1 text-micro font-semibold text-ink-mist">
          {OPPONENT_LABELS[match.opponent_type]}
          {match.difficulty === "easy" ? " · лёгкий" : ""} · {match.opponent_name}
        </span>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="font-display text-lg font-bold text-ink-chalk">
          {inPlay ? `Раунд ${match.round} из ${match.rounds}` : pending ? "Вызов" : "Бой окончен"}
        </h1>
        {inPlay && (
          <div className="flex gap-1" aria-label={`Обмен ${match.exchange} из ${match.exchanges_per_round}`}>
            {Array.from({ length: match.exchanges_per_round }, (_, i) => (
              <span key={i} className={`h-2 w-5 rounded-full ${i < match.exchange - 1 ? "bg-yellow-400" : i === match.exchange - 1 ? "bg-yellow-400/50" : "bg-white/10"}`} />
            ))}
          </div>
        )}
      </div>

      <BoxingRing me={match.me} opponent={match.opponent} hit={hit} />

      {match.scorecards.length > 0 && (
        <div className="flex items-center justify-between rounded-2xl bg-bg-surface px-4 py-2 text-xs text-ink-mist">
          <span>Судьи</span>
          <span className="flex gap-2 font-mono">
            {match.scorecards.map((c, i) => (
              <span key={i} className="rounded bg-white/5 px-1.5">{c.mine}:{c.opponent}</span>
            ))}
            <span className="font-bold text-ink-chalk">= {totals.mine}:{totals.opponent}</span>
          </span>
        </div>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {pending && (
        match.viewer_side === "opponent" ? (
          <div className="flex gap-2">
            <button onClick={() => action.mutate("accept")} disabled={action.isPending} className="flex-1 rounded-2xl bg-yellow-500 py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50">
              Выйти на ринг
            </button>
            <button onClick={() => action.mutate("decline")} disabled={action.isPending} className="flex-1 rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95">
              Отказаться
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4 text-center">
            <p className="text-sm text-ink-chalk">Ждём, когда {match.opponent_name} примет вызов…</p>
            <button onClick={() => action.mutate("cancel")} disabled={action.isPending} className="text-xs text-ink-mist underline">
              Отменить вызов
            </button>
          </div>
        )
      )}

      {inPlay && (
        <>
          {match.can_pick ? (
            <div className="grid grid-cols-5 gap-1.5">
              {ACTION_ORDER.map((a) => {
                const meta = ACTION_META[a];
                const allowed = match.available_actions.includes(a);
                return (
                  <motion.button
                    key={a}
                    whileTap={{ scale: 0.9 }}
                    onClick={() => pick.mutate({ action: a, version: match.version })}
                    disabled={!allowed || pick.isPending}
                    aria-label={meta.label}
                    className={`flex flex-col items-center gap-0.5 rounded-2xl bg-gradient-to-b px-1 py-2.5 ring-1 disabled:opacity-30 ${meta.tone}`}
                  >
                    <span className="text-2xl leading-none">{meta.emoji}</span>
                    <span className="text-micro font-bold text-ink-chalk">{meta.label}</span>
                  </motion.button>
                );
              })}
            </div>
          ) : (
            <motion.div
              className="rounded-2xl bg-bg-surface px-4 py-3 text-center text-sm text-ink-mist"
              animate={{ opacity: [0.6, 1, 0.6] }}
              transition={{ repeat: Infinity, duration: 1.6 }}
            >
              {match.my_pick ? `Ты выбрал: ${ACTION_META[match.my_pick].label}. Ждём соперника…` : "Ждём соперника…"}
            </motion.div>
          )}
          <p className="text-center text-caption text-ink-mist-dim">
            {match.can_pick && match.opponent_ready ? "Соперник уже выбрал — твоя очередь. " : ""}
            {match.deadline ? `Ход до ${new Date(match.deadline).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: match.live ? "2-digit" : undefined })}` : ""}
            {match.my_auto_moves > 0 ? ` · автопилот ${match.my_auto_moves}/${match.max_auto_moves}` : ""}
          </p>
        </>
      )}

      {recent.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <h2 className="font-mono text-caption uppercase tracking-wider text-ink-mist">Обмены</h2>
          {recent.map((e) => {
            const d = describeExchange(e);
            return (
              <div key={e.n} className="rounded-xl bg-bg-surface px-3 py-2 text-caption">
                <div className="mb-0.5 flex justify-between text-micro text-ink-mist-dim">
                  <span>Раунд {e.round} · обмен {e.exchange}</span>
                  <span className="font-mono">{e.my_hp} : {e.opponent_hp} HP</span>
                </div>
                <p className="text-ink-chalk">Ты: {d.mine}</p>
                <p className="text-ink-mist">Соперник: {d.theirs}</p>
              </div>
            );
          })}
        </div>
      )}

      {inPlay && (
        <button onClick={() => setConfirmForfeit(true)} className="mt-1 text-center text-xs text-ink-mist-dim underline">
          Выбросить полотенце
        </button>
      )}
      {!inPlay && !pending && !showResult && match.status === "finished" && (
        <button onClick={() => setShowResult(true)} className="rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95">
          Итог боя
        </button>
      )}

      <ConfirmDialog
        open={confirmForfeit}
        title="Сдаться?"
        description="Бой засчитают поражением без награды."
        danger
        confirmLabel="Сдаться"
        onConfirm={() => { setConfirmForfeit(false); action.mutate("forfeit"); }}
        onCancel={() => setConfirmForfeit(false)}
      />

      <AnimatePresence>
        {showResult && match.status === "finished" && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowResult(false)}
          >
            <motion.div
              className="w-full max-w-sm rounded-3xl bg-bg-base p-6 text-center"
              initial={{ scale: 0.7, rotate: -4 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: "spring", stiffness: 260, damping: 18 }}
              onClick={(e) => e.stopPropagation()}
            >
              <p className="text-5xl">{match.result === "win" ? "🏆" : match.result === "loss" ? "🤕" : "🤝"}</p>
              <p className="mt-2 font-display text-2xl font-black text-ink-chalk">{RESULT_TITLES[match.result ?? "draw"]}</p>
              <p className="text-sm text-yellow-400">{WIN_REASON_LABELS[match.win_reason ?? ""] ?? ""}</p>
              {match.scorecards.length > 0 && (
                <p className="mt-1 font-mono text-xs text-ink-mist">Судьи: {totals.mine}:{totals.opponent}</p>
              )}
              <div className="mt-4 flex justify-center gap-4 text-sm">
                <span className="flex items-center gap-1 font-bold text-ink-chalk">
                  +{match.reward_coins} <IconCoin size={14} />
                </span>
                {match.rating_delta !== 0 && (
                  <span className={match.rating_delta > 0 ? "font-bold text-accent-green" : "font-bold text-red-400"}>
                    {match.rating_delta > 0 ? "+" : ""}{match.rating_delta} рейтинга
                  </span>
                )}
              </div>
              <div className="mt-5 flex gap-2">
                {match.opponent_type !== "online" && (
                  <button
                    onClick={() => rematch.mutate(match)}
                    disabled={rematch.isPending}
                    className="flex-1 rounded-2xl bg-yellow-500 py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
                  >
                    Реванш
                  </button>
                )}
                <button onClick={() => navigate("/play/mordoboi")} className="flex-1 rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95">
                  К режиму
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
