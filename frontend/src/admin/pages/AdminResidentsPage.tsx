import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import {
  fetchAdminTownResidents, fetchGameConfig, grantAdminTownResident, saveAdminTownResident, updateGameConfig,
  uploadAdminTownResidentImage,
} from "@/admin/api";
import { useAdminToastStore } from "@/admin/adminToastStore";
import type { AdminTownResident, GameConfig } from "@/admin/types";
import MuseArt from "@/components/muses/MuseArt";
import { ApiRequestError } from "@/lib/api";
import { RARITY_LABELS } from "@/lib/rarity";
import type { Rarity } from "@/types";

const input = "w-full rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none";
const errText = (err: unknown, fallback: string) => (err instanceof ApiRequestError ? err.message : fallback);
const toast = (text: string) => useAdminToastStore.getState().push(text, "success");
const toastError = (err: unknown, fallback: string) => useAdminToastStore.getState().push(errText(err, fallback), "error");
const NEW_RESIDENT: AdminTownResident = {
  name: "", title: "", description: "", icon: "🧑", rarity: "common", bonus: "none", bonus_value: 0, drop_weight: 100,
  is_pack_droppable: true, is_active: true, sort_order: 0,
};
const SPARE_RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];

/** «Жители города»: the resident cards (picture, name, rarity, a bonus for the
 * legendary ones), their drop weight, a grant, and the settings — rent per
 * resident, spare-copy prices, bonus caps (GameConfig). Residents drop from
 * packs with «Шанс жителя» set (the «Жители» packs, «Паки»). */
