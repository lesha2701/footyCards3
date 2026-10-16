import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAdminArtifacts, fetchAdminStadiums, grantArtifact, saveAdminArtifact, uploadArtifactImage } from "@/admin/api";
import { useAdminToastStore } from "@/admin/adminToastStore";
import type { AdminArtifact } from "@/admin/types";
import ArtifactTile from "@/components/artifacts/ArtifactTile";
import { ApiRequestError } from "@/lib/api";
import { RARITY_LABELS } from "@/lib/rarity";
import type { Rarity } from "@/types";

const input = "w-full rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none";
const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary", "diamond"];
const NEW: AdminArtifact = {
  name: "", description: "", icon: "🏺", rarity: "rare", target: "my_player", effect: "attack", effect_value: 1,
  stadium_id: null, stadium_effect_value: 0, coins_price: 0, stars_price: 0, max_supply: null, is_active: true, sort_order: 0,
};
const errText = (err: unknown, fallback: string) => (err instanceof ApiRequestError ? err.message : fallback);

/** «Артефакты»: catalogue, picture upload and handing one to a player. */
export default function AdminArtifactsTab() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-artifacts"], queryFn: fetchAdminArtifacts });
  const { data: stadiums } = useQuery({ queryKey: ["admin-stadiums-all"], queryFn: () => fetchAdminStadiums("", 1) });
  const [editing, setEditing] = useState<AdminArtifact | null>(null);
  const [grantUser, setGrantUser] = useState("");
  const [error, setError] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin-artifacts"] });

  const save = useMutation({
    mutationFn: (a: AdminArtifact) => saveAdminArtifact(a),
    onSuccess: (saved) => {
      setEditing(saved);
      setError(null);
      refresh();
      useAdminToastStore.getState().push("Артефакт сохранён", "success");
    },
    onError: (err) => setError(errText(err, "Не удалось сохранить")),
  });
  const upload = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => uploadArtifactImage(id, file),
    onSuccess: (saved) => {
      setEditing(saved);
      refresh();
    },
    onError: (err) => setError(errText(err, "Не удалось загрузить картинку")),
  });
  const grant = useMutation({
    mutationFn: ({ id, userId }: { id: number; userId: number }) => grantArtifact(id, userId),
    onSuccess: (r) => {
      refresh();
      useAdminToastStore.getState().push(`Выдан экземпляр №${r.serial_number}`, "success");
    },
    onError: (err) => setError(errText(err, "Не удалось выдать")),
  });

  if (!data) return <p className="text-sm text-slate-400">Загрузка...</p>;
  const effectsFor = (target: string) => data.target_effects[target] ?? [];

  if (editing) {
    const e = editing;
    const set = (patch: Partial<AdminArtifact>) => setEditing({ ...e, ...patch });
    const preview = { ...e, id: e.id ?? 0, image_path: e.image_path ?? null, description: e.description ?? null,
      target_label: data.targets[e.target], effect_label: "", stadium_name: null, stadium_label: "", stadium_owned: false,
      active_label: "", left: null };
    return (
      <div className="flex flex-col gap-3 rounded-2xl border border-accent/40 bg-bg-surface p-3">
        <div className="flex items-start gap-3">
          <ArtifactTile artifact={preview} />
          {e.id ? (
            <label className="cursor-pointer rounded-lg bg-white/5 px-3 py-1.5 text-xs">
              Загрузить картинку
              <input type="file" accept="image/*" className="hidden"
                onChange={(ev) => ev.target.files?.[0] && upload.mutate({ id: e.id!, file: ev.target.files[0] })} />
            </label>
          ) : (
            <p className="text-xs text-slate-400">Картинку можно загрузить после сохранения</p>
          )}
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Название</span>
            <input value={e.name} onChange={(ev) => set({ name: ev.target.value })} className={input} /></label>
          <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Иконка (без картинки)</span>
            <input value={e.icon} onChange={(ev) => set({ icon: ev.target.value })} className={input} /></label>
          <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Редкость (рамка)</span>
            <select value={e.rarity} onChange={(ev) => set({ rarity: ev.target.value as Rarity })} className={input}>
              {RARITIES.map((r) => <option key={r} value={r}>{RARITY_LABELS[r]}</option>)}
            </select></label>
          <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Для кого</span>
            <select
              value={e.target}
              onChange={(ev) => {
                const target = ev.target.value as AdminArtifact["target"];
                set({ target, effect: effectsFor(target).includes(e.effect) ? e.effect : "none" });
              }}
              className={input}
            >
              {Object.entries(data.targets).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></label>
          <label className="col-span-2 flex flex-col gap-0.5"><span className="text-micro text-slate-500">Эффект</span>
            <select value={e.effect} onChange={(ev) => set({ effect: ev.target.value })} className={input}>
              {effectsFor(e.target).map((k) => (
                <option key={k} value={k}>{k === "none" ? "Без эффекта (для красоты)" : data.effects[k].replace("{v}", "N")}</option>
              ))}
            </select></label>
          <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">N</span>
            <input type="number" min={0} value={e.effect_value} onChange={(ev) => set({ effect_value: Number(ev.target.value) })} className={input} /></label>
          <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Порядок</span>
            <input type="number" value={e.sort_order} onChange={(ev) => set({ sort_order: Number(ev.target.value) })} className={input} /></label>
          <label className="col-span-2 flex flex-col gap-0.5"><span className="text-micro text-slate-500">Сильнее со стадионом</span>
            <select value={e.stadium_id ?? ""} onChange={(ev) => set({ stadium_id: ev.target.value ? Number(ev.target.value) : null })} className={input}>
              <option value="">—</option>
              {stadiums?.items.map((s) => <option key={s.id} value={s.id}>{s.display_name}</option>)}
            </select></label>
          <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">N со стадионом</span>
            <input type="number" min={0} value={e.stadium_effect_value} onChange={(ev) => set({ stadium_effect_value: Number(ev.target.value) })} className={input} /></label>
          <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Тираж (пусто — без лимита)</span>
            <input type="number" min={1} value={e.max_supply ?? ""} onChange={(ev) => set({ max_supply: ev.target.value ? Number(ev.target.value) : null })} className={input} /></label>
          <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Цена, монеты (0 — нет)</span>
            <input type="number" min={0} value={e.coins_price} onChange={(ev) => set({ coins_price: Number(ev.target.value) })} className={input} /></label>
          <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Цена, ⭐ (0 — нет)</span>
            <input type="number" min={0} value={e.stars_price} onChange={(ev) => set({ stars_price: Number(ev.target.value) })} className={input} /></label>
          <label className="col-span-2 flex flex-col gap-0.5"><span className="text-micro text-slate-500">Описание</span>
            <input value={e.description ?? ""} onChange={(ev) => set({ description: ev.target.value || null })} className={input} /></label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={e.is_active} onChange={(ev) => set({ is_active: ev.target.checked })} /> В продаже
          </label>
        </div>
        {error && <p className="text-xs text-red-400">{error}</p>}
        <div className="flex flex-wrap gap-2">
          <button onClick={() => save.mutate(e)} disabled={save.isPending || !e.name} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40">Сохранить</button>
          <button onClick={() => setEditing(null)} className="rounded-lg bg-white/5 px-3 py-1.5 text-xs">Назад</button>
          {e.id && (
            <span className="ml-auto flex items-center gap-1.5">
              <input value={grantUser} onChange={(ev) => setGrantUser(ev.target.value)} placeholder="ID игрока" className="w-24 rounded-lg bg-bg-base px-2 py-1.5 text-xs" />
              <button
                onClick={() => grant.mutate({ id: e.id!, userId: Number(grantUser) })}
                disabled={!Number(grantUser) || grant.isPending}
                className="rounded-lg bg-white/10 px-3 py-1.5 text-xs disabled:opacity-40"
              >
                Выдать
              </button>
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-slate-400">
        Активными у игрока могут быть не больше «слотов» (Настройки), по одной копии каждого артефакта — остальные стоят
        на полке. Бонусы суммируются до лимитов в Настройках.
      </p>
      <button onClick={() => setEditing({ ...NEW })} className="self-start rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg-base">
        + Новый артефакт
      </button>
      {data.artifacts.map((a) => (
        <button key={a.id} onClick={() => setEditing(a)} className={`flex items-center gap-3 rounded-xl bg-bg-surface p-2 text-left ${a.is_active ? "" : "opacity-50"}`}>
          <ArtifactTile size="sm" artifact={{ ...a, id: a.id!, image_path: a.image_path ?? null, target_label: "", effect_label: "",
            stadium_name: null, stadium_label: "", stadium_owned: false, active_label: "", left: null }} />
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-semibold">#{a.id} {a.name}</span>
            <span className="block text-micro text-slate-500">
              {data.targets[a.target]} · {a.effect === "none" ? "без эффекта" : data.effects[a.effect].replace("{v}", String(a.effect_value))}
              {" · "}{a.coins_price || "—"} мон. / {a.stars_price || "—"} ⭐ · продано {a.sold_count ?? 0}{a.max_supply ? ` из ${a.max_supply}` : ""}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}
