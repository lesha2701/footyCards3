import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  createAdminPathTask,
  deleteAdminPathTask,
  fetchAdminPath,
  fetchGameConfig,
  updateAdminPathStage,
  updateAdminPathTalent,
  updateAdminPathTask,
  updateGameConfig,
  type AdminPathTaskIn,
} from "@/admin/api";
import type { AdminPathOverview, AdminPathTalent, GameConfig } from "@/admin/types";
import { ApiRequestError } from "@/lib/api";

type NumKey = Extract<keyof GameConfig, `path_${string}` | `${string}_max_path_cards`>;

const NUMBER_FIELDS: [NumKey, string][] = [
  ["path_xp_base", "Опыт за 1-й уровень (база)"],
  ["path_xp_step", "+ опыта за каждый следующий уровень"],
  ["path_start_rating", "Рейтинг, от которого считается шкала"],
  ["path_rating_per_level", "Рейтинга за уровень"],
  ["path_xp_match", "Опыт: сыгранный матч"],
  ["path_xp_win", "Опыт: победа"],
  ["path_xp_draw", "Опыт: ничья"],
  ["path_xp_goal", "Опыт: гол"],
  ["path_xp_assist", "Опыт: голевой пас"],
  ["path_daily_free_arena", "Бесплатных попыток Card Arena в день (на карту)"],
  ["path_daily_ptour", "Матчей турнира игроков в день (на карту)"],
  ["path_daily_career", "Туров карьеры в день (на карту)"],
  ["path_talent_cap", "Потолок прибавки талантов за матч"],
  ["match_max_path_cards", "Макс. карт пути в составе Card Arena"],
  ["tactico_max_path_cards", "Макс. карт пути в составе Тактико"],
  ["stratego_max_path_cards", "Макс. карт пути в составе Стратего"],
];

const PARAM_LABELS: Record<string, string> = {
  bonus: "Бонус к рейтингу",
  threshold_pct: "Соперник сильнее на, %",
  from_minute: "С минуты",
  fatigue_cut_pct: "Карьера: меньше усталости, %",
  link_floor: "Мин. связь (1 средняя, 2 сильная)",
  extra_points: "+ очков химии",
  coach_bonus: "Тренер-земляк: бонус",
  stadium_bonus: "Стадион клуба: бонус",
  per_match: "За матч подряд",
  max: "Максимум",
  keep_on_miss_pct: "Пропуск: оставить серии, %",
  aura: "Аура соседу",
  aura_cap: "Аура на команду, максимум",
};

function errorText(err: unknown) {
  return err instanceof ApiRequestError ? err.message : "Ошибка";
}

function totalXp(config: Partial<GameConfig>, top: number): number {
  const per = Math.max(1, config.path_rating_per_level ?? 1);
  const levels = Math.max(0, Math.floor((top - (config.path_start_rating ?? 60)) / per));
  let sum = 0;
  for (let n = 1; n <= levels; n++) sum += Math.max(1, (config.path_xp_base ?? 0) + (config.path_xp_step ?? 0) * (n - 1));
  return sum;
}

