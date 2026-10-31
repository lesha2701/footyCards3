import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchAdminFanBattle, updateAdminFanBattle, type AdminFanBattle } from "@/admin/api";
import { ApiRequestError } from "@/lib/api";

const NUMBERS: [string, string][] = [
  ["points_per_game", "Очков за наградную игру"],
  ["points_games_daily_cap", "Лимит очков с игр в день (0 — без лимита)"],
  ["points_per_task", "Очков за забранное задание"],
  ["points_per_daily_chest", "Очков за сундук дня"],
  ["points_per_weekly_chest", "Очков за сундук недели"],
  ["underdog_bonus_pct", "Бонус слабой стороне, %"],
  ["underdog_gap_pct", "Бонус, когда сторона меньше другой на, %"],
  ["underdog_min_members", "…и у большей стороны хотя бы фанатов"],
  ["boss_multiplier", "Множитель очков за «Перебежчика»"],
  ["daily_min_points", "Битва дня: минимум очков для награды"],
  ["daily_win_coins", "Битва дня: монет победителям"],
  ["daily_lose_coins", "Битва дня: монет проигравшим"],
  ["final_min_points", "Финал: минимум очков для награды"],
  ["final_win_coins", "Финал: монет победителям"],
  ["final_lose_coins", "Финал: монет проигравшим"],
  ["top_n", "Топ фанатов каждой стороны (бонус финала)"],
  ["top_bonus_coins", "Бонус топ-фанатам, монет"],
  ["claim_days", "Награды можно забрать дней после конца"],
  ["teaser_days", "Анонс на главной за дней до старта"],
  ["final_pack_id", "ID пака победителям финала (пусто — без пака)"],
  ["champion_badge_id", "ID значка «Чемпион трибун 2026»"],
  ["fan_badge_id", "ID значка «Фанат 2026» (рубеж)"],
  ["collection_id", "ID коллекции «Капитаны»"],
];

/** datetime-local value (local time) ⇄ ISO with the browser's offset. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** «⚔️ Битва фанатов»: one switch, the dates, the sides and every number. */
export default function AdminFanBattlePage() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-fan-battle"], queryFn: fetchAdminFanBattle });
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [sidesText, setSidesText] = useState("");
  const [milestonesText, setMilestonesText] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const load = (d: AdminFanBattle) => {
    setForm(d.settings);
    setSidesText(JSON.stringify(d.settings.sides ?? [], null, 2));
    setMilestonesText(JSON.stringify(d.settings.milestones ?? [], null, 2));
    setStart(toLocalInput(d.starts_at));
    setEnd(toLocalInput(d.ends_at));
  };
  useEffect(() => {
    if (data) load(data);
  }, [data]);

  const save = useMutation({
    mutationFn: updateAdminFanBattle,
    onSuccess: (d) => {
      queryClient.setQueryData(["admin-fan-battle"], d);
      load(d);
      setMessage("Сохранено");
    },
    onError: (err) => setMessage(err instanceof ApiRequestError ? err.message : "Не удалось сохранить"),
  });

  if (!data) return <p className="text-sm text-slate-400">Загрузка…</p>;

  const submit = () => {
    setMessage(null);
    let sides: unknown;
    let milestones: unknown;
    try {
      sides = JSON.parse(sidesText);
      milestones = JSON.parse(milestonesText);
    } catch {
      setMessage("Стороны или рубежи — неверный JSON");
      return;
    }
    const settings: Record<string, unknown> = { sides, milestones, boss_enabled: !!form.boss_enabled };
    for (const [key] of NUMBERS) settings[key] = form[key] === "" || form[key] === undefined ? null : Number(form[key]);
    save.mutate({
      settings,
      starts_at: start ? new Date(start).toISOString() : undefined,
      ends_at: end ? new Date(end).toISOString() : undefined,
    });
  };

  const sideCodes = Object.keys({ ...(data.stats.members ?? {}), ...(data.stats.points ?? {}) });

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <h1 className="text-xl font-bold">⚔️ Битва фанатов</h1>

      <section className="flex flex-col gap-3 rounded-xl bg-bg-surface p-4">
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input
            type="checkbox"
            checked={data.enabled}
            disabled={save.isPending}
            onChange={(e) => save.mutate({ enabled: e.target.checked })}
          />
          Ивент включён (выкл — ни выбора сторон, ни очков, ни наград, ни босса, ни баннера)
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">Начало (сторону можно выбрать и раньше)</span>
            <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className="rounded-lg bg-bg-base px-3 py-2" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">Конец = финал (не включительно)</span>
            <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded-lg bg-bg-base px-3 py-2" />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs text-slate-300 sm:grid-cols-4">
          {sideCodes.map((code) => (
            <Stat key={code} label={`«${code}»: фанатов / очков`} value={`${data.stats.members?.[code] ?? 0} / ${(data.stats.points?.[code] ?? 0).toLocaleString("ru-RU")}`} />
          ))}
          <Stat label="Очков всего" value={(data.stats.points_total ?? 0).toLocaleString("ru-RU")} />
          <Stat label="Забрано наград" value={(data.stats.claims ?? 0).toLocaleString("ru-RU")} />
        </div>
      </section>

      <section className="grid gap-3 rounded-xl bg-bg-surface p-4 sm:grid-cols-2">
        {NUMBERS.map(([key, label]) => (
          <label key={key} className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">{label}</span>
            <input
              type="number"
              min={0}
              value={form[key] === null || form[key] === undefined ? "" : String(form[key])}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              className="rounded-lg bg-bg-base px-3 py-2"
            />
          </label>
        ))}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={!!form.boss_enabled} onChange={(e) => setForm({ ...form, boss_enabled: e.target.checked })} />
          «Перебежчик» вместо босса недели в «Контратаке»
        </label>
      </section>

      <section className="flex flex-col gap-2 rounded-xl bg-bg-surface p-4">
        <span className="text-sm font-semibold">Стороны</span>
        <span className="text-xs text-slate-400">
          Ровно две: code (латиницей, до 16 символов — не меняй после старта, фанаты привязаны к нему), name, emoji, color
          (#rrggbb). Например дерби: «Спартак» и «ЦСКА».
        </span>
        <textarea value={sidesText} onChange={(e) => setSidesText(e.target.value)} rows={8} className="rounded-lg bg-bg-base p-3 font-mono text-xs" />
        <span className="text-sm font-semibold">Рубежи личных очков</span>
        <span className="text-xs text-slate-400">
          points, kind (coins / skill_tokens / pack / badge), amount; для pack — pack_id, для badge — badge_id (пусто — значок
          «Фанат 2026»), для skill_tokens — skill_code (пусто — случайный навык).
        </span>
        <textarea value={milestonesText} onChange={(e) => setMilestonesText(e.target.value)} rows={10} className="rounded-lg bg-bg-base p-3 font-mono text-xs" />
      </section>

      <div className="flex items-center gap-3">
        <button onClick={submit} disabled={save.isPending} className="rounded-lg bg-accent px-4 py-2 font-semibold text-black disabled:opacity-50">
          Сохранить
        </button>
        {message && <span className="text-sm text-slate-300">{message}</span>}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-bg-base px-3 py-2">
      <div className="text-slate-400">{label}</div>
      <div className="text-base font-bold text-white">{value}</div>
    </div>
  );
}
