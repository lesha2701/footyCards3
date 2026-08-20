import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchUpgradeRules, updateUpgradeRule } from "@/admin/api";
import NumberInput from "@/components/common/NumberInput";
import { ApiRequestError } from "@/lib/api";
import { RARITY_LABELS } from "@/lib/rarity";
import type { CardUpgradeRule } from "@/types";

type RuleForm = Pick<CardUpgradeRule, "success_chance" | "coin_cost" | "is_active" | "extra_card_bonus" | "max_success_chance">;

function isDirtyRule(r: CardUpgradeRule, f?: RuleForm): boolean {
  return (
    !!f &&
    (f.success_chance !== r.success_chance ||
      f.coin_cost !== r.coin_cost ||
      f.is_active !== r.is_active ||
      f.extra_card_bonus !== r.extra_card_bonus ||
      f.max_success_chance !== r.max_success_chance)
  );
}

export default function AdminUpgradesPage() {
  const queryClient = useQueryClient();
  const { data: rules, isLoading } = useQuery({ queryKey: ["admin-upgrade-rules"], queryFn: fetchUpgradeRules });

  const [forms, setForms] = useState<Record<number, RuleForm>>({});
  useEffect(() => {
    if (!rules) return;
    setForms(
      Object.fromEntries(
        rules.map((r) => [
          r.id,
          {
            success_chance: r.success_chance,
            coin_cost: r.coin_cost,
            is_active: r.is_active,
            extra_card_bonus: r.extra_card_bonus,
            max_success_chance: r.max_success_chance,
          },
        ])
      )
    );
  }, [rules]);

  const [error, setError] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const changed = (rules ?? []).filter((r) => isDirtyRule(r, forms[r.id]));
      await Promise.all(changed.map((r) => updateUpgradeRule(r.id, forms[r.id])));
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["admin-upgrade-rules"] }); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить изменения"),
  });

  const isDirty = (rules ?? []).some((r) => isDirtyRule(r, forms[r.id]));

  const patch = (id: number, patch: Partial<RuleForm>) => setForms((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Апгрейд карточек</h1>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={!isDirty || saveMutation.isPending}
          className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
        >
          {saveMutation.isPending ? "Сохранение..." : "Сохранить изменения"}
        </button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="flex flex-col gap-2">
        {rules?.map((r) => {
          const form = forms[r.id];
          if (!form) return null;
          return (
            <div key={r.id} className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/5 bg-bg-surface p-3">
              <div className="w-40 text-sm font-semibold">
                {RARITY_LABELS[r.from_rarity]} → {RARITY_LABELS[r.to_rarity]}
              </div>
              <label className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Шанс успеха, %</span>
                <NumberInput
                  step={0.01}
                  min={0}
                  max={100}
                  value={Math.round(form.success_chance * 10000) / 100}
                  onChange={(v) => patch(r.id, { success_chance: Math.round(v * 100) / 10000 })}
                  className="w-24 rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none"
                />
              </label>
              <label className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Стоимость, монеты</span>
                <NumberInput
                  min={0}
                  value={form.coin_cost}
                  onChange={(v) => patch(r.id, { coin_cost: v })}
                  className="w-24 rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none"
                />
              </label>
              <label className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Бонус за карту, %</span>
                <NumberInput
                  step={0.01}
                  min={0}
                  max={100}
                  value={Math.round(form.extra_card_bonus * 10000) / 100}
                  onChange={(v) => patch(r.id, { extra_card_bonus: Math.round(v * 100) / 10000 })}
                  className="w-24 rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none"
                />
              </label>
              <label className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Максимум шанса, %</span>
                <NumberInput
                  step={0.01}
                  min={0}
                  max={100}
                  value={Math.round(form.max_success_chance * 10000) / 100}
                  onChange={(v) => patch(r.id, { max_success_chance: Math.round(v * 100) / 10000 })}
                  className="w-24 rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none"
                />
              </label>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => patch(r.id, { is_active: e.target.checked })} />
                Активно
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}
