import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  fetchAdminEquipment, fetchGameConfig, grantAdminEquipment, saveAdminEquipmentCollection, saveAdminEquipmentItem,
  updateGameConfig, uploadAdminEquipmentImage,
} from "@/admin/api";
import { useAdminToastStore } from "@/admin/adminToastStore";
import type { AdminEquipmentCollection, AdminEquipmentItem, GameConfig } from "@/admin/types";
import EquipmentTile from "@/components/equipment/EquipmentTile";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { RARITY_LABELS } from "@/lib/rarity";
import type { Rarity } from "@/types";

const input = "w-full rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none";
const errText = (err: unknown, fallback: string) => (err instanceof ApiRequestError ? err.message : fallback);
const toast = (text: string) => useAdminToastStore.getState().push(text, "success");
const NEW_ITEM: AdminEquipmentItem = {
  name: "", description: "", icon: "👕", slot: "boots", rarity: "rare", collection_id: null, effect: "rating",
  effect_value: 1, cond_club: null, cond_country: null, coins_price: 0, stars_price: 0, is_active: true, sort_order: 0,
};
const NEW_COLLECTION: AdminEquipmentCollection = {
  name: "", description: "", set_size: 3, set_bonus_rating: 1, is_active: true, sort_order: 0,
};

/** «Экипировка»: switch and ceilings, collections, things (photo, effect,
 * prices), handing a thing to a player. */
