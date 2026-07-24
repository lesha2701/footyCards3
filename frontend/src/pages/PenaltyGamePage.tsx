import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import { claimPenaltyReward, kickPenalty, startPenalty } from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { PenaltyDirection, PenaltyKickResult } from "@/types";

type Phase = "pick_card" | "playing" | "finished";

const DIRECTIONS: { value: PenaltyDirection; label: string }[] = [
  { value: "left", label: "⬅️ Лево" },
  { value: "center", label: "⬆️ Центр" },
  { value: "right", label: "➡️ Право" },
];

const OUTCOME_LABELS: Record<string, string> = { goal: "⚽ Гол!", saved: "🧤 Отбито", miss: "❌ Мимо" };

export default function PenaltyGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("pick_card");
  const [lastKick, setLastKick] = useState<PenaltyKickResult | null>(null);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: collection } = useQuery({
    queryKey: ["collection", "penalty"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
  });

  const startMutation = useMutation({
    mutationFn: startPenalty,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setLastKick(null);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать игру")),
  });

  const kickMutation = useMutation({
    mutationFn: (direction: PenaltyDirection) => kickPenalty(sessionId!, direction),
    onSuccess: (result) => {
      haptic(result.outcome === "goal" || result.outcome === "saved" ? "medium" : "light");
      setLastKick(result);
      if (result.is_finished) {
        hapticNotify(result.result === "win" ? "success" : "error");
        setPhase("finished");
      }
    },
  });

  const claimMutation = useMutation({
    mutationFn: () => claimPenaltyReward(sessionId!),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimResult(data);
    },
  });

  if (phase === "pick_card") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-2xl font-bold text-slate-100">🥅 Пенальти</h1>
        <p className="text-sm text-slate-400">
          Выбери игрока для серии пенальти. Чем выше его рейтинг, тем меньше шанс промазать по воротам.
        </p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <CardPickerModal
          open
          title="Выбери игрока"
          cards={collection?.items ?? []}
          onSelect={(card) => startMutation.mutate(card.id)}
          onClose={() => navigate("/play")}
        />
      </div>
    );
  }

  if (phase === "finished") {
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        <p className="text-5xl">{lastKick?.result === "win" ? "🏆" : "😔"}</p>
        <p className="font-display text-2xl font-bold text-slate-100">
          {lastKick?.result === "win" ? "Победа!" : "Поражение"}
        </p>
        <p className="text-sm text-slate-400">
          Счёт: <span className="font-bold text-amber-300">{lastKick?.player_score} : {lastKick?.bot_score}</span>
        </p>

        {!claimResult ? (
          <button
            onClick={() => claimMutation.mutate()}
            disabled={claimMutation.isPending}
            className="rounded-2xl bg-accent px-6 py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
          >
            {claimMutation.isPending ? "Начисление..." : "Забрать награду"}
          </button>
        ) : (
          <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-5 py-3">
            <p className="font-display text-lg font-bold text-emerald-400">+{claimResult.reward_coins} 🪙</p>
          </div>
        )}

        <div className="flex gap-3">
          <button onClick={() => setPhase("pick_card")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-slate-300">
            Ещё раз
          </button>
          <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-slate-300">
            Назад
          </button>
        </div>
      </div>
    );
  }

  const roleLabel = kickMutation.isPending
    ? "..."
    : lastKick?.next_kicker === "bot"
      ? "Бот бьёт — угадай направление"
      : "Твой удар — выбери направление";

  return (
    <div className="flex flex-col items-center gap-6 py-6">
      <p className="text-sm text-slate-400">
        Счёт: <span className="font-bold text-amber-300">{lastKick?.player_score ?? 0} : {lastKick?.bot_score ?? 0}</span>
      </p>

      <AnimatePresence mode="wait">
        {lastKick && (
          <motion.div
            key={lastKick.player_score + lastKick.bot_score + lastKick.outcome}
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ opacity: 0 }}
            className="rounded-2xl bg-bg-surface px-6 py-4 text-center"
          >
            <p className="font-display text-xl font-bold text-slate-100">{OUTCOME_LABELS[lastKick.outcome]}</p>
          </motion.div>
        )}
      </AnimatePresence>

      <p className="text-sm font-semibold text-slate-300">{roleLabel}</p>

      <div className="grid grid-cols-3 gap-3">
        {DIRECTIONS.map((d) => (
          <button
            key={d.value}
            onClick={() => kickMutation.mutate(d.value)}
            disabled={kickMutation.isPending}
            className="rounded-2xl bg-bg-surface px-4 py-4 text-sm font-semibold text-slate-200 active:scale-90 disabled:opacity-40"
          >
            {d.label}
          </button>
        ))}
      </div>
    </div>
  );
}
