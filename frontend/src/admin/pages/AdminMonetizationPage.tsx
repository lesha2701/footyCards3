import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  fetchAdminBadges,
  fetchAdminCosmetics,
  fetchAdminPacks,
  fetchAdminSeasons,
  fetchGameConfig,
  saveAdminCosmetic,
  saveAdminSeason,
  updateGameConfig,
} from "@/admin/api";
import { useAdminToastStore } from "@/admin/adminToastStore";
import RewardBundleEditor from "@/admin/components/RewardBundleEditor";
import { EMPTY_BUNDLE, type AdminSeason, type GameConfig } from "@/admin/types";
import CosmeticPreview from "@/components/shop/CosmeticPreview";
import { ApiRequestError } from "@/lib/api";
import { KIND_LABELS, STYLE_OPTIONS } from "@/lib/cosmetics";
import type { Cosmetic, CosmeticKind } from "@/types";

type Tab = "settings" | "cosmetics" | "seasons";
const input = "w-full rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none";
const toast = (msg: string) => useAdminToastStore.getState().push(msg, "success");
const errText = (err: unknown, fallback: string) => (err instanceof ApiRequestError ? err.message : fallback);

/** «Клубный абонемент», «Сезонный пропуск», стартовое предложение и
 * косметика — every price and reward is edited here (GameConfig + tables). */
