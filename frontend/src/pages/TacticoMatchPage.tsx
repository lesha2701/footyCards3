import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  acceptTacticoChallenge,
  cancelTacticoChallenge,
  createTacticoBotMatch,
  createTacticoChallenge,
  declineTacticoChallenge,
  fetchTacticoMatch,
  forfeitTacticoMatch,
  submitTacticoRound,
} from "@/api/tactico";
import { IconClock, IconCoin } from "@/components/icons";
import RoundResultOverlay from "@/components/tactico/RoundResultOverlay";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { RARITY_GLOW, RARITY_GRADIENTS } from "@/lib/rarity";
import { useAuthStore } from "@/store/authStore";
import { useMatchGuardStore } from "@/store/matchGuardStore";
import type { TacticoCard, TacticoMatch, TacticoRound } from "@/types";

const LEAVE_WARNING = "Матч ещё не завершён. Если выйдешь сейчас, он будет засчитан как поражение.";

const RESULT_LABELS: Record<string, string> = { win: "Победа", draw: "Ничья", loss: "Поражение" };
const PHASE_LABELS: Record<string, { label: string; emoji: string }> = {
  attack: { label: "Атакующий эпизод", emoji: "⚔️" },
  defense: { label: "Оборонительный эпизод", emoji: "🛡" },
};

