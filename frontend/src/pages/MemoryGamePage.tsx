import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimMemoryReward, fetchMemoryLeaderboard, startMemoryGame, submitMemoryRound } from "@/api/games";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { MemoryStart } from "@/types";

const SYMBOLS = ["⚽", "🥅", "🟨", "🟥", "👟", "🧤", "🏆", "🚩", "🎯", "🔥"];

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
      }
    },
  });

  const claimMutation = useMutation({
    mutationFn: () => claimMemoryReward(session!.session_id),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      setClaimResult(data);
      queryClient.invalidateQueries({ queryKey: ["memory-leaderboard"] });
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
        <h1 className="font-display text-2xl font-bold text-slate-100">🧠 Memory Sequence</h1>
        <p className="text-sm text-slate-400">
          Запомни последовательность символов и повтори её. С каждым уровнем последовательность становится длиннее.
        </p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
          className="rounded-2xl bg-accent py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {startMutation.isPending ? "Загрузка..." : "Начать игру"}
        </button>

        {!!leaderboard?.length && (
          <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
            <p className="mb-2 font-display text-sm font-bold text-slate-200">🏆 Таблица лидеров</p>
            <div className="flex flex-col gap-2">
              {leaderboard.slice(0, 5).map((entry, i) => (
                <div key={entry.user_id} className="flex items-center justify-between text-sm">
                  <span className="text-slate-300">{i + 1}. {entry.display_name}</span>
                  <span className="font-bold text-cyan-300">{entry.best_score}</span>
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
        <p className="text-5xl">🏁</p>
        <p className="font-display text-2xl font-bold text-slate-100">Игра окончена</p>
        <p className="text-sm text-slate-400">Твой результат: <span className="font-bold text-amber-300">{score}</span> очков</p>

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
            {claimResult.new_best_score && <p className="text-xs text-emerald-300">Новый рекорд!</p>}
          </div>
        )}

        <div className="flex gap-3">
          <button onClick={() => setPhase("idle")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-slate-300">
            Ещё раз
          </button>
          <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-slate-300">
            Назад
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-6 py-6">
      <p className="text-sm text-slate-400">Раунд {session?.round_number} · Очки: {score}</p>

      <div className="flex min-h-[64px] flex-wrap items-center justify-center gap-2">
        {phase === "showing"
          ? session?.sequence.map((s, i) => (
              <span key={i} className="text-4xl">{s}</span>
            ))
          : session?.sequence.map((_, i) => (
              <span key={i} className={`flex h-11 w-11 items-center justify-center rounded-xl text-2xl ${input[i] ? "bg-accent/20" : "bg-white/5"}`}>
                {input[i] ?? ""}
              </span>
            ))}
      </div>

      <p className="text-xs text-slate-500">
        {phase === "showing" ? "Запоминай..." : "Повтори последовательность"}
      </p>

      <div className="grid grid-cols-5 gap-3">
        {SYMBOLS.map((symbol) => (
          <button
            key={symbol}
            onClick={() => tapSymbol(symbol)}
            disabled={phase !== "input" || submitMutation.isPending}
            className="flex h-14 w-14 items-center justify-center rounded-2xl bg-bg-surface text-2xl active:scale-90 disabled:opacity-40"
          >
            {symbol}
          </button>
        ))}
      </div>
    </div>
  );
}
