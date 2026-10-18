import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  fetchAdminBadges,
  fetchAdminClubEmblemItems,
  fetchAdminClubPacks,
  fetchAdminClubQuests,
  fetchAdminClubShopItems,
  fetchAdminCosmetics,
  fetchAdminPacks,
  fetchAdminSeasons,
  fetchGameConfig,
  saveAdminClubEmblemItem,
  saveAdminClubQuest,
  saveAdminClubShopItem,
  type AdminClubQuest,
  type AdminClubShopItem,
  saveAdminCosmetic,
  saveAdminSeason,
  updateGameConfig,
} from "@/admin/api";
import { useAdminToastStore } from "@/admin/adminToastStore";
import AdminArtifactsTab from "@/admin/components/AdminArtifactsTab";
import RewardBundleEditor from "@/admin/components/RewardBundleEditor";
import { EMPTY_BUNDLE, type AdminSeason, type GameConfig } from "@/admin/types";
import CosmeticPreview from "@/components/shop/CosmeticPreview";
import { ApiRequestError } from "@/lib/api";
import { KIND_LABELS, STYLE_OPTIONS } from "@/lib/cosmetics";
import { RARITY_LABELS } from "@/lib/rarity";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import type { ClubEmblemItem, ClubEmblemKind, Cosmetic, CosmeticKind } from "@/types";

