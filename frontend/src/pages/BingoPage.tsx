import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimBingoCard, claimBingoReward, fetchCurrentBingo } from "@/api/bingo";
import EmptyState from "@/components/common/EmptyState";
import { IconCheck, IconClock, IconCoin, IconPack, IconParty, IconTarget, IconUsers } from "@/components/icons";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { communityReady } from "@/lib/bingo";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { BingoCard, BingoClaimResult, BingoGoal, BingoGoalType } from "@/types";

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

/** «Бинго недели»: the player's own 3×3 card (a line pays, the whole card
 * pays more) and, below it, the server's common goal — whose reward goes
 * only to players with a closed line on their own card. */
export default function BingoPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data, isLoading } = useQuery({ queryKey: ["bingo-current"], queryFn: fetchCurrentBingo });
  const [claimError, setClaimError] = useState<string | null>(null);
  const [claimedCoins, setClaimedCoins] = useState<number | null>(null);

  const onClaimed = (result: BingoClaimResult) => {
    updateBalance(result.new_balance);
    hapticNotify("success");
    setClaimError(null);
    queryClient.invalidateQueries({ queryKey: ["bingo-current"] });
    queryClient.invalidateQueries({ queryKey: ["collection"] });
    if (result.granted_pack) {
      // The same packshot + per-card reveal as a real pack purchase.
      navigate(`/packs/${result.granted_pack.pack.id}/open`, { state: { result: result.granted_pack } });
    } else if (result.coins_granted > 0) {
      setClaimedCoins(result.coins_granted);
    }
  };
  const onClaimError = (err: unknown) => {
    hapticNotify("error");
    setClaimError(err instanceof ApiRequestError ? err.message : "Не удалось забрать награду");
  };
  const cardMutation = useMutation({ mutationFn: claimBingoCard, onSuccess: onClaimed, onError: onClaimError });
  const claimMutation = useMutation({ mutationFn: claimBingoReward, onSuccess: onClaimed, onError: onClaimError });

  if (isLoading) {
    return <div className="flex flex-col gap-3 pb-20">{[0, 1, 2].map((i) => <div key={i} className="h-20 animate-pulse rounded-2xl bg-bg-surface" />)}</div>;
  }

  if (!data?.is_enabled) {
    return (
      <EmptyState icon={IconTarget} title="Бинго недели сейчас не идёт" description="Загляни позже — админ ещё не запустил ивент" />
    );
  }

  const hasCommunityReward = data.reward_coins > 0 || !!data.reward_pack_name;
  const card = data.card;

  return (
    <div className="flex flex-col gap-5 pb-20">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-fuchsia-500/25 via-purple-600/10 to-bg-surface p-5">
        <div className="relative flex items-center gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-fuchsia-400/20 text-fuchsia-300">
            <IconTarget size={24} />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold text-ink-chalk">Бинго недели · неделя {data.week_number}</h1>
            <p className="text-xs text-ink-mist">Своя карточка 3×3: закрывай ряды и всю карточку целиком.</p>
          </div>
        </div>
        {data.ends_at && (
          <div className="relative mt-4 flex items-center gap-1.5 rounded-2xl bg-black/20 px-3 py-2 text-xs text-ink-mist">
            <IconClock size={14} />
            До конца недели: <b className="text-ink-chalk">{formatTimeRemaining(data.ends_at)}</b>
          </div>
        )}
      </section>

      {card && (
        <CardSection
          card={card}
          onOpen={(path) => navigate(path)}
          onClaim={() => cardMutation.mutate()}
          claiming={cardMutation.isPending}
        />
      )}

      {claimError && <p className="rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-400">{claimError}</p>}

      {data.goals.length > 0 && (
        <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
          <div>
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-ink-mist">
              <IconUsers size={13} />
              Общая цель сервера
            </p>
            <p className="mt-1 text-xs leading-relaxed text-ink-mist">
              Все игроки копят общие счётчики. Если к концу недели цели выполнены, бонус забирают те, кто закрыл{" "}
              <b className="text-ink-chalk">хотя бы один ряд</b> в своей карточке.
            </p>
          </div>
          {hasCommunityReward && (
            <div className="flex items-center gap-4">
              {data.reward_coins > 0 && (
                <span className="flex items-center gap-1.5 font-mono text-base font-bold text-accent-lime">
                  <IconCoin size={16} />+{data.reward_coins}
                </span>
              )}
              {data.reward_pack_name && (
                <span className="flex items-center gap-2 text-sm font-semibold text-accent-cyan">
                  {data.reward_pack_image_path ? (
                    <img decoding="async" loading="lazy" src={staticUrl(data.reward_pack_image_path) ?? undefined} className="h-7 w-7 rounded-lg object-cover" />
                  ) : (
                    <IconPack size={16} />
                  )}
                  {data.reward_pack_name}
                </span>
              )}
            </div>
          )}
          {data.goals.map((g) => <GoalRow key={g.goal_type} goal={g} />)}

          {communityReady(data) && (
            <button
              onClick={() => claimMutation.mutate()}
              disabled={claimMutation.isPending}
              className="w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              {claimMutation.isPending ? "Забираем..." : "Забрать общий бонус"}
            </button>
          )}
          {data.all_goals_completed && !data.has_claimed && card && !card.community_eligible && (
            <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">
              Общие цели выполнены. Закрой ряд в своей карточке, чтобы забрать бонус.
            </p>
          )}
          {data.has_claimed && (
            <p className="flex items-center gap-2 text-xs text-ink-mist">
              <IconCheck size={14} className="shrink-0 text-accent-lime" />
              Общий бонус за эту неделю получен.
            </p>
          )}
        </section>
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
            <p className="mt-1 text-sm text-ink-mist">Монеты начислены на баланс.</p>
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

/** The 3×3 card: a cell lights up when its target is met; a tap opens the
 * game behind it. Closed lines' cells get a ring. */
function CardSection({
  card, onOpen, onClaim, claiming,
}: {
  card: BingoCard;
  onOpen: (path: string) => void;
  onClaim: () => void;
  claiming: boolean;
}) {
  const inLine = new Set(card.lines_done.flatMap((i) => card.lines[i] ?? []));
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4" aria-label="Моя карточка">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-mist">Моя карточка</p>
        <p className="font-mono text-xs text-ink-mist">
          Рядов <b className="text-ink-chalk">{card.lines_done.length}/{card.lines.length}</b>
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {card.cells.map((cell, i) => (
          <button
            key={i}
            type="button"
            disabled={cell.free || !cell.path}
            onClick={() => cell.path && onOpen(cell.path)}
            className={`flex aspect-square flex-col items-center justify-center gap-1 rounded-xl p-1.5 text-center active:scale-95 ${
              cell.done ? "bg-accent-lime/15 text-accent-lime" : "bg-white/5 text-ink-mist"
            } ${inLine.has(i) ? "ring-2 ring-accent-lime/60" : ""}`}
          >
            {cell.free ? (
              <span className="text-2xl" aria-hidden>⭐</span>
            ) : (
              <span className="font-mono text-base font-bold leading-none text-ink-chalk">
                {cell.value}/{cell.target}
              </span>
            )}
            <span className="line-clamp-2 text-[10px] font-semibold leading-tight">
              {cell.free ? "Бесплатно" : cell.label}
            </span>
            {cell.done && !cell.free && <IconCheck size={12} className="text-accent-lime" />}
          </button>
        ))}
      </div>
      <p className="text-xs leading-relaxed text-ink-mist">
        Считаются только твои игры этой недели. Каждый закрытый ряд —{" "}
        <b className="text-accent-lime">+{card.line_coins}</b>, все три ряда — ещё{" "}
        <b className="text-accent-lime">+{card.full_coins}</b>
        {card.full_pack_name && <> и «{card.full_pack_name}»</>}. Нажми на клетку, чтобы перейти к игре.
      </p>
      {card.can_claim ? (
        <button
          onClick={onClaim}
          disabled={claiming}
          className="flex w-full items-center justify-center gap-1.5 rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {claiming ? "Забираем..." : <>Забрать <IconCoin size={14} />+{card.claimable_coins}</>}
        </button>
      ) : card.full_claimed ? (
        <p className="flex items-center gap-2 text-xs text-ink-mist">
          <IconCheck size={14} className="shrink-0 text-accent-lime" />
          Карточка закрыта целиком — награды получены.
        </p>
      ) : null}
    </section>
  );
}

function GoalRow({ goal }: { goal: BingoGoal }) {
  const percent = Math.min(100, Math.round((goal.current_value / goal.target_value) * 100));
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-ink-chalk">{GOAL_LABELS[goal.goal_type]}</p>
        {goal.is_completed && <IconCheck size={16} className="shrink-0 text-accent-lime" />}
      </div>
      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className={`h-full rounded-full ${goal.is_completed ? "bg-accent-lime" : "bg-fuchsia-400"}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="mt-1 font-mono text-caption text-ink-mist">
        {goal.current_value.toLocaleString("ru-RU")} / {goal.target_value.toLocaleString("ru-RU")}
      </p>
    </div>
  );
}
