import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import {
  fetchAdminMuses, fetchGameConfig, grantAdminMuse, saveAdminMuseRow, updateGameConfig, uploadAdminMuseImage,
  type AdminMuseKind,
} from "@/admin/api";
import { useAdminToastStore } from "@/admin/adminToastStore";
import type { AdminMuse, AdminMuseAccessory, AdminMuseCollection, GameConfig } from "@/admin/types";
import MuseArt from "@/components/muses/MuseArt";
import { ApiRequestError } from "@/lib/api";
import { RARITY_LABELS } from "@/lib/rarity";
import type { Rarity } from "@/types";

const input = "w-full rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none";
const errText = (err: unknown, fallback: string) => (err instanceof ApiRequestError ? err.message : fallback);
const toast = (text: string) => useAdminToastStore.getState().push(text, "success");
const NEW_MUSE: AdminMuse = {
  name: "", title: "", description: "", icon: "💃", rarity: "rare", collection_id: null, effect: "daily_coins",
  effect_value: 100, drop_weight: 100, is_active: true, sort_order: 0,
};
const NEW_COLLECTION: AdminMuseCollection = { name: "", description: "", is_active: true, sort_order: 0 };
const NEW_GIFT: AdminMuseAccessory = {
  name: "", description: "", icon: "👜", kind: "bag", rarity: "common", boost_pct: 10, coins_price: 1000, stars_price: 0,
  is_active: true, sort_order: 0,
};

type Tab = "muses" | "collections" | "gifts" | "settings";
type Editing =
  | { kind: "muses"; row: AdminMuse }
  | { kind: "collections"; row: AdminMuseCollection }
  | { kind: "accessories"; row: AdminMuseAccessory };

/** «Музы»: the switch and ceilings, collections, Muses (photo, bonus, drop
 * weight), gifts (photo, +% to the bonus, prices), handing a Muse to a player.
 * Muses drop from packs with «Шанс музы» set (the «Музы» pack, «Паки»). */