export default function AdminEquipmentTab() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-equipment"], queryFn: fetchAdminEquipment });
  const [item, setItem] = useState<AdminEquipmentItem | null>(null);
  const [collection, setCollection] = useState<AdminEquipmentCollection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin-equipment"] });

  const saveItem = useMutation({
    mutationFn: saveAdminEquipmentItem,
    onSuccess: (saved) => { setItem(saved); setError(null); refresh(); toast("Вещь сохранена"); },
    onError: (err) => setError(errText(err, "Не удалось сохранить")),
  });
  const saveCollection = useMutation({
    mutationFn: saveAdminEquipmentCollection,
    onSuccess: (saved) => { setCollection(saved); setError(null); refresh(); toast("Коллекция сохранена"); },
    onError: (err) => setError(errText(err, "Не удалось сохранить")),
  });
  const upload = useMutation({
    mutationFn: ({ kind, id, file }: { kind: "items" | "collections"; id: number; file: File }) => uploadAdminEquipmentImage(kind, id, file),
    onSuccess: (saved, vars) => { (vars.kind === "items" ? setItem : setCollection)(saved); refresh(); toast("Фото загружено"); },
    onError: (err) => setError(errText(err, "Не удалось загрузить фото")),
  });

  if (!data) return <p className="text-sm text-slate-400">Загрузка...</p>;
  const slotLabel = (code: string) => data.slots.find((s) => s.code === code)?.label ?? code;
  const effectLabel = (code: string, v: number) => (data.effects.find((e) => e.code === code)?.label ?? code).replace("N", String(v));

  return (
    <div className="flex flex-col gap-4">
      <SettingsBlock />
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {collection ? (
        <Editor title={collection.id ? "Коллекция" : "Новая коллекция"} onClose={() => setCollection(null)}
          onSave={() => saveCollection.mutate(collection)} saving={saveCollection.isPending}
          photo={collection.id ? (file) => upload.mutate({ kind: "collections", id: collection.id!, file }) : undefined}
          preview={collection.image_path ? <img src={staticUrl(collection.image_path)} alt="" className="h-16 w-16 rounded-xl object-cover" /> : null}>
          <Field label="Название"><input value={collection.name} onChange={(e) => setCollection({ ...collection, name: e.target.value })} className={input} /></Field>
          <Field label="Описание" wide><input value={collection.description ?? ""} onChange={(e) => setCollection({ ...collection, description: e.target.value })} className={input} /></Field>
          <Field label="Вещей для комплекта"><input type="number" min={1} value={collection.set_size} onChange={(e) => setCollection({ ...collection, set_size: Number(e.target.value) })} className={input} /></Field>
          <Field label="+ рейтинга за комплект"><input type="number" min={0} value={collection.set_bonus_rating} onChange={(e) => setCollection({ ...collection, set_bonus_rating: Number(e.target.value) })} className={input} /></Field>
          <Field label="Порядок"><input type="number" value={collection.sort_order} onChange={(e) => setCollection({ ...collection, sort_order: Number(e.target.value) })} className={input} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={collection.is_active} onChange={(e) => setCollection({ ...collection, is_active: e.target.checked })} /> В магазине</label>
        </Editor>
      ) : item ? (
        <Editor title={item.id ? "Вещь" : "Новая вещь"} onClose={() => setItem(null)} onSave={() => saveItem.mutate(item)} saving={saveItem.isPending}
          photo={item.id ? (file) => upload.mutate({ kind: "items", id: item.id!, file }) : undefined}
          preview={<EquipmentTile item={{ name: item.name, image_path: item.image_path ?? null, icon: item.icon, rarity: item.rarity as Rarity }} />}
          footer={item.id ? <GrantBlock itemId={item.id} /> : null}>
          <Field label="Название"><input value={item.name} onChange={(e) => setItem({ ...item, name: e.target.value })} className={input} /></Field>
          <Field label="Иконка (без фото)"><input value={item.icon} onChange={(e) => setItem({ ...item, icon: e.target.value })} className={input} /></Field>
          <Field label="Описание" wide><input value={item.description ?? ""} onChange={(e) => setItem({ ...item, description: e.target.value })} className={input} /></Field>
          <Field label="Слот"><select value={item.slot} onChange={(e) => setItem({ ...item, slot: e.target.value })} className={input}>
            {data.slots.map((s) => <option key={s.code} value={s.code}>{s.label}</option>)}</select></Field>
          <Field label="Редкость"><select value={item.rarity} onChange={(e) => setItem({ ...item, rarity: e.target.value })} className={input}>
            {data.rarities.map((r) => <option key={r} value={r}>{RARITY_LABELS[r as Rarity] ?? r}</option>)}</select></Field>
          <Field label="Коллекция"><select value={item.collection_id ?? ""} onChange={(e) => setItem({ ...item, collection_id: e.target.value ? Number(e.target.value) : null })} className={input}>
            <option value="">— отдельная вещь —</option>
            {data.collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
          <Field label="Эффект"><select value={item.effect} onChange={(e) => setItem({ ...item, effect: e.target.value })} className={input}>
            {data.effects.map((ef) => <option key={ef.code} value={ef.code}>{ef.label}</option>)}</select></Field>
          <Field label="N"><input type="number" min={0} value={item.effect_value} onChange={(e) => setItem({ ...item, effect_value: Number(e.target.value) })} className={input} /></Field>
          <Field label="Только для клуба"><input value={item.cond_club ?? ""} placeholder="любой" onChange={(e) => setItem({ ...item, cond_club: e.target.value || null })} className={input} /></Field>
          <Field label="Только для страны"><input value={item.cond_country ?? ""} placeholder="любая" onChange={(e) => setItem({ ...item, cond_country: e.target.value || null })} className={input} /></Field>
          <Field label="Цена, монеты (0 — нет)"><input type="number" min={0} value={item.coins_price} onChange={(e) => setItem({ ...item, coins_price: Number(e.target.value) })} className={input} /></Field>
          <Field label="Цена, звёзды ⭐ (0 — нет)"><input type="number" min={0} value={item.stars_price} onChange={(e) => setItem({ ...item, stars_price: Number(e.target.value) })} className={input} /></Field>
          <Field label="Порядок"><input type="number" value={item.sort_order} onChange={(e) => setItem({ ...item, sort_order: Number(e.target.value) })} className={input} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={item.is_active} onChange={(e) => setItem({ ...item, is_active: e.target.checked })} /> В магазине</label>
        </Editor>
      ) : (
        <>
          <section className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="font-display text-base font-bold">Коллекции</p>
              <button onClick={() => setCollection({ ...NEW_COLLECTION })} className="rounded-lg bg-accent-lime/15 px-3 py-1 text-xs font-semibold text-accent-lime">+ Коллекция</button>
            </div>
            {data.collections.map((c) => (
              <button key={c.id} onClick={() => setCollection(c)} className="flex w-full items-center justify-between border-t border-white/5 py-2 text-left text-sm">
                <span>{c.name} {!c.is_active && <span className="text-xs text-slate-500">(скрыта)</span>}</span>
                <span className="text-xs text-slate-400">комплект {c.set_size} → +{c.set_bonus_rating}</span>
              </button>
            ))}
          </section>
          <section className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="font-display text-base font-bold">Вещи</p>
              <button onClick={() => setItem({ ...NEW_ITEM })} className="rounded-lg bg-accent-lime/15 px-3 py-1 text-xs font-semibold text-accent-lime">+ Вещь</button>
            </div>
            {data.items.map((i) => (
              <button key={i.id} onClick={() => setItem(i)} className="flex w-full items-center gap-3 border-t border-white/5 py-2 text-left">
                <EquipmentTile item={{ name: i.name, image_path: i.image_path ?? null, icon: i.icon, rarity: i.rarity as Rarity }} size="sm" dimmed={!i.is_active} />
                <span className="min-w-0 flex-1 text-sm">
                  <span className="block truncate">{i.name}</span>
                  <span className="block text-xs text-slate-400">
                    {slotLabel(i.slot)} · {effectLabel(i.effect, i.effect_value)}
                    {i.collection_id ? ` · ${data.collections.find((c) => c.id === i.collection_id)?.name ?? ""}` : ""}
                  </span>
                </span>
                <span className="shrink-0 text-xs text-slate-400">
                  {i.coins_price > 0 && `${i.coins_price} 🪙`} {i.stars_price > 0 && `${i.stars_price} ⭐`}
                </span>
              </button>
            ))}
          </section>
        </>
      )}
    </div>
  );
}

