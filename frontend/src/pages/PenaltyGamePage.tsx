import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import { claimPenaltyReward, kickPenalty, startPenalty } from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import {
  IconBall,
  IconChevronLeft,
  IconChevronRight,
  IconChevronUp,
  IconClose,
  IconCoin,
  IconFlagCheckered,
  IconGloves,
  IconTrophy,
  type IconProps,
} from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { PenaltyDirection, PenaltyKickResult } from "@/types";

type Phase = "pick_card" | "playing" | "finished";

const DIRECTIONS: { value: PenaltyDirection; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { value: "left", label: "Лево", Icon: IconChevronLeft },
  { value: "center", label: "Центр", Icon: IconChevronUp },
  { value: "right", label: "Право", Icon: IconChevronRight },
];

const OUTCOME: Record<string, { label: string; Icon: (props: IconProps) => JSX.Element; className: string }> = {
  goal: { label: "Гол!", Icon: IconBall, className: "text-accent-green" },
  saved: { label: "Отбито", Icon: IconGloves, className: "text-accent-cyan" },
  miss: { label: "Мимо", Icon: IconClose, className: "text-ink-mist" },
};

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
        <h1 className="font-display text-xl font-bold text-ink-chalk">Пенальти</h1>
        <p className="text-sm text-ink-mist">
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
        {lastKick?.result === "win" ? (
          <IconTrophy size={40} className="text-accent-lime" />
        ) : (
          <IconFlagCheckered size={40} className="text-ink-mist" />
        )}
        <p className="font-display text-2xl font-bold text-ink-chalk">
          {lastKick?.result === "win" ? "Победа!" : "Поражение"}
        </p>
        <p className="text-sm text-ink-mist">
          Счёт: <span className="font-mono font-bold text-accent-cyan">{lastKick?.player_score} : {lastKick?.bot_score}</span>
        </p>

        {!claimResult ? (
          <button
            onClick={() => claimMutation.mutate()}
            disabled={claimMutation.isPending}
            className="rounded-2xl bg-floodlight px-6 py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
          >
            {claimMutation.isPending ? "Начисление..." : "Забрать награду"}
          </button>
        ) : (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              +{claimResult.reward_coins}
              <IconCoin size={16} />
            </p>
          </div>
        )}

        <div className="flex gap-3">
          <button onClick={() => setPhase("pick_card")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Ещё раз
          </button>
          <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
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
      <p className="text-sm text-ink-mist">
        Счёт: <span className="font-mono font-bold text-accent-cyan">{lastKick?.player_score ?? 0} : {lastKick?.bot_score ?? 0}</span>
      </p>

      <AnimatePresence mode="wait">
        {lastKick && (
          <motion.div
            key={lastKick.player_score + lastKick.bot_score + lastKick.outcome}
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center gap-2 rounded-2xl bg-bg-surface px-6 py-4 text-center"
          >
            {(() => {
              const outcome = OUTCOME[lastKick.outcome];
              const OutcomeIcon = outcome.Icon;
              return (
                <>
                  <OutcomeIcon size={28} className={outcome.className} />
                  <p className="font-display text-xl font-bold text-ink-chalk">{outcome.label}</p>
                </>
              );
            })()}
          </motion.div>
        )}
      </AnimatePresence>

      <p className="text-sm font-semibold text-ink-mist">{roleLabel}</p>

      <div className="grid grid-cols-3 gap-3">
        {DIRECTIONS.map((d) => (
          <button
            key={d.value}
            onClick={() => kickMutation.mutate(d.value)}
            disabled={kickMutation.isPending}
            className="flex flex-col items-center gap-1.5 rounded-2xl bg-bg-surface px-4 py-4 text-sm font-semibold text-ink-chalk active:scale-90 disabled:opacity-40"
          >
            <d.Icon size={18} />
            {d.label}
          </button>
        ))}
      </div>
    </div>
  );
}
