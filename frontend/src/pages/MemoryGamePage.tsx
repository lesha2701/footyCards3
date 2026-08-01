import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimMemoryReward, fetchMemoryLeaderboard, startMemoryGame, submitMemoryRound } from "@/api/games";
import {
  IconBall,
  IconBoot,
  IconCard,
  IconCoin,
  IconFire,
  IconFlag,
  IconGloves,
  IconGoal,
  IconTarget,
  IconTrophy,
  type IconProps,
} from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { MemoryStart } from "@/types";

// Values must match backend/app/services/memory_game_service.py SYMBOLS exactly —
// the server generates/validates sequences using these emoji as opaque IDs.
const SYMBOLS = ["⚽", "🥅", "🟨", "🟥", "👟", "🧤", "🏆", "🚩", "🎯", "🔥"];

const SYMBOL_ICON: Record<string, { Icon: (props: IconProps) => JSX.Element; className: string }> = {
  "⚽": { Icon: IconBall, className: "text-ink-chalk" },
  "🥅": { Icon: IconGoal, className: "text-accent-cyan" },
  "🟨": { Icon: IconCard, className: "text-amber-400" },
  "🟥": { Icon: IconCard, className: "text-red-500" },
  "👟": { Icon: IconBoot, className: "text-ink-chalk" },
  "🧤": { Icon: IconGloves, className: "text-accent-cyan" },
  "🏆": { Icon: IconTrophy, className: "text-accent-lime" },
  "🚩": { Icon: IconFlag, className: "text-red-500" },
  "🎯": { Icon: IconTarget, className: "text-accent-lime" },
  "🔥": { Icon: IconFire, className: "text-orange-400" },
};

function SymbolIcon({ symbol, size }: { symbol: string; size: number }) {
  const entry = SYMBOL_ICON[symbol];
  if (!entry) return null;
  const { Icon, className } = entry;
  return <Icon size={size} className={className} />;
}

type Phase = "idle" | "showing" | "input" | "gameover";

export default function MemoryGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();

  const [session, setSession] = useState<MemoryStart | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [input, setInput] = useState<string[]>([]);
  const [score, setScore] = useState(0);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number; new_best_score: boolean } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: leaderboard } = useQuery({ queryKey: ["memory-leaderboard"], queryFn: fetchMemoryLeaderboard });

  const startMutation = useMutation({
    mutationFn: startMemoryGame,
    onSuccess: (data) => {
      setSession(data);
      setScore(0);
      setInput([]);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("showing");
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать игру")),
  });

  const claimMutation = useMutation({
    mutationFn: (sessionId: number) => claimMemoryReward(sessionId),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      setClaimResult(data);
      queryClient.invalidateQueries({ queryKey: ["memory-leaderboard"] });
    },
  });

  const submitMutation = useMutation({
    mutationFn: (answer: string[]) => submitMemoryRound(session!.session_id, answer),
    onSuccess: (result) => {
      setScore(result.score);
      if (result.correct && result.next_round) {
        hapticNotify("success");
        setSession(result.next_round);
        setInput([]);
        setPhase("showing");
      } else {
        hapticNotify("error");
        setPhase("gameover");
        claimMutation.mutate(result.session_id);
      }
    },
  });

  useEffect(() => {
    if (phase !== "showing" || !session) return;
    const timer = setTimeout(() => setPhase("input"), session.reveal_ms);
    return () => clearTimeout(timer);
  }, [phase, session]);

  const tapSymbol = (symbol: string) => {
    if (!session || phase !== "input") return;
    haptic("light");
    const next = [...input, symbol];
    setInput(next);
    if (next.length === session.sequence.length) {
      submitMutation.mutate(next);
    }
  };

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Memory Sequence</h1>
        <p className="text-sm text-ink-mist">
          Запомни последовательность символов и повтори её. С каждым уровнем последовательность становится длиннее.
        </p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {startMutation.isPending ? "Загрузка..." : "Начать игру"}
        </button>

        {!!leaderboard?.length && (
          <div className="rounded-2xl bg-bg-surface p-4">
            <p className="mb-2 flex items-center gap-1.5 font-display text-sm font-bold text-ink-chalk">
              <IconTrophy size={14} className="text-accent-lime" />
              Таблица лидеров
            </p>
            <div className="flex flex-col gap-2">
              {leaderboard.slice(0, 5).map((entry, i) => (
                <div key={entry.user_id} className="flex items-center justify-between text-sm">
                  <span className="text-ink-mist">{i + 1}. {entry.display_name}</span>
                  <span className="font-mono font-bold text-accent-cyan">{entry.best_score}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (phase === "gameover") {
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        <IconFlag size={40} className="text-ink-mist" />
        <p className="font-display text-2xl font-bold text-ink-chalk">Игра окончена</p>
        <p className="text-sm text-ink-mist">Твой результат: <span className="font-mono font-bold text-accent-cyan">{score}</span> очков</p>

        {claimMutation.isPending ? (
          <p className="text-sm text-ink-mist">Начисление награды...</p>
        ) : claimResult ? (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              Ты получил +{claimResult.reward_coins}
              <IconCoin size={16} />
            </p>
            {claimResult.new_best_score && <p className="text-xs text-accent-green">Новый рекорд!</p>}
          </div>
        ) : claimMutation.isError ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(claimMutation.error, "Не удалось начислить награду")}
          </p>
        ) : null}

        <div className="flex gap-3">
          <button onClick={() => setPhase("idle")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Ещё раз
          </button>
          <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Назад
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-6 py-6">
      <p className="font-mono text-sm text-ink-mist">Раунд {session?.round_number} · Очки: {score}</p>

      <div className="flex min-h-[64px] flex-wrap items-center justify-center gap-2">
        {phase === "showing"
          ? session?.sequence.map((s, i) => (
              <span key={i} className="flex h-11 w-11 items-center justify-center">
                <SymbolIcon symbol={s} size={32} />
              </span>
            ))
          : session?.sequence.map((_, i) => (
              <span key={i} className={`flex h-11 w-11 items-center justify-center rounded-xl ${input[i] ? "bg-accent-lime/15" : "bg-white/5"}`}>
                {input[i] ? <SymbolIcon symbol={input[i]} size={22} /> : ""}
              </span>
            ))}
      </div>

      <p className="text-xs text-ink-mist-dim">
        {phase === "showing" ? "Запоминай..." : "Повтори последовательность"}
      </p>

      <div className="grid grid-cols-5 gap-3">
        {SYMBOLS.map((symbol) => (
          <button
            key={symbol}
            onClick={() => tapSymbol(symbol)}
            disabled={phase !== "input" || submitMutation.isPending}
            className="flex h-14 w-14 items-center justify-center rounded-2xl bg-bg-surface active:scale-90 disabled:opacity-40"
          >
            <SymbolIcon symbol={symbol} size={24} />
          </button>
        ))}
      </div>
    </div>
  );
}