function Field({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <label className={`flex flex-col gap-0.5 ${wide ? "col-span-2" : ""}`}>
      <span className="text-micro text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function Editor({
  title, children, onSave, onClose, saving, photo, preview, footer,
}: {
  title: string;
  children: React.ReactNode;
  onSave: () => void;
  onClose: () => void;
  saving: boolean;
  photo?: (file: File) => void;
  preview: React.ReactNode;
  footer?: React.ReactNode;
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

function GrantBlock({ itemId }: { itemId: number }) {
  const [userId, setUserId] = useState("");
  const grant = useMutation({
    mutationFn: () => grantAdminEquipment(itemId, Number(userId)),
    onSuccess: () => toast("Вещь выдана"),
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
  const num = (k: "equipment_max_rating" | "equipment_max_pp" | "equipment_max_chemistry", label: string) => (
    <Field label={label}>
      <input type="number" min={0} value={value(k)} onChange={(e) => setDraft({ ...draft, [k]: Number(e.target.value) })} className={input} />
    </Field>
  );
  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-3">
      <p className="font-display text-base font-bold">Экипировка: настройки</p>
      <p className="mb-2 text-xs text-slate-400">
        Выключено — магазин и надевание закрыты, надетые вещи ничего не дают. Потолки — сколько все вещи одной карточки дают вместе
        (с бонусом комплекта). Удар и обыгрыш действуют в Card Arena, турнирах игроков и карьере.
      </p>
      <label className="mb-2 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={value("equipment_enabled")} onChange={(e) => setDraft({ ...draft, equipment_enabled: e.target.checked })} />
        Включить экипировку
      </label>
      <div className="grid grid-cols-3 gap-2">
        {num("equipment_max_rating", "Потолок + рейтинга")}
        {num("equipment_max_pp", "Потолок % удара/обыгрыша")}
        {num("equipment_max_chemistry", "Потолок + химии")}
      </div>
      <button onClick={() => save.mutate()} disabled={!Object.keys(draft).length || save.isPending}
        className="mt-2 rounded-lg bg-accent-lime px-4 py-1.5 text-sm font-semibold text-bg-base disabled:opacity-40">
        Сохранить настройки
      </button>
    </section>
  );
}
