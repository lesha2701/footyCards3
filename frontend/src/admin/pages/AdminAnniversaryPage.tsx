import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchAdminAnniversary, updateAdminAnniversary, type AdminAnniversary } from "@/admin/api";
import { ApiRequestError } from "@/lib/api";

const NUMBERS: [string, string][] = [
  ["community_goal", "«Сотня»: цель, наградных игр всего"],
  ["community_min_games", "«Сотня»: минимум своих игр для подарков"],
  ["recap_coins", "Монет за просмотр «Мои 100 дней» (0 — без подарка)"],
  ["claim_days", "Ступени «Сотни» можно забрать дней после конца"],
  ["teaser_days", "Анонс на главной за дней до старта"],
  ["badge_id", "ID значка «100 дней» (флаг badge в подарке)"],
  ["pack_id", "ID юбилейного пака (флаг pack в подарке)"],
  ["collection_id", "ID коллекции «Клуб Центурионов»"],
];

/** datetime-local value (local time) ⇄ ISO with the browser's offset. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** «💯 Нам 100 дней!»: one switch, the dates, the calendar, the tiers and every number. */
export default function AdminAnniversaryPage() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-anniversary"], queryFn: fetchAdminAnniversary });
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [calendarText, setCalendarText] = useState("");
  const [tiersText, setTiersText] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const load = (d: AdminAnniversary) => {
    setForm(d.settings);
    setCalendarText(JSON.stringify(d.settings.calendar ?? [], null, 2));
    setTiersText(JSON.stringify(d.settings.community_tiers ?? [], null, 2));
    setStart(toLocalInput(d.starts_at));
    setEnd(toLocalInput(d.ends_at));
  };
  useEffect(() => {
    if (data) load(data);
  }, [data]);

  const save = useMutation({
    mutationFn: updateAdminAnniversary,
    onSuccess: (d) => {
      queryClient.setQueryData(["admin-anniversary"], d);
      load(d);
      setMessage("Сохранено");
    },
    onError: (err) => setMessage(err instanceof ApiRequestError ? err.message : "Не удалось сохранить"),
  });

  if (!data) return <p className="text-sm text-slate-400">Загрузка…</p>;

  const submit = () => {
    setMessage(null);
    let calendar: unknown;
    let tiers: unknown;
    try {
      calendar = JSON.parse(calendarText);
      tiers = JSON.parse(tiersText);
    } catch {
      setMessage("Календарь или ступени — неверный JSON");
      return;
    }
    const settings: Record<string, unknown> = { calendar, community_tiers: tiers };
    for (const [key] of NUMBERS) settings[key] = form[key] === "" || form[key] === undefined ? null : Number(form[key]);
    save.mutate({
      settings,
      starts_at: start ? new Date(start).toISOString() : undefined,
      ends_at: end ? new Date(end).toISOString() : undefined,
    });
  };

  const n = (v: number | undefined) => (v ?? 0).toLocaleString("ru-RU");

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <h1 className="text-xl font-bold">💯 Нам 100 дней!</h1>

      <section className="flex flex-col gap-3 rounded-xl bg-bg-surface p-4">
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input
            type="checkbox"
            checked={data.enabled}
            disabled={save.isPending}
            onChange={(e) => save.mutate({ enabled: e.target.checked })}
          />
          Ивент включён (выкл — ни подарков, ни «Сотни», ни баннера)
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
          <Stat label="Участников" value={n(data.stats.members)} />
          <Stat label="Игр в «Сотню»" value={n(data.stats.games)} />
          <Stat label="Подарков дня" value={n(data.stats.calendar_claims)} />
          <Stat label="Ступеней забрано" value={n(data.stats.community_claims)} />
          <Stat label="Recap-подарков" value={n(data.stats.recaps)} />
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
      </section>

      <section className="flex flex-col gap-2 rounded-xl bg-bg-surface p-4">
        <span className="text-sm font-semibold">Календарь подарков</span>
        <span className="text-xs text-slate-400">
          По подарку на день, по порядку: coins, card_rarity (common / rare / epic / legendary / diamond), pack_id, а также
          флаги pack: true (юбилейный пак из настроек) и badge: true (значок «100 дней»).
        </span>
        <textarea value={calendarText} onChange={(e) => setCalendarText(e.target.value)} rows={10} className="rounded-lg bg-bg-base p-3 font-mono text-xs" />
        <span className="text-sm font-semibold">Ступени «Сотни»</span>
        <span className="text-xs text-slate-400">pct (1–100) и награда в том же виде, что и подарок календаря.</span>
        <textarea value={tiersText} onChange={(e) => setTiersText(e.target.value)} rows={8} className="rounded-lg bg-bg-base p-3 font-mono text-xs" />
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