export default function AdminResidentsPage() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-town-residents"], queryFn: fetchAdminTownResidents });
  const [editing, setEditing] = useState<AdminTownResident | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin-town-residents"] });
  const save = useMutation({
    mutationFn: saveAdminTownResident,
    onSuccess: (saved) => { setEditing(saved); refresh(); toast("Сохранено"); },
    onError: (err) => toastError(err, "Не удалось сохранить"),
  });
  const upload = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => uploadAdminTownResidentImage(id, file),
    onSuccess: (saved: AdminTownResident) => { setEditing(saved); refresh(); toast("Картинка загружена"); },
    onError: (err) => toastError(err, "Не удалось загрузить картинку"),
  });

  if (!data) return <p className="text-sm text-slate-400">Загрузка...</p>;
  const r = editing;
  const set = (patch: Partial<AdminTownResident>) => r && setEditing({ ...r, ...patch });

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-xl font-bold">Жители города</h1>
        <p className="text-xs text-slate-400">
          Каждая копия жителя платит ренту каждый день (настройка ниже). Бонус жителя (обычно у легендарных) считается один раз,
          сколько бы копий ни было. Жители выпадают из паков с «Шансом жителя» (паки «Жители» — раздел «Паки»), продаются в
          витрине «Магазин» и выдаются вручную. Лишние копии игрок продаёт за монеты.
        </p>
      </div>

      <SettingsBlock />

      {r ? (
        <div className="flex flex-col gap-3 rounded-2xl border border-accent/40 bg-bg-surface p-3">
          <p className="font-display text-base font-bold">{r.id ? "Житель" : "Новый житель"}</p>
          <div className="flex items-start gap-3">
            <MuseArt muse={{ name: r.name, icon: r.icon, image_path: r.image_path ?? null, rarity: r.rarity as Rarity }}
              className="aspect-[3/4] w-[72px] rounded-xl" iconClass="text-3xl" />
            {r.id ? (
              <label className="cursor-pointer rounded-lg bg-white/5 px-3 py-1.5 text-xs">
                Загрузить картинку (3:4)
                <input type="file" accept="image/*" className="hidden"
                  onChange={(e) => e.target.files?.[0] && upload.mutate({ id: r.id!, file: e.target.files[0] })} />
              </label>
            ) : (
              <p className="text-xs text-slate-400">Картинку можно загрузить после сохранения</p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Field label="Имя"><input value={r.name} onChange={(e) => set({ name: e.target.value })} className={input} /></Field>
            <Field label="Кто он (подпись)"><input value={r.title ?? ""} placeholder="рыбак, бариста…" onChange={(e) => set({ title: e.target.value || null })} className={input} /></Field>
            <Field label="Описание" wide><input value={r.description ?? ""} onChange={(e) => set({ description: e.target.value || null })} className={input} /></Field>
            <Field label="Иконка (без картинки)"><input value={r.icon} onChange={(e) => set({ icon: e.target.value })} className={input} /></Field>
            <Field label="Редкость"><select value={r.rarity} onChange={(e) => set({ rarity: e.target.value })} className={input}>
              {data.rarities.map((x) => <option key={x} value={x}>{RARITY_LABELS[x as Rarity] ?? x}</option>)}</select></Field>
            <Field label="Бонус"><select value={r.bonus} onChange={(e) => set({ bonus: e.target.value })} className={input}>
              {data.bonuses.map((b) => <option key={b.code} value={b.code}>{b.label || "— без бонуса —"}</option>)}</select></Field>
            <Field label="N"><input type="number" min={0} value={r.bonus_value} onChange={(e) => set({ bonus_value: Number(e.target.value) })} className={input} /></Field>
            <Field label="Вес выпадения (среди редкости)"><input type="number" min={0} value={r.drop_weight} onChange={(e) => set({ drop_weight: Number(e.target.value) })} className={input} /></Field>
            <Field label="Порядок"><input type="number" value={r.sort_order} onChange={(e) => set({ sort_order: Number(e.target.value) })} className={input} /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={r.is_active} onChange={(e) => set({ is_active: e.target.checked })} /> Активен (выпадает, платит)</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={r.is_pack_droppable} onChange={(e) => set({ is_pack_droppable: e.target.checked })} /> Выпадает из паков</label>
          </div>
          <div className="flex gap-2">
            <button onClick={() => save.mutate(r)} disabled={save.isPending || !r.name.trim()} className="rounded-lg bg-accent-lime px-4 py-1.5 text-sm font-semibold text-bg-base disabled:opacity-50">Сохранить</button>
            <button onClick={() => setEditing(null)} className="rounded-lg bg-white/5 px-4 py-1.5 text-sm">Назад</button>
          </div>
          {r.id && <GrantBlock residentId={r.id} />}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <button onClick={() => setEditing(NEW_RESIDENT)} className="self-start rounded-lg bg-accent-lime px-3 py-1.5 text-sm font-semibold text-bg-base">+ Житель</button>
          {data.residents.length === 0 && <p className="text-xs text-slate-400">Жителей пока нет — добавь первого.</p>}
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
            {data.residents.map((x) => (
              <button key={x.id} onClick={() => setEditing(x)} className={`flex flex-col gap-1 rounded-xl bg-bg-surface p-1.5 text-left ${x.is_active ? "" : "opacity-50"}`}>
                <MuseArt muse={{ name: x.name, icon: x.icon, image_path: x.image_path ?? null, rarity: x.rarity as Rarity }}
                  className="aspect-[3/4] w-full rounded-xl" iconClass="text-3xl" />
                <span className="truncate text-xs font-semibold">{x.name}</span>
                <span className="truncate text-micro text-slate-400">
                  {RARITY_LABELS[x.rarity as Rarity] ?? x.rarity}{x.bonus_label ? ` · ${x.bonus_label}` : ""}
                </span>
                <span className="text-micro text-slate-500">у игроков: {x.copies_held ?? 0}{x.is_pack_droppable ? "" : " · не из паков"}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
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

function GrantBlock({ residentId }: { residentId: number }) {
  const [userId, setUserId] = useState("");
  const grant = useMutation({
    mutationFn: () => grantAdminTownResident(residentId, Number(userId)),
    onSuccess: (res) => toast(`Житель выдан (копий у игрока: ${res.copies})`),
    onError: (err) => toastError(err, "Не удалось выдать"),
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

type SettingsKey = "town_residents_enabled" | "town_resident_rent" | "town_resident_spare_coins"
  | "town_resident_bonus_max_pct" | "town_resident_max_daily_coins";

function SettingsBlock() {
  const queryClient = useQueryClient();
  const { data: config } = useQuery({ queryKey: ["admin-game-config"], queryFn: fetchGameConfig });
  const [draft, setDraft] = useState<Partial<Pick<GameConfig, SettingsKey>>>({});
  const save = useMutation({
    mutationFn: () => updateGameConfig(draft),
    onSuccess: (saved) => { queryClient.setQueryData(["admin-game-config"], saved); setDraft({}); toast("Настройки сохранены"); },
    onError: (err) => toastError(err, "Не удалось сохранить"),
  });
  if (!config) return null;
  const value = <K extends SettingsKey>(k: K) => (k in draft ? draft[k] : config[k]) as GameConfig[K];
  const spare = value("town_resident_spare_coins") ?? {};
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-3">
      <p className="font-display text-sm font-bold">Настройки</p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={value("town_residents_enabled")} onChange={(e) => setDraft({ ...draft, town_residents_enabled: e.target.checked })} />
        Жители включены (выключено — не выпадают и не платят)
      </label>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Field label="Монет в день за каждую копию">
          <input type="number" min={0} value={value("town_resident_rent")} onChange={(e) => setDraft({ ...draft, town_resident_rent: Number(e.target.value) })} className={input} />
        </Field>
        <Field label="Потолок бонусов, % (рента / отель)">
          <input type="number" min={0} value={value("town_resident_bonus_max_pct")} onChange={(e) => setDraft({ ...draft, town_resident_bonus_max_pct: Number(e.target.value) })} className={input} />
        </Field>
        <Field label="Потолок «+монет в день» от бонусов">
          <input type="number" min={0} value={value("town_resident_max_daily_coins")} onChange={(e) => setDraft({ ...draft, town_resident_max_daily_coins: Number(e.target.value) })} className={input} />
        </Field>
      </div>
      <p className="text-micro text-slate-500">Лишняя копия продаётся за, монет:</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {SPARE_RARITIES.map((rarity) => (
          <Field key={rarity} label={RARITY_LABELS[rarity]}>
            <input type="number" min={0} value={spare[rarity] ?? 0}
              onChange={(e) => setDraft({ ...draft, town_resident_spare_coins: { ...spare, [rarity]: Number(e.target.value) } })} className={input} />
          </Field>
        ))}
      </div>
      <button onClick={() => save.mutate()} disabled={save.isPending || Object.keys(draft).length === 0}
        className="self-start rounded-lg bg-accent-lime px-4 py-1.5 text-sm font-semibold text-bg-base disabled:opacity-50">Сохранить настройки</button>
    </section>
  );
}
