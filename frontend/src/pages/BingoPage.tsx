import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimBingoReward, fetchCurrentBingo } from "@/api/bingo";
import EmptyState from "@/components/common/EmptyState";
import { IconCheck, IconClock, IconCoin, IconPack, IconParty, IconScroll, IconTarget, IconUsers } from "@/components/icons";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { BingoGoal, BingoGoalType } from "@/types";

const GOAL_LABELS: Record<BingoGoalType, string> = {
  packs_opened: "Открыть паков",
  rare_drops: "Получить редких карт",
  epic_drops: "Получить эпических карт",
  legendary_drops: "Получить легендарных карт",
  tactico_matches_played: "Сыграть матчей в Тактико",
  penalty_matches_played: "Сыграть матчей в Пенальти",
  arena_matches_played: "Сыграть матчей в Кард Арене",
  trades_completed: "Совершить обменов",
};

function formatTimeRemaining(endsAt: string): string {
  const ms = new Date(endsAt).getTime() - Date.now();
  if (ms <= 0) return "меньше минуты";
  const days = Math.floor(ms / (24 * 60 * 60 * 1000));
  const hours = Math.floor((ms % (24 * 60 * 60 * 1000)) / (60 * 60 * 1000));
  if (days > 0) return `${days} дн. ${hours} ч.`;
  const minutes = Math.floor((ms % (60 * 60 * 1000)) / (60 * 1000));
  if (hours > 0) return `${hours} ч. ${minutes} мин.`;
  return `${minutes} мин.`;
}

