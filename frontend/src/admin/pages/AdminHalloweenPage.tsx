import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchAdminHalloween, updateAdminHalloween, type AdminHalloween } from "@/admin/api";
import { ApiRequestError } from "@/lib/api";

const NUMBERS: [string, string][] = [
  ["pumpkins_per_game", "🎃 за наградную игру"],
  ["pumpkins_games_daily_cap", "Лимит 🎃 с игр в день (0 — без лимита)"],
  ["pumpkins_per_task", "🎃 за забранное задание"],
  ["pumpkins_per_daily_chest", "🎃 за сундук дня"],
  ["pumpkins_per_weekly_chest", "🎃 за сундук недели"],
  ["boss_multiplier", "Множитель 🎃 за победу над боссом"],
  ["door_trick_pct", "Шанс «гадости» за дверью, %"],
  ["door_zombie_weight", "Гадость: вес зомби-рамки"],
  ["door_joke_weight", "Гадость: вес шутки"],
  ["door_zombie_hours", "Зомби-рамка держится, часов"],
  ["pack_id", "ID пака «Ночь живых Легенд»"],
  ["badge_id", "ID значка «Тыква 2026»"],
  ["collection_id", "ID коллекции «Ночь живых Легенд»"],
];

/** datetime-local value (local time) ⇄ ISO with the browser's offset. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** «🎃 Ночь тыкв»: one switch, the dates and every number of the event. */
export default function AdminHalloweenPage() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-halloween"], queryFn: fetchAdminHalloween });
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [shopText, setShopText] = useState("");
  const [treatsText, setTreatsText] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const load = (d: AdminHalloween) => {
    setForm(d.settings);
    setShopText(JSON.stringify(d.settings.shop ?? [], null, 2));
    setTreatsText(JSON.stringify(d.settings.door_treats ?? [], null, 2));
    setStart(toLocalInput(d.starts_at));
    setEnd(toLocalInput(d.ends_at));
  };
  useEffect(() => {
    if (data) load(data);
  }, [data]);

  const save = useMutation({
    mutationFn: updateAdminHalloween,
    onSuccess: (d) => {
      queryClient.setQueryData(["admin-halloween"], d);
      load(d);
      setMessage("Сохранено");
    },
    onError: (err) => setMessage(err instanceof ApiRequestError ? err.message : "Не удалось сохранить"),
  });

  if (!data) return <p className="text-sm text-slate-400">Загрузка…</p>;

  const submit = () => {
    setMessage(null);
    let shop: unknown;
    let treats: unknown;
    try {
      shop = JSON.parse(shopText);
      treats = JSON.parse(treatsText);
    } catch {
      setMessage("Лавка или сладости — неверный JSON");
      return;
    }
    const settings: Record<string, unknown> = { shop, door_treats: treats, boss_enabled: !!form.boss_enabled };
    for (const [key] of NUMBERS) settings[key] = form[key] === "" || form[key] === undefined ? null : Number(form[key]);
    save.mutate({
      settings,
      starts_at: start ? new Date(start).toISOString() : undefined,
      ends_at: end ? new Date(end).toISOString() : undefined,
    });
  };

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <h1 className="text-xl font-bold">🎃 Ночь тыкв</h1>

      <section className="flex flex-col gap-3 rounded-xl bg-bg-surface p-4">
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input
            type="checkbox"
            checked={data.enabled}
            disabled={save.isPending}
            onChange={(e) => save.mutate({ enabled: e.target.checked })}
          />
          Ивент включён (выкл — ни тыкв, ни лавки, ни дверей, ни босса, ни оформления)
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">Начало</span>
            <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className="rounded-lg bg-bg-base px-3 py-2" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">Конец (не включительно)</span>
            <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded-lg bg-bg-base px-3 py-2" />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs text-slate-300 sm:grid-cols-5">
          <Stat label="Игроков" value={data.stats.players} />
          <Stat label="Собрано 🎃" value={data.stats.earned} />
          <Stat label="На руках 🎃" value={data.stats.held} />
          <Stat label="Покупок в лавке" value={data.stats.purchases} />
          <Stat label="Открыто дверей" value={data.stats.doors} />
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
          «Безголовый вратарь» вместо босса недели в «Контратаке»
        </label>
      </section>

      <section className="flex flex-col gap-2 rounded-xl bg-bg-surface p-4">
        <span className="text-sm font-semibold">Лавка тыкв</span>
        <span className="text-xs text-slate-400">
          Список товаров: code, kind (pack / coins / skill_tokens / badge), title, price (🎃), amount (монеты / жетоны), limit
          (на игрока, 0 — без лимита), skill_code (пусто — случайный навык), pack_id / badge_id (пусто — из полей выше).
        </span>
        <textarea value={shopText} onChange={(e) => setShopText(e.target.value)} rows={14} className="rounded-lg bg-bg-base p-3 font-mono text-xs" />
        <span className="text-sm font-semibold">Сладости за дверью</span>
        <span className="text-xs text-slate-400">weight, kind (coins / pumpkins / pack), amount; для pack — pack_id (пусто — пак ивента).</span>
        <textarea value={treatsText} onChange={(e) => setTreatsText(e.target.value)} rows={7} className="rounded-lg bg-bg-base p-3 font-mono text-xs" />
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

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-lg bg-bg-base px-3 py-2">
      <div className="text-slate-400">{label}</div>
      <div className="text-base font-bold text-white">{(value ?? 0).toLocaleString("ru-RU")}</div>
    </div>
  );
}
