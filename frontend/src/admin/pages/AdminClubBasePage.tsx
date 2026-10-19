import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  deleteClubBaseArt,
  fetchClubBaseArt,
  fetchClubBaseLedger,
  fetchGameConfig,
  updateGameConfig,
  uploadClubBaseArt,
} from "@/admin/api";
import type { GameConfig } from "@/admin/types";
import { ApiRequestError, staticUrl } from "@/lib/api";

const BUILDING_NAMES: Record<string, string> = {
  hq: "🏢 Штаб-квартира", stadium: "🏟️ Стадион", hotel: "🏨 Клубный отель", training: "⚽ Тренировочный центр",
  medical: "🩺 Медцентр", analytics: "📊 Аналитический центр", media: "🎙️ Медиацентр",
  marketing: "📣 Отдел маркетинга", shop: "👕 Клубный магазин", accounting: "🧮 Бухгалтерия",
};

const FIELD_NAMES: Record<string, string> = {
  costs: "Монеты", hours: "Часы", cap: "Потолок корпусов", matchday: "Монеты за дом. матч", capacity: "Вместимость",
  matchday_pct: "+% к доходу матча", familiarity_pct: "+% сыгранности", my_player_xp_pct: "+% опыта «Моего игрока»",
  injury_pct: "−% травм", recovery: "+восстановление", prep_pct: "+% разбора/стандартов", rep_pct: "+% репутации",
  daily: "Монет в день", sell_pct: "+% быстрой продажи", discount_pct: "−% стоимости стройки",
};

const KIND_NAMES: Record<string, string> = {
  upgrade: "Стройка", speedup: "Ускорение ⭐", complete: "Готово", income: "Доход",
};

function errorText(err: unknown) {
  return err instanceof ApiRequestError ? err.message : "Ошибка";
}

function parseList(value: string): number[] {
  return value.split(",").map((v) => Number(v.trim())).filter((v) => !Number.isNaN(v));
}

type Form = Pick<GameConfig, "club_base_enabled" | "club_base_buildings" | "club_base_caps" | "club_base_stars_per_hour" | "club_base_income_max_days">;