export default function AdminMusesPage() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-muses"], queryFn: fetchAdminMuses });
  const [tab, setTab] = useState<Tab>("muses");
  const [editing, setEditing] = useState<Editing | null>(null);
  const [filter, setFilter] = useState<number | "all">("all");
  const [error, setError] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin-muses"] });

  const save = useMutation({
    mutationFn: (e: Editing) => saveAdminMuseRow(e.kind, e.row),
    onSuccess: (saved, e) => { setEditing({ kind: e.kind, row: saved } as Editing); setError(null); refresh(); toast("Сохранено"); },
    onError: (err) => setError(errText(err, "Не удалось сохранить")),
  });
  const upload = useMutation({
    mutationFn: ({ kind, id, file }: { kind: AdminMuseKind; id: number; file: File }) => uploadAdminMuseImage(kind, id, file),
    onSuccess: (saved, vars) => { setEditing({ kind: vars.kind, row: saved } as Editing); refresh(); toast("Фото загружено"); },
    onError: (err) => setError(errText(err, "Не удалось загрузить фото")),
  });

  if (!data) return <p className="text-sm text-slate-400">Загрузка...</p>;
  const effectLabel = (code: string, v: number) => (data.effects.find((e) => e.code === code)?.label ?? code).replace("N", String(v));
  const collectionName = (id: number | null) => data.collections.find((c) => c.id === id)?.name ?? "без коллекции";
  const muses = data.muses.filter((m) => filter === "all" || m.collection_id === filter);

  const editor = editing && (() => {
    const photo = editing.row.id ? (file: File) => upload.mutate({ kind: editing.kind, id: editing.row.id!, file }) : undefined;
    const onSave = () => save.mutate(editing);
    const onClose = () => setEditing(null);
    if (editing.kind === "collections") {
      const c = editing.row;
      const set = (patch: Partial<AdminMuseCollection>) => setEditing({ kind: "collections", row: { ...c, ...patch } });
      return (
        <Editor title={c.id ? "Коллекция" : "Новая коллекция"} onSave={onSave} onClose={onClose} saving={save.isPending} photo={photo}
          preview={<MuseArt muse={{ name: c.name, icon: "💖", image_path: c.image_path ?? null, rarity: "epic" }} className="h-20 w-16 rounded-xl" iconClass="text-3xl" />}>
          <Field label="Название"><input value={c.name} onChange={(e) => set({ name: e.target.value })} className={input} /></Field>
          <Field label="Описание" wide><input value={c.description ?? ""} onChange={(e) => set({ description: e.target.value })} className={input} /></Field>
          <Field label="Порядок"><input type="number" value={c.sort_order} onChange={(e) => set({ sort_order: Number(e.target.value) })} className={input} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={c.is_active} onChange={(e) => set({ is_active: e.target.checked })} /> Показывать</label>
        </Editor>
      );
    }
    if (editing.kind === "accessories") {
      const g = editing.row;
      const set = (patch: Partial<AdminMuseAccessory>) => setEditing({ kind: "accessories", row: { ...g, ...patch } });
      return (
        <Editor title={g.id ? "Подарок" : "Новый подарок"} onSave={onSave} onClose={onClose} saving={save.isPending} photo={photo}
          preview={<MuseArt muse={{ name: g.name, icon: g.icon, image_path: g.image_path ?? null, rarity: g.rarity as Rarity }} className="h-16 w-16 rounded-xl" iconClass="text-3xl" />}>
          <Field label="Название"><input value={g.name} onChange={(e) => set({ name: e.target.value })} className={input} /></Field>
          <Field label="Иконка (без фото)"><input value={g.icon} onChange={(e) => set({ icon: e.target.value })} className={input} /></Field>
          <Field label="Описание" wide><input value={g.description ?? ""} onChange={(e) => set({ description: e.target.value })} className={input} /></Field>
          <Field label="Вид"><select value={g.kind} onChange={(e) => set({ kind: e.target.value })} className={input}>
            {data.kinds.map((k) => <option key={k.code} value={k.code}>{k.label}</option>)}</select></Field>
          <Field label="Редкость"><select value={g.rarity} onChange={(e) => set({ rarity: e.target.value })} className={input}>
            {data.rarities.map((r) => <option key={r} value={r}>{RARITY_LABELS[r as Rarity] ?? r}</option>)}</select></Field>
          <Field label="+% к бонусу музы"><input type="number" min={0} value={g.boost_pct} onChange={(e) => set({ boost_pct: Number(e.target.value) })} className={input} /></Field>
          <Field label="Цена, монеты (0 — нет)"><input type="number" min={0} value={g.coins_price} onChange={(e) => set({ coins_price: Number(e.target.value) })} className={input} /></Field>
          <Field label="Цена, звёзды ⭐ (0 — нет)"><input type="number" min={0} value={g.stars_price} onChange={(e) => set({ stars_price: Number(e.target.value) })} className={input} /></Field>
          <Field label="Порядок"><input type="number" value={g.sort_order} onChange={(e) => set({ sort_order: Number(e.target.value) })} className={input} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={g.is_active} onChange={(e) => set({ is_active: e.target.checked })} /> В продаже</label>
        </Editor>
      );
    }
    const m = editing.row;
    const set = (patch: Partial<AdminMuse>) => setEditing({ kind: "muses", row: { ...m, ...patch } });
    return (
      <Editor title={m.id ? "Муза" : "Новая муза"} onSave={onSave} onClose={onClose} saving={save.isPending} photo={photo}
        preview={<MuseArt muse={{ name: m.name, icon: m.icon, image_path: m.image_path ?? null, rarity: m.rarity as Rarity }} className="h-24 w-[72px] rounded-xl" iconClass="text-3xl" />}
        footer={m.id ? <GrantBlock museId={m.id} /> : null}>
        <Field label="Имя"><input value={m.name} onChange={(e) => set({ name: e.target.value })} className={input} /></Field>
        <Field label="Кто она (подпись)"><input value={m.title ?? ""} placeholder="певица, модель…" onChange={(e) => set({ title: e.target.value || null })} className={input} /></Field>
        <Field label="Описание" wide><input value={m.description ?? ""} onChange={(e) => set({ description: e.target.value })} className={input} /></Field>
        <Field label="Иконка (без фото)"><input value={m.icon} onChange={(e) => set({ icon: e.target.value })} className={input} /></Field>
        <Field label="Редкость"><select value={m.rarity} onChange={(e) => set({ rarity: e.target.value })} className={input}>
          {data.rarities.map((r) => <option key={r} value={r}>{RARITY_LABELS[r as Rarity] ?? r}</option>)}</select></Field>
        <Field label="Коллекция"><select value={m.collection_id ?? ""} onChange={(e) => set({ collection_id: e.target.value ? Number(e.target.value) : null })} className={input}>
          <option value="">— без коллекции —</option>
          {data.collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <Field label="Бонус"><select value={m.effect} onChange={(e) => set({ effect: e.target.value })} className={input}>
          {data.effects.map((ef) => <option key={ef.code} value={ef.code}>{ef.label}</option>)}</select></Field>
        <Field label="N"><input type="number" min={0} value={m.effect_value} onChange={(e) => set({ effect_value: Number(e.target.value) })} className={input} /></Field>
        <Field label="Вес выпадения (среди её редкости)"><input type="number" min={0} value={m.drop_weight} onChange={(e) => set({ drop_weight: Number(e.target.value) })} className={input} /></Field>
        <Field label="Порядок"><input type="number" value={m.sort_order} onChange={(e) => set({ sort_order: Number(e.target.value) })} className={input} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={m.is_active} onChange={(e) => set({ is_active: e.target.checked })} /> Активна (выпадает, даёт бонус)</label>
      </Editor>
    );
  })();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-xl font-bold">Музы</h1>
        <p className="text-xs text-slate-400">
          Муза вдохновляет «Моего футболиста»: бонус даёт одна активная муза игрока, подарки усиливают его на свой %.
          Музы выпадают из паков с «Шансом музы» (пак «Музы» — раздел «Паки»).
        </p>
      </div>
      <div className="flex flex-wrap gap-1">
        {([["muses", "Музы"], ["collections", "Коллекции"], ["gifts", "Подарки"], ["settings", "Настройки"]] as [Tab, string][]).map(([id, label]) => (
          <button key={id} onClick={() => { setTab(id); setEditing(null); }}
            className={`rounded-lg px-3 py-1.5 text-sm ${tab === id ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"}`}>
            {label}
          </button>
        ))}
      </div>
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {tab === "settings" ? (
        <SettingsBlock />
      ) : editor ? (
        editor
      ) : tab === "collections" ? (
        <ListSection title="Коллекции" onAdd={() => setEditing({ kind: "collections", row: { ...NEW_COLLECTION } })} addLabel="+ Коллекция">
          {data.collections.map((c) => (
            <Row key={c.id} onClick={() => setEditing({ kind: "collections", row: c })}
              art={<MuseArt muse={{ name: c.name, icon: "💖", image_path: c.image_path ?? null, rarity: "epic" }} className="h-12 w-10 rounded-lg" iconClass="text-xl" />}
              title={<>{c.name} {!c.is_active && <span className="text-xs text-slate-500">(скрыта)</span>}</>}
              subtitle={`${data.muses.filter((m) => m.collection_id === c.id).length} муз`} />
          ))}
        </ListSection>
      ) : tab === "gifts" ? (
        <ListSection title="Подарки" onAdd={() => setEditing({ kind: "accessories", row: { ...NEW_GIFT } })} addLabel="+ Подарок">
          {data.accessories.map((g) => (
            <Row key={g.id} onClick={() => setEditing({ kind: "accessories", row: g })}
              art={<MuseArt muse={{ name: g.name, icon: g.icon, image_path: g.image_path ?? null, rarity: g.rarity as Rarity }} className="h-10 w-10 rounded-lg" iconClass="text-xl" />}
              title={<>{g.name} {!g.is_active && <span className="text-xs text-slate-500">(скрыт)</span>}</>}
              subtitle={`${g.kind_label ?? g.kind} · +${g.boost_pct}% к бонусу`}
              right={<>{g.coins_price > 0 && `${g.coins_price} 🪙`} {g.stars_price > 0 && `${g.stars_price} ⭐`}</>} />
          ))}
        </ListSection>
      ) : (
        <ListSection title="Музы" onAdd={() => setEditing({ kind: "muses", row: { ...NEW_MUSE, collection_id: filter === "all" ? null : filter } })} addLabel="+ Муза"
          extra={
            <select value={filter} onChange={(e) => setFilter(e.target.value === "all" ? "all" : Number(e.target.value))} className="rounded-lg bg-bg-base px-2 py-1 text-xs">
              <option value="all">Все коллекции</option>
              {data.collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          }>
          {muses.map((m) => (
            <Row key={m.id} onClick={() => setEditing({ kind: "muses", row: m })}
              art={<MuseArt muse={{ name: m.name, icon: m.icon, image_path: m.image_path ?? null, rarity: m.rarity as Rarity }} locked={!m.is_active} className="h-12 w-10 rounded-lg" iconClass="text-xl" />}
              title={<>{m.name} {!m.image_path && <span className="text-xs text-amber-300">нет фото</span>}</>}
              subtitle={`${RARITY_LABELS[m.rarity as Rarity] ?? m.rarity} · ${effectLabel(m.effect, m.effect_value)} · ${collectionName(m.collection_id)}`}
              right={`вес ${m.drop_weight}`} />
          ))}
        </ListSection>
      )}
    </div>
  );
}