type Tab = "settings" | "cosmetics" | "seasons" | "artifacts" | "emblems" | "club_shop" | "club_quests";
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
        {([["settings", "Настройки"], ["cosmetics", "Косметика"], ["seasons", "Сезоны"], ["artifacts", "Артефакты"], ["emblems", "Эмблемы"], ["club_shop", "Клуб. магазин"], ["club_quests", "Клуб. задания"]] as [Tab, string][]).map(([id, label]) => (
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
      {tab === "artifacts" && <AdminArtifactsTab />}
      {tab === "emblems" && <ClubEmblemsTab />}
      {tab === "club_shop" && <ClubShopTab />}
      {tab === "club_quests" && <ClubQuestsTab />}
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
  const { data: clubPacks } = useQuery({ queryKey: ["admin-club-packs"], queryFn: fetchAdminClubPacks });
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
        {flag("club_pass_enabled", "Продаётся (запуск)")}
        <div className={grid}>
          {num("club_pass_stars", "Цена, ⭐ в месяц")}
          {num("club_pass_daily_coins", "Монеты каждый день")}
          {pick("club_pass_daily_pack_id", "Пак каждый день", packs)}
          {num("club_pass_extra_rewarded_attempts", "+ награждаемых попыток в мини-играх")}
          {pick("club_pass_frame_cosmetic_id", "Эксклюзивная рамка", frames)}
          {pick("club_pass_badge_id", "Значок", badges)}
          {num("club_pass_season_xp_bonus_pct", "+% опыта сезона")}
          {num("club_pass_free_catchups", "Бесплатных догонов календаря в месяц")}
          {num("club_pass_status", "+ статуса Моему игроку, пока активен")}
        </div>
        <p className="text-micro text-slate-500">Бонус с каждой оплатой (сразу и при каждом продлении):</p>
        <div className={grid}>
          {num("club_pass_bonus_coins", "Монеты")}
          {pick("club_pass_bonus_pack_id", "Пак", packs)}
          <label className="flex flex-col gap-0.5">
            <span className="text-micro text-slate-500">Карточка</span>
            <select
              value={(value("club_pass_bonus_card_rarity") as string | null) ?? ""}
              onChange={(e) => set("club_pass_bonus_card_rarity", e.target.value)}
              className={input}
            >
              <option value="">— нет —</option>
              {(["common", "rare", "epic", "legendary", "diamond"] as const).map((r) => (
                <option key={r} value={r}>{RARITY_LABELS[r]}</option>
              ))}
            </select>
          </label>
        </div>
        {flag("club_pass_ad_free", "Без рекламы (на будущее)")}
      </section>
      <section className={block}>
        <p className="font-display text-sm font-bold">Стартовое предложение (один раз, новичкам)</p>
        {flag("starter_offer_enabled", "Включено (запуск)")}
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
        {flag("season_pass_enabled", "Сезоны включены (запуск)")}
        <div className={grid}>
          {num("season_xp_per_game", "XP за игру с наградой")}
          {num("season_xp_per_daily_claim", "XP за награду календаря")}
          {num("season_premium_status", "+ статуса за премиум сезона")}
        </div>
      </section>
      <section className={block}>
        <p className="font-display text-sm font-bold">Клубы: эмблемы, «Казна за Stars», лишние карты</p>
        {flag("club_emblems_enabled", "Магазин элементов эмблем открыт (цены — вкладка «Эмблемы»)")}
        {flag("club_donation_enabled", "Пополнение казны клуба звёздами (запуск)")}
        {flag("club_card_market_enabled", "«Лишние карты»: продажа в казну и обмен")}
        {flag("club_quests_enabled", "Задания недели клубов (сами задания — вкладка «Клуб. задания»)")}
        <div className={grid}>
          {num("club_donation_coins_per_star", "Монет в казну за 1 ⭐")}
          {num("club_sponsor_silver_stars", "Серебряный меценат, всего ⭐")}
          {num("club_sponsor_gold_stars", "Золотой меценат, всего ⭐")}
          {num("club_card_sell_pct", "Лишние карты: % от цены быстрой продажи")}
          {num("club_card_exchange_count", "Лишние карты: сколько слить за пак")}
          {pick("club_card_exchange_pack_id", "Лишние карты: клубный пак (нет — самый дешёвый)", clubPacks)}
          {num("club_announcement_cooldown_minutes", "Стена: минут между объявлениями")}
          <label className="flex flex-col gap-0.5">
            <span className="text-micro text-slate-500">Суммы пополнения, ⭐ через запятую</span>
            <input
              defaultValue={(value("club_donation_star_options") as number[]).join(", ")}
              onBlur={(e) =>
                set("club_donation_star_options", e.target.value.split(",").map((v) => Number(v.trim())).filter((v) => v > 0))
              }
              className={input}
            />
          </label>
        </div>
      </section>
      <section className={block}>
        <p className="font-display text-sm font-bold">Артефакты</p>
        {flag("artifacts_enabled", "Включены (запуск)")}
        <div className={grid}>
          {num("artifact_slots", "Активных слотов у игрока")}
          {num("artifact_max_opp_pct", "Максимум %, сумма (сила соперника / команды)")}
          {num("artifact_max_stat", "Максимум к атаке/защите, сумма")}
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
  is_exclusive: false, is_active: true, sort_order: 0, status: 5,
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
              <span className="text-micro text-slate-500">+ статуса</span>
              <input type="number" min={0} value={editing.status} onChange={(e) => setEditing({ ...editing, status: Number(e.target.value) })} className={input} />
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

// --- club emblem catalog -------------------------------------------------------------

const EMBLEM_KIND_LABELS: Record<ClubEmblemKind, string> = {
  color2: "Второй цвет", pattern: "Узор", letters: "Буквы", symbol: "Символ", outline: "Обводка", effect: "Анимация",
};

function ClubEmblemsTab() {
  const queryClient = useQueryClient();
  const { data: items } = useQuery({ queryKey: ["admin-club-emblem-items"], queryFn: fetchAdminClubEmblemItems });
  const [drafts, setDrafts] = useState<Record<number, ClubEmblemItem>>({});
  const save = useMutation({
    mutationFn: saveAdminClubEmblemItem,
    onSuccess: (item) => {
      queryClient.invalidateQueries({ queryKey: ["admin-club-emblem-items"] });
      setDrafts((d) => {
        const next = { ...d };
        delete next[item.id];
        return next;
      });
      toast("Сохранено");
    },
    onError: (err) => useAdminToastStore.getState().push(errText(err, "Не удалось сохранить"), "error"),
  });
  if (!items) return <p className="text-sm text-slate-400">Загрузка...</p>;
  const edit = (item: ClubEmblemItem, patch: Partial<ClubEmblemItem>) =>
    setDrafts((d) => ({ ...d, [item.id]: { ...(d[item.id] ?? item), ...patch } }));

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-slate-400">
        Цена в монетах списывается из бюджета клуба (капитан или ассистент), в звёздах — платит любой участник.
        Укажи одну из цен, другую оставь 0. Внешний вид элементов задан в коде.
      </p>
      {items.map((item) => {
        const d = drafts[item.id] ?? item;
        return (
          <div key={item.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-white/5 bg-bg-surface p-2">
            <ClubLogo
              shape="shield"
              color="#3B82F6"
              size={36}
              emblem={{
                color2: item.kind === "color2" ? "#F97316" : null,
                pattern: item.kind === "pattern" ? item.style_key : null,
                symbol: item.kind === "symbol" ? item.style_key : null,
                letters: item.kind === "letters" ? "ФК" : null,
                outline: item.kind === "outline" ? item.style_key : null,
                outline_thin: false,
                effect: item.kind === "effect" ? item.style_key : null,
              }}
            />
            <span className="w-24 text-micro text-slate-500">{EMBLEM_KIND_LABELS[item.kind]}</span>
            <input value={d.name} onChange={(e) => edit(item, { name: e.target.value })} className={`${input} w-40`} />
            <label className="flex items-center gap-1 text-micro text-slate-500">
              монеты
              <input type="number" min={0} value={d.coins_price} onChange={(e) => edit(item, { coins_price: Number(e.target.value) })} className={`${input} w-24`} />
            </label>
            <label className="flex items-center gap-1 text-micro text-slate-500">
              ⭐
              <input type="number" min={0} value={d.stars_price} onChange={(e) => edit(item, { stars_price: Number(e.target.value) })} className={`${input} w-20`} />
            </label>
            <label className="flex items-center gap-1 text-micro text-slate-500">
              порядок
              <input type="number" value={d.sort_order} onChange={(e) => edit(item, { sort_order: Number(e.target.value) })} className={`${input} w-16`} />
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={d.is_active} onChange={(e) => edit(item, { is_active: e.target.checked })} /> продаётся
            </label>
            <button
              onClick={() => save.mutate(d)}
              disabled={!drafts[item.id] || save.isPending}
              className="ml-auto rounded-lg bg-accent px-3 py-1 text-xs font-bold text-bg-base disabled:opacity-40"
            >
              Сохранить
            </button>
          </div>
        );
      })}
    </div>
  );
}

// --- «Клубный магазин» ---------------------------------------------------------------

const NEW_SHOP_ITEM: AdminClubShopItem = {
  name: "", description: "", price: 5000, weekly_limit: 1, reward: { ...EMPTY_BUNDLE }, is_active: true, sort_order: 0,
};

function ClubShopTab() {
  const queryClient = useQueryClient();
  const { data: items } = useQuery({ queryKey: ["admin-club-shop-items"], queryFn: fetchAdminClubShopItems });
  const [draft, setDraft] = useState<AdminClubShopItem | null>(null);
  const save = useMutation({
    mutationFn: saveAdminClubShopItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-club-shop-items"] });
      setDraft(null);
      toast("Сохранено");
    },
    onError: (err) => useAdminToastStore.getState().push(errText(err, "Не удалось сохранить"), "error"),
  });
  if (!items) return <p className="text-sm text-slate-400">Загрузка...</p>;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-slate-400">
        Клуб покупает товар за свой бюджет, награду (на каждого участника) забирает каждый, кто был в клубе на момент покупки.
        Лимит — сколько раз в неделю один клуб может купить товар.
      </p>
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => setDraft(item)}
          className="flex items-center gap-3 rounded-xl border border-white/5 bg-bg-surface p-3 text-left text-sm"
        >
          <span className="flex-1 font-semibold">{item.name}</span>
          <span className="text-xs text-slate-400">{item.price} монет · {item.weekly_limit}/нед.</span>
          {!item.is_active && <span className="text-xs text-red-400">выкл</span>}
        </button>
      ))}
      <button onClick={() => setDraft({ ...NEW_SHOP_ITEM, reward: { ...EMPTY_BUNDLE } })} className="self-start rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base">
        + Товар
      </button>
      {draft && (
        <div className="flex flex-col gap-2 rounded-2xl border border-accent/30 bg-bg-surface p-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Название" className={input} />
            <input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="Описание" className={input} />
            <label className="flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">Цена (бюджет клуба)</span>
              <input type="number" min={1} value={draft.price} onChange={(e) => setDraft({ ...draft, price: Number(e.target.value) })} className={input} />
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">Покупок в неделю</span>
              <input type="number" min={1} value={draft.weekly_limit} onChange={(e) => setDraft({ ...draft, weekly_limit: Number(e.target.value) })} className={input} />
            </label>
          </div>
          <p className="text-micro text-slate-500">Награда каждому участнику:</p>
          <RewardBundleEditor value={draft.reward} onChange={(reward) => setDraft({ ...draft, reward })} />
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} /> продаётся
            </label>
            <label className="flex items-center gap-1 text-xs text-slate-500">
              порядок
              <input type="number" value={draft.sort_order} onChange={(e) => setDraft({ ...draft, sort_order: Number(e.target.value) })} className={`${input} w-16`} />
            </label>
            <button onClick={() => setDraft(null)} className="ml-auto rounded-lg bg-white/5 px-3 py-1.5 text-xs">Отмена</button>
            <button
              onClick={() => save.mutate(draft)}
              disabled={!draft.name || save.isPending}
              className="rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
            >
              Сохранить
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// --- «Задания недели» клуба ----------------------------------------------------------

const QUEST_METRICS: Record<AdminClubQuest["metric"], string> = { games: "Игры / матчи", packs: "Платные паки", tasks: "Задания" };
const NEW_QUEST: AdminClubQuest = {
  title: "", metric: "games", target_per_member: 5, reward_budget: 1000, reward: { ...EMPTY_BUNDLE }, is_active: true, sort_order: 0,
};

function ClubQuestsTab() {
  const queryClient = useQueryClient();
  const { data: quests } = useQuery({ queryKey: ["admin-club-quests"], queryFn: fetchAdminClubQuests });
  const [draft, setDraft] = useState<AdminClubQuest | null>(null);
  const save = useMutation({
    mutationFn: saveAdminClubQuest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-club-quests"] });
      setDraft(null);
      toast("Сохранено");
    },
    onError: (err) => useAdminToastStore.getState().push(errText(err, "Не удалось сохранить"), "error"),
  });
  if (!quests) return <p className="text-sm text-slate-400">Загрузка...</p>;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-slate-400">
        Каждое активное задание — общее для каждого клуба на неделю лиги. Цель = «на участника» × число участников клуба.
        Считается та же активность, что и в лиге клубов. Выполнили — бюджет клуба получает награду, а каждый участник забирает свою.
      </p>
      {quests.map((q) => (
        <button key={q.id} onClick={() => setDraft(q)} className="flex items-center gap-3 rounded-xl border border-white/5 bg-bg-surface p-3 text-left text-sm">
          <span className="flex-1 font-semibold">{q.title}</span>
          <span className="text-xs text-slate-400">{QUEST_METRICS[q.metric]} · {q.target_per_member}/участника · казна +{q.reward_budget}</span>
          {!q.is_active && <span className="text-xs text-red-400">выкл</span>}
        </button>
      ))}
      <button onClick={() => setDraft({ ...NEW_QUEST, reward: { ...EMPTY_BUNDLE } })} className="self-start rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base">
        + Задание
      </button>
      {draft && (
        <div className="flex flex-col gap-2 rounded-2xl border border-accent/30 bg-bg-surface p-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} placeholder="Название" className={input} />
            <select value={draft.metric} onChange={(e) => setDraft({ ...draft, metric: e.target.value as AdminClubQuest["metric"] })} className={input}>
              {Object.entries(QUEST_METRICS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <label className="flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">Цель на участника</span>
              <input type="number" min={1} value={draft.target_per_member} onChange={(e) => setDraft({ ...draft, target_per_member: Number(e.target.value) })} className={input} />
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-micro text-slate-500">В бюджет клуба</span>
              <input type="number" min={0} value={draft.reward_budget} onChange={(e) => setDraft({ ...draft, reward_budget: Number(e.target.value) })} className={input} />
            </label>
          </div>
          <p className="text-micro text-slate-500">Награда каждому участнику:</p>
          <RewardBundleEditor value={draft.reward} onChange={(reward) => setDraft({ ...draft, reward })} />
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} /> активно
            </label>
            <label className="flex items-center gap-1 text-xs text-slate-500">
              порядок
              <input type="number" value={draft.sort_order} onChange={(e) => setDraft({ ...draft, sort_order: Number(e.target.value) })} className={`${input} w-16`} />
            </label>
            <button onClick={() => setDraft(null)} className="ml-auto rounded-lg bg-white/5 px-3 py-1.5 text-xs">Отмена</button>
            <button onClick={() => save.mutate(draft)} disabled={!draft.title || save.isPending} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40">
              Сохранить
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
