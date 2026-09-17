import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchAdminPacks, fetchDailyRewardOptions, updateDailyRewardOptions } from "@/admin/api";
import { useAdminToastStore } from "@/admin/adminToastStore";
import type { DailyRewardOption } from "@/admin/types";
import { ApiRequestError } from "@/lib/api";

type DraftOption = Omit<DailyRewardOption, "id">;

const DAYS = [1, 2, 3, 4, 5, 6, 7];

function groupByDay(options: DailyRewardOption[]): Record<number, DraftOption[]> {
  const byDay: Record<number, DraftOption[]> = {};
  for (const day of DAYS) byDay[day] = [];
  for (const opt of [...options].sort((a, b) => a.option_index - b.option_index)) {
    byDay[opt.day] = byDay[opt.day] ?? [];
    byDay[opt.day].push({ day: opt.day, option_index: opt.option_index, coins: opt.coins, free_pack_slug: opt.free_pack_slug, grants_random_card: opt.grants_random_card });
  }
  return byDay;
}

export default function AdminDailyRewardsPage() {
  const queryClient = useQueryClient();
  const { data: options, isLoading } = useQuery({ queryKey: ["admin-daily-reward-options"], queryFn: fetchDailyRewardOptions });
  const { data: packs } = useQuery({ queryKey: ["admin-packs"], queryFn: fetchAdminPacks });
  const [draft, setDraft] = useState<Record<number, DraftOption[]> | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Server data only ever needs to seed the draft once per fetch — after
  // that the draft is the user's own in-progress edit, which a background
  // refetch (e.g. React Query's window-focus refetch) must not clobber.
  useEffect(() => {
    if (options && draft === null) setDraft(groupByDay(options));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options]);

  const saveMutation = useMutation({
    mutationFn: (payload: DraftOption[]) => updateDailyRewardOptions(payload),
    onSuccess: (saved) => {
      setDraft(groupByDay(saved));
      queryClient.invalidateQueries({ queryKey: ["admin-daily-reward-options"] });
      useAdminToastStore.getState().push("Награды сохранены", "success");
    },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить награды"),
  });

  if (isLoading || !draft) return <p className="text-sm text-slate-400">Загрузка...</p>;

  const updateOption = (day: number, index: number, patch: Partial<DraftOption>) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const next = { ...prev, [day]: prev[day].map((o, i) => (i === index ? { ...o, ...patch } : o)) };
      return next;
    });
  };

  const addOption = (day: number) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const nextIndex = (prev[day][prev[day].length - 1]?.option_index ?? 0) + 1;
      return { ...prev, [day]: [...prev[day], { day, option_index: nextIndex, coins: 0, free_pack_slug: null, grants_random_card: false }] };
    });
  };

  const removeOption = (day: number, index: number) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return { ...prev, [day]: prev[day].filter((_, i) => i !== index) };
    });
  };

  const save = () => {
    setError(null);
    const flattened = DAYS.flatMap((day) => (draft[day] ?? []).map((o, i) => ({ ...o, day, option_index: i + 1 })));
    const emptyDay = DAYS.find((day) => (draft[day] ?? []).length === 0);
    if (emptyDay) {
      setError(`У дня ${emptyDay} должен быть хотя бы один вариант награды`);
      return;
    }
    saveMutation.mutate(flattened);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">Ежедневные награды</h1>
          <p className="text-xs text-slate-400">
            Для каждого дня цикла (1–7) задай несколько вариантов награды — при старте нового 7-дневного цикла игроку
            случайно достаётся один вариант на каждый день, и это же сочетание держится до конца цикла.
          </p>
        </div>
        <button
          onClick={save}
          disabled={saveMutation.isPending}
          className="rounded-lg bg-accent px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
        >
          {saveMutation.isPending ? "Сохранение..." : "Сохранить"}
        </button>
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="flex flex-col gap-5">
        {DAYS.map((day) => (
          <div key={day} className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="font-display text-sm font-bold">День {day}</p>
              <button onClick={() => addOption(day)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">
                + Вариант
              </button>
            </div>
            <div className="flex flex-col gap-2">
              {(draft[day] ?? []).map((opt, index) => (
                <div key={index} className="grid grid-cols-[1fr_2fr_auto_auto] items-center gap-2 rounded-xl bg-bg-base p-2">
                  <label className="flex flex-col gap-0.5">
                    <span className="text-[10px] text-slate-500">Монеты</span>
                    <input
                      type="number"
                      value={opt.coins}
                      onChange={(e) => updateOption(day, index, { coins: Number(e.target.value) })}
                      className="rounded-lg bg-bg-surface px-2 py-1.5 text-sm outline-none"
                    />
                  </label>
                  <label className="flex flex-col gap-0.5">
                    <span className="text-[10px] text-slate-500">Бесплатный пак</span>
                    <select
                      value={opt.free_pack_slug ?? ""}
                      onChange={(e) => updateOption(day, index, { free_pack_slug: e.target.value || null })}
                      className="rounded-lg bg-bg-surface px-2 py-1.5 text-sm outline-none"
                    >
                      <option value="">Нет</option>
                      {packs?.map((p) => <option key={p.id} value={p.slug}>{p.name}</option>)}
                    </select>
                  </label>
                  <label className="flex flex-col items-center gap-0.5">
                    <span className="text-[10px] text-slate-500">Карта</span>
                    <input
                      type="checkbox"
                      checked={opt.grants_random_card}
                      onChange={(e) => updateOption(day, index, { grants_random_card: e.target.checked })}
                    />
                  </label>
                  <button
                    onClick={() => removeOption(day, index)}
                    className="rounded-lg bg-red-500/10 px-2 py-1.5 text-[11px] text-red-400"
                  >
                    Удалить
                  </button>
                </div>
              ))}
              {(draft[day] ?? []).length === 0 && <p className="text-xs text-slate-500">Нет вариантов — добавь хотя бы один</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