export default function BingoPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data, isLoading } = useQuery({ queryKey: ["bingo-current"], queryFn: fetchCurrentBingo });
  const [claimError, setClaimError] = useState<string | null>(null);
  const [claimedCoins, setClaimedCoins] = useState<number | null>(null);

  const claimMutation = useMutation({
    mutationFn: claimBingoReward,
    onSuccess: (result) => {
      updateBalance(result.new_balance);
      hapticNotify("success");
      setClaimError(null);
      queryClient.invalidateQueries({ queryKey: ["bingo-current"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      if (result.granted_pack) {
        // Reuses the same full packshot + per-card reveal animation as a
        // real pack purchase, instead of a bespoke "reward received" popup.
        navigate(`/packs/${result.granted_pack.pack.id}/open`, { state: { result: result.granted_pack } });
      } else if (result.coins_granted > 0) {
        setClaimedCoins(result.coins_granted);
      }
    },
    onError: (err) => {
      hapticNotify("error");
      setClaimError(err instanceof ApiRequestError ? err.message : "Не удалось забрать награду");
    },
  });

  if (isLoading) {
    return <div className="flex flex-col gap-3 pb-20">{[0, 1, 2].map((i) => <div key={i} className="h-20 animate-pulse rounded-2xl bg-bg-surface" />)}</div>;
  }

  if (!data?.is_enabled) {
    return (
      <EmptyState icon={IconTarget} title="Бинго недели сейчас не идёт" description="Загляни позже — админ ещё не запустил ивент" />
    );
  }

  const hasReward = data.reward_coins > 0 || !!data.reward_pack_name;

  return (
    <div className="flex flex-col gap-5 pb-20">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-fuchsia-500/25 via-purple-600/10 to-bg-surface p-5">
        <div className="relative flex items-center gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-fuchsia-400/20 text-fuchsia-300">
            <IconUsers size={24} />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold text-ink-chalk">Бинго недели · неделя {data.week_number}</h1>
            <p className="text-xs text-ink-mist">Все игроки — одна команда. Цели общие на всех.</p>
          </div>
        </div>
        {data.ends_at && (
          <div className="relative mt-4 flex items-center gap-1.5 rounded-2xl bg-black/20 px-3 py-2 text-xs text-ink-mist">
            <IconClock size={14} />
            До конца недели: <b className="text-ink-chalk">{formatTimeRemaining(data.ends_at)}</b>
          </div>
        )}
      </section>

      <section className="rounded-2xl bg-bg-surface p-4">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-ink-mist">
          <IconScroll size={13} />
          Как это работает
        </p>
        <p className="text-xs leading-relaxed text-ink-mist">
          Все игроки — одна команда. Любое ваше действие (открытие паков, матчи, обмены) прибавляется в общий счётчик
          ниже. Если до конца недели будут выполнены <b className="text-ink-chalk">все</b> цели — каждый игрок сможет
          забрать награду сам, прямо здесь. Если что-то не успеют выполнить — награда сгорает, и в новую неделю
          начинается новый набор целей.
        </p>
      </section>

      {hasReward && (
        <section className="rounded-2xl bg-bg-surface p-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-mist">Награда за неделю</p>
          <div className="flex items-center gap-4">
            {data.reward_coins > 0 && (
              <span className="flex items-center gap-1.5 font-mono text-lg font-bold text-accent-lime">
                <IconCoin size={18} />+{data.reward_coins}
              </span>
            )}
            {data.reward_pack_name && (
              <span className="flex items-center gap-2 text-sm font-semibold text-accent-cyan">
                {data.reward_pack_image_path ? (
                  <img src={staticUrl(data.reward_pack_image_path) ?? undefined} className="h-8 w-8 rounded-lg object-cover" />
                ) : (
                  <IconPack size={18} />
                )}
                {data.reward_pack_name}
              </span>
            )}
          </div>
        </section>
      )}

      {data.goals.length === 0 ? (
        <EmptyState icon={IconTarget} title="На этой неделе пока нет заданий" description="Задания, добавленные админом, появятся здесь со следующей недели" />
      ) : (
        <div className="flex flex-col gap-3">
          {data.goals.map((g) => <GoalCard key={g.goal_type} goal={g} />)}
        </div>
      )}

      {claimError && <p className="rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-400">{claimError}</p>}

      {data.all_goals_completed && !data.has_claimed && (
        <div className="flex flex-col gap-3 rounded-2xl bg-accent-lime/10 px-4 py-3">
          <p className="flex items-center gap-3 text-sm text-accent-lime">
            <IconParty size={20} className="shrink-0" />
            Все цели недели выполнены! Забери свою награду, пока идёт эта неделя.
          </p>
          <button
            onClick={() => claimMutation.mutate()}
            disabled={claimMutation.isPending}
            className="w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            {claimMutation.isPending ? "Забираем..." : "Забрать награду"}
          </button>
        </div>
      )}

      {data.all_goals_completed && data.has_claimed && (
        <div className="flex items-center gap-3 rounded-2xl bg-white/5 px-4 py-3 text-sm text-ink-mist">
          <IconCheck size={18} className="shrink-0 text-accent-lime" />
          Награда за эту неделю уже получена.
        </div>
      )}

      {claimedCoins !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-6"
          onClick={() => setClaimedCoins(null)}
        >
          <div className="w-full max-w-xs rounded-2xl border border-white/10 bg-bg-surface p-6 text-center" onClick={(e) => e.stopPropagation()}>
            <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-accent-lime/15 text-accent-lime">
              <IconParty size={32} />
            </span>
            <p className="mt-3 font-display text-lg font-bold text-ink-chalk">Награда получена!</p>
            <p className="mt-1 text-sm text-ink-mist">Бинго недели выполнено, монеты начислены на баланс.</p>
            <p className="mt-3 flex items-center justify-center gap-1.5 font-display text-2xl font-bold text-amber-300">
              <IconCoin size={20} />+{claimedCoins}
            </p>
            <button
              onClick={() => setClaimedCoins(null)}
              className="mt-5 w-full rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base active:scale-95"
            >
              Ок
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function GoalCard({ goal }: { goal: BingoGoal }) {
  const percent = Math.min(100, Math.round((goal.current_value / goal.target_value) * 100));
  return (
    <div className="rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-ink-chalk">{GOAL_LABELS[goal.goal_type]}</p>
        {goal.is_completed && <IconCheck size={16} className="shrink-0 text-accent-lime" />}
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className={`h-full rounded-full ${goal.is_completed ? "bg-accent-lime" : "bg-fuchsia-400"}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="mt-1.5 font-mono text-[11px] text-ink-mist">
        {goal.current_value.toLocaleString("ru-RU")} / {goal.target_value.toLocaleString("ru-RU")}
      </p>
    </div>
  );
}