function TalentRow({ talent, onSave, busy }: { talent: AdminPathTalent; onSave: (payload: Parameters<typeof updateAdminPathTalent>[1]) => void; busy: boolean }) {
  const [values, setValues] = useState(talent.level_values);
  useEffect(() => setValues(talent.level_values), [talent.level_values]);
  return (
    <div className="rounded-xl border border-white/5 bg-bg-base p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">
          {talent.emoji} {talent.name} <span className="text-xs text-slate-400">({talent.code}, {talent.kind === "static" ? "на старте матча" : "по ходу матча"})</span>
        </p>
        <label className="flex items-center gap-2 text-xs">
          <input type="checkbox" checked={talent.is_enabled} disabled={busy} onChange={(e) => onSave({ is_enabled: e.target.checked })} />
          Включён
        </label>
      </div>
      <p className="mt-1 text-xs text-slate-400">{talent.summary}</p>
      <p className="mt-1 text-[11px] text-slate-500">
        Режимы: {Object.entries(talent.modes).map(([m, t]) => `${m} — ${t}`).join("; ")}
        {talent.positions && ` · позиции: ${talent.positions.join(", ")}`} · игроков: {talent.players}
      </p>
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {["1", "2"].map((lvl) => (
          <div key={lvl} className="rounded-lg bg-white/5 p-2">
            <p className="mb-1 text-xs font-semibold">Уровень {lvl === "1" ? "I" : "II"}</p>
            {Object.keys(talent.params).map((key) => (
              <label key={key} className="mb-1 flex items-center justify-between gap-2 text-xs">
                <span className="text-slate-400">{PARAM_LABELS[key] ?? key}</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={values[lvl]?.[key] ?? 0}
                  onChange={(e) => setValues({ ...values, [lvl]: { ...values[lvl], [key]: Number(e.target.value) } })}
                  className="w-20 rounded bg-bg-surface px-2 py-1 text-right outline-none"
                />
              </label>
            ))}
          </div>
        ))}
      </div>
      <button
        type="button"
        disabled={busy}
        onClick={() => onSave({ level_values: values })}
        className="mt-2 rounded-lg bg-accent-lime px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
      >
        Сохранить силу
      </button>
    </div>
  );
}

const EMPTY_TASK: AdminPathTaskIn = { stage_index: 0, metric: "matches", target: 10, positions: null, sort_order: 0, is_active: true };

