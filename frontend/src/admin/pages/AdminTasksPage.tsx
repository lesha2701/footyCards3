import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createTask, fetchAdminPacks, fetchAdminTasks, toggleTaskActive, updateTask } from "@/admin/api";
import type { TaskDefinition } from "@/admin/types";

type Category = TaskDefinition["category"];
type ConditionType = TaskDefinition["condition_type"];

interface TaskForm {
  code: string;
  name: string;
  description: string;
  category: Category;
  condition_type: ConditionType;
  metric: string;
  target_value: number;
  min_rating: number;
  reward_coins: number;
  reward_pack_id: number | "";
  channel_username: string;
  is_active: boolean;
}

function taskToForm(t?: TaskDefinition): TaskForm {
  return {
    code: t?.code ?? "",
    name: t?.name ?? "",
    description: t?.description ?? "",
    category: t?.category ?? "regular",
    condition_type: t?.condition_type ?? "metric_counter",
    metric: t?.metric ?? "",
    target_value: t?.target_value ?? 1,
    min_rating: (t?.condition_params?.min_rating as number | undefined) ?? 67,
    reward_coins: t?.reward_coins ?? 0,
    reward_pack_id: t?.reward_pack_id ?? "",
    channel_username: t?.channel_username ?? "",
    is_active: t?.is_active ?? true,
  };
}

export default function AdminTasksPage() {
  const queryClient = useQueryClient();
  const { data: tasks, isLoading } = useQuery({ queryKey: ["admin-tasks"], queryFn: fetchAdminTasks });
  const { data: packs } = useQuery({ queryKey: ["admin-packs"], queryFn: fetchAdminPacks });
  const [editing, setEditing] = useState<TaskDefinition | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<TaskForm>(taskToForm());

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-tasks"] });
  const toggleMutation = useMutation({ mutationFn: toggleTaskActive, onSuccess: invalidate });

  const buildPayload = () => ({
    code: form.code,
    name: form.name,
    description: form.description,
    category: form.category,
    condition_type: form.condition_type,
    metric: form.condition_type === "metric_counter" ? form.metric || null : null,
    target_value: form.condition_type === "metric_counter" ? form.target_value : 1,
    condition_params: form.condition_type === "match_min_rating" ? { min_rating: form.min_rating } : null,
    reward_coins: form.reward_coins,
    reward_pack_id: form.reward_pack_id || null,
    channel_username: form.category === "premium" ? form.channel_username || null : null,
    is_active: form.is_active,
  });

  const createMutation = useMutation({ mutationFn: () => createTask(buildPayload()), onSuccess: () => { invalidate(); setCreating(false); } });
  const updateMutation = useMutation({ mutationFn: () => updateTask(editing!.id, buildPayload()), onSuccess: () => { invalidate(); setEditing(null); } });

  const openEdit = (t: TaskDefinition) => { setEditing(t); setForm(taskToForm(t)); };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Задания</h1>
        <button onClick={() => { setCreating(true); setForm(taskToForm()); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">
          + Новое задание
        </button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {tasks?.map((t) => (
          <div key={t.id} className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="flex items-center justify-between">
              <p className="font-display text-sm font-bold">{t.name}</p>
              {t.category === "premium" && <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] text-amber-300">Премиум</span>}
            </div>
            <p className="text-xs text-slate-400">{t.description}</p>
            <p className="mt-1 text-xs text-slate-500">
              {t.condition_type === "metric_counter" ? `${t.metric} ≥ ${t.target_value}` : `рейтинг ≥ ${t.condition_params?.min_rating}`}
              {" · "}
              {t.reward_pack_id ? `пак #${t.reward_pack_id}` : `+${t.reward_coins} 🪙`}
            </p>
            <p className="text-xs text-slate-500">{t.is_active ? "Активно" : "Отключено"}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              <button onClick={() => openEdit(t)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => toggleMutation.mutate(t.id)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">
                {t.is_active ? "Отключить" : "Включить"}
              </button>
            </div>
          </div>
        ))}
      </div>

      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => { setCreating(false); setEditing(null); }}>
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать задание" : "Новое задание"}</p>
            <div className="flex flex-col gap-2 text-sm">
              {!editing && <Field label="Code (латиницей)" value={form.code} onChange={(v) => setForm({ ...form, code: v })} />}
              <Field label="Название" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
              <Field label="Описание" value={form.description} onChange={(v) => setForm({ ...form, description: v })} />

              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Категория</span>
                <select
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value as Category })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                >
                  <option value="regular">Обычное</option>
                  <option value="premium">Премиум</option>
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Тип условия</span>
                <select
                  value={form.condition_type}
                  onChange={(e) => setForm({ ...form, condition_type: e.target.value as ConditionType })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                >
                  <option value="metric_counter">Счётчик метрики</option>
                  <option value="match_min_rating">Мин. рейтинг состава в матче</option>
                </select>
              </label>

              {form.condition_type === "metric_counter" ? (
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Метрика (packs_opened, ...)" value={form.metric} onChange={(v) => setForm({ ...form, metric: v })} />
                  <NumField label="Целевое значение" value={form.target_value} onChange={(v) => setForm({ ...form, target_value: v })} />
                </div>
              ) : (
                <NumField label="Мин. рейтинг игрока" value={form.min_rating} onChange={(v) => setForm({ ...form, min_rating: v })} />
              )}

              <div className="grid grid-cols-2 gap-2">
                <NumField label="Награда, монеты" value={form.reward_coins} onChange={(v) => setForm({ ...form, reward_coins: v })} />
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Награда: пак</span>
                  <select
                    value={form.reward_pack_id}
                    onChange={(e) => setForm({ ...form, reward_pack_id: e.target.value ? Number(e.target.value) : "" })}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  >
                    <option value="">Нет</option>
                    {packs?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </label>
              </div>

              {form.category === "premium" && (
                <Field label="Канал (@username)" value={form.channel_username} onChange={(v) => setForm({ ...form, channel_username: v })} />
              )}

              <label className="mt-1 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активно
              </label>
            </div>

            <div className="mt-4 flex gap-2">
              <button onClick={() => { setCreating(false); setEditing(null); }} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm">Отмена</button>
              <button
                onClick={() => (editing ? updateMutation.mutate() : createMutation.mutate())}
                className="flex-1 rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base"
              >
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
    </label>
  );
}

function NumField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
    </label>
  );
}