export default function TacticoMatchPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const id = Number(matchId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: match, isLoading } = useQuery({
    queryKey: ["tactico-match", id],
    queryFn: () => fetchTacticoMatch(id),
    refetchInterval: (query) => {
      const data = query.state.data as TacticoMatch | undefined;
      if (data?.status !== "in_progress") return false;
      // Poll faster once one side has already committed a card for this
      // round (a live 15s response window is running for the other side),
      // so both players see the countdown resolve promptly.
      if (data.round_deadline) return 3000;
      return data.waiting_for_opponent ? 20000 : false;
    },
  });

  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["tactico-match", id] });
    queryClient.invalidateQueries({ queryKey: ["tactico-matches"] });
    queryClient.invalidateQueries({ queryKey: ["tactico-stats"] });
    queryClient.invalidateQueries({ queryKey: ["game-limits"] });
  };

  const submitMutation = useMutation({
    mutationFn: (cardId: number) => submitTacticoRound(id, cardId),
    onSuccess: () => { hapticNotify("success"); invalidate(); },
    onError: (err) => setError(formatGameError(err, "Не удалось сыграть карту")),
  });
  const acceptMutation = useMutation({ mutationFn: () => acceptTacticoChallenge(id), onSuccess: () => { hapticNotify("success"); invalidate(); } });
  const declineMutation = useMutation({ mutationFn: () => declineTacticoChallenge(id), onSuccess: () => navigate("/play/tactico") });
  const cancelMutation = useMutation({ mutationFn: () => cancelTacticoChallenge(id), onSuccess: () => navigate("/play/tactico") });
  const forfeitMutation = useMutation({
    mutationFn: () => forfeitTacticoMatch(id),
    onSuccess: () => { invalidate(); useMatchGuardStore.getState().deactivate(); },
  });

  const rematchMutation = useMutation({
    mutationFn: () =>
      match?.opponent_type === "bot"
        ? createTacticoBotMatch(match.difficulty ?? "medium")
        : createTacticoChallenge(match!.opponent_user_id!),
    onSuccess: (newMatch) => navigate(`/play/tactico/matches/${newMatch.id}`),
    onError: (err) => setError(formatGameError(err, "Не удалось начать новый матч")),
  });

  // Guards in-app navigation while the match is live — leaving mid-match
  // costs the same loss as staying and losing, so quitting to dodge a
  // defeat isn't a viable strategy. The confirm dialog (rendered globally)
  // calls this same forfeit endpoint if the player chooses to leave anyway.
  useEffect(() => {
    if (match?.status === "in_progress") {
      useMatchGuardStore.getState().activate(
        LEAVE_WARNING,
        () => { forfeitTacticoMatch(id).catch(() => {}); },
        `/tactico/matches/${id}/forfeit`,
      );
    } else {
      useMatchGuardStore.getState().deactivate();
    }
    return () => useMatchGuardStore.getState().deactivate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [match?.status, id]);

  // Shows a brief battle-result animation whenever a new round resolves —
  // whether from our own submission, a background poll noticing the
  // opponent finally moved, or the timeout sweep. Skips the very first
  // render of an already-in-progress match so resuming one doesn't replay
  // its most recent round.
  const roundsSeenRef = useRef<{ id: number; count: number } | null>(null);
  const [revealRound, setRevealRound] = useState<TacticoRound | null>(null);
  useEffect(() => {
    if (!match) return;
    if (!roundsSeenRef.current || roundsSeenRef.current.id !== id) {
      roundsSeenRef.current = { id, count: match.rounds.length };
      return;
    }
    if (match.rounds.length > roundsSeenRef.current.count) {
      setRevealRound(match.rounds[match.rounds.length - 1]);
      roundsSeenRef.current = { id, count: match.rounds.length };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [match?.rounds.length, id]);

  // Credits the reward to the visible wallet balance the moment the match
  // actually finishes while this page is open — whether that's from our own
  // submission, a background poll noticing the opponent moved, or the
  // timeout sweep. Only fires on a live transition into "finished" (not on
  // mount, e.g. revisiting an already-finished match from history), so a
  // reward already reflected in the session's balance never gets counted
  // twice — same guard idea as roundsSeenRef above.
  const prevStatusRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!match) return;
    const prevStatus = prevStatusRef.current;
    prevStatusRef.current = match.status;
    if (prevStatus && prevStatus !== "finished" && match.status === "finished" && match.reward_coins > 0) {
      const updateBalance = useAuthStore.getState().updateBalance;
      updateBalance((useAuthStore.getState().user?.balance ?? 0) + match.reward_coins);
    }
  }, [match?.status, match?.reward_coins]);

  if (isLoading || !match) {
    return <p className="text-sm text-ink-mist">Загрузка...</p>;
  }

  return (
    <div className="flex flex-col gap-4 pb-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-lg font-bold text-ink-chalk">Тактико</h1>
          <p className="text-xs text-ink-mist">
            {match.opponent_type === "bot" ? "Против бота" : "Против друга"} · {match.opponent_name}
          </p>
        </div>
        <ScoreBadge match={match} />
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {match.status === "pending_accept" && (
        <div className="rounded-2xl bg-bg-surface p-4 text-center">
          <p className="text-sm text-ink-mist">
            {match.viewer_side === "user" ? "Вызов отправлен, ждём ответа." : `${match.opponent_name} вызывает тебя на матч в Тактико.`}
          </p>
          <div className="mt-3 flex justify-center gap-2">
            {match.viewer_side === "opponent" && (
              <>
                <button onClick={() => acceptMutation.mutate()} className="rounded-xl bg-accent-green px-5 py-2 text-xs font-bold text-bg-base active:scale-95">
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
        </div>
      )}

      {match.status === "in_progress" && match.current_phase && (
        <div className="rounded-2xl bg-bg-surface p-4 text-center">
          <p className="font-display text-base font-bold text-ink-chalk">
            {PHASE_LABELS[match.current_phase].emoji} {PHASE_LABELS[match.current_phase].label}
          </p>
          {match.waiting_for_opponent ? (
            <>
              <p className="mt-2 flex items-center justify-center gap-1.5 text-xs text-ink-mist">
                <IconClock size={13} />
                Ждём ход соперника...
              </p>
              {match.round_deadline && (
                <p className="mt-1 text-[11px] text-ink-mist-dim">
                  Если соперник не успеет за <RoundCountdown deadline={match.round_deadline} />, за него сыграет случайная карта
                </p>
              )}
            </>
          ) : match.round_deadline ? (
            <p className="mt-2 flex items-center justify-center gap-1.5 text-xs font-semibold text-red-400">
              <IconClock size={13} />
              Соперник уже сделал ход — успей за <RoundCountdown deadline={match.round_deadline} />, иначе сыграет случайная карта
            </p>
          ) : (
            <p className="mt-1 text-xs text-ink-mist">Выбери карту для этого раунда</p>
          )}
          <button
            onClick={() => forfeitMutation.mutate()}
            disabled={forfeitMutation.isPending}
            className="mt-3 text-[11px] font-semibold text-ink-mist-dim underline underline-offset-2 active:scale-95"
          >
            Сдаться (засчитается поражение)
          </button>
        </div>
      )}

      {match.status === "in_progress" && !match.waiting_for_opponent && match.pickable_cards && (
        <div className="grid grid-cols-3 gap-2.5">
          {match.pickable_cards.map((card) => (
            <TacticoCardTile
              key={card.user_card_id}
              card={card}
              phase={match.current_phase}
              onClick={() => card.user_card_id && submitMutation.mutate(card.user_card_id)}
            />
          ))}
        </div>
      )}

      {match.status === "finished" && (
        <div className="rounded-2xl bg-bg-surface p-4 text-center">
          <p className="font-display text-lg font-bold text-accent-lime">{match.result ? RESULT_LABELS[match.result] : ""}</p>
          <div className="mt-2 flex items-center justify-center gap-4 text-xs text-ink-mist">
            <span className={match.rating_delta >= 0 ? "text-accent-green" : "text-red-400"}>
              Рейтинг Тактико {match.rating_delta >= 0 ? "+" : ""}{match.rating_delta}
            </span>
            {match.reward_coins > 0 && (
              <span className="flex items-center gap-1 text-accent-lime">
                +{match.reward_coins} <IconCoin size={12} />
              </span>
            )}
          </div>
          <button
            onClick={() => rematchMutation.mutate()}
            disabled={rematchMutation.isPending}
            className="mt-4 w-full rounded-2xl bg-accent-lime py-4 text-base font-bold text-bg-base ring-2 ring-accent-lime/40 active:scale-95 disabled:opacity-40"
          >
            Играть ещё раз
          </button>
        </div>
      )}

      {(match.status === "declined" || match.status === "cancelled" || match.status === "expired") && (
        <div className="rounded-2xl bg-bg-surface p-4 text-center text-sm text-ink-mist">
          {match.status === "declined" && "Вызов отклонён"}
          {match.status === "cancelled" && "Вызов отменён"}
          {match.status === "expired" && "Вызов истёк"}
        </div>
      )}

      {match.rounds.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-semibold text-ink-mist-dim">Раунды</p>
          {match.rounds.map((round) => (
            <RoundRow key={round.index} round={round} />
          ))}
        </div>
      )}

      {revealRound && <RoundResultOverlay round={revealRound} onDismiss={() => setRevealRound(null)} />}
    </div>
  );
}

