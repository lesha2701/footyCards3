import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchAdminLoyalty, updateAdminLoyalty, type AdminLoyalty } from "@/admin/api";
import { ApiRequestError } from "@/lib/api";

/** [key, label] — numbers and ids of GameConfig.loyalty_settings (loyalty_service.DEFAULTS). */
const FIELDS: [string, string][] = [
  ["oldtimer_days", "«Старожил»: дней с регистрации"],
  ["oldtimer_active_days", "«Старожил»: из них активных дней"],
  ["oldtimer_coins", "«Старожил»: монеты"],
  ["oldtimer_pack_id", "«Старожил»: ID пака (пусто = без пака; юбилейный — отдельным подарком на ивенте)"],
  ["oldtimer_badge_id", "«Старожил»: ID значка"],
  ["oldtimer_cosmetic_id", "«Старожил»: ID рамки"],
  ["pioneer_limit", "«Первопроходец»: первые N игроков"],
  ["pioneer_badge_id", "«Первопроходец»: ID значка"],
  ["pioneer_cosmetic_id", "«Первопроходец»: ID рамки"],
  ["centurion_player_id", "«Центурион»: ID футболиста"],
  ["centurion_badge_id", "«Центурион»: ID значка"],
  ["streak_save_min_streak", "Страховка: от скольки дней серии"],
  ["streak_save_hours", "Страховка: часов на спасение"],
  ["streak_save_stars", "Страховка: цена, ⭐"],
  ["streak_save_free_period_days", "Страховка: бесплатно с абонементом раз в N дней"],
];
const RARITIES = ["", "common", "rare", "epic", "legendary", "diamond"];
const LABELS: Record<string, string> = { oldtimer: "Старожил", oldtimer_gift: "Подарок старожилу", pioneer: "Первопроходец", centurion: "Центурион (доплата)" };

/** Admin «Лояльность»: «Старожил», «Первопроходец», «Центурион» and «Страховка серии». */
export default function LoyaltySettingsPanel() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-loyalty"], queryFn: fetchAdminLoyalty });
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    if (data) setForm(data.settings);
  }, [data]);
  const save = useMutation({
    mutationFn: updateAdminLoyalty,
    onSuccess: (d: AdminLoyalty) => {
      queryClient.setQueryData(["admin-loyalty"], d);
      setForm(d.settings);
      setMessage("Сохранено");
    },
    onError: (err) => setMessage(err instanceof ApiRequestError ? err.message : "Не удалось сохранить"),
  });
  if (!data) return null;

  const submit = () => {
    setMessage(null);
    const settings: Record<string, unknown> = {
      enabled: !!form.enabled,
      streak_save_enabled: !!form.streak_save_enabled,
      oldtimer_card_rarity: form.oldtimer_card_rarity || null,
    };
    for (const [key] of FIELDS) {
      const raw = form[key];
      const value = raw === "" || raw == null ? null : Number(raw);
      // Empty numbers fall back to the defaults; empty ids switch that part off.
      if (value !== null || key.endsWith("_id")) settings[key] = value;
    }
    save.mutate(settings);
  };
  const granted = Object.entries(data.granted).map(([code, n]) => `${LABELS[code] ?? code} — ${n}`).join(", ");

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="mb-1 font-display text-base font-bold">Лояльность</p>
      <p className="mb-3 text-xs text-slate-500">
        «Старожил» (100 дней в игре и 50 активных), «Первопроходец» (первые игроки), карта «Центурион» за 100 дней подряд
        (её саму выдаёт порог 100 в «Наградах за дни подряд»; здесь — доплата тем, кто дошёл до 100 раньше) и «Страховка
        серии». Выдано: {granted || "пока никому"}.
      </p>
      <div className="mb-3 flex flex-wrap gap-4 text-xs text-slate-300">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={!!form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
          Награды за верность включены
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={!!form.streak_save_enabled}
            onChange={(e) => setForm({ ...form, streak_save_enabled: e.target.checked })}
          />
          Страховка серии включена
        </label>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {FIELDS.map(([key, label]) => (
          <label key={key} className="flex flex-col gap-1 text-xs text-slate-400">
            {label}
            <input
              type="number"
              value={form[key] == null ? "" : String(form[key])}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              className="rounded-lg bg-bg-base px-2 py-1.5 text-sm text-white outline-none"
            />
          </label>
        ))}
        <label className="flex flex-col gap-1 text-xs text-slate-400">
          «Старожил»: редкость карты
          <select
            value={String(form.oldtimer_card_rarity ?? "")}
            onChange={(e) => setForm({ ...form, oldtimer_card_rarity: e.target.value })}
            className="rounded-lg bg-bg-base px-2 py-1.5 text-sm text-white outline-none"
          >
            {RARITIES.map((r) => (
              <option key={r} value={r}>
                {r || "без карты"}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button onClick={submit} disabled={save.isPending} className="rounded-lg bg-accent-lime px-4 py-2 text-sm font-bold text-bg-base">
          Сохранить лояльность
        </button>
        {message && <span className="text-xs text-slate-400">{message}</span>}
      </div>
    </section>
  );
}
