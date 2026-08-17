import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import {
  acceptPenaltyChallenge,
  cancelPenaltyChallenge,
  declinePenaltyChallenge,
  fetchPenaltyMatch,
  forfeitPenaltyMatch,
  submitPenaltyPick,
} from "@/api/penalty";
import CardPickerModal from "@/components/cards/CardPickerModal";
import PenaltyGoalScene, { type PenaltyGoalKick } from "@/components/penalty/PenaltyGoalScene";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { useMatchGuardStore } from "@/store/matchGuardStore";
import type { PenaltyDirection, PenaltyMatch, PenaltyRound } from "@/types";

const LEAVE_WARNING = "Матч ещё не завершён. Если выйдешь сейчас, он будет засчитан как поражение.";

const ZONES: { value: PenaltyDirection; label: string; arrow: string }[] = [
  { value: "top_left", label: "Верх-лево", arrow: "↖" },
  { value: "top_center", label: "Верх-центр", arrow: "↑" },
  { value: "top_right", label: "Верх-право", arrow: "↗" },
  { value: "bottom_left", label: "Низ-лево", arrow: "↙" },
  { value: "bottom_center", label: "Низ-центр", arrow: "↓" },
  { value: "bottom_right", label: "Низ-право", arrow: "↘" },
];

const RESULT_LABELS: Record<string, string> = { win: "Победа", draw: "Ничья", loss: "Поражение" };

function goalKickFrom(round: PenaltyRound, viewerIsKicker: boolean): PenaltyGoalKick {
  return {
    shotZone: round.shot_zone,
    diveZone: round.dive_zone,
    outcome: viewerIsKicker ? round.outcome : (round.outcome === "goal" ? "goal" : round.outcome === "saved" ? "saved" : "miss"),
  };
}

function outcomeFor(round: PenaltyRound, viewerIsKicker: boolean): { label: string; good: boolean } {
  if (viewerIsKicker) {
    if (round.outcome === "goal") return { label: "Гол!", good: true };
    if (round.outcome === "saved") return { label: "Отбито", good: false };
    return { label: "Мимо", good: false };
  }
  if (round.outcome === "saved") return { label: "Отбил!", good: true };
  if (round.outcome === "goal") return { label: "Пропустил", good: false };
  return { label: "Соперник промазал", good: true };
}

