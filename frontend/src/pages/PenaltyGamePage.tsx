import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import { fetchFeatureFlags } from "@/api/featureFlags";
import { claimPenaltyReward, forfeitPenalty, kickPenalty, startPenalty } from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import { IconCoin, IconFlagCheckered, IconPlay, IconTrophy, IconUsers } from "@/components/icons";
import PenaltyGoalScene, { type PenaltyGoalKick } from "@/components/penalty/PenaltyGoalScene";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import { useMatchGuardStore } from "@/store/matchGuardStore";
import type { PenaltyDirection, PenaltyKickResult } from "@/types";

type Phase = "pick_card" | "playing" | "finished";

const ZONES: { value: PenaltyDirection; label: string; arrow: string }[] = [
  { value: "top_left", label: "Верх-лево", arrow: "↖" },
  { value: "top_center", label: "Верх-центр", arrow: "↑" },
  { value: "top_right", label: "Верх-право", arrow: "↗" },
  { value: "bottom_left", label: "Низ-лево", arrow: "↙" },
  { value: "bottom_center", label: "Низ-центр", arrow: "↓" },
  { value: "bottom_right", label: "Низ-право", arrow: "↘" },
];

function goalKickFrom(result: PenaltyKickResult): PenaltyGoalKick | null {
  if (!result.player_direction) return null;
  return result.kicker === "player"
    ? { shotZone: result.player_direction, diveZone: result.bot_direction, outcome: result.outcome }
    : { shotZone: result.bot_direction, diveZone: result.player_direction, outcome: result.outcome };
}

function outcomeLabelFor(result: PenaltyKickResult): { label: string; good: boolean } {
  if (result.kicker === "player") {
    if (result.outcome === "goal") return { label: "Гол!", good: true };
    if (result.outcome === "saved") return { label: "Отбито", good: false };
    return { label: "Мимо", good: false };
  }
  if (result.outcome === "saved") return { label: "Отбил!", good: true };
  if (result.outcome === "goal") return { label: "Пропустил", good: false };
  return { label: "Соперник промазал", good: true };
}

