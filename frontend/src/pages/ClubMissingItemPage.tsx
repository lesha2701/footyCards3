import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  claimMissingItemReward,
  endMissingItemGame,
  fetchMyClub,
  revealMissingItemRound,
  startMissingItemGame,
  submitMissingItemRound,
} from "@/api/clubs";
import { IconCheck, IconChevronLeft, IconCoin, IconFlag } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { ClubMissingItemReveal, ClubMissingItemStart } from "@/types";

type Phase = "idle" | "memorize" | "revealing" | "answering" | "gameover";

// No item ever matches this — used to auto-submit a guaranteed-wrong answer
// when the player runs out of time.
const TIMEOUT_ANSWER = "";

export default function ClubMissingItemPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [session, setSession] = useState<ClubMissingItemStart | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [reveal, setReveal] = useState<ClubMissingItemReveal | null>(null);
  const [score, setScore] = useState(0);
  const [answerTimeLeftMs, setAnswerTimeLeftMs] = useState(0);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number; new_club_budget: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: club } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub, retry: false });

  const startMutation = useMutation({
    mutationFn: startMissingItemGame,
    onSuccess: (data) => {
      setSession(data);
      setScore(0);
      setReveal(null);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("memorize");
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать игру")),
  });

  const claimMutation = useMutation({
    mutationFn: (sessionId: number) => claimMissingItemReward(sessionId),
    onSuccess: (data) => {
      setClaimResult(data);
      queryClient.invalidateQueries({ queryKey: ["clubs", "me"] });
    },
  });

  const revealMutation = useMutation({
    mutationFn: (sessionId: number) => revealMissingItemRound(sessionId),
    onSuccess: (data) => {
      setReveal(data);
      setPhase("revealing");
    },
  });

  const submitMutation = useMutation({
    mutationFn: (answer: string) => submitMissingItemRound(session!.session_id, answer),
    onSuccess: (result) => {
      setScore(result.score);
      if (result.correct && result.next_round) {
        hapticNotify("success");
        setSession(result.next_round);
        setReveal(null);
        setPhase("memorize");
      } else {
        hapticNotify("error");
        setPhase("gameover");
        claimMutation.mutate(result.session_id);
      }
    },
  });

  const endMutation = useMutation({
    mutationFn: (sessionId: number) => endMissingItemGame(sessionId),
    onSuccess: (result) => {
      setPhase("gameover");
      claimMutation.mutate(result.session_id);
    },
  });

  // Phase B: flashes the N-1 reshuffled items for `hide_after_ms`, then moves on to
  // the answer phase automatically — the player never controls how long this lasts.
  useEffect(() => {
    if (phase !== "revealing" || !reveal) return;
    const timer = setTimeout(() => setPhase("answering"), reveal.hide_after_ms);
    return () => clearTimeout(timer);
  }, [phase, reveal]);

  // Phase C: countdown to auto-submit if the player never answers.
  useEffect(() => {
    if (phase !== "answering" || !reveal) return;
    const total = reveal.answer_timeout_ms;
    const deadline = Date.now() + total;
    setAnswerTimeLeftMs(total);

    const interval = setInterval(() => setAnswerTimeLeftMs(Math.max(0, deadline - Date.now())), 100);
    const timeout = setTimeout(() => submitMutation.mutate(TIMEOUT_ANSWER), total);

    return () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, reveal]);

  const pickAnswer = (item: string) => {
    if (phase !== "answering" || submitMutation.isPending || answerTimeLeftMs <= 0) return;
    haptic("light");
    submitMutation.mutate(item);
  };

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
            <IconChevronLeft size={18} className="text-ink-chalk" />
          </button>
          <h1 className="font-display text-xl font-bold text-ink-chalk">Что исчезло?</h1>
        </div>

        <p className="text-sm text-ink-mist">
          Запомни предметы, нажми «Запомнил», а когда часть из них покажут заново — угадай, какой пропал. С каждым
          раундом предметов на один больше. Доступно раз в час каждому участнику клуба — награда пополняет бюджет
          клуба{club ? ` «${club.name}»` : ""}.
        </p>

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}

        <button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {startMutation.isPending ? "Загрузка..." : "Начать игру"}
        </button>
      </div>
    );
  }

  if (phase === "gameover") {
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        <IconFlag size={40} className="text-ink-mist" />
        <p className="font-display text-2xl font-bold text-ink-chalk">Игра окончена</p>
        <p className="text-sm text-ink-mist">
          Твой результат: <span className="font-mono font-bold text-accent-cyan">{score}</span> очков
        </p>

        {endMutation.isPending || claimMutation.isPending ? (
          <p className="text-sm text-ink-mist">Начисление награды...</p>
        ) : claimResult ? (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              Бюджет клуба +{claimResult.reward_coins}
              <IconCoin size={16} />
            </p>
            <p className="text-xs text-accent-green">Новый бюджет клуба: {claimResult.new_club_budget}</p>
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
          <button onClick={() => navigate("/clubs")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Назад
          </button>
        </div>
      </div>
    );
  }

  const displayedItems = phase === "revealing" && reveal ? reveal.items_shown : session?.items ?? [];

  return (
    <div className="flex flex-col items-center gap-6 py-6">
      <p className="font-mono text-sm text-ink-mist">Раунд {session?.round_number} · Очки: {score}</p>

      <p className="text-xs text-ink-mist-dim">
        {phase === "memorize" && "Запомни все предметы"}
        {phase === "revealing" && "Что изменилось?"}
        {phase === "answering" && "Какой предмет пропал?"}
      </p>

      {phase === "answering" && reveal && (
        <div className="flex w-full max-w-xs flex-col items-center gap-1.5">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div
              className={`h-full rounded-full ${answerTimeLeftMs <= 0 ? "" : "transition-[width] duration-100 ease-linear"} ${
                answerTimeLeftMs < 5000 ? "bg-red-500" : "bg-accent-lime"
              }`}
              style={{ width: `${Math.max(0, (answerTimeLeftMs / reveal.answer_timeout_ms) * 100)}%` }}
            />
          </div>
          <span className={`font-mono text-xs ${answerTimeLeftMs < 5000 ? "text-red-400" : "text-ink-mist-dim"}`}>
            {Math.ceil(answerTimeLeftMs / 1000)}с
          </span>
        </div>
      )}

      <div className="flex flex-wrap justify-center gap-3">
        {(phase === "answering" ? session?.items ?? [] : displayedItems).map((item, i) => (
          <button
            key={`${item}-${i}`}
            onClick={() => pickAnswer(item)}
            disabled={phase !== "answering" || submitMutation.isPending || answerTimeLeftMs <= 0}
            className={`flex h-16 w-16 items-center justify-center rounded-2xl bg-bg-surface text-3xl transition-colors active:scale-90 disabled:opacity-90 ${
              phase === "answering" ? "active:bg-accent-lime/30" : ""
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      {phase === "memorize" && (
        <button
          onClick={() => session && revealMutation.mutate(session.session_id)}
          disabled={revealMutation.isPending}
          className="mt-1 flex items-center gap-2 rounded-2xl bg-floodlight px-6 py-3 font-display text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          <IconCheck size={18} />
          {revealMutation.isPending ? "..." : "Запомнил"}
        </button>
      )}

      {phase === "answering" && (
        <button
          onClick={() => session && endMutation.mutate(session.session_id)}
          disabled={endMutation.isPending}
          className="mt-2 text-xs text-ink-mist-dim underline disabled:opacity-40"
        >
          Закончить и забрать {score} очков
        </button>
      )}
    </div>
  );
}
