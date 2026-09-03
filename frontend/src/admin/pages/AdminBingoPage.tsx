import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { BingoStatsPreviewItem } from "@/types";

import {
  createBingoGoal,
  deleteBingoGoal,
  fetchAdminPacks,
  fetchBingoGoals,
  fetchBingoStatsPreview,
  fetchBingoState,
  fetchGameConfig,
  updateBingoGoal,
  updateBingoState,
  updateGameConfig,
} from "@/admin/api";
import NumberInput from "@/components/common/NumberInput";
import { ApiRequestError } from "@/lib/api";
import type { BingoGoalDefinition, BingoGoalType } from "@/types";

const GOAL_LABELS: Record<BingoGoalType, string> = {
  packs_opened: "Открыто паков",
  rare_drops: "Выпало редких карт",
  epic_drops: "Выпало эпических карт",
  legendary_drops: "Выпало легендарок",
  tactico_matches_played: "Сыграно матчей Тактико",
  penalty_matches_played: "Сыграно матчей Пенальти",
  arena_matches_played: "Сыграно матчей Кард Арены",
  trades_completed: "Совершено обменов",
};

const GOAL_TYPES = Object.keys(GOAL_LABELS) as BingoGoalType[];

export default function AdminBingoPage() {
  const queryClient = useQueryClient();
  const { data: state } = useQuery({ queryKey: ["admin-bingo-state"], queryFn: fetchBingoState });
  const { data: goals } = useQuery({ queryKey: ["admin-bingo-goals"], queryFn: fetchBingoGoals });
  const { data: config } = useQuery({ queryKey: ["admin-game-config"], queryFn: fetchGameConfig });
  const { data: packs } = useQuery({ queryKey: ["admin-packs"], queryFn: fetchAdminPacks });

  const [error, setError] = useState<string | null>(null);
  const [forms, setForms] = useState<Record<number, Pick<BingoGoalDefinition, "target_value" | "is_active">>>({});
  const [newGoalType, setNewGoalType] = useState<BingoGoalType>("packs_opened");
  const [newTarget, setNewTarget] = useState(1000);
  const [rewardCoins, setRewardCoins] = useState<number | null>(null);
  const [rewardPackId, setRewardPackId] = useState<number | "" | null>(null);
  const [statsPreview, setStatsPreview] = useState<BingoStatsPreviewItem[] | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const formFor = (g: BingoGoalDefinition) => forms[g.id] ?? { target_value: g.target_value, is_active: g.is_active };
  const patch = (id: number, p: Partial<Pick<BingoGoalDefinition, "target_value" | "is_active">>) =>
    setForms((prev) => ({ ...prev, [id]: { ...(goals ? { target_value: goals.find((g) => g.id === id)!.target_value, is_active: goals.find((g) => g.id === id)!.is_active } : { target_value: 0, is_active: false }), ...prev[id], ...p } }));

  const toggleMutation = useMutation({
    mutationFn: (isEnabled: boolean) => updateBingoState(isEnabled),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["admin-bingo-state"] }); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось изменить состояние"),
  });

  const saveGoalMutation = useMutation({
    mutationFn: (g: BingoGoalDefinition) => updateBingoGoal(g.id, forms[g.id]),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["admin-bingo-goals"] }); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить задание"),
  });

  const deleteGoalMutation = useMutation({
    mutationFn: (id: number) => deleteBingoGoal(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["admin-bingo-goals"] }); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить задание"),
  });

  const createGoalMutation = useMutation({
    mutationFn: () => createBingoGoal({ goal_type: newGoalType, target_value: newTarget, is_active: true }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["admin-bingo-goals"] }); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось добавить задание"),
  });

  const saveRewardMutation = useMutation({
    mutationFn: () =>
      updateGameConfig({
        bingo_reward_coins: rewardCoins ?? config?.bingo_reward_coins ?? 0,
        bingo_reward_pack_id: rewardPackId === "" ? null : rewardPackId ?? config?.bingo_reward_pack_id ?? null,
      }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["admin-game-config"] }); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить награду"),
  });

  const activeGoalTypes = new Set((goals ?? []).filter((g) => g.is_active).map((g) => g.goal_type));

  const loadStatsPreview = async () => {
    setStatsLoading(true);
    setError(null);
    try {
      setStatsPreview(await fetchBingoStatsPreview());
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Не удалось получить статистику");
    } finally {
      setStatsLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-2xl font-bold">Бинго недели</h1>
        <p className="mt-1 text-xs text-slate-400">
          Коллективный еженедельный ивент: все игроки вместе выполняют задания. Изменение цели или добавление нового
          задания применяется только со следующей недели — текущая неделя идёт с той конфигурацией, с которой началась.
        </p>
        {!state?.is_enabled && (
          <p className="mt-2 text-xs text-amber-300">
            Рекомендуемый порядок: 1) настрой задания ниже → 2) посмотри статистику за последнюю неделю, чтобы
            подобрать реалистичные цели → 3) включи ивент.
          </p>
        )}
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="flex flex-col gap-2">
        {goals?.map((g) => {
          const form = formFor(g);
          const dirty = form.target_value !== g.target_value || form.is_active !== g.is_active;
          return (
            <div key={g.id} className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/5 bg-bg-surface p-3">
              <div className="w-56 text-sm font-semibold">{GOAL_LABELS[g.goal_type]}</div>
              <label className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Цель</span>
                <NumberInput min={1} value={form.target_value} onChange={(v) => patch(g.id, { target_value: v })} className="w-28 rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none" />
              </label>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => patch(g.id, { is_active: e.target.checked })} />
                Активно
              </label>
              <div className="ml-auto flex gap-2">
                <button
                  onClick={() => saveGoalMutation.mutate(g)}
                  disabled={!dirty || saveGoalMutation.isPending}
                  className="rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
                >
                  Сохранить
                </button>
                <button
                  onClick={() => deleteGoalMutation.mutate(g.id)}
                  disabled={deleteGoalMutation.isPending}
                  className="rounded-lg bg-red-500/10 px-3 py-1.5 text-xs font-semibold text-red-400 disabled:opacity-40"
                >
                  Удалить
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-dashed border-white/10 bg-bg-surface/50 p-3">
        <span className="w-full text-xs font-semibold text-slate-300">Новое задание</span>
        <label className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Тип</span>
          <select
            value={newGoalType}
            onChange={(e) => setNewGoalType(e.target.value as BingoGoalType)}
            className="rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none"
          >
            {GOAL_TYPES.map((t) => (
              <option key={t} value={t} disabled={activeGoalTypes.has(t)}>
                {GOAL_LABELS[t]}{activeGoalTypes.has(t) ? " (уже активно)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Цель</span>
          <NumberInput min={1} value={newTarget} onChange={setNewTarget} className="w-28 rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none" />
        </label>
        <button
          onClick={() => createGoalMutation.mutate()}
          disabled={createGoalMutation.isPending}
          className="ml-auto rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
        >
          Добавить
        </button>
      </div>

      <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-sm font-semibold">Статистика за последние 7 дней</p>
            <p className="mt-1 text-xs text-slate-400">
              Реальная активность игроков за неделю — помогает подобрать цели, которые не слишком легко и не слишком сложно достичь.
            </p>
          </div>
          <button
            onClick={loadStatsPreview}
            disabled={statsLoading}
            className="shrink-0 rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold text-slate-200 disabled:opacity-40"
          >
            {statsLoading ? "Считаем..." : "Получить статистику"}
          </button>
        </div>
        {statsPreview && (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {statsPreview.map((item) => (
              <div key={item.goal_type} className="rounded-xl bg-bg-base px-3 py-2">
                <p className="text-[11px] text-slate-400">{GOAL_LABELS[item.goal_type]}</p>
                <p className="font-mono text-lg font-bold text-ink-chalk">{item.trailing_7d_count}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 text-sm font-semibold">Награда за выполненную неделю</p>
        <p className="mb-3 text-xs text-slate-400">
          Не начисляется автоматически — игрок сам забирает её на странице Бинго, пока идёт неделя с выполненными
          заданиями. Если не забрать до конца недели — награда сгорает.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Монеты</span>
            <NumberInput
              min={0}
              value={rewardCoins ?? config?.bingo_reward_coins ?? 0}
              onChange={setRewardCoins}
              className="w-28 rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none"
            />
          </label>
          <label className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Пак</span>
            <select
              value={rewardPackId ?? config?.bingo_reward_pack_id ?? ""}
              onChange={(e) => setRewardPackId(e.target.value ? Number(e.target.value) : "")}
              className="rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none"
            >
              <option value="">Нет</option>
              {packs?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <button
            onClick={() => saveRewardMutation.mutate()}
            disabled={saveRewardMutation.isPending}
            className="rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
          >
            Сохранить
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between rounded-2xl border border-white/5 bg-bg-surface p-4">
        <div>
          <p className="text-sm font-semibold">Ивент {state?.is_enabled ? "включён" : "выключен"}</p>
          {state?.started_at && (
            <p className="mt-1 text-xs text-slate-400">
              Отсчёт недель идёт с {new Date(state.started_at).toLocaleString("ru-RU")}
            </p>
          )}
        </div>
        <button
          onClick={() => toggleMutation.mutate(!state?.is_enabled)}
          disabled={toggleMutation.isPending}
          className={`rounded-lg px-4 py-2 text-xs font-bold disabled:opacity-40 ${
            state?.is_enabled ? "bg-red-500/10 text-red-400" : "bg-accent text-bg-base"
          }`}
        >
          {state?.is_enabled ? "Выключить" : "Включить"}
        </button>
      </div>
    </div>
  );
}