function ListSection({ title, onAdd, addLabel, extra, children }: {
  title: string; onAdd: () => void; addLabel: string; extra?: ReactNode; children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="font-display text-base font-bold">{title}</p>
        <div className="flex items-center gap-2">
          {extra}
          <button onClick={onAdd} className="rounded-lg bg-accent-lime/15 px-3 py-1 text-xs font-semibold text-accent-lime">{addLabel}</button>
        </div>
      </div>
      {children}
    </section>
  );
}

function Row({ onClick, art, title, subtitle, right }: {
  onClick: () => void; art: ReactNode; title: ReactNode; subtitle: string; right?: ReactNode;
}) {
  return (
    <button onClick={onClick} className="flex w-full items-center gap-3 border-t border-white/5 py-2 text-left">
      {art}
      <span className="min-w-0 flex-1 text-sm">
        <span className="block truncate">{title}</span>
        <span className="block truncate text-xs text-slate-400">{subtitle}</span>
      </span>
      {right && <span className="shrink-0 text-xs text-slate-400">{right}</span>}
    </button>
  );
}

function Field({ label, wide, children }: { label: string; wide?: boolean; children: ReactNode }) {
  return (
    <label className={`flex flex-col gap-0.5 ${wide ? "col-span-2" : ""}`}>
      <span className="text-micro text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function Editor({ title, children, onSave, onClose, saving, photo, preview, footer }: {
  title: string; children: ReactNode; onSave: () => void; onClose: () => void; saving: boolean;
  photo?: (file: File) => void; preview: ReactNode; footer?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-accent/40 bg-bg-surface p-3">
      <p className="font-display text-base font-bold">{title}</p>
      <div className="flex items-start gap-3">
        {preview}
        {photo ? (
          <label className="cursor-pointer rounded-lg bg-white/5 px-3 py-1.5 text-xs">
            Загрузить фото
            <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && photo(e.target.files[0])} />
          </label>
        ) : (
          <p className="text-xs text-slate-400">Фото можно загрузить после сохранения</p>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{children}</div>
      <div className="flex gap-2">
        <button onClick={onSave} disabled={saving} className="rounded-lg bg-accent-lime px-4 py-1.5 text-sm font-semibold text-bg-base disabled:opacity-50">Сохранить</button>
        <button onClick={onClose} className="rounded-lg bg-white/5 px-4 py-1.5 text-sm">Назад</button>
      </div>
      {footer}
    </div>
  );
}

function GrantBlock({ museId }: { museId: number }) {
  const [userId, setUserId] = useState("");
  const grant = useMutation({
    mutationFn: () => grantAdminMuse(museId, Number(userId)),
    onSuccess: (res) => toast(`Муза выдана (копий у игрока: ${res.copies})`),
    onError: (err) => useAdminToastStore.getState().push(errText(err, "Не удалось выдать"), "error"),
  });
  return (
    <div className="flex items-end gap-2 border-t border-white/5 pt-3">
      <Field label="Выдать игроку (ID пользователя)">
        <input value={userId} onChange={(e) => setUserId(e.target.value.replace(/\D/g, ""))} className={input} />
      </Field>
      <button onClick={() => grant.mutate()} disabled={!userId || grant.isPending} className="rounded-lg bg-white/10 px-3 py-1.5 text-sm disabled:opacity-40">Выдать</button>
    </div>
  );
}

const SPARE_RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];
const DATE_GAMES: [string, string][] = [["memory", "Memory Sequence"], ["pairs", "Найди пару"], ["hangman", "Футбольные буквы"]];

