import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimClubGameReward, endClubGame, fetchMyClub, startClubGame, submitClubGameRound } from "@/api/clubs";
import {
  IconBall,
  IconCard,
  IconChevronLeft,
  IconCoin,
  IconFlag,
  IconGoal,
  IconTrophy,
  type IconProps,
} from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { ClubGameStart } from "@/types";

// Values must match backend/app/services/club_game_service.py ICONS exactly —
// the server generates/validates sequences using these emoji as opaque IDs.
const ICON_MAP: Record<string, { Icon: (props: IconProps) => JSX.Element; className: string }> = {
  "⚽": { Icon: IconBall, className: "text-ink-chalk" },
  "🥅": { Icon: IconGoal, className: "text-accent-cyan" },
  "🟨": { Icon: IconCard, className: "text-amber-400" },
  "🟥": { Icon: IconCard, className: "text-red-500" },
  "🏆": { Icon: IconTrophy, className: "text-accent-lime" },
};

type Phase = "idle" | "showing" | "input" | "gameover";

// Pause before the first icon flashes, so the round doesn't start mid-blink.
const ROUND_START_DELAY_MS = 1500;

export default function ClubGamePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [session, setSession] = useState<ClubGameStart | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [input, setInput] = useState<string[]>([]);
  const [score, setScore] = useState(0);
  const [revealIndex, setRevealIndex] = useState<number | null>(null);
  const [tapFlashIndex, setTapFlashIndex] = useState<number | null>(null);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number; new_club_budget: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [timeLeftMs, setTimeLeftMs] = useState(0);
  const inputRef = useRef<string[]>([]);
  const submittedRef = useRef(false);

  const { data: club } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub, retry: false });

  const startMutation = useMutation({
    mutationFn: startClubGame,
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
    mutationFn: (sessionId: number) => claimClubGameReward(sessionId),
    onSuccess: (data) => {
      setClaimResult(data);
      queryClient.invalidateQueries({ queryKey: ["clubs", "me"] });
    },
  });

  const submitMutation = useMutation({
    mutationFn: (answer: string[]) => submitClubGameRound(session!.session_id, answer),
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

  const endMutation = useMutation({
    mutationFn: (sessionId: number) => endClubGame(sessionId),
    onSuccess: (result) => {
      setPhase("gameover");
      claimMutation.mutate(result.session_id);
    },
  });

  // Flashes each icon in `session.sequence` in turn, at its position in the
  // fixed 5-icon row, then switches to the input phase once the last one's done.
  // A short pause before the first flash gives the player a beat to settle
  // on the row before it starts, and generous fixed on/off floors (rather
  // than a pure fraction of stepMs) keep back-to-back repeats of the same
  // icon (e.g. "🏆","🏆") as two clearly separate pulses instead of a blur.
  useEffect(() => {
    if (phase !== "showing" || !session) return;
    let cancelled = false;
    const steps = session.sequence.length;
    const stepMs = Math.max(350, Math.floor(session.reveal_ms / steps));
    const onMs = Math.max(450, Math.floor(stepMs * 0.6));
    const offMs = Math.max(350, Math.floor(stepMs * 0.4));
    let i = 0;

    function tick() {
      if (cancelled || !session) return;
      setRevealIndex(session.icons.indexOf(session.sequence[i]));
      setTimeout(() => {
        if (cancelled) return;
        setRevealIndex(null);
        i += 1;
        if (i < steps) {
          setTimeout(tick, offMs);
        } else {
          setTimeout(() => {
            if (!cancelled) setPhase("input");
          }, offMs);
        }
      }, onMs);
    }
    const startTimer = setTimeout(tick, ROUND_START_DELAY_MS);

    return () => {
      cancelled = true;
      clearTimeout(startTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, session]);

  const submitAnswer = (answer: string[]) => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    submitMutation.mutate(answer);
  };

  useEffect(() => {
    if (phase !== "input" || !session) return;
    submittedRef.current = false;
    inputRef.current = [];
    const total = session.answer_timeout_ms;
    const deadline = Date.now() + total;
    setTimeLeftMs(total);

    const interval = setInterval(() => {
      setTimeLeftMs(Math.max(0, deadline - Date.now()));
    }, 100);
    const timeout = setTimeout(() => submitAnswer(inputRef.current), total);

    return () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, session]);

  const tapIcon = (position: number) => {
    if (!session || phase !== "input" || timeLeftMs <= 0) return;
    haptic("light");
    setTapFlashIndex(position);
    setTimeout(() => setTapFlashIndex((p) => (p === position ? null : p)), 150);
    const symbol = session.icons[position];
    const next = [...input, symbol];
    inputRef.current = next;
    setInput(next);
    if (next.length === session.sequence.length) {
      submitAnswer(next);
    }
  };

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
            <IconChevronLeft size={18} className="text-ink-chalk" />
          </button>
          <h1 className="font-display text-xl font-bold text-ink-chalk">Клубная игра</h1>
        </div>

        <p className="text-sm text-ink-mist">
          Запомни, в каком порядке загораются иконки, и повтори последовательность. Доступно раз в час каждому
          участнику клуба — награда пополняет бюджет клуба{club ? ` «${club.name}»` : ""}.
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

  return (
    <div className="flex flex-col items-center gap-6 py-6">
      <p className="font-mono text-sm text-ink-mist">Раунд {session?.round_number} · Очки: {score}</p>

      <p className="text-xs text-ink-mist-dim">
        {phase === "showing" ? "Запоминай..." : "Повтори последовательность"}
      </p>

      {phase === "input" && session && (
        <div className="flex w-full max-w-xs flex-col items-center gap-1.5">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div
              className={`h-full rounded-full ${timeLeftMs <= 0 ? "" : "transition-[width] duration-100 ease-linear"} ${
                timeLeftMs < 5000 ? "bg-red-500" : "bg-accent-lime"
              }`}
              style={{ width: `${Math.max(0, (timeLeftMs / session.answer_timeout_ms) * 100)}%` }}
            />
          </div>
          <span className={`font-mono text-xs ${timeLeftMs < 5000 ? "text-red-400" : "text-ink-mist-dim"}`}>
            {Math.ceil(timeLeftMs / 1000)}с
          </span>
        </div>
      )}

      <div className="flex min-h-[28px] items-center gap-1.5">
        {session?.sequence.map((_, i) => (
          <span key={i} className={`h-2.5 w-2.5 rounded-full ${input[i] ? "bg-accent-lime" : "bg-white/10"}`} />
        ))}
      </div>

      <div className="flex gap-3">
        {session?.icons.map((symbol, position) => {
          const entry = ICON_MAP[symbol];
          const lit = revealIndex === position || tapFlashIndex === position;
          if (!entry) return null;
          const { Icon, className } = entry;
          return (
            <button
              key={position}
              onClick={() => tapIcon(position)}
              disabled={phase !== "input" || submitMutation.isPending || timeLeftMs <= 0}
              className={`flex h-16 w-16 items-center justify-center rounded-2xl active:scale-90 disabled:opacity-60 ${
                phase === "showing" ? "" : "transition-colors"
              } ${lit ? "bg-accent-lime/50 ring-4 ring-accent-lime" : "bg-bg-surface"}`}
            >
              <Icon size={28} className={className} />
            </button>
          );
        })}
      </div>

      {phase === "input" && (
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
