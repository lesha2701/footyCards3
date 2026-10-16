import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchCalendarTemplate, updateCalendarTemplate } from "@/admin/api";
import { useAdminToastStore } from "@/admin/adminToastStore";
import RewardBundleEditor from "@/admin/components/RewardBundleEditor";
import type { CalendarTemplateDay } from "@/admin/types";
import { ApiRequestError } from "@/lib/api";

/** «Календарь наград»: one template for every month — a reward per day of
 * the month (29–31 only show in long months) plus the full-month bonus.
 * Catch-up prices live in «Абонемент, сезон, стиль» → Настройки. */
export default function AdminDailyRewardsPage() {
  const queryClient = useQueryClient();
  const { data: template, isLoading } = useQuery({ queryKey: ["admin-login-calendar"], queryFn: fetchCalendarTemplate });
  const [draft, setDraft] = useState<CalendarTemplateDay[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Seed the draft once; a background refetch must not clobber edits.
  useEffect(() => {
    if (template && draft === null) setDraft(template);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [template]);

  const save = useMutation({
    mutationFn: (days: CalendarTemplateDay[]) => updateCalendarTemplate(days),
    onSuccess: (saved) => {
      setDraft(saved);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-login-calendar"] });
      useAdminToastStore.getState().push("Календарь сохранён", "success");
    },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить календарь"),
  });

  if (isLoading || !draft) return <p className="text-sm text-slate-400">Загрузка...</p>;

  const update = (day: number, next: CalendarTemplateDay) =>
    setDraft((prev) => prev?.map((d) => (d.day === day ? next : d)) ?? prev);
  const ordered = [...draft.filter((d) => d.day > 0).sort((a, b) => a.day - b.day), ...draft.filter((d) => d.day === 0)];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-bold">Календарь наград</h1>
          <p className="text-xs text-slate-400">
            Награда на каждое число месяца (один шаблон для всех месяцев) и бонус за все дни месяца. Пропущенный день
            игрок может догнать за монеты или ⭐ — цены и лимит в разделе «Абонемент, сезон, стиль».
          </p>
        </div>
        <button
          onClick={() => save.mutate(draft)}
          disabled={save.isPending}
          className="shrink-0 rounded-lg bg-accent px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
        >
          {save.isPending ? "Сохранение..." : "Сохранить"}
        </button>
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="flex flex-col gap-2">
        {ordered.map((d) => (
          <div
            key={d.day}
            className={`rounded-2xl border p-3 ${
              d.day === 0 ? "border-amber-400/40 bg-amber-400/5" : d.day % 7 === 0 ? "border-amber-400/20 bg-bg-surface" : "border-white/5 bg-bg-surface"
            }`}
          >
            <p className="mb-2 font-display text-sm font-bold">
              {d.day === 0 ? "Бонус за весь месяц" : `${d.day} число${d.day > 28 ? " (не в каждом месяце)" : ""}`}
            </p>
            <RewardBundleEditor value={d} onChange={(next) => update(d.day, { ...next, day: d.day })} />
          </div>
        ))}
      </div>
    </div>
  );
}
