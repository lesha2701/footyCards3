import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimSaboteurReward, endSaboteur, revealSaboteurCell, startSaboteur } from "@/api/games";
import { IconBomb, IconCoin, IconFlagCheckered, IconHelp } from "@/components/icons";
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
        <h1 className="font-display text-xl font-bold text-ink-chalk">Футбольный сапёр</h1>
        <p className="text-sm text-ink-mist">
          Поле 4×4. Открывай ячейки — каждая безопасная приносит монеты. Забери накопленное в любой момент или
          рискни продолжить. Попадёшь на бомбу — потеряешь половину заработанного за раунд.
        </p>

        <div>
          <p className="mb-2 text-xs font-semibold text-ink-mist">Выбери сложность</p>
          <div className="grid grid-cols-2 gap-2">
            {DIFFICULTIES.map((d) => (
              <button
                key={d.bombCount}
                onClick={() => setBombCount(d.bombCount)}
                className={`rounded-2xl px-3 py-2.5 text-left ${
                  bombCount === d.bombCount ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
                }`}
              >
                <p className="text-sm font-bold">{d.label}</p>
                <p className={`flex items-center gap-1 text-[11px] ${bombCount === d.bombCount ? "text-bg-base/70" : "text-ink-mist-dim"}`}>
                  <IconBomb size={11} />
                  {d.bombCount} · ×{d.bombCount} награда за ячейку
                </p>
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-ink-mist-dim">
            Чем больше бомб — тем больше монет за ячейку, но и риск выше.
          </p>
        </div>

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <button
          onClick={() => startMutation.mutate(bombCount)}
          disabled={startMutation.isPending}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
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
        {isLoss ? <IconBomb size={40} className="text-red-500" /> : <IconFlagCheckered size={40} className="text-accent-lime" />}
        <p className="font-display text-2xl font-bold text-ink-chalk">{isLoss ? "Бабах!" : "Забрано"}</p>
        <p className="text-sm text-ink-mist">
          {isLoss ? "Ты попал на бомбу. Половина заработанного сгорела." : "Ты вовремя остановился."}
        </p>

        {!claimResult ? (
          <button
            onClick={() => claimMutation.mutate()}
            disabled={claimMutation.isPending || finalReward === 0}
            className="rounded-2xl bg-floodlight px-6 py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
          >
            {claimMutation.isPending ? "Начисление..." : finalReward > 0 ? "Забрать награду" : "Нечего забирать"}
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
    <div className="flex flex-col items-center gap-5 py-4">
      <p className="text-sm text-ink-mist">
        Накоплено: <span className="inline-flex items-center gap-1 font-mono font-bold text-accent-lime">{score}<IconCoin size={13} /></span>
      </p>

      <div className="grid grid-cols-4 gap-2">
        {Array.from({ length: GRID_SIZE }, (_, i) => (
          <button
            key={i}
            onClick={() => revealMutation.mutate(i)}
            disabled={revealed.has(i) || revealMutation.isPending}
            className={`flex h-16 w-16 items-center justify-center rounded-2xl active:scale-90 disabled:active:scale-100 ${
              revealed.has(i)
                ? bombIndex === i
                  ? "bg-red-500/20 text-red-500"
                  : "bg-accent-green/15 text-accent-green"
                : "bg-bg-surface text-ink-mist-dim"
            }`}
          >
            {revealed.has(i) ? bombIndex === i ? <IconBomb size={24} /> : <IconCoin size={24} /> : <IconHelp size={20} />}
          </button>
        ))}
      </div>

      <button
        onClick={() => bankMutation.mutate()}
        disabled={score === 0 || bankMutation.isPending}
        className="flex items-center gap-1.5 rounded-2xl bg-floodlight px-8 py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        Забрать {score > 0 ? <span className="inline-flex items-center gap-1 font-mono">{score}<IconCoin size={15} /></span> : ""}
      </button>
    </div>
  );
}
