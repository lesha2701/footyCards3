import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { createClubPack, deleteClubPack, fetchAdminClubPacks, toggleClubPackActive, updateClubPack, uploadClubPackImage } from "@/admin/api";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { showConfirm } from "@/lib/telegram";
import type { ClubPack } from "@/types";

type Rarity = "common" | "rare" | "epic" | "legendary" | "diamond";
const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary", "diamond"];

interface ClubPackForm {
  slug: string;
  name: string;
  description: string;
  price: number;
  card_count: number;
  guaranteed_min_rarity: Rarity | "";
  probabilities: Record<Rarity, number>;
  is_active: boolean;
  image_path: string | null;
}

function packToForm(p?: ClubPack): ClubPackForm {
  const probabilities = { common: 0, rare: 0, epic: 0, legendary: 0, diamond: 0 } as Record<Rarity, number>;
  for (const rp of p?.rarity_probabilities ?? []) probabilities[rp.rarity as Rarity] = rp.probability * 100;
  return {
    slug: p?.slug ?? "", name: p?.name ?? "", description: p?.description ?? "",
    price: p?.price ?? 100, card_count: p?.card_count ?? 3,
    guaranteed_min_rarity: (p?.guaranteed_min_rarity as Rarity) ?? "",
    probabilities, is_active: p?.is_active ?? true, image_path: p?.image_path ?? null,
  };
}

export default function AdminClubPacksPage() {
  const queryClient = useQueryClient();
  const { data: packs, isLoading } = useQuery({ queryKey: ["admin-club-packs"], queryFn: fetchAdminClubPacks });
  const [editing, setEditing] = useState<ClubPack | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<ClubPackForm>(packToForm());
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-club-packs"] });
  const toggleMutation = useMutation({
    mutationFn: toggleClubPackActive,
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось изменить статус пака"),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteClubPack,
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить пак"),
  });

  const confirmDelete = async (p: ClubPack) => {
    if (await showConfirm(`Удалить пак «${p.name}» навсегда? Это действие необратимо.`)) {
      deleteMutation.mutate(p.id);
    }
  };

  const probabilitySum = RARITIES.reduce((sum, r) => sum + (form.probabilities[r] || 0), 0);
  const probabilitiesValid = Math.abs(probabilitySum - 100) < 2;

  const buildPayload = () => ({
    slug: form.slug, name: form.name, description: form.description, price: form.price, card_count: form.card_count,
    guaranteed_min_rarity: form.guaranteed_min_rarity || null,
    rarity_probabilities: RARITIES.filter((r) => form.probabilities[r] > 0).map((r) => ({ rarity: r, probability: form.probabilities[r] / 100 })),
    is_active: form.is_active,
  });

  const createMutation = useMutation({
    mutationFn: () => createClubPack(buildPayload()),
    onSuccess: () => { invalidate(); setCreating(false); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось создать пак"),
  });
  const updateMutation = useMutation({
    mutationFn: () => updateClubPack(editing!.id, buildPayload()),
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось обновить пак"),
  });
  const uploadImageMutation = useMutation({
    mutationFn: (file: File) => uploadClubPackImage(editing!.id, file),
    onSuccess: (p) => { invalidate(); setForm((f) => ({ ...f, image_path: p.image_path })); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось загрузить изображение"),
  });

  const openEdit = (p: ClubPack) => { setEditing(p); setForm(packToForm(p)); setError(null); };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Клубные паки</h1>
        <button onClick={() => { setCreating(true); setForm(packToForm()); setError(null); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">+ Новый пак</button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {packs?.map((p) => (
          <div key={p.id} className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="flex items-center gap-3">
              <img src={staticUrl(p.image_path ?? undefined) ?? staticUrl("packs/basic.webp")} className="h-12 w-12 rounded-lg object-cover" />
              <div className="flex-1">
                <p className="font-display text-sm font-bold">{p.name}</p>
                <p className="text-xs text-slate-400">{p.card_count} карточки · 🪙 {p.price}</p>
              </div>
            </div>
            <p className="mt-1 text-xs text-slate-500">{p.is_active ? "Активен" : "Отключён"}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              <button onClick={() => openEdit(p)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => toggleMutation.mutate(p.id)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">{p.is_active ? "Отключить" : "Включить"}</button>
              <button onClick={() => confirmDelete(p)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
      </div>

      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => { setCreating(false); setEditing(null); }}>
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать клубный пак" : "Новый клубный пак"}</p>
            <div className="flex flex-col gap-2 text-sm">
              {editing && (
                <div className="flex items-center gap-3">
                  <img src={staticUrl(form.image_path ?? undefined) ?? staticUrl("packs/basic.webp")} className="h-16 w-16 rounded-lg object-cover" />
                  <div className="flex flex-col gap-1">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploadImageMutation.isPending}
                      className="rounded-lg bg-white/5 px-3 py-1.5 text-xs disabled:opacity-40"
                    >
                      {uploadImageMutation.isPending ? "Загрузка..." : "Загрузить изображение"}
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".png,.jpg,.jpeg,.webp"
                      className="hidden"
                      onChange={(e) => e.target.files?.[0] && uploadImageMutation.mutate(e.target.files[0])}
                    />
                  </div>
                </div>
              )}
              {!editing && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Slug</span>
                  <input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
                </label>
              )}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Название</span>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Описание</span>
                <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Цена (бюджет клуба)</span>
                  <input type="number" value={form.price} onChange={(e) => setForm({ ...form, price: Number(e.target.value) })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Карточек в паке</span>
                  <input type="number" value={form.card_count} onChange={(e) => setForm({ ...form, card_count: Number(e.target.value) })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
                </label>
              </div>
              <p className="mt-2 text-xs text-slate-400">Вероятности редкости (сумма ≈ 100%): {probabilitySum.toFixed(1)}%</p>
              <div className="grid grid-cols-2 gap-2">
                {RARITIES.map((r) => (
                  <label key={r} className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">{r}</span>
                    <input
                      type="number" value={form.probabilities[r]}
                      onChange={(e) => setForm({ ...form, probabilities: { ...form.probabilities, [r]: Number(e.target.value) } })}
                      className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                    />
                  </label>
                ))}
              </div>
              <label className="mt-1 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен
              </label>
            </div>
            {error && <p className="mt-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="mt-4 flex gap-2">
              <button onClick={() => { setCreating(false); setEditing(null); }} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm">Отмена</button>
              <button
                onClick={() => (editing ? updateMutation.mutate() : createMutation.mutate())}
                disabled={!probabilitiesValid || !form.slug.trim() && !editing || !form.name.trim()}
                className="flex-1 rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
              >
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
