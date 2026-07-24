import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimSaboteurReward, endSaboteur, revealSaboteurCell, startSaboteur } from "@/api/games";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

type Phase = "idle" | "playing" | "lost" | "banked";

const GRID_SIZE = 16;

const DIFFICULTIES: { bombCount: number; label: string }[] = [
  { bombCount: 1, label: "Лёгкий" },
  { bombCount: 2, label: "Средний" },
  { bombCount: 3, label: "Сложный" },
  { bombCount: 4, label: "Экстрим" },
];

export default function SaboteurGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [bombCount, setBombCount] = useState(1);
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const [bombIndex, setBombIndex] = useState<number | null>(null);
  const [score, setScore] = useState(0);
  const [finalReward, setFinalReward] = useState(0);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const startMutation = useMutation({
    mutationFn: (count: number) => startSaboteur(count),
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setBombCount(data.bomb_count);
      setRevealed(new Set());
      setBombIndex(null);
      setScore(0);
      setFinalReward(0);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать игру")),
  });

  const revealMutation = useMutation({
    mutationFn: (cellIndex: number) => revealSaboteurCell(sessionId!, cellIndex),
    onSuccess: (result, cellIndex) => {
      setRevealed((prev) => new Set(prev).add(cellIndex));
      if (result.is_bomb) {
        haptic("heavy");
        setBombIndex(cellIndex);
        setFinalReward(result.reward_coins ?? 0);
        setPhase("lost");
      } else {
        haptic("light");
        setScore(result.score);
      }
    },
  });

  const bankMutation = useMutation({
    mutationFn: () => endSaboteur(sessionId!),
    onSuccess: (result) => {
      setFinalReward(result.reward_coins ?? result.score);
      setPhase("banked");
    },
  });

  const claimMutation = useMutation({
    mutationFn: () => claimSaboteurReward(sessionId!),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimResult(data);
    },
  });

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-2xl font-bold text-slate-100">💣 Футбольный сапёр</h1>
        <p className="text-sm text-slate-400">
          Поле 4×4. Открывай ячейки — каждая безопасная приносит монеты. Забери накопленное в любой момент или
          рискни продолжить. Попадёшь на бомбу — потеряешь половину заработанного за раунд.
        </p>

        <div>
          <p className="mb-2 text-xs font-semibold text-slate-300">Выбери сложность</p>
          <div className="grid grid-cols-2 gap-2">
            {DIFFICULTIES.map((d) => (
              <button
                key={d.bombCount}
                onClick={() => setBombCount(d.bombCount)}
                className={`rounded-2xl px-3 py-2.5 text-left ${
                  bombCount === d.bombCount ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"
                }`}
              >
                <p className="text-sm font-bold">{d.label}</p>
                <p className={`text-[11px] ${bombCount === d.bombCount ? "text-bg-base/70" : "text-slate-500"}`}>
                  💣 {d.bombCount} · ×{d.bombCount} награда за ячейку
                </p>
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-white/50">
            Чем больше бомб — тем больше монет за ячейку, но и риск выше.
          </p>
        </div>

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <button
          onClick={() => startMutation.mutate(bombCount)}
          disabled={startMutation.isPending}
          className="rounded-2xl bg-accent py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {startMutation.isPending ? "Загрузка..." : "Начать игру"}
        </button>
      </div>
    );
  }

  if (phase === "lost" || phase === "banked") {
    const isLoss = phase === "lost";
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        <p className="text-5xl">{isLoss ? "💥" : "🏁"}</p>
        <p className="font-display text-2xl font-bold text-slate-100">{isLoss ? "Бабах!" : "Забрано"}</p>
        <p className="text-sm text-slate-400">
          {isLoss ? "Ты попал на бомбу. Половина заработанного сгорела." : "Ты вовремя остановился."}
        </p>

        {!claimResult ? (
          <button
            onClick={() => claimMutation.mutate()}
            disabled={claimMutation.isPending || finalReward === 0}
            className="rounded-2xl bg-accent px-6 py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
          >
            {claimMutation.isPending ? "Начисление..." : finalReward > 0 ? "Забрать награду" : "Нечего забирать"}
          </button>
        ) : (
          <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-5 py-3">
            <p className="font-display text-lg font-bold text-emerald-400">+{claimResult.reward_coins} 🪙</p>
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
    <div className="flex flex-col items-center gap-5 py-4">
      <p className="text-sm text-slate-400">Накоплено: <span className="font-bold text-amber-300">{score} 🪙</span></p>

      <div className="grid grid-cols-4 gap-2">
        {Array.from({ length: GRID_SIZE }, (_, i) => (
          <button
            key={i}
            onClick={() => revealMutation.mutate(i)}
            disabled={revealed.has(i) || revealMutation.isPending}
            className={`flex h-16 w-16 items-center justify-center rounded-2xl text-2xl active:scale-90 disabled:active:scale-100 ${
              revealed.has(i)
                ? bombIndex === i
                  ? "bg-red-500/30"
                  : "bg-emerald-500/20"
                : "bg-bg-surface"
            }`}
          >
            {revealed.has(i) ? (bombIndex === i ? "💣" : "💰") : "❓"}
          </button>
        ))}
      </div>

      <button
        onClick={() => bankMutation.mutate()}
        disabled={score === 0 || bankMutation.isPending}
        className="rounded-2xl bg-accent px-8 py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        Забрать {score > 0 ? `${score} 🪙` : ""}
      </button>
    </div>
  );
}