export default function AdminClubBasePage() {
  const queryClient = useQueryClient();
  const { data: config } = useQuery({ queryKey: ["admin-game-config"], queryFn: fetchGameConfig });
  const { data: art } = useQuery({ queryKey: ["admin-club-base-art"], queryFn: fetchClubBaseArt });
  const [userFilter, setUserFilter] = useState("");
  const userId = Number(userFilter) || undefined;
  const { data: ledger } = useQuery({ queryKey: ["admin-club-base-ledger", userId], queryFn: () => fetchClubBaseLedger(userId) });
  const [form, setForm] = useState<Form | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!config) return;
    setForm({
      club_base_enabled: config.club_base_enabled,
      club_base_buildings: config.club_base_buildings,
      club_base_caps: config.club_base_caps,
      club_base_stars_per_hour: config.club_base_stars_per_hour,
      club_base_income_max_days: config.club_base_income_max_days,
    });
  }, [config]);

  const save = useMutation({
    mutationFn: () => updateGameConfig(form!),
    onSuccess: () => {
      setMessage("Настройки сохранены");
      queryClient.invalidateQueries({ queryKey: ["admin-game-config"] });
    },
    onError: (err) => setMessage(errorText(err)),
  });
  const upload = useMutation({
    mutationFn: ({ slot, file }: { slot: string; file: File }) => uploadClubBaseArt(slot, file),
    onSuccess: (data) => queryClient.setQueryData(["admin-club-base-art"], (old: typeof art) => ({ ...old, ...data })),
    onError: (err) => setMessage(errorText(err)),
  });
  const remove = useMutation({
    mutationFn: (slot: string) => deleteClubBaseArt(slot),
    onSuccess: (data) => queryClient.setQueryData(["admin-club-base-art"], (old: typeof art) => ({ ...old, ...data })),
    onError: (err) => setMessage(errorText(err)),
  });

  if (!form) return <p className="text-sm text-slate-400">Загрузка…</p>;
  const pathOf = (slot: string) => (slot === "background" ? art?.art.background : art?.art.buildings?.[slot]) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold">Клубная база</h1>
      {message && <p className="rounded-lg bg-white/5 px-3 py-2 text-sm">{message}</p>}

      <section className="rounded-xl bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Настройки</p>
        <p className="mb-3 text-xs text-slate-400">
          Значения по уровням через запятую — количество значений = число уровней, у всех строк корпуса одинаковое.
          Потолки ограничивают сумму эффекта по всем корпусам. Бонусы карьеры фиксируются у игрока на сезон.
        </p>
        <label className="mb-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.club_base_enabled} onChange={(e) => setForm({ ...form, club_base_enabled: e.target.checked })} />
          База включена
        </label>
        <div className="mb-3 flex flex-wrap gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">Stars за час ускорения</span>
            <input type="number" min={1} value={form.club_base_stars_per_hour}
                   onChange={(e) => setForm({ ...form, club_base_stars_per_hour: Number(e.target.value) })}
                   className="w-32 rounded-lg bg-bg-base px-3 py-2 outline-none" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">Доход копится, дней</span>
            <input type="number" min={1} max={30} value={form.club_base_income_max_days}
                   onChange={(e) => setForm({ ...form, club_base_income_max_days: Number(e.target.value) })}
                   className="w-32 rounded-lg bg-bg-base px-3 py-2 outline-none" />
          </label>
        </div>
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
          {Object.entries(form.club_base_buildings ?? {}).map(([code, fields]) => (
            <div key={code} className="rounded-lg bg-white/5 p-2 text-xs">
              <p className="mb-1 font-semibold">{BUILDING_NAMES[code] ?? code}</p>
              {Object.entries(fields).map(([key, values]) => (
                <label key={key} className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-slate-400">{FIELD_NAMES[key] ?? key}</span>
                  <input
                    value={values.join(", ")}
                    onChange={(e) => setForm({
                      ...form,
                      club_base_buildings: { ...form.club_base_buildings, [code]: { ...fields, [key]: parseList(e.target.value) } },
                    })}
                    className="w-48 rounded bg-bg-base px-2 py-1 outline-none"
                  />
                </label>
              ))}
            </div>
          ))}
          <div className="rounded-lg bg-white/5 p-2 text-xs">
            <p className="mb-1 font-semibold">Потолки эффектов (сумма по базе)</p>
            {Object.entries(form.club_base_caps ?? {}).map(([key, value]) => (
              <label key={key} className="mb-1 flex items-center justify-between gap-2">
                <span className="text-slate-400">{FIELD_NAMES[key] ?? key}</span>
                <input type="number" min={0} value={value}
                       onChange={(e) => setForm({ ...form, club_base_caps: { ...form.club_base_caps, [key]: Number(e.target.value) } })}
                       className="w-24 rounded bg-bg-base px-2 py-1 outline-none" />
              </label>
            ))}
          </div>
        </div>
        <button type="button" disabled={save.isPending} onClick={() => save.mutate()}
                className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-black disabled:opacity-50">
          Сохранить настройки
        </button>
      </section>

      <section className="rounded-xl bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Картинки карты</p>
        <p className="mb-3 text-xs text-slate-400">
          Без картинки используется нарисованная карта. Фон — широкая картинка (примерно 360×330, можно крупнее);
          корпус — квадратная PNG/WebP с прозрачным фоном. Уровни и стройка рисуются поверх.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {(art?.slots ?? []).map((slot) => {
            const path = pathOf(slot.code);
            return (
              <div key={slot.code} className="flex flex-col gap-1 rounded-lg bg-white/5 p-2 text-xs">
                <p className="font-semibold">{slot.name}</p>
                <div className="grid h-20 place-items-center overflow-hidden rounded bg-bg-base">
                  {path ? <img src={staticUrl(path)} alt={slot.name} className="max-h-20 object-contain" /> : <span className="text-slate-500">рисованная</span>}
                </div>
                <label className="cursor-pointer rounded bg-white/10 px-2 py-1 text-center">
                  Загрузить
                  <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                         onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate({ slot: slot.code, file: f }); e.target.value = ""; }} />
                </label>
                {path && (
                  <button type="button" onClick={() => remove.mutate(slot.code)} className="rounded bg-red-500/10 px-2 py-1 text-red-400">
                    Убрать
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-xl bg-bg-surface p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="font-display text-base font-bold">Журнал базы</p>
          <input value={userFilter} onChange={(e) => setUserFilter(e.target.value)} placeholder="ID игрока"
                 className="w-32 rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-slate-400">
              <tr><th className="py-1 pr-2">Когда</th><th className="pr-2">Игрок</th><th className="pr-2">Действие</th><th className="pr-2">Корпус</th><th className="pr-2">Ур.</th><th className="pr-2">Монеты</th><th>⭐</th></tr>
            </thead>
            <tbody>
              {(ledger ?? []).map((e) => (
                <tr key={e.id} className="border-t border-white/5">
                  <td className="py-1 pr-2 whitespace-nowrap">{new Date(e.created_at).toLocaleString("ru-RU")}</td>
                  <td className="pr-2">{e.user_name} <span className="text-slate-500">#{e.user_id}</span></td>
                  <td className="pr-2">{KIND_NAMES[e.kind] ?? e.kind}</td>
                  <td className="pr-2">{e.building_name ?? "—"}</td>
                  <td className="pr-2">{e.to_level ?? "—"}</td>
                  <td className="pr-2">{e.coins_spent ? `−${e.coins_spent}` : e.coins_earned ? `+${e.coins_earned}` : "—"}</td>
                  <td>{e.stars_spent || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!ledger?.length && <p className="py-2 text-xs text-slate-500">Записей пока нет</p>}
        </div>
      </section>
    </div>
  );
}
