import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createDiamondUpgradeTier,
  deleteDiamondUpgradeTier,
  fetchDiamondUpgradeTiers,
  updateDiamondUpgradeTier,
} from "@/admin/api";
import NullableNumberInput from "@/components/common/NullableNumberInput";
import NumberInput from "@/components/common/NumberInput";
import { ApiRequestError } from "@/lib/api";
import type { DiamondUpgradeTier } from "@/types";

type TierForm = Omit<DiamondUpgradeTier, "id">;

const EMPTY_FORM: TierForm = {
  min_rating: 60, max_rating: 70, common_cost: 10, rare_cost: 5, epic_cost: 3, legendary_cost: 1, is_active: true,
};

export default function AdminDiamondUpgradesPage() {
  const queryClient = useQueryClient();
  const { data: tiers, isLoading } = useQuery({ queryKey: ["admin-diamond-upgrade-tiers"], queryFn: fetchDiamondUpgradeTiers });

  const [forms, setForms] = useState<Record<number, TierForm>>({});
  const [newTier, setNewTier] = useState<TierForm>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const formFor = (t: DiamondUpgradeTier): TierForm =>
    forms[t.id] ?? {
      min_rating: t.min_rating, max_rating: t.max_rating, common_cost: t.common_cost,
      rare_cost: t.rare_cost, epic_cost: t.epic_cost, legendary_cost: t.legendary_cost, is_active: t.is_active,
    };

  const patch = (id: number, p: Partial<TierForm>) =>
    setForms((prev) => ({ ...prev, [id]: { ...formFor(tiers!.find((t) => t.id === id)!), ...prev[id], ...p } }));

  const isDirty = (t: DiamondUpgradeTier) => {
    const f = forms[t.id];
    if (!f) return false;
    return (
      f.min_rating !== t.min_rating || f.max_rating !== t.max_rating || f.common_cost !== t.common_cost ||
      f.rare_cost !== t.rare_cost || f.epic_cost !== t.epic_cost || f.legendary_cost !== t.legendary_cost ||
      f.is_active !== t.is_active
    );
  };

  const saveMutation = useMutation({
    mutationFn: async (t: DiamondUpgradeTier) => updateDiamondUpgradeTier(t.id, forms[t.id]),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["admin-diamond-upgrade-tiers"] }); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить тир"),
  });

  const createMutation = useMutation({
    mutationFn: () => createDiamondUpgradeTier(newTier),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-diamond-upgrade-tiers"] });
      setNewTier(EMPTY_FORM);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось создать тир"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteDiamondUpgradeTier(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["admin-diamond-upgrade-tiers"] }); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить тир"),
  });

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-2xl font-bold">Апгрейд диамантовых карт</h1>
        <p className="mt-1 text-xs text-slate-400">
          Сколько карточек той или иной редкости нужно скормить диамантовой карте для +1 рейтинга, в зависимости от её
          текущего рейтинга. Диапазоны рейтинга не должны пересекаться. Оставь поле пустым (прочерк), чтобы эта
          редкость была недоступна для апгрейда в этом диапазоне.
        </p>
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="flex flex-col gap-2">
        {tiers?.map((t) => {
          const form = formFor(t);
          const dirty = isDirty(t);
          return (
            <div key={t.id} className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/5 bg-bg-surface p-3">
              <label className="flex items-center gap-1.5">
                <span className="text-xs text-slate-400">Рейтинг от</span>
                <NumberInput min={1} max={99} value={form.min_rating} onChange={(v) => patch(t.id, { min_rating: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
              </label>
              <label className="flex items-center gap-1.5">
                <span className="text-xs text-slate-400">до</span>
                <NumberInput min={1} max={99} value={form.max_rating} onChange={(v) => patch(t.id, { max_rating: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
              </label>
              <label className="flex items-center gap-1.5">
                <span className="text-xs text-slate-400">Обычных за +1</span>
                <NullableNumberInput min={1} value={form.common_cost} onChange={(v) => patch(t.id, { common_cost: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
              </label>
              <label className="flex items-center gap-1.5">
                <span className="text-xs text-slate-400">Редких за +1</span>
                <NullableNumberInput min={1} value={form.rare_cost} onChange={(v) => patch(t.id, { rare_cost: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
              </label>
              <label className="flex items-center gap-1.5">
                <span className="text-xs text-slate-400">Эпик за +1</span>
                <NullableNumberInput min={1} value={form.epic_cost} onChange={(v) => patch(t.id, { epic_cost: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
              </label>
              <label className="flex items-center gap-1.5">
                <span className="text-xs text-slate-400">Легенд за +1</span>
                <NullableNumberInput min={1} value={form.legendary_cost} onChange={(v) => patch(t.id, { legendary_cost: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
              </label>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => patch(t.id, { is_active: e.target.checked })} />
                Активно
              </label>
              <div className="ml-auto flex gap-2">
                <button
                  onClick={() => saveMutation.mutate(t)}
                  disabled={!dirty || saveMutation.isPending}
                  className="rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
                >
                  Сохранить
                </button>
                <button
                  onClick={() => deleteMutation.mutate(t.id)}
                  disabled={deleteMutation.isPending}
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
        <span className="w-full text-xs font-semibold text-slate-300">Новый диапазон</span>
        <label className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400">Рейтинг от</span>
          <NumberInput min={1} max={99} value={newTier.min_rating} onChange={(v) => setNewTier({ ...newTier, min_rating: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400">до</span>
          <NumberInput min={1} max={99} value={newTier.max_rating} onChange={(v) => setNewTier({ ...newTier, max_rating: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400">Обычных за +1</span>
          <NullableNumberInput min={1} value={newTier.common_cost} onChange={(v) => setNewTier({ ...newTier, common_cost: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400">Редких за +1</span>
          <NullableNumberInput min={1} value={newTier.rare_cost} onChange={(v) => setNewTier({ ...newTier, rare_cost: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400">Эпик за +1</span>
          <NullableNumberInput min={1} value={newTier.epic_cost} onChange={(v) => setNewTier({ ...newTier, epic_cost: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400">Легенд за +1</span>
          <NullableNumberInput min={1} value={newTier.legendary_cost} onChange={(v) => setNewTier({ ...newTier, legendary_cost: v })} className="w-16 rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none" />
        </label>
        <button
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          className="ml-auto rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
        >
          Добавить
        </button>
      </div>
    </div>
  );
}
