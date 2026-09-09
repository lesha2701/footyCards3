import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimClubPenaltyReward, fetchMyClub, forfeitClubPenalty, kickClubPenalty, startClubPenalty } from "@/api/clubs";
import { fetchClubCards } from "@/api/clubSquad";
import ClubCardPickerModal from "@/components/clubs/ClubCardPickerModal";
import { IconChevronLeft, IconCoin, IconFlagCheckered, IconTrophy } from "@/components/icons";
import PenaltyGoalScene, { type PenaltyGoalKick } from "@/components/penalty/PenaltyGoalScene";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useMatchGuardStore } from "@/store/matchGuardStore";
import type { ClubPenaltyKick, PenaltyDirection } from "@/types";

type Phase = "idle" | "pick_card" | "playing" | "finished";

const ZONES: { value: PenaltyDirection; label: string; arrow: string }[] = [
  { value: "top_left", label: "Верх-лево", arrow: "↖" },
  { value: "top_center", label: "Верх-центр", arrow: "↑" },
  { value: "top_right", label: "Верх-право", arrow: "↗" },
  { value: "bottom_left", label: "Низ-лево", arrow: "↙" },
  { value: "bottom_center", label: "Низ-центр", arrow: "↓" },
  { value: "bottom_right", label: "Низ-право", arrow: "↘" },
];

function goalKickFrom(result: ClubPenaltyKick): PenaltyGoalKick | null {
  if (!result.player_direction) return null;
  return result.kicker === "player"
    ? { shotZone: result.player_direction, diveZone: result.bot_direction, outcome: result.outcome }
    : { shotZone: result.bot_direction, diveZone: result.player_direction, outcome: result.outcome };
}

function outcomeLabelFor(result: ClubPenaltyKick): { label: string; good: boolean } {
  if (result.kicker === "player") {
    if (result.outcome === "goal") return { label: "Гол!", good: true };
    if (result.outcome === "saved") return { label: "Отбито", good: false };
    return { label: "Мимо", good: false };
  }
  if (result.outcome === "saved") return { label: "Отбил!", good: true };
  if (result.outcome === "goal") return { label: "Пропустил", good: false };
  return { label: "Соперник промазал", good: true };
}

export default function ClubPenaltyPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [lastKick, setLastKick] = useState<ClubPenaltyKick | null>(null);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number; new_club_budget: number; daily_cap_reached: boolean } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [settled, setSettled] = useState(true);
  const [pickedZone, setPickedZone] = useState<PenaltyDirection | null>(null);

  const { data: club } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub, retry: false });
  const { data: clubCards } = useQuery({ queryKey: ["clubs", "me", "cards"], queryFn: fetchClubCards });

  const startMutation = useMutation({
    mutationFn: startClubPenalty,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setLastKick(null);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => {
      setPhase("idle");
      setErrorMsg(formatGameError(err, "Не удалось начать игру"));
    },
  });

  const claimMutation = useMutation({
    mutationFn: () => claimClubPenaltyReward(sessionId!),
    onSuccess: (data) => {
      hapticNotify("success");
      setClaimResult(data);
      queryClient.invalidateQueries({ queryKey: ["clubs", "me"] });
    },
  });

  const kickMutation = useMutation({
    mutationFn: (direction: PenaltyDirection) => kickClubPenalty(sessionId!, direction),
    onSuccess: (result) => {
      haptic(result.outcome === "goal" || result.outcome === "saved" ? "medium" : "light");
      setLastKick(result);
    },
  });

  // Same hold-then-advance pattern as PenaltyGamePage: let the deciding kick's
  // animation play before swapping this whole screen out for the finish screen.
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
        queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      }
    }, 900);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastKick]);

  useEffect(() => {
    if (phase === "playing" && sessionId != null) {
      useMatchGuardStore.getState().activate(
        "Серия пенальти не завершена. Если выйдешь сейчас, она будет засчитана как поражение.",
        () => {
          forfeitClubPenalty(sessionId)
            .then(() => claimClubPenaltyReward(sessionId))
            .catch(() => {});
        },
        `/clubs/me/penalty/${sessionId}/forfeit`,
      );
    } else {
      useMatchGuardStore.getState().deactivate();
    }
    return () => useMatchGuardStore.getState().deactivate();
  }, [phase, sessionId]);

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate("/clubs/games")} className="rounded-full bg-bg-surface p-2 active:scale-95">
            <IconChevronLeft size={18} className="text-ink-chalk" />
          </button>
          <h1 className="font-display text-xl font-bold text-ink-chalk">Пенальти</h1>
        </div>

        <p className="text-sm text-ink-mist">
          Серия пенальти против бота — выбери игрока из состава клуба{club ? ` «${club.name}»` : ""}. Чем выше его
          рейтинг, тем меньше шанс промазать по воротам. Доступно раз в час каждому участнику клуба — награда
          пополняет бюджет клуба.
        </p>

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}

        <button
          onClick={() => setPhase("pick_card")}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
        >
          Начать игру
        </button>
      </div>
    );
  }

  if (phase === "pick_card") {
    return (
      <ClubCardPickerModal
        open
        title="Выбери игрока"
        cards={clubCards ?? []}
        onSelect={(card) => startMutation.mutate(card.id)}
        onClose={() => setPhase("idle")}
      />
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
              Бюджет клуба +{claimResult.reward_coins}
              <IconCoin size={16} />
            </p>
            <p className="text-xs text-accent-green">Новый бюджет клуба: {claimResult.new_club_budget}</p>
            {claimResult.reward_coins === 0 && claimResult.daily_cap_reached && (
              <p className="mt-1 text-xs text-amber-300">
                Дневной лимит наградных попыток в этой игре исчерпан — результат не пропал, но награда не
                начисляется до завтра.
              </p>
            )}
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
          <button onClick={() => navigate("/clubs/games")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
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
