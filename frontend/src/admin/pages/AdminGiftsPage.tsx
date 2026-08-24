import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  createGiftSet,
  deleteGiftSet,
  deleteGiftSetImage,
  fetchAdminCardCollections,
  fetchAdminGiftSets,
  fetchAdminPacks,
  updateGiftSet,
  uploadGiftSetImage,
} from "@/admin/api";
import NumberInput from "@/components/common/NumberInput";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { showConfirm } from "@/lib/telegram";
import type { CardCollection } from "@/admin/types";
import type { GiftSet } from "@/types";

interface GiftSetForm {
  name: string;
  description: string;
  kind: "bundle" | "collectible";
  pack_id: number | null;
  coins_amount: number;
  stars_price: number;
  coins_price: number;
  max_supply: number;
  collection_id: number | null;
  is_active: boolean;
  sort_order: number;
}

function giftSetToForm(g?: GiftSet): GiftSetForm {
  return {
    name: g?.name ?? "",
    description: g?.description ?? "",
    kind: g?.kind ?? "bundle",
    pack_id: g?.pack_id ?? null,
    coins_amount: g?.coins_amount ?? 0,
    stars_price: g?.stars_price ?? 0,
    coins_price: g?.coins_price ?? 0,
    max_supply: g?.max_supply ?? 0,
    collection_id: g?.collection_id ?? null,
    is_active: g?.is_active ?? true,
    sort_order: g?.sort_order ?? 0,
  };
}