export default function AdminMonetizationPage() {
  const [tab, setTab] = useState<Tab>("settings");
  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Абонемент, сезон, стиль</h1>
      <div className="flex gap-1 rounded-xl bg-bg-surface p-1">
        {([["settings", "Настройки"], ["cosmetics", "Косметика"], ["seasons", "Сезоны"]] as [Tab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex-1 rounded-lg py-2 text-xs font-semibold ${tab === id ? "bg-accent text-bg-base" : "text-slate-400"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "settings" && <SettingsTab />}
      {tab === "cosmetics" && <CosmeticsTab />}
      {tab === "seasons" && <SeasonsTab />}
    </div>
  );
}

// --- settings (GameConfig) -----------------------------------------------------------

type ConfigKey = keyof GameConfig;

function SettingsTab() {
  const queryClient = useQueryClient();
  const { data: config } = useQuery({ queryKey: ["admin-game-config"], queryFn: fetchGameConfig });
  const { data: packs } = useQuery({ queryKey: ["admin-packs"], queryFn: fetchAdminPacks });
  const { data: badges } = useQuery({ queryKey: ["admin-badges"], queryFn: fetchAdminBadges });
  const { data: cosmetics } = useQuery({ queryKey: ["admin-cosmetics"], queryFn: fetchAdminCosmetics });
  const [draft, setDraft] = useState<Partial<GameConfig>>({});
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => updateGameConfig(draft),
    onSuccess: (data) => {
      queryClient.setQueryData(["admin-game-config"], data);
      setDraft({});
      setError(null);
      toast("Настройки сохранены");
    },
    onError: (err) => setError(errText(err, "Не удалось сохранить")),
  });
  if (!config) return <p className="text-sm text-slate-400">Загрузка...</p>;

  const value = <K extends ConfigKey>(k: K): GameConfig[K] => (k in draft ? (draft[k] as GameConfig[K]) : config[k]);
  const set = (k: ConfigKey, v: unknown) => setDraft((d) => ({ ...d, [k]: v }));
  const num = (k: ConfigKey, label: string) => (
    <label className="flex flex-col gap-0.5">
      <span className="text-micro text-slate-500">{label}</span>
      <input type="number" min={0} value={value(k) as number} onChange={(e) => set(k, Number(e.target.value))} className={input} />
    </label>
  );
  const flag = (k: ConfigKey, label: string) => (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={value(k) as boolean} onChange={(e) => set(k, e.target.checked)} /> {label}
    </label>
  );
  const pick = (k: ConfigKey, label: string, options: { id: number; name: string }[] | undefined) => (
    <label className="flex flex-col gap-0.5">
      <span className="text-micro text-slate-500">{label}</span>
      <select value={(value(k) as number | null) ?? ""} onChange={(e) => set(k, e.target.value ? Number(e.target.value) : null)} className={input}>
        <option value="">— нет —</option>
        {options?.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
      </select>
    </label>
  );
  const frames = cosmetics?.filter((c) => c.kind === "profile_frame");
  const block = "flex flex-col gap-3 rounded-2xl border border-white/5 bg-bg-surface p-4";
  const grid = "grid grid-cols-2 gap-2 sm:grid-cols-4";

  return (
    <div className="flex flex-col gap-3">
      <section className={block}>
        <p className="font-display text-sm font-bold">Клубный абонемент (подписка Stars, 30 дней)</p>
        {flag("club_pass_enabled", "Продаётся")}
        <div className={grid}>
          {num("club_pass_stars", "Цена, ⭐ в месяц")}
          {num("club_pass_daily_coins", "Монеты каждый день")}
          {pick("club_pass_daily_pack_id", "Пак каждый день", packs)}
          {num("club_pass_extra_rewarded_attempts", "+ награждаемых попыток в мини-играх")}
          {pick("club_pass_frame_cosmetic_id", "Эксклюзивная рамка", frames)}
          {pick("club_pass_badge_id", "Значок", badges)}
        </div>
        {flag("club_pass_ad_free", "Без рекламы (на будущее)")}
      </section>
      <section className={block}>
        <p className="font-display text-sm font-bold">Стартовое предложение (один раз, новичкам)</p>
        {flag("starter_offer_enabled", "Включено")}
        <div className={grid}>
          {num("starter_offer_stars", "Цена, ⭐")}
          {num("starter_offer_hours", "Доступно часов после регистрации")}
          {num("starter_offer_coins", "Монеты")}
          {pick("starter_offer_pack_id", "Пак", packs)}
          {pick("starter_offer_cosmetic_id", "Эксклюзивная рамка", frames)}
        </div>
      </section>
      <section className={block}>
        <p className="font-display text-sm font-bold">Календарь наград: догнать пропущенный день</p>
        <div className={grid}>
          {num("calendar_catchup_coins", "Цена, монеты (0 — нельзя)")}
          {num("calendar_catchup_stars", "Цена, ⭐ (0 — нельзя)")}
          {num("calendar_catchup_max_per_month", "Не больше раз в месяц")}
        </div>
      </section>
      <section className={block}>
        <p className="font-display text-sm font-bold">Сезонный пропуск: опыт</p>
        {flag("season_pass_enabled", "Сезоны включены")}
        <div className={grid}>
          {num("season_xp_per_game", "XP за игру с наградой")}
          {num("season_xp_per_daily_claim", "XP за награду календаря")}
        </div>
      </section>
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      <button
        onClick={() => save.mutate()}
        disabled={save.isPending || !Object.keys(draft).length}
        className="self-end rounded-lg bg-accent px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
      >
        Сохранить
      </button>
    </div>
  );
}

// --- cosmetics -----------------------------------------------------------------------

type CosmeticDraft = Omit<Cosmetic, "id"> & { id?: number };
const NEW_COSMETIC: CosmeticDraft = {
  kind: "profile_frame", name: "", description: "", style_key: "gold", coins_price: 0, stars_price: 0,
  is_exclusive: false, is_active: true, sort_order: 0,
};

function CosmeticsTab() {
  const queryClient = useQueryClient();
  const { data: items } = useQuery({ queryKey: ["admin-cosmetics"], queryFn: fetchAdminCosmetics });
  const [editing, setEditing] = useState<CosmeticDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (c: CosmeticDraft) => saveAdminCosmetic(c),
    onSuccess: () => {
      setEditing(null);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-cosmetics"] });
      toast("Сохранено");
    },
    onError: (err) => setError(errText(err, "Не удалось сохранить")),
  });

  return (
    <div className="flex flex-col gap-3">
      <button onClick={() => setEditing({ ...NEW_COSMETIC })} className="self-start rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base">
        + Новый предмет
      </button>
      {editing && (
        <div className="flex flex-col gap-2 rounded-2xl border border-accent/40 bg-bg-surface p-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <label className="flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">Тип</span>
              <select
                value={editing.kind}
                onChange={(e) => {
                  const kind = e.target.value as CosmeticKind;
                  setEditing({ ...editing, kind, style_key: STYLE_OPTIONS[kind][0] });
                }}
                className={input}
              >
                {(Object.keys(KIND_LABELS) as CosmeticKind[]).map((k) => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">Вид</span>
              <select value={editing.style_key} onChange={(e) => setEditing({ ...editing, style_key: e.target.value })} className={input}>
                {STYLE_OPTIONS[editing.kind].map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">Название</span>
              <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} className={input} />
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">Порядок</span>
              <input type="number" value={editing.sort_order} onChange={(e) => setEditing({ ...editing, sort_order: Number(e.target.value) })} className={input} />
            </label>
            <label className="col-span-2 flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">Описание</span>
              <input value={editing.description ?? ""} onChange={(e) => setEditing({ ...editing, description: e.target.value || null })} className={input} />
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">Цена, монеты (0 — нет)</span>
              <input type="number" min={0} value={editing.coins_price} onChange={(e) => setEditing({ ...editing, coins_price: Number(e.target.value) })} className={input} />
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">Цена, ⭐ (0 — нет)</span>
              <input type="number" min={0} value={editing.stars_price} onChange={(e) => setEditing({ ...editing, stars_price: Number(e.target.value) })} className={input} />
            </label>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <CosmeticPreview item={editing} />
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={editing.is_exclusive} onChange={(e) => setEditing({ ...editing, is_exclusive: e.target.checked })} /> Эксклюзив (только в наградах)</label>
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={editing.is_active} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} /> Активен</label>
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2">
            <button onClick={() => save.mutate(editing)} disabled={save.isPending || !editing.name} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40">Сохранить</button>
            <button onClick={() => setEditing(null)} className="rounded-lg bg-white/5 px-3 py-1.5 text-xs">Отмена</button>
          </div>
        </div>
      )}
      <div className="flex flex-col gap-1.5">
        {items?.map((c) => (
          <button
            key={c.id}
            onClick={() => setEditing(c)}
            className={`flex items-center gap-3 rounded-xl bg-bg-surface p-2 text-left ${c.is_active ? "" : "opacity-50"}`}
          >
            <CosmeticPreview item={c} />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold">#{c.id} {c.name}</span>
              <span className="block text-micro text-slate-500">
                {KIND_LABELS[c.kind]} · {c.style_key}
                {c.is_exclusive ? " · эксклюзив" : ` · ${c.coins_price || "—"} мон. / ${c.stars_price || "—"} ⭐`}
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// --- seasons -------------------------------------------------------------------------

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function newSeason(): AdminSeason {
  const start = new Date();
  const end = new Date(start.getTime() + 30 * 86_400_000);
  return {
    name: "Новый сезон", starts_at: start.toISOString(), ends_at: end.toISOString(), premium_stars: 399, is_active: true,
    levels: Array.from({ length: 10 }, (_, i) => ({
      level: i + 1, xp_required: (i + 1) * 100,
      free: { ...EMPTY_BUNDLE, coins: 100 + i * 25 },
      premium: { ...EMPTY_BUNDLE, coins: 250 + i * 50 },
    })),
  };
}

function SeasonsTab() {
  const queryClient = useQueryClient();
  const { data: seasons } = useQuery({ queryKey: ["admin-seasons"], queryFn: fetchAdminSeasons });
  const [editing, setEditing] = useState<AdminSeason | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setError(null), [editing?.id]);
  const save = useMutation({
    mutationFn: (s: AdminSeason) => saveAdminSeason(s),
    onSuccess: () => {
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["admin-seasons"] });
      toast("Сезон сохранён");
    },
    onError: (err) => setError(errText(err, "Не удалось сохранить сезон")),
  });

  if (editing) {
    const setLevel = (i: number, patch: Partial<AdminSeason["levels"][number]>) =>
      setEditing({ ...editing, levels: editing.levels.map((l, j) => (j === i ? { ...l, ...patch } : l)) });
    return (
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-2 rounded-2xl bg-bg-surface p-3 sm:grid-cols-4">
          <label className="flex flex-col gap-0.5">
            <span className="text-micro text-slate-500">Название</span>
            <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} className={input} />
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-micro text-slate-500">Начало</span>
            <input type="datetime-local" value={toLocalInput(editing.starts_at)} onChange={(e) => setEditing({ ...editing, starts_at: new Date(e.target.value).toISOString() })} className={input} />
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-micro text-slate-500">Конец</span>
            <input type="datetime-local" value={toLocalInput(editing.ends_at)} onChange={(e) => setEditing({ ...editing, ends_at: new Date(e.target.value).toISOString() })} className={input} />
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-micro text-slate-500">Премиум, ⭐</span>
            <input type="number" min={1} value={editing.premium_stars} onChange={(e) => setEditing({ ...editing, premium_stars: Number(e.target.value) })} className={input} />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={editing.is_active} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} /> Активен
          </label>
        </div>
        {editing.levels.map((lv, i) => (
          <div key={i} className="flex flex-col gap-2 rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="flex items-center gap-2">
              <span className="font-display text-sm font-bold">Уровень {lv.level}</span>
              <label className="flex items-center gap-1 text-xs text-slate-400">
                XP: <input type="number" min={0} value={lv.xp_required} onChange={(e) => setLevel(i, { xp_required: Number(e.target.value) })} className="w-24 rounded-lg bg-bg-base px-2 py-1 text-sm" />
              </label>
              <button
                onClick={() => setEditing({ ...editing, levels: editing.levels.filter((_, j) => j !== i).map((l, j) => ({ ...l, level: j + 1 })) })}
                className="ml-auto rounded-lg bg-red-500/10 px-2 py-1 text-caption text-red-400"
              >
                Удалить
              </button>
            </div>
            <p className="text-micro text-slate-500">Бесплатно</p>
            <RewardBundleEditor value={lv.free} onChange={(free) => setLevel(i, { free })} />
            <p className="text-micro text-amber-300">Премиум</p>
            <RewardBundleEditor value={lv.premium} onChange={(premium) => setLevel(i, { premium })} />
          </div>
        ))}
        <button
          onClick={() => {
            const last = editing.levels[editing.levels.length - 1];
            setEditing({
              ...editing,
              levels: [...editing.levels, {
                level: editing.levels.length + 1, xp_required: (last?.xp_required ?? 0) + 100,
                free: { ...EMPTY_BUNDLE }, premium: { ...EMPTY_BUNDLE },
              }],
            });
          }}
          className="self-start rounded-lg bg-white/5 px-3 py-1.5 text-xs"
        >
          + Уровень
        </button>
        {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
        <div className="flex gap-2">
          <button onClick={() => save.mutate(editing)} disabled={save.isPending} className="rounded-lg bg-accent px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40">Сохранить сезон</button>
          <button onClick={() => setEditing(null)} className="rounded-lg bg-white/5 px-4 py-2 text-xs">Назад</button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <button onClick={() => setEditing(newSeason())} className="self-start rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base">
        + Новый сезон
      </button>
      {seasons?.map((s) => (
        <button key={s.id} onClick={() => setEditing(s)} className="flex items-center justify-between rounded-xl bg-bg-surface p-3 text-left">
          <span>
            <span className="block text-sm font-semibold">{s.name}{s.is_active ? "" : " (выключен)"}</span>
            <span className="block text-micro text-slate-500">
              {new Date(s.starts_at).toLocaleDateString("ru-RU")} — {new Date(s.ends_at).toLocaleDateString("ru-RU")} ·{" "}
              уровней: {s.levels.length} · {s.premium_stars} ⭐
            </span>
          </span>
          <span className="text-right text-micro text-slate-400">
            Игроков: {s.players ?? 0}<br />Премиум: {s.premium_players ?? 0}
          </span>
        </button>
      ))}
      {seasons && !seasons.length && <p className="text-sm text-slate-400">Сезонов пока нет</p>}
    </div>
  );
}
