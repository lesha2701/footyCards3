import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimSaboteurReward, endSaboteur, revealSaboteurCell, startSaboteur } from "@/api/games";
import { IconCoin, IconFlagCheckered, IconHelp, IconProfile } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

type Phase = "idle" | "playing" | "lost" | "banked";

const LINE_SIZE = 5;
const REVEAL_PAUSE_MS = 550;

const DIFFICULTIES: { stewardCount: number; label: string }[] = [
  { stewardCount: 1, label: "Лёгкий" },
  { stewardCount: 2, label: "Средний" },
  { stewardCount: 3, label: "Сложный" },
  { stewardCount: 4, label: "Экстрим" },
];

export default function SaboteurGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [stewardCount, setStewardCount] = useState(1);
  const [level, setLevel] = useState(1);
  const [score, setScore] = useState(0);
  const [pickedIndex, setPickedIndex] = useState<number | null>(null);
  const [pickedIsSteward, setPickedIsSteward] = useState(false);
  const [finalReward, setFinalReward] = useState(0);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const startMutation = useMutation({
    mutationFn: (count: number) => startSaboteur(count),
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setStewardCount(data.steward_count);
      setLevel(data.level);
      setScore(0);
      setPickedIndex(null);
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
      setPickedIndex(cellIndex);
      setPickedIsSteward(result.is_steward);
      if (result.is_steward) {
        haptic("heavy");
        setFinalReward(result.reward_coins ?? 0);
        setTimeout(() => setPhase("lost"), REVEAL_PAUSE_MS);
      } else {
        haptic("light");
        setScore(result.score);
        setTimeout(() => {
          setLevel(result.level);
          setPickedIndex(null);
        }, REVEAL_PAUSE_MS);
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
          Ты — фанат, который пробирается сквозь стюардов к любимому игроку. На каждой линии выбирай одну из{" "}
          {LINE_SIZE} ячеек. Прошёл мимо стюарда — линия открывается дальше и награда растёт. Заберёшь накопленное
          в любой момент или пойдёшь дальше на свой риск.
        </p>

        <div>
          <p className="mb-2 text-xs font-semibold text-ink-mist">Выбери сложность</p>
          <div className="grid grid-cols-2 gap-2">
            {DIFFICULTIES.map((d) => (
              <button
                key={d.stewardCount}
                onClick={() => setStewardCount(d.stewardCount)}
                className={`rounded-2xl px-3 py-2.5 text-left ${
                  stewardCount === d.stewardCount ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
                }`}
              >
                <p className="text-sm font-bold">{d.label}</p>
                <p className={`flex items-center gap-1 text-[11px] ${stewardCount === d.stewardCount ? "text-bg-base/70" : "text-ink-mist-dim"}`}>
                  <IconProfile size={11} />
                  {d.stewardCount} из {LINE_SIZE} — стюардов в линии
                </p>
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-ink-mist-dim">
            Чем больше стюардов в линии — тем выше награда за проход, но и риск попасться больше.
          </p>
        </div>

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <button
          onClick={() => startMutation.mutate(stewardCount)}
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
        {isLoss ? <IconProfile size={40} className="text-red-500" /> : <IconFlagCheckered size={40} className="text-accent-lime" />}
        <p className="font-display text-2xl font-bold text-ink-chalk">{isLoss ? "Поймали!" : "Прорвался!"}</p>
        <p className="text-sm text-ink-mist">
          {isLoss ? "Стюард тебя заметил. Получишь утешительную награду за одну линию." : "Ты вовремя остановился и забрал всё до цента."}
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

  const isBusy = pickedIndex !== null || revealMutation.isPending;

  return (
    <div className="flex flex-col items-center gap-5 py-4">
      <div className="flex items-center gap-4 font-mono text-sm text-ink-mist">
        <span>
          Линия <b className="text-ink-chalk">{level}</b>
        </span>
        <span>
          Накоплено <span className="inline-flex items-center gap-1 font-bold text-accent-lime">{score}<IconCoin size={13} /></span>
        </span>
      </div>

      <div className="flex gap-2">
        {Array.from({ length: LINE_SIZE }, (_, i) => {
          const isPicked = pickedIndex === i;
          return (
            <button
              key={i}
              onClick={() => revealMutation.mutate(i)}
              disabled={isBusy}
              className={`flex h-16 w-16 items-center justify-center rounded-2xl active:scale-90 disabled:active:scale-100 ${
                isPicked
                  ? pickedIsSteward
                    ? "bg-red-500/20 text-red-500"
                    : "bg-accent-green/15 text-accent-green"
                  : "bg-bg-surface text-ink-mist-dim"
              }`}
            >
              {isPicked ? pickedIsSteward ? <IconProfile size={24} /> : <IconCoin size={24} /> : <IconHelp size={20} />}
            </button>
          );
        })}
      </div>

      <button
        onClick={() => bankMutation.mutate()}
        disabled={score === 0 || bankMutation.isPending || isBusy}
        className="flex items-center gap-1.5 rounded-2xl bg-floodlight px-8 py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        Забрать {score > 0 ? <span className="inline-flex items-center gap-1 font-mono">{score}<IconCoin size={15} /></span> : ""}
      </button>
    </div>
  );
}
