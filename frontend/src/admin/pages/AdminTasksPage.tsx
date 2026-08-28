import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  backfillPremiumTaskCoins,
  createTask,
  deleteTask,
  fetchAdminPacks,
  fetchAdminTasks,
  sendPremiumTaskBroadcast,
  toggleTaskActive,
  updateTask,
} from "@/admin/api";
import type { TaskDefinition } from "@/admin/types";
import { ApiRequestError } from "@/lib/api";
import { showConfirm } from "@/lib/telegram";

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
  max_rating: number;
  reward_coins: number;
  reward_pack_id: number | "";
  channel_username: string;
  channel_chat_id: string;
  invite_link: string;
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
    max_rating: (t?.condition_params?.max_rating as number | undefined) ?? 70,
    reward_coins: t?.reward_coins ?? 0,
    reward_pack_id: t?.reward_pack_id ?? "",
    channel_username: t?.channel_username ?? "",
    channel_chat_id: t?.channel_chat_id ? String(t.channel_chat_id) : "",
    invite_link: t?.invite_link ?? "",
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
  const [error, setError] = useState<string | null>(null);

  const [broadcastCount, setBroadcastCount] = useState(1);
  const [broadcastMessage, setBroadcastMessage] = useState("");
  const [broadcastResult, setBroadcastResult] = useState<number | null>(null);
  const [broadcastError, setBroadcastError] = useState<string | null>(null);

  const [backfillResult, setBackfillResult] = useState<{ definitions_updated: number; users_credited: number } | null>(null);
  const [backfillError, setBackfillError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-tasks"] });
  const toggleMutation = useMutation({ mutationFn: toggleTaskActive, onSuccess: invalidate });
  const deleteMutation = useMutation({
    mutationFn: deleteTask,
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить задание"),
  });

  const confirmDelete = async (t: TaskDefinition) => {
    if (await showConfirm(`Удалить задание «${t.name}» навсегда? Это действие необратимо.`)) {
      deleteMutation.mutate(t.id);
    }
  };

  const broadcastMutation = useMutation({
    mutationFn: () => sendPremiumTaskBroadcast(broadcastCount, broadcastMessage),
    onSuccess: (res) => { setBroadcastResult(res.recipients); setBroadcastError(null); setBroadcastMessage(""); },
    onError: (err) => {
      setBroadcastError(err instanceof ApiRequestError ? err.message : "Не удалось отправить рассылку");
      setBroadcastResult(null);
    },
  });

  const sendBroadcast = async () => {
    if (broadcastCount < 1) return;
    if (!(await showConfirm(`Отправить одно уведомление о новых премиум-заданиях (${broadcastCount} шт.) всем пользователям? Отменить рассылку будет нельзя.`))) return;
    setBroadcastResult(null);
    broadcastMutation.mutate();
  };

  const backfillMutation = useMutation({
    mutationFn: backfillPremiumTaskCoins,
    onSuccess: (res) => { setBackfillResult(res); setBackfillError(null); invalidate(); },
    onError: (err) => {
      setBackfillError(err instanceof ApiRequestError ? err.message : "Не удалось выполнить начисление");
      setBackfillResult(null);
    },
  });

  const runBackfill = async () => {
    if (!(await showConfirm("Проставить 1000 монет тем активным премиум-заданиям, где награда сейчас 0, и задним числом начислить эти монеты игрокам, которые уже забрали такое задание? Действие безопасно повторять."))) return;
    setBackfillResult(null);
    backfillMutation.mutate();
  };

  const buildPayload = () => ({
    code: form.code,
    name: form.name,
    description: form.description,
    category: form.category,
    condition_type: form.condition_type,
    metric: form.condition_type === "metric_counter" ? form.metric || null : null,
    target_value: form.condition_type === "metric_counter" ? form.target_value : 1,
    condition_params:
      form.condition_type === "match_min_rating"
        ? { min_rating: form.min_rating }
        : form.condition_type === "penalty_win_max_rating"
          ? { max_rating: form.max_rating }
          : null,
    reward_coins: form.reward_coins,
    reward_pack_id: form.reward_pack_id || null,
    channel_username: form.category === "premium" ? form.channel_username || null : null,
    channel_chat_id: form.category === "premium" && form.channel_chat_id ? Number(form.channel_chat_id) : null,
    invite_link: form.category === "premium" ? form.invite_link || null : null,
    is_active: form.is_active,
  });

  const createMutation = useMutation({ mutationFn: () => createTask(buildPayload()), onSuccess: () => { invalidate(); setCreating(false); } });
  const updateMutation = useMutation({ mutationFn: () => updateTask(editing!.id, buildPayload()), onSuccess: () => { invalidate(); setEditing(null); } });

  const openEdit = (t: TaskDefinition) => { setEditing(t); setForm(taskToForm(t)); setError(null); };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Задания</h1>
        <button onClick={() => { setCreating(true); setForm(taskToForm()); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">
          + Новое задание
        </button>
      </div>

      <div className="rounded-2xl border border-white/5 bg-bg-surface p-3">
        <p className="mb-1 font-display text-sm font-bold">Оповестить о новых премиум-заданиях</p>
        <p className="mb-3 text-xs text-slate-400">
          Создание задания больше не рассылает уведомление автоматически — добавь все нужные задания, затем пришли
          одно оповещение здесь, чтобы игроки не получали по уведомлению на каждое задание.
        </p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">Сколько заданий добавлено</span>
            <input
              type="number"
              min={1}
              max={50}
              value={broadcastCount}
              onChange={(e) => setBroadcastCount(Math.max(1, Number(e.target.value)))}
              className="w-28 rounded-lg bg-bg-base px-3 py-2 text-sm outline-none"
            />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className="text-xs text-slate-400">Дополнительный текст (необязательно)</span>
            <input
              value={broadcastMessage}
              onChange={(e) => setBroadcastMessage(e.target.value)}
              maxLength={500}
              placeholder="Например: успей до конца недели"
              className="rounded-lg bg-bg-base px-3 py-2 text-sm outline-none"
            />
          </label>
          <button
            onClick={sendBroadcast}
            disabled={broadcastMutation.isPending}
            className="rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
          >
            {broadcastMutation.isPending ? "Отправка..." : "Отправить"}
          </button>
        </div>
        <p className="mt-2 text-[11px] text-slate-500">
          Предпросмотр: «Появилось {broadcastCount} {pluralizeTasks(broadcastCount)}! Успей получить награду»
          {broadcastMessage.trim() && <> + «{broadcastMessage.trim()}»</>}
        </p>
        {broadcastError && <p className="mt-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{broadcastError}</p>}
        {broadcastResult !== null && (
          <p className="mt-2 rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">Отправлено {broadcastResult} пользователям.</p>
        )}
      </div>

      <div className="rounded-2xl border border-white/5 bg-bg-surface p-3">
        <p className="mb-1 font-display text-sm font-bold">Начислить монеты за старые премиум-задания</p>
        <p className="mb-3 text-xs text-slate-400">
          Разово: активным премиум-заданиям без награды (0 монет) проставляет 1000 монет и задним числом начисляет
          эту сумму игрокам, которые уже забрали награду за такое задание. Безопасно нажимать повторно — уже
          обработанные задания и игроки не трогаются второй раз.
        </p>
        <button
          onClick={runBackfill}
          disabled={backfillMutation.isPending}
          className="rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
        >
          {backfillMutation.isPending ? "Выполняется..." : "Начислить"}
        </button>
        {backfillError && <p className="mt-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{backfillError}</p>}
        {backfillResult !== null && (
          <p className="mt-2 rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">
            Обновлено заданий: {backfillResult.definitions_updated} · начислено игрокам: {backfillResult.users_credited}
          </p>
        )}
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}
      {error && !creating && !editing && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {tasks?.map((t) => (
          <div key={t.id} className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="flex items-center justify-between">
              <p className="font-display text-sm font-bold">{t.name}</p>
              {t.category === "premium" && <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] text-amber-300">Премиум</span>}
            </div>
            <p className="text-xs text-slate-400">{t.description}</p>
            <p className="mt-1 text-xs text-slate-500">
              {t.condition_type === "metric_counter"
                ? `${t.metric} ≥ ${t.target_value}`
                : t.condition_type === "match_min_rating"
                  ? `рейтинг ≥ ${t.condition_params?.min_rating}`
                  : t.condition_type === "penalty_win_max_rating"
                    ? `победа, рейтинг < ${t.condition_params?.max_rating}`
                    : "состав из одной страны"}
              {" · "}
              {t.reward_pack_id ? `пак #${t.reward_pack_id}` : `+${t.reward_coins} 🪙`}
            </p>
            <p className="text-xs text-slate-500">{t.is_active ? "Активно" : "Отключено"}</p>
            <p className="mt-1 text-xs text-slate-500">
              Выполнили: <span className="font-semibold text-slate-300">{t.completed_count}</span>
              {" · "}
              Забрали награду: <span className="font-semibold text-slate-300">{t.claimed_count}</span>
            </p>
            <div className="mt-2 flex flex-wrap gap-1">
              <button onClick={() => openEdit(t)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => toggleMutation.mutate(t.id)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">
                {t.is_active ? "Отключить" : "Включить"}
              </button>
              <button onClick={() => confirmDelete(t)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">
                Удалить
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
                  <option value="match_same_country">Состав Card Arena из одной страны</option>
                  <option value="penalty_win_max_rating">Победа в Пенальти игроком с рейтингом ниже X</option>
                </select>
              </label>

              {form.condition_type === "metric_counter" ? (
                <div className="grid grid-cols-2 gap-2">
                  <Field
                    label="Метрика (packs_opened, unique_players, referrals_count, trades_completed, arena_clean_sheet_wins, memory_levels_completed, saboteur_levels_cleared, ...)"
                    value={form.metric}
                    onChange={(v) => setForm({ ...form, metric: v })}
                  />
                  <NumField label="Целевое значение" value={form.target_value} onChange={(v) => setForm({ ...form, target_value: v })} />
                </div>
              ) : form.condition_type === "match_min_rating" ? (
                <NumField label="Мин. рейтинг игрока" value={form.min_rating} onChange={(v) => setForm({ ...form, min_rating: v })} />
              ) : form.condition_type === "penalty_win_max_rating" ? (
                <NumField
                  label="Макс. рейтинг игрока (строго меньше)"
                  value={form.max_rating}
                  onChange={(v) => setForm({ ...form, max_rating: v })}
                />
              ) : (
                <p className="text-[11px] text-slate-500">
                  Выполняется автоматически, когда игрок сыграет матч Card Arena составом из 11 карточек одной страны.
                </p>
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
                <>
                  <Field
                    label="Канал (@username, если есть)"
                    value={form.channel_username}
                    onChange={(v) => setForm({ ...form, channel_username: v })}
                  />
                  <Field
                    label="ID канала (обязательно, если нет @username)"
                    value={form.channel_chat_id}
                    onChange={(v) => setForm({ ...form, channel_chat_id: v })}
                  />
                  <Field
                    label="Ссылка-приглашение (показывается пользователю)"
                    value={form.invite_link}
                    onChange={(v) => setForm({ ...form, invite_link: v })}
                  />
                  <p className="text-[11px] text-slate-500">
                    Заполни @username ИЛИ ID канала — бот проверяет подписку по ID, если он указан, иначе по
                    @username (бот должен быть админом канала). Для приватных каналов без @username ID узнают у
                    админа канала — обычно вида -100xxxxxxxxxx. Пользователю в приложении показывается кнопка со
                    ссылкой-приглашением; если её не указать, используется прямая ссылка на @username.
                  </p>
                </>
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

function pluralizeTasks(n: number): string {
  const lastTwo = n % 100;
  const lastOne = n % 10;
  if (lastOne === 1 && lastTwo !== 11) return "новое премиум задание";
  if ([2, 3, 4].includes(lastOne) && ![12, 13, 14].includes(lastTwo)) return "новых премиум задания";
  return "новых премиум заданий";
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
