import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createClubCoachPack, deleteClubCoachPack, fetchAdminClubCoachPacks, updateClubCoachPack, type ClubCoachPackAdmin } from "@/admin/api";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { showConfirm } from "@/lib/telegram";

// No "diamond" — Coach carries a DB check constraint against it
// (ck_coaches_rarity_not_diamond), unlike player cards. A pack that could
// roll "diamond" would silently violate its own advertised odds, since
// pick_random_coach can never find one and falls through to any rarity.
type Rarity = "common" | "rare" | "epic" | "legendary";
const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];

interface ClubCoachPackForm {
  slug: string;
  name: string;
  description: string;
  price: number;
  card_count: number;
  guaranteed_min_rarity: Rarity | "";
  probabilities: Record<Rarity, number>;
  is_active: boolean;
  sort_order: number;
}

function packToForm(p?: ClubCoachPackAdmin): ClubCoachPackForm {
  const probabilities = { common: 0, rare: 0, epic: 0, legendary: 0 } as Record<Rarity, number>;
  for (const rp of p?.rarity_probabilities ?? []) probabilities[rp.rarity as Rarity] = rp.probability * 100;
  return {
    slug: p?.slug ?? "", name: p?.name ?? "", description: p?.description ?? "",
    price: p?.price ?? 100, card_count: p?.card_count ?? 3,
    guaranteed_min_rarity: (p?.guaranteed_min_rarity as Rarity) ?? "",
    probabilities, is_active: p?.is_active ?? true, sort_order: p?.sort_order ?? 0,
  };
}

export default function AdminClubCoachPacksPage() {
  const queryClient = useQueryClient();
  const { data: packs, isLoading } = useQuery({ queryKey: ["admin-club-coach-packs"], queryFn: fetchAdminClubCoachPacks });
  const [editing, setEditing] = useState<ClubCoachPackAdmin | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<ClubCoachPackForm>(packToForm());
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-club-coach-packs"] });
  const deleteMutation = useMutation({
    mutationFn: deleteClubCoachPack,
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить пак"),
  });

  const confirmDelete = async (p: ClubCoachPackAdmin) => {
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
    sort_order: form.sort_order,
  });

  const createMutation = useMutation({
    mutationFn: () => createClubCoachPack(buildPayload()),
    onSuccess: () => { invalidate(); setCreating(false); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось создать пак"),
  });
  const updateMutation = useMutation({
    mutationFn: () => updateClubCoachPack(editing!.id, buildPayload()),
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось обновить пак"),
  });

  const openEdit = (p: ClubCoachPackAdmin) => { setEditing(p); setForm(packToForm(p)); setError(null); };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Клубные паки тренеров</h1>
        <button onClick={() => { setCreating(true); setForm(packToForm()); setError(null); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">+ Новый пак</button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {packs?.map((p) => (
          <div key={p.id} className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="flex items-center gap-3">
              <img src={staticUrl(p.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")} className="h-12 w-12 rounded-lg object-cover" />
              <div className="flex-1">
                <p className="font-display text-sm font-bold">{p.name}</p>
                <p className="text-xs text-slate-400">{p.card_count} карточки · 🪙 {p.price}</p>
              </div>
            </div>
            <p className="mt-1 text-xs text-slate-500">{p.is_active ? "Активен" : "Отключён"} · порядок {p.sort_order}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              <button onClick={() => openEdit(p)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => confirmDelete(p)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
      </div>

      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => { setCreating(false); setEditing(null); }}>
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать пак тренеров" : "Новый пак тренеров"}</p>
            <div className="flex flex-col gap-2 text-sm">
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
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Мин. гарантированная редкость</span>
                  <select
                    value={form.guaranteed_min_rarity}
                    onChange={(e) => setForm({ ...form, guaranteed_min_rarity: e.target.value as Rarity | "" })}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  >
                    <option value="">Нет</option>
                    {RARITIES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Порядок сортировки</span>
                  <input type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
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
                disabled={!probabilitiesValid || (!form.slug.trim() && !editing) || !form.name.trim()}
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