export default function AdminGiftsPage() {
  const queryClient = useQueryClient();
  const { data: giftSets, isLoading } = useQuery({ queryKey: ["admin-gift-sets"], queryFn: fetchAdminGiftSets });
  const { data: packs } = useQuery({ queryKey: ["admin-packs-for-gifts"], queryFn: fetchAdminPacks });
  const { data: collections } = useQuery({ queryKey: ["admin-card-collections-for-gifts"], queryFn: fetchAdminCardCollections });
  const [editing, setEditing] = useState<GiftSet | "new" | null>(null);
  const [form, setForm] = useState<GiftSetForm>(giftSetToForm());
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-gift-sets"] });

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = { ...form, max_supply: form.max_supply > 0 ? form.max_supply : null };
      return editing === "new" ? createGiftSet(payload) : updateGiftSet((editing as GiftSet).id, payload);
    },
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить набор"),
  });
  const deleteMutation = useMutation({ mutationFn: deleteGiftSet, onSuccess: invalidate });
  const uploadImageMutation = useMutation({
    mutationFn: (file: File) => uploadGiftSetImage((editing as GiftSet).id, file),
    onSuccess: (g) => { invalidate(); setEditing(g); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось загрузить изображение"),
  });
  const removeImageMutation = useMutation({
    mutationFn: () => deleteGiftSetImage((editing as GiftSet).id),
    onSuccess: (g) => { invalidate(); setEditing(g); },
  });

  const openEdit = (g: GiftSet) => { setEditing(g); setForm(giftSetToForm(g)); setError(null); };
  const openCreate = () => { setEditing("new"); setForm(giftSetToForm()); setError(null); };

  const confirmDelete = async (g: GiftSet) => {
    if (await showConfirm(`Удалить набор «${g.name}» навсегда?`)) {
      deleteMutation.mutate(g.id);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">Подарочные наборы</h1>
          <p className="text-xs text-slate-500">
            Каталог наборов (пак + монеты) для раздела «Подарки» в профиле. Отправка игрокам — там же.
          </p>
        </div>
        <button onClick={openCreate} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">+ Набор</button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {giftSets?.map((g) => (
          <div key={g.id} className="flex items-center justify-between rounded-xl border border-white/5 bg-bg-surface px-3 py-2">
            <div className="flex items-center gap-2">
              {g.image_path ? (
                <img src={staticUrl(g.image_path) ?? undefined} className="h-10 w-10 rounded-lg object-cover" />
              ) : (
                <span className="text-2xl">🎁</span>
              )}
              <div>
                <p className="text-sm font-semibold">{g.name}</p>
                <p className="text-[11px] text-slate-500">
                  <span className="rounded bg-white/10 px-1.5 py-0.5 font-semibold">
                    {g.kind === "collectible" ? "Коллекционный" : "Набор"}
                  </span>{" "}
                  {g.kind === "collectible"
                    ? `${g.stars_price} ⭐ · ${g.coins_price} монет`
                    : `${g.stars_price} ⭐ · ${g.coins_amount} монет${g.pack_id ? " · с паком" : ""}`}{" "}
                  · {g.is_active ? "Активен" : "Отключён"}
                  {g.kind === "collectible" && (
                    <> · Тираж: {g.next_serial_number - 1}/{g.max_supply ?? "∞"}</>
                  )}
                </p>
              </div>
            </div>
            <div className="flex gap-1">
              <button onClick={() => openEdit(g)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => confirmDelete(g)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
        {giftSets?.length === 0 && <p className="text-xs text-slate-500">Наборов пока нет.</p>}
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setEditing(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-bg-base p-5 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing === "new" ? "Новый набор" : "Редактировать набор"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Название</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Описание</span>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  rows={2}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                />
              </label>
              {editing === "new" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Тип подарка</span>
                  <div className="flex gap-2 rounded-lg bg-bg-surface p-1">
                    <button
                      type="button"
                      onClick={() => setForm({ ...form, kind: "bundle" })}
                      className={`flex-1 rounded-md py-1.5 text-xs font-semibold ${form.kind === "bundle" ? "bg-accent text-bg-base" : "text-slate-400"}`}
                    >
                      Набор
                    </button>
                    <button
                      type="button"
                      onClick={() => setForm({ ...form, kind: "collectible" })}
                      className={`flex-1 rounded-md py-1.5 text-xs font-semibold ${form.kind === "collectible" ? "bg-accent text-bg-base" : "text-slate-400"}`}
                    >
                      Коллекционный
                    </button>
                  </div>
                </label>
              )}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">
                  {form.kind === "bundle" ? "Пак в наборе (необязательно)" : "Пак-приз при получении (необязательно)"}
                </span>
                <select
                  value={form.pack_id ?? ""}
                  onChange={(e) => setForm({ ...form, pack_id: e.target.value ? Number(e.target.value) : null })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                >
                  <option value="">Без пака</option>
                  {packs?.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">
                  {form.kind === "bundle" ? "Монеты в наборе" : "Монеты-приз при получении"}
                </span>
                <NumberInput min={0} value={form.coins_amount} onChange={(v) => setForm({ ...form, coins_amount: v })} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Цена в ⭐ (для покупки игроками)</span>
                <NumberInput min={0} value={form.stars_price} onChange={(v) => setForm({ ...form, stars_price: v })} />
              </label>
              {form.kind === "collectible" && (
                <>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">Цена в монетах (для покупки игроками)</span>
                    <NumberInput min={0} value={form.coins_price} onChange={(v) => setForm({ ...form, coins_price: v })} />
                    <span className="text-[10px] text-slate-500">Нужна хотя бы одна цена — в ⭐ или в монетах.</span>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">Тираж (0 = без ограничения)</span>
                    <NumberInput min={0} value={form.max_supply} onChange={(v) => setForm({ ...form, max_supply: v })} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">Коллекция (необязательно)</span>
                    <select
                      value={form.collection_id ?? ""}
                      onChange={(e) => setForm({ ...form, collection_id: e.target.value ? Number(e.target.value) : null })}
                      className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                    >
                      <option value="">Без коллекции</option>
                      {collections?.map((c: CardCollection) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </label>
                </>
              )}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Порядок сортировки</span>
                <NumberInput value={form.sort_order} onChange={(v) => setForm({ ...form, sort_order: v })} />
              </label>
              <label className="mt-1 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен (доступен для покупки/выдачи)
              </label>

              {editing !== "new" && (
                <div className="mt-2 flex flex-col gap-2">
                  <span className="text-xs font-semibold text-slate-400">Картинка набора</span>
                  <div className="flex items-center gap-3">
                    {(editing as GiftSet).image_path ? (
                      <img
                        src={staticUrl((editing as GiftSet).image_path!) ?? undefined}
                        className="h-14 w-14 rounded-lg border border-white/10 object-cover"
                      />
                    ) : (
                      <span className="flex h-14 w-14 items-center justify-center rounded-lg bg-black/30 text-2xl">🎁</span>
                    )}
                    <div className="flex flex-col gap-1">
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploadImageMutation.isPending}
                        className="rounded-lg bg-white/5 px-2 py-1 text-[11px]"
                      >
                        {uploadImageMutation.isPending ? "Загрузка..." : "Загрузить"}
                      </button>
                      {(editing as GiftSet).image_path && (
                        <button onClick={() => removeImageMutation.mutate()} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">
                          Удалить картинку
                        </button>
                      )}
                    </div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/gif"
                      className="hidden"
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadImageMutation.mutate(f); }}
                    />
                  </div>
                </div>
              )}
            </div>
            <div className="mt-4 flex gap-2">
              <button onClick={() => setEditing(null)} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm">Отмена</button>
              <button onClick={() => saveMutation.mutate()} className="flex-1 rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base">
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