function SettingsBlock() {
  const queryClient = useQueryClient();
  const { data: config } = useQuery({ queryKey: ["admin-game-config"], queryFn: fetchGameConfig });
  const [draft, setDraft] = useState<Partial<GameConfig>>({});
  const save = useMutation({
    mutationFn: () => updateGameConfig(draft),
    onSuccess: (saved) => { queryClient.setQueryData(["admin-game-config"], saved); setDraft({}); toast("Настройки сохранены"); },
    onError: (err) => useAdminToastStore.getState().push(errText(err, "Не удалось сохранить"), "error"),
  });
  if (!config) return null;
  const value = <K extends keyof GameConfig>(k: K) => (k in draft ? draft[k] : config[k]) as GameConfig[K];
  type NumKey =
    | "muse_max_stat" | "muse_max_pp" | "muse_max_xp_pct" | "muse_max_daily_coins" | "muse_max_accessory_pct"
    | "muse_date_coins" | "muse_inspiration_hours";
  const num = (k: NumKey, label: string) => (
    <Field label={label}>
      <input type="number" min={0} value={value(k)} onChange={(e) => setDraft({ ...draft, [k]: Number(e.target.value) })} className={input} />
    </Field>
  );
  const spare = value("muse_spare_coins") ?? {};
  const dateGames = value("muse_date_games") ?? [];
  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-3">
      <p className="font-display text-base font-bold">Музы: настройки</p>
      <p className="mb-2 text-xs text-slate-400">
        Выключено — бонусы муз не действуют, подарки и монеты дня закрыты, паки дают футболистов вместо муз. Потолки — сколько
        может дать муза вместе с подарками.
      </p>
      <label className="mb-2 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={value("muses_enabled")} onChange={(e) => setDraft({ ...draft, muses_enabled: e.target.checked })} />
        Включить музы
      </label>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {num("muse_max_stat", "Потолок + рейтинга/атаки/защиты/свежести")}
        {num("muse_max_pp", "Потолок % удара/обыгрыша")}
        {num("muse_max_xp_pct", "Потолок % опыта")}
        {num("muse_max_daily_coins", "Потолок монет в день")}
        {num("muse_max_accessory_pct", "Потолок % от всех подарков")}
        {SPARE_RARITIES.map((r) => (
          <Field key={r} label={`Лишняя копия (${RARITY_LABELS[r]}), монет`}>
            <input type="number" min={0} value={spare[r] ?? 0}
              onChange={(e) => setDraft({ ...draft, muse_spare_coins: { ...spare, [r]: Number(e.target.value) } })} className={input} />
          </Field>
        ))}
      </div>
      <p className="mt-4 font-display text-sm font-bold">Свидание с музой</p>
      <p className="mb-2 text-xs text-slate-400">
        Раз в день — случайная мини-игра с активной музой на отдельной попытке (часовые и дневные попытки игр не тратятся,
        результат не важен). Даёт монеты и вдохновение. Если «бонус только со свиданием» включён — без вдохновения бонус музы
        (и монеты дня) не действует.
      </p>
      <label className="mb-2 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={value("muse_date_required")} onChange={(e) => setDraft({ ...draft, muse_date_required: e.target.checked })} />
        Бонус музы только со свиданием
      </label>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {num("muse_date_coins", "Монет за свидание")}
        {num("muse_inspiration_hours", "Вдохновение, часов")}
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-sm">
        {DATE_GAMES.map(([code, label]) => (
          <label key={code} className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={dateGames.includes(code)}
              onChange={(e) => {
                const next = e.target.checked ? [...dateGames, code] : dateGames.filter((g) => g !== code);
                if (next.length) setDraft({ ...draft, muse_date_games: next });
              }}
            />
            {label}
          </label>
        ))}
      </div>
      <button onClick={() => save.mutate()} disabled={!Object.keys(draft).length || save.isPending}
        className="mt-3 rounded-lg bg-accent-lime px-4 py-1.5 text-sm font-semibold text-bg-base disabled:opacity-40">
        Сохранить настройки
      </button>
    </section>
  );
}
