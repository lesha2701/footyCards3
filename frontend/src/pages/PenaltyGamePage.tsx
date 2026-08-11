import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import { claimPenaltyReward, kickPenalty, startPenalty } from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import { IconCoin, IconFlagCheckered, IconTrophy } from "@/components/icons";
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
  const [lastKick, setLastKick] = useState<PenaltyKickResult | null>(null);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [settled, setSettled] = useState(true);

  const { data: collection } = useQuery({
    queryKey: ["collection", "penalty"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
  });

  const startMutation = useMutation({
    mutationFn: startPenalty,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setLastKick(null);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать игру")),
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

  // Warns before leaving a live game, same as Card Arena — no backend
  // forfeit exists for solo Penalty either, so this is a UX nudge (keeps
  // BottomNav/TopBar's confirm dialog consistent across every tab,
  // including "Играть") rather than an enforced loss.
  useEffect(() => {
    if (phase === "playing") {
      useMatchGuardStore.getState().activate("Серия пенальти не завершена. Уверен, что хочешь выйти?");
    } else {
      useMatchGuardStore.getState().deactivate();
    }
    return () => useMatchGuardStore.getState().deactivate();
  }, [phase]);

  if (phase === "pick_card" && !choosingBot) {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Пенальти</h1>
        <p className="text-sm text-ink-mist">Выбери, с кем играть.</p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <button
          onClick={() => setChoosingBot(true)}
          className="flex items-center justify-center gap-2 rounded-2xl bg-floodlight py-4 text-base font-bold text-bg-base ring-2 ring-accent-cyan/40 active:scale-95"
        >
          Играть с ботом
        </button>
        <button
          onClick={() => navigate("/play/penalty/matches")}
          className="flex items-center justify-center gap-2 rounded-2xl bg-white/5 py-4 text-base font-bold text-accent-lime active:scale-95"
        >
          Играть с другом
        </button>
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
                onClick={() => kickMutation.mutate(z.value)}
                disabled={kickMutation.isPending}
                className="flex flex-col items-center gap-1 rounded-2xl bg-bg-surface px-3 py-3.5 text-[11px] font-semibold text-ink-chalk active:scale-90 disabled:opacity-40"
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