export default function PenaltyMatchPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const id = Number(matchId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [acceptingCard, setAcceptingCard] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [pickedZone, setPickedZone] = useState<PenaltyDirection | null>(null);
  const [settled, setSettled] = useState(true);
  const knownRoundsLengthRef = useRef<number | null>(null);

  const { data: match, isLoading } = useQuery({
    queryKey: ["penalty-match", id],
    queryFn: () => fetchPenaltyMatch(id),
    refetchInterval: (query) => {
      const data = query.state.data as PenaltyMatch | undefined;
      // Same fix as TacticoMatchPage (2026-08-10): poll while the challenger
      // is waiting so acceptance is picked up live, without a manual reload.
      if (data?.status === "pending_accept" && data.viewer_side === "user") return 5000;
      if (data?.status !== "in_progress") return false;
      return 2500; // kicks are on a 10s clock, poll faster than Tactico's 3s
    },
  });

  const { data: collection } = useQuery({
    queryKey: ["collection", "penalty-pvp-accept"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
    enabled: acceptingCard,
  });

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  // Holds each round's kick/dive animation on screen for a beat before
  // resetting to the idle pose (matches PenaltyGamePage's solo fix) —
  // without this, the scene jumped straight from one round's finished
  // position to the next round's the moment new data arrived, and the
  // keeper's color/position for the *next* round only updated once the
  // player had already submitted their next pick, reading as "nothing
  // happened" right when the turn actually changed. Also what makes the
  // deciding round's animation play instead of getting skipped straight
  // to the results screen (that screen is gated on `settled` below).
  // Skips the very first run (page mount / refetch of an already-live
  // match) so opening the page doesn't replay an old round's animation.
  useEffect(() => {
    if (!match) return; // still loading — don't consume the "skip first run" guard below
    const length = match.rounds.length;
    const previous = knownRoundsLengthRef.current;
    knownRoundsLengthRef.current = length;
    if (previous === null || length <= previous) {
      setSettled(true);
      return;
    }
    setSettled(false);
    const timer = setTimeout(() => {
      setSettled(true);
      setPickedZone(null);
    }, 900);
    return () => clearTimeout(timer);
  }, [match?.rounds.length]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["penalty-match", id] });
    queryClient.invalidateQueries({ queryKey: ["penalty-matches"] });
    queryClient.invalidateQueries({ queryKey: ["penalty-stats"] });
    queryClient.invalidateQueries({ queryKey: ["game-limits"] });
  };

  const acceptMutation = useMutation({
    mutationFn: (cardId: number) => acceptPenaltyChallenge(id, cardId),
    onSuccess: () => { hapticNotify("success"); setAcceptingCard(false); invalidate(); },
    onError: (err) => setError(formatGameError(err, "Не удалось принять вызов")),
  });
  const declineMutation = useMutation({ mutationFn: () => declinePenaltyChallenge(id), onSuccess: () => navigate("/play/penalty/matches") });
  const cancelMutation = useMutation({ mutationFn: () => cancelPenaltyChallenge(id), onSuccess: () => navigate("/play/penalty/matches") });
  const pickMutation = useMutation({
    mutationFn: (zone: PenaltyDirection) => submitPenaltyPick(id, zone),
    onSuccess: () => invalidate(),
    onError: (err) => {
      // The opponent may have forfeited (or the match otherwise resolved)
      // between our last poll and this tap — refetch so the real,
      // already-finished result replaces this stale "in progress" view
      // right away instead of requiring a manual reload.
      invalidate();
      setError(formatGameError(err, "Не удалось сделать удар"));
    },
  });
  const forfeitMutation = useMutation({
    mutationFn: () => forfeitPenaltyMatch(id),
    onSuccess: () => { invalidate(); useMatchGuardStore.getState().deactivate(); },
  });

  // Guards in-app navigation while the match is live — leaving mid-match
  // costs the same loss as staying and losing, same as Тактико. The confirm
  // dialog (rendered globally) calls this same forfeit endpoint if the
  // player chooses to leave anyway.
  useEffect(() => {
    if (match?.status === "in_progress") {
      useMatchGuardStore.getState().activate(
        LEAVE_WARNING,
        () => { forfeitPenaltyMatch(id).catch(() => {}); },
        `/games/penalty/matches/${id}/forfeit`,
      );
    } else {
      useMatchGuardStore.getState().deactivate();
    }
    return () => useMatchGuardStore.getState().deactivate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [match?.status, id]);

  if (isLoading || !match) {
    return <p className="text-sm text-ink-mist">Загрузка...</p>;
  }

  if (match.status === "pending_accept") {
    return (
      <div className="rounded-2xl bg-bg-surface p-4 text-center">
        <p className="text-sm text-ink-mist">
          {match.viewer_side === "user"
            ? "Вызов отправлен, ждём ответа."
            : `${match.opponent_name} вызывает тебя на серию пенальти.`}
        </p>
        {error && <p className="mt-2 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
        <div className="mt-3 flex justify-center gap-2">
          {match.viewer_side === "opponent" && (
            <>
              <button onClick={() => setAcceptingCard(true)} className="rounded-xl bg-accent-green px-5 py-2 text-xs font-bold text-bg-base active:scale-95">
                Принять
              </button>
              <button onClick={() => declineMutation.mutate()} className="rounded-xl bg-red-500/80 px-5 py-2 text-xs font-bold text-white active:scale-95">
                Отклонить
              </button>
            </>
          )}
          {match.viewer_side === "user" && (
            <button onClick={() => cancelMutation.mutate()} className="rounded-xl bg-white/5 px-5 py-2 text-xs font-bold text-ink-mist active:scale-95">
              Отменить вызов
            </button>
          )}
        </div>
        {acceptingCard && (
          <CardPickerModal
            open
            title="Выбери карточку"
            cards={collection?.items ?? []}
            onSelect={(card) => acceptMutation.mutate(card.id)}
            onClose={() => setAcceptingCard(false)}
          />
        )}
      </div>
    );
  }

  if (["declined", "cancelled", "expired"].includes(match.status)) {
    return (
      <div className="rounded-2xl bg-bg-surface p-4 text-center text-sm text-ink-mist">
        {match.status === "declined" && "Вызов отклонён"}
        {match.status === "cancelled" && "Вызов отменён"}
        {match.status === "expired" && "Вызов истёк"}
      </div>
    );
  }

  const lastRound = match.rounds[match.rounds.length - 1];
  const viewerWasLastKicker = lastRound ? lastRound.kicker === "user" : false;
  const isViewerTurn = match.status === "in_progress" && match.is_viewer_turn;

  const outcome = lastRound ? outcomeFor(lastRound, viewerWasLastKicker) : null;
  // Settled: pose the keeper for whoever kicks *next* (match.kicker).
  // Mid-animation: pose it for whoever just dove in the round that's
  // currently playing out (the last round's kicker's opponent).
  const sceneKeeperSide = settled
    ? (match.kicker === "user" ? "opponent" : "own")
    : (viewerWasLastKicker ? "opponent" : "own");
  const sceneKick = settled || !lastRound ? null : goalKickFrom(lastRound, viewerWasLastKicker);
  const sceneOutcome = settled ? null : outcome;

  const kickSecondsLeft = match.kick_deadline
    ? Math.max(0, Math.ceil((new Date(match.kick_deadline).getTime() - now) / 1000))
    : null;
  const matchSecondsLeft = match.match_deadline
    ? Math.max(0, Math.ceil((new Date(match.match_deadline).getTime() - now) / 1000))
    : null;

  return (
    <div className="flex flex-col items-center gap-4 py-4">
      <div className="flex items-center gap-3">
        <p className="text-xs text-ink-mist">Против {match.opponent_name}</p>
        <span className="font-mono text-sm font-bold text-accent-cyan">{match.user_score} : {match.opponent_score}</span>
      </div>

      {match.status === "in_progress" && (
        <div className="flex gap-3 text-[11px] font-mono">
          <span className={kickSecondsLeft !== null && kickSecondsLeft <= 3 ? "text-red-400" : "text-ink-mist"}>
            Ход: {kickSecondsLeft ?? "—"}с
          </span>
          <span className={matchSecondsLeft !== null && matchSecondsLeft <= 20 ? "text-red-400" : "text-ink-mist"}>
            Матч: {matchSecondsLeft !== null ? `${Math.floor(matchSecondsLeft / 60)}:${String(matchSecondsLeft % 60).padStart(2, "0")}` : "—"}
          </span>
        </div>
      )}

      <PenaltyGoalScene
        keeperSide={sceneKeeperSide}
        kick={sceneKick}
        outcomeLabel={sceneOutcome?.label ?? null}
        outcomeGood={sceneOutcome?.good ?? false}
      />

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {match.status === "in_progress" && (
        <>
          <p className="text-sm font-semibold text-ink-mist">
            {isViewerTurn
              ? (match.kicker === "user" ? "Твой удар — выбери зону" : "Ты в воротах — угадай зону")
              : "Ждём соперника..."}
          </p>
          <div className="grid grid-cols-3 gap-2.5">
            {ZONES.map((z) => (
              <button
                key={z.value}
                onClick={() => { setPickedZone(z.value); pickMutation.mutate(z.value); }}
                disabled={!isViewerTurn || pickMutation.isPending}
                className={`flex flex-col items-center gap-1 rounded-2xl px-3 py-3.5 text-[11px] font-semibold text-ink-chalk transition-colors active:scale-90 disabled:opacity-40 ${
                  pickedZone === z.value ? "bg-accent-cyan/20 ring-2 ring-accent-cyan" : "bg-bg-surface"
                }`}
              >
                <span className="text-base leading-none">{z.arrow}</span>
                {z.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => forfeitMutation.mutate()}
            disabled={forfeitMutation.isPending}
            className="text-[11px] font-semibold text-ink-mist-dim underline underline-offset-2 active:scale-95"
          >
            Сдаться (засчитается поражение)
          </button>
        </>
      )}

      {match.status === "finished" && settled && (
        <div className="flex flex-col items-center gap-3">
          <p className="font-display text-lg font-bold text-accent-lime">
            {match.result ? RESULT_LABELS[match.result] : ""}
          </p>
          <p className={`text-xs ${match.rating_delta >= 0 ? "text-accent-green" : "text-red-400"}`}>
            Рейтинг Пенальти {match.rating_delta >= 0 ? "+" : ""}{match.rating_delta}
          </p>
          <button
            onClick={() => navigate("/play/penalty/matches")}
            className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist"
          >
            К списку матчей
          </button>
        </div>
      )}
    </div>
  );
}