export default function PenaltyGamePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("pick_card");
  const [choosingBot, setChoosingBot] = useState(false);
  const [pickingForSearch, setPickingForSearch] = useState(false);
  const [lastKick, setLastKick] = useState<PenaltyKickResult | null>(null);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [settled, setSettled] = useState(true);
  const [pickedZone, setPickedZone] = useState<PenaltyDirection | null>(null);

  const { data: collection } = useQuery({
    queryKey: ["collection", "penalty"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
  });
  // Refetches periodically so an admin's "kill switch" toggle takes effect
  // for already-open sessions without requiring a reload.
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, refetchInterval: 30000 });

  const startMutation = useMutation({
    mutationFn: startPenalty,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setLastKick(null);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => {
      // Close the card picker so the error is actually visible — it's a
      // full-screen overlay, so leaving it open (e.g. after the hourly
      // limit is hit) hid the message behind it, reading as the tap on a
      // card just doing nothing.
      setChoosingBot(false);
      setErrorMsg(formatGameError(err, "Не удалось начать игру"));
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

  const kickMutation = useMutation({
    mutationFn: (direction: PenaltyDirection) => kickPenalty(sessionId!, direction),
    onSuccess: (result) => {
      haptic(result.outcome === "goal" || result.outcome === "saved" ? "medium" : "light");
      setLastKick(result);
      // Do NOT switch to the "finished" phase here even if result.is_finished
      // — that swaps out this whole screen (and the goal scene with it)
      // before the deciding kick's own animation has had a chance to play.
      // The settle effect below holds it on screen first, then transitions.
    },
  });

  // The scene shows the just-resolved kick's animation/outcome briefly, then
  // resets to an idle pose with the keeper already recolored for whoever
  // kicks *next* — without this, the keeper stayed on the previous kick's
  // color/position until the player had already submitted their next pick,
  // which read as "nothing happened" right when the turn actually changed.
  // On the deciding kick (is_finished), the same hold is what lets that
  // final animation actually play before the win/loss screen replaces it.
  // Declared unconditionally (before any early `return`) — hooks can't
  // follow a conditional return without violating the Rules of Hooks.
  useEffect(() => {
    if (!lastKick) {
      setSettled(true);
      return;
    }
    setSettled(false);
    const timer = setTimeout(() => {
      setSettled(true);
      setPickedZone(null);
      if (lastKick.is_finished) {
        hapticNotify(lastKick.result === "win" ? "success" : "error");
        setPhase("finished");
        claimMutation.mutate();
        queryClient.invalidateQueries({ queryKey: ["penalty-stats"] });
        queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      }
    }, 900);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastKick]);

  // Guards in-app navigation while a shootout is live, same as Тактико —
  // leaving mid-match costs the same -1 rating as playing it out and
  // losing, so quitting to dodge a loss isn't a viable strategy. The
  // confirm dialog (rendered globally) calls this same forfeit endpoint if
  // the player chooses to leave anyway; claiming right after keeps the
  // (small, loss-tier) reward from going unclaimed forever, since there's
  // no page to come back and claim it from later.
  useEffect(() => {
    if (phase === "playing" && sessionId != null) {
      useMatchGuardStore.getState().activate(
        "Серия пенальти не завершена. Если выйдешь сейчас, она будет засчитана как поражение.",
        () => {
          forfeitPenalty(sessionId)
            .then(() => claimPenaltyReward(sessionId))
            .catch(() => {});
        },
        `/games/penalty/${sessionId}/forfeit`,
      );
    } else {
      useMatchGuardStore.getState().deactivate();
    }
    return () => useMatchGuardStore.getState().deactivate();
  }, [phase, sessionId]);

  if (phase === "pick_card" && !choosingBot) {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Пенальти</h1>
        <p className="text-sm text-ink-mist">Выбери, с кем играть.</p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        {flags?.matchmaking_enabled !== false && (
          <button
            onClick={() => setPickingForSearch(true)}
            className="flex items-center justify-center gap-2 rounded-2xl bg-accent py-5 text-base font-bold text-bg-base ring-2 ring-accent/40 active:scale-95"
          >
            <IconPlay size={20} />
            Играть
          </button>
        )}
        <div className="flex gap-2">
          <button
            onClick={() => setChoosingBot(true)}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
          >
            <IconPlay size={14} />
            С ботом
          </button>
          <button
            onClick={() => navigate("/play/penalty/matches")}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
          >
            <IconUsers size={14} />
            Вызвать друга
          </button>
        </div>
        {pickingForSearch && (
          <CardPickerModal
            open
            title="Выбери карточку для матча"
            cards={collection?.items ?? []}
            onSelect={(card) => navigate("/play/penalty/matches/search", { state: { userCardId: card.id } })}
            onClose={() => setPickingForSearch(false)}
          />
        )}
      </div>
    );
  }

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
          onClose={() => setChoosingBot(false)}
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
        {lastKick?.rating_delta != null && (
          <p className={`text-xs ${lastKick.rating_delta >= 0 ? "text-accent-green" : "text-red-400"}`}>
            Рейтинг Пенальти {lastKick.rating_delta >= 0 ? "+" : ""}{lastKick.rating_delta}
          </p>
        )}

        {claimMutation.isPending ? (
          <p className="text-sm text-ink-mist">Начисление награды...</p>
        ) : claimResult ? (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              Ты получил +{claimResult.reward_coins}
              <IconCoin size={16} />
            </p>
          </div>
        ) : claimMutation.isError ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(claimMutation.error, "Не удалось начислить награду")}
          </p>
        ) : null}

        <div className="flex gap-3">
          <button
            onClick={() => { setChoosingBot(false); setPhase("pick_card"); }}
            className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist"
          >
            Ещё раз
          </button>
          <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Назад
          </button>
        </div>
      </div>
    );
  }

  const isPlayerKicking = !lastKick || lastKick.next_kicker === "player";
  const roleLabel = kickMutation.isPending
    ? "..."
    : isPlayerKicking
      ? "Твой удар — выбери зону"
      : "Бот бьёт — угадай, куда прыгнуть";

  const outcome = lastKick ? outcomeLabelFor(lastKick) : null;

  const upcomingKicker = lastKick?.next_kicker ?? "player";
  const sceneKeeperSide = settled
    ? upcomingKicker === "bot" ? "own" : "opponent"
    : lastKick?.kicker === "bot" ? "own" : "opponent";
  const sceneKick = settled || !lastKick ? null : goalKickFrom(lastKick);
  const sceneOutcome = settled ? null : outcome;

  return (
    <div className="flex flex-col items-center gap-5 py-6">
      <p className="text-sm text-ink-mist">
        Счёт: <span className="font-mono font-bold text-accent-cyan">{lastKick?.player_score ?? 0} : {lastKick?.bot_score ?? 0}</span>
      </p>

      <PenaltyGoalScene
        keeperSide={sceneKeeperSide}
        kick={sceneKick}
        outcomeLabel={sceneOutcome?.label ?? null}
        outcomeGood={sceneOutcome?.good ?? false}
      />

      {!lastKick?.is_finished && (
        <>
          <p className="text-sm font-semibold text-ink-mist">{roleLabel}</p>

          <div className="grid grid-cols-3 gap-2.5">
            {ZONES.map((z) => (
              <button
                key={z.value}
                onClick={() => { setPickedZone(z.value); kickMutation.mutate(z.value); }}
                disabled={kickMutation.isPending}
                className={`flex flex-col items-center gap-1 rounded-2xl px-3 py-3.5 text-[11px] font-semibold text-ink-chalk transition-colors active:scale-90 disabled:opacity-40 ${
                  pickedZone === z.value ? "bg-accent-cyan/20 ring-2 ring-accent-cyan" : "bg-bg-surface"
                }`}
              >
                <span className="text-base leading-none">{z.arrow}</span>
                {z.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