function RoundCountdown({ deadline }: { deadline: string }) {
  const target = new Date(deadline).getTime();
  const [secondsLeft, setSecondsLeft] = useState(() => Math.max(0, Math.ceil((target - Date.now()) / 1000)));

  useEffect(() => {
    setSecondsLeft(Math.max(0, Math.ceil((target - Date.now()) / 1000)));
    const timer = setInterval(() => {
      setSecondsLeft(Math.max(0, Math.ceil((target - Date.now()) / 1000)));
    }, 250);
    return () => clearInterval(timer);
  }, [target]);

  return <span className="font-mono font-bold">{secondsLeft} сек</span>;
}

function ScoreBadge({ match }: { match: TacticoMatch }) {
  if (match.status === "pending_accept") return null;
  return (
    <div className="flex items-center gap-1.5 rounded-full bg-white/5 px-3 py-1.5 font-mono text-sm font-bold text-ink-chalk">
      <span className="text-accent-lime">{match.user_score}</span>
      <span className="text-ink-mist-dim">:</span>
      <span>{match.opponent_score}</span>
    </div>
  );
}

function TacticoCardTile({ card, phase, onClick }: { card: TacticoCard; phase: string | null; onClick: () => void }) {
  const imageUrl = staticUrl(card.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp");
  const attackActive = phase === "attack";
  const defenseActive = phase === "defense";
  return (
    <button
      onClick={onClick}
      className={`group relative flex aspect-[3/4] w-full flex-col overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[card.rarity]} ${RARITY_GLOW[card.rarity]} p-[2px] transition-transform active:scale-[0.97]`}
    >
      <div className="flex h-full w-full flex-col overflow-hidden rounded-[14px] bg-bg-surface/90">
        <div className="relative flex-1 overflow-hidden">
          <img src={imageUrl} alt={card.display_name} className="h-full w-full object-cover" loading="lazy" />
          <div className="absolute left-1.5 top-1.5 rounded-md bg-black/60 px-1.5 py-0.5 font-display text-xs font-bold leading-none text-white">★{card.rating}</div>
          <div className="absolute right-1.5 top-1.5 rounded-md bg-black/60 px-1.5 py-0.5 font-display text-xs font-semibold leading-none text-white">{card.position}</div>
        </div>
        <div className="border-t border-white/10 bg-black/30 px-2 py-1.5 text-center">
          <p className="truncate font-display text-xs font-semibold text-ink-chalk">{card.display_name}</p>
          <p className="mt-0.5 flex items-center justify-center gap-2 font-mono text-[9px]">
            <span className={attackActive ? "font-bold text-accent-lime" : "text-ink-mist"}>
              АТК <b>{card.attack_rating}</b>
            </span>
            <span className={defenseActive ? "font-bold text-accent-lime" : "text-ink-mist"}>
              ЗЩТ <b>{card.defense_rating}</b>
            </span>
          </p>
        </div>
      </div>
    </button>
  );
}

function RoundRow({ round }: { round: TacticoRound }) {
  const winnerColor = round.winner === "user" ? "text-accent-green" : round.winner === "opponent" ? "text-red-400" : "text-ink-mist";
  return (
    <div className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-xs">
      <span className="w-6 font-mono text-ink-mist-dim">#{round.index + 1}</span>
      <span className="flex-1 text-center text-ink-mist">{PHASE_LABELS[round.phase].emoji}</span>
      <RoundCardLabel card={round.user_card} align="right" />
      <span className={`mx-2 font-bold ${winnerColor}`}>
        {round.winner === "user" ? "✓" : round.winner === "opponent" ? "✗" : "="}
      </span>
      <RoundCardLabel card={round.opponent_card} align="left" />
    </div>
  );
}

function RoundCardLabel({ card, align }: { card: TacticoCard | null; align: "left" | "right" }) {
  if (!card) return <span className="flex-1 text-ink-mist-dim">···</span>;
  return (
    <span className={`flex-1 truncate text-ink-chalk ${align === "right" ? "text-right" : "text-left"}`}>{card.display_name}</span>
  );
}