export default function AdminPathPage() {
  const queryClient = useQueryClient();
  const { data: overview } = useQuery({ queryKey: ["admin-path"], queryFn: fetchAdminPath });
  const { data: config } = useQuery({ queryKey: ["admin-game-config"], queryFn: fetchGameConfig });
  const [form, setForm] = useState<Partial<GameConfig> | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [newTask, setNewTask] = useState<AdminPathTaskIn>(EMPTY_TASK);

  useEffect(() => {
    if (!config) return;
    const picked: Partial<GameConfig> = {
      path_enabled: config.path_enabled,
      path_title: config.path_title,
      path_coin_attempt_prices: config.path_coin_attempt_prices,
      path_stars_attempt_prices: config.path_stars_attempt_prices,
    };
    for (const [key] of NUMBER_FIELDS) (picked as Record<string, number>)[key] = config[key] as number;
    setForm(picked);
  }, [config]);

  const onOverview = (data: AdminPathOverview) => {
    setMessage(null);
    queryClient.setQueryData(["admin-path"], data);
  };
  const saveConfig = useMutation({
    mutationFn: () => updateGameConfig(form!),
    onSuccess: () => {
      setMessage("Настройки сохранены");
      queryClient.invalidateQueries({ queryKey: ["admin-game-config"] });
    },
    onError: (err) => setMessage(errorText(err)),
  });
  const talentMutation = useMutation({
    mutationFn: ({ code, payload }: { code: string; payload: Parameters<typeof updateAdminPathTalent>[1] }) =>
      updateAdminPathTalent(code, payload),
    onSuccess: onOverview,
    onError: (err) => setMessage(errorText(err)),
  });
  const stageMutation = useMutation({
    mutationFn: ({ index, payload }: { index: number; payload: Parameters<typeof updateAdminPathStage>[1] }) =>
      updateAdminPathStage(index, payload),
    onSuccess: onOverview,
    onError: (err) => setMessage(errorText(err)),
  });
  const taskMutation = useMutation({
    mutationFn: (op: { kind: "create"; task: AdminPathTaskIn } | { kind: "update"; id: number; task: AdminPathTaskIn } | { kind: "delete"; id: number }) =>
      op.kind === "create"
        ? createAdminPathTask(op.task)
        : op.kind === "update"
          ? updateAdminPathTask(op.id, op.task)
          : deleteAdminPathTask(op.id),
    onSuccess: onOverview,
    onError: (err) => setMessage(errorText(err)),
  });

  if (!overview || !form) return <p className="text-sm text-slate-400">Загрузка...</p>;
  const ceiling = overview.stages[overview.stages.length - 1]?.max_rating ?? 96;
  const priceList = (key: "path_coin_attempt_prices" | "path_stars_attempt_prices", label: string) => (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label} (через запятую; число цен = лимит покупок в день на карту)</span>
      <input
        value={(form[key] ?? []).join(", ")}
        onChange={(e) =>
          setForm({ ...form, [key]: e.target.value.split(",").map((v) => Number(v.trim())).filter((v) => v > 0) })
        }
        className="rounded-lg bg-bg-base px-3 py-2 outline-none"
      />
    </label>
  );

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold">🌱 {overview.title}</h1>
      {message && <p className="rounded-lg bg-white/5 px-3 py-2 text-sm">{message}</p>}

      <section className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4">
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={!!form.path_enabled} onChange={(e) => setForm({ ...form, path_enabled: e.target.checked })} />
          Механика включена
        </label>
        <p className="mt-2 text-xs text-slate-400">
          Выключение: опыт и покупки попыток недоступны, таланты не действуют в новых матчах. Полученные уровни (рейтинг) остаются.
          Карточка пути — бриллиантовый игрок с выбранным талантом (вкладка «Игроки» → «Талант пути»).
        </p>
        <label className="mt-3 flex flex-col gap-1">
          <span className="text-xs text-slate-400">Название механики / коллекции / пака</span>
          <input
            value={form.path_title ?? ""}
            onChange={(e) => setForm({ ...form, path_title: e.target.value })}
            className="rounded-lg bg-bg-base px-3 py-2 outline-none"
          />
        </label>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Опыт, лимиты, цены</p>
        <p className="mb-3 text-xs text-slate-400">
          Уровень n стоит «база + шаг × (n − 1)». Сейчас до потолка {ceiling}: {totalXp(form, ceiling).toLocaleString("ru-RU")} опыта.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {NUMBER_FIELDS.map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">{label}</span>
              <input
                type="number"
                min={0}
                value={(form[key] as number | undefined) ?? 0}
                onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
                className="rounded-lg bg-bg-base px-3 py-2 outline-none"
              />
            </label>
          ))}
          {priceList("path_coin_attempt_prices", "Цены попыток за монеты")}
          {priceList("path_stars_attempt_prices", "Цены попыток за Stars")}
        </div>
        <button
          type="button"
          disabled={saveConfig.isPending}
          onClick={() => saveConfig.mutate()}
          className="mt-4 rounded-xl bg-accent-lime px-4 py-2 text-sm font-bold text-bg-base disabled:opacity-40"
        >
          Сохранить настройки
        </button>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Этапы и задания</p>
        <div className="flex flex-col gap-3">
          {overview.stages.map((stage) => (
            <div key={stage.index} className="rounded-xl border border-white/5 bg-bg-base p-3">
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] text-slate-400">Этап {stage.index + 1}</span>
                  <input
                    defaultValue={stage.name}
                    onBlur={(e) => e.target.value !== stage.name && stageMutation.mutate({ index: stage.index, payload: { name: e.target.value } })}
                    className="w-40 rounded bg-bg-surface px-2 py-1 outline-none"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] text-slate-400">Верхний рейтинг</span>
                  <input
                    type="number"
                    defaultValue={stage.max_rating}
                    onBlur={(e) => Number(e.target.value) !== stage.max_rating && stageMutation.mutate({ index: stage.index, payload: { max_rating: Number(e.target.value) } })}
                    className="w-24 rounded bg-bg-surface px-2 py-1 outline-none"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] text-slate-400">Открывает талант</span>
                  <select
                    value={stage.talent_level}
                    onChange={(e) => stageMutation.mutate({ index: stage.index, payload: { talent_level: Number(e.target.value) } })}
                    className="rounded bg-bg-surface px-2 py-1 outline-none"
                  >
                    <option value={0}>—</option>
                    <option value={1}>уровень I</option>
                    <option value={2}>уровень II</option>
                  </select>
                </label>
              </div>
              <ul className="mt-2 space-y-1">
                {overview.tasks.filter((t) => t.stage_index === stage.index).map((task) => (
                  <li key={task.id} className="flex flex-wrap items-center gap-2 text-xs">
                    <span className={task.is_active ? "" : "text-slate-500 line-through"}>
                      {overview.metrics[task.metric] ?? task.metric}: {task.target}
                      {task.positions && ` (${task.positions.join(", ")})`}
                    </span>
                    <input
                      type="number"
                      min={1}
                      defaultValue={task.target}
                      onBlur={(e) =>
                        Number(e.target.value) !== task.target &&
                        taskMutation.mutate({ kind: "update", id: task.id, task: { ...task, target: Number(e.target.value) } })
                      }
                      className="w-20 rounded bg-bg-surface px-2 py-0.5 outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => taskMutation.mutate({ kind: "update", id: task.id, task: { ...task, is_active: !task.is_active } })}
                      className="rounded bg-white/5 px-2 py-0.5"
                    >
                      {task.is_active ? "Выключить" : "Включить"}
                    </button>
                    <button
                      type="button"
                      onClick={() => taskMutation.mutate({ kind: "delete", id: task.id })}
                      className="rounded bg-red-500/20 px-2 py-0.5 text-red-300"
                    >
                      Удалить
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-2 rounded-xl bg-white/5 p-3 text-xs">
          <label className="flex flex-col gap-1">
            <span className="text-slate-400">Этап</span>
            <select value={newTask.stage_index} onChange={(e) => setNewTask({ ...newTask, stage_index: Number(e.target.value) })} className="rounded bg-bg-base px-2 py-1">
              {overview.stages.map((s) => <option key={s.index} value={s.index}>{s.name}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-400">Метрика</span>
            <select value={newTask.metric} onChange={(e) => setNewTask({ ...newTask, metric: e.target.value })} className="rounded bg-bg-base px-2 py-1">
              {Object.entries(overview.metrics).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-400">Цель</span>
            <input type="number" min={1} value={newTask.target} onChange={(e) => setNewTask({ ...newTask, target: Number(e.target.value) })} className="w-20 rounded bg-bg-base px-2 py-1" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-400">Позиции (пусто = все)</span>
            <input
              placeholder="ST, LW, RW"
              value={(newTask.positions ?? []).join(", ")}
              onChange={(e) => {
                const list = e.target.value.split(",").map((v) => v.trim().toUpperCase()).filter(Boolean);
                setNewTask({ ...newTask, positions: list.length ? list : null });
              }}
              className="w-32 rounded bg-bg-base px-2 py-1"
            />
          </label>
          <button
            type="button"
            onClick={() => taskMutation.mutate({ kind: "create", task: newTask })}
            className="rounded-lg bg-accent-lime px-3 py-1.5 font-bold text-bg-base"
          >
            Добавить задание
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Таланты</p>
        <div className="flex flex-col gap-3">
          {overview.talents.map((talent) => (
            <TalentRow
              key={talent.code}
              talent={talent}
              busy={talentMutation.isPending}
              onSave={(payload) => talentMutation.mutate({ code: talent.code, payload })}
            />
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-2 font-display text-base font-bold">Игроки пути ({overview.players.length})</p>
        <p className="mb-2 text-xs text-slate-400">
          Пак «{overview.title}» (вкладка «Паки», пул «Начало пути») в бриллиантовых слотах выдаёт только этих игроков;
          обычные паки их никогда не выдают.
        </p>
        <ul className="divide-y divide-white/5 text-sm">
          {overview.players.map((p) => {
            const talent = overview.talents.find((t) => t.code === p.talent_code);
            return (
              <li key={p.id} className="flex flex-wrap justify-between gap-2 py-1.5">
                <span>
                  {p.display_name} <span className="text-xs text-slate-400">{p.position} · {p.rating}</span>
                  {!p.is_active && <span className="ml-1 text-xs text-red-300">неактивен</span>}
                </span>
                <span className="text-xs text-slate-400">
                  {talent ? `${talent.emoji} ${talent.name}` : p.talent_code} · копий: {p.copies}
                </span>
              </li>
            );
          })}
          {!overview.players.length && <li className="py-2 text-xs text-slate-500">Пока нет — назначь талант бриллиантовому игроку.</li>}
        </ul>
      </section>
    </div>
  );
}
