import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  createCoach, deleteCoach, deleteCoachImage, fetchAdminCoaches,
  toggleCoachActive, toggleCoachPackDroppable, updateCoach, uploadCoachImage,
} from "@/admin/api";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { BOOST_TYPES, BOOST_TYPE_LABELS, BOOST_TYPE_UNIT_HINTS } from "@/lib/coaches";
import { RARITY_LABELS } from "@/lib/rarity";
import type { Coach, CoachBoostType, Rarity } from "@/types";

const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];

const BOOST_SLOTS_BY_RARITY: Record<Rarity, number> = {
  common: 1, rare: 1, epic: 2, legendary: 3, diamond: 0,
};

type BoostFormRow = { boost_type: CoachBoostType; magnitude: number };

const emptyForm = {
  display_name: "", rarity: "common" as Rarity, quick_sell_price: 10, is_active: true, is_pack_droppable: true,
  boosts: [{ boost_type: "attack_central" as CoachBoostType, magnitude: 2 }] as BoostFormRow[],
};

export default function AdminCoachesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Coach | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery({ queryKey: ["admin-coaches", search, page], queryFn: () => fetchAdminCoaches(search, page) });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-coaches"] });

  const createMutation = useMutation({
    mutationFn: () => createCoach(form),
    onSuccess: () => { invalidate(); setCreating(false); setForm(emptyForm); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Ошибка"),
  });
  const updateMutation = useMutation({
    mutationFn: () => updateCoach(editing!.id, form),
    onSuccess: () => { invalidate(); setEditing(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Ошибка"),
  });
  const toggleMutation = useMutation({ mutationFn: toggleCoachActive, onSuccess: invalidate });
  const toggleDroppableMutation = useMutation({ mutationFn: toggleCoachPackDroppable, onSuccess: invalidate });
  const deleteMutation = useMutation({
    mutationFn: deleteCoach, onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить"),
  });
  const uploadImageMutation = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => uploadCoachImage(id, file), onSuccess: invalidate,
  });
  const deleteImageMutation = useMutation({ mutationFn: deleteCoachImage, onSuccess: invalidate });

  const openEdit = (c: Coach) => {
    setEditing(c);
    setForm({
      display_name: c.display_name, rarity: c.rarity, quick_sell_price: c.quick_sell_price,
      is_active: c.is_active, is_pack_droppable: c.is_pack_droppable,
      boosts: c.boosts.map((b) => ({ boost_type: b.boost_type, magnitude: b.magnitude })),
    });
  };

  const slotsForRarity = BOOST_SLOTS_BY_RARITY[form.rarity];
  const boostsValid = form.boosts.length === slotsForRarity && new Set(form.boosts.map((b) => b.boost_type)).size === form.boosts.length;

  const setRarity = (rarity: Rarity) => {
    const slots = BOOST_SLOTS_BY_RARITY[rarity];
    const boosts = form.boosts.slice(0, slots);
    while (boosts.length < slots) {
      const unused = BOOST_TYPES.find((t) => !boosts.some((b) => b.boost_type === t)) ?? BOOST_TYPES[0];
      boosts.push({ boost_type: unused, magnitude: 2 });
    }
    setForm({ ...form, rarity, boosts });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-display text-2xl font-bold">Тренеры</h1>
        <button onClick={() => { setCreating(true); setForm(emptyForm); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">
          + Добавить
        </button>
      </div>

      <input
        value={search}
        onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        placeholder="Поиск по имени..."
        className="max-w-sm rounded-xl bg-bg-surface px-4 py-2.5 text-sm outline-none"
      />

      <div className="overflow-x-auto rounded-2xl border border-white/5">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-bg-surface text-left text-xs text-slate-400">
            <tr>
              <th className="px-3 py-2" />
              <th className="px-3 py-2">Имя</th>
              <th className="px-3 py-2">Редкость</th>
              <th className="px-3 py-2">Усиления</th>
              <th className="px-3 py-2">Активен</th>
              <th className="px-3 py-2">В паках</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id} className="border-t border-white/5">
                <td className="px-3 py-2">
                  <img src={staticUrl(c.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")} className="h-10 w-10 rounded-lg object-cover" />
                </td>
                <td className="px-3 py-2">{c.display_name}</td>
                <td className="px-3 py-2">{RARITY_LABELS[c.rarity]}</td>
                <td className="px-3 py-2 text-xs text-slate-400">{c.boosts.map((b) => BOOST_TYPE_LABELS[b.boost_type]).join(", ")}</td>
                <td className="px-3 py-2">{c.is_active ? "✅" : "🚫"}</td>
                <td className="px-3 py-2">{c.is_pack_droppable ? "✅" : "🚫"}</td>
                <td className="px-3 py-2">
                  <div className="flex gap-1">
                    <button onClick={() => openEdit(c)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">✏️</button>
                    <button onClick={() => toggleMutation.mutate(c.id)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">
                      {c.is_active ? "🚫" : "✅"}
                    </button>
                    <button onClick={() => toggleDroppableMutation.mutate(c.id)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">
                      {c.is_pack_droppable ? "📦🚫" : "📦"}
                    </button>
                    <button onClick={() => deleteMutation.mutate(c.id)} className="rounded-lg bg-red-500/70 px-2 py-1 text-xs">🗑️</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <p className="p-4 text-sm text-slate-400">Загрузка...</p>}
      </div>

      {data && data.pages > 1 && (
        <div className="flex gap-2">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">←</button>
          <span className="text-sm text-slate-400">{page} / {data.pages}</span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">→</button>
        </div>
      )}

      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => { setCreating(false); setEditing(null); }}>
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать тренера" : "Новый тренер"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Имя</span>
                <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Редкость</span>
                <select value={form.rarity} onChange={(e) => setRarity(e.target.value as Rarity)} className="rounded-lg bg-bg-surface px-3 py-2 outline-none">
                  {RARITIES.map((r) => <option key={r} value={r}>{RARITY_LABELS[r]}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Цена продажи</span>
                <input
                  type="number" min={0} value={form.quick_sell_price}
                  onChange={(e) => setForm({ ...form, quick_sell_price: Number(e.target.value) })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                />
              </label>

              <p className="mt-2 text-xs font-semibold text-slate-300">Усиления ({slotsForRarity} для этой редкости)</p>
              {form.boosts.map((boost, i) => (
                <div key={i} className="grid grid-cols-2 gap-2">
                  <select
                    value={boost.boost_type}
                    onChange={(e) => {
                      const boosts = [...form.boosts];
                      boosts[i] = { ...boosts[i], boost_type: e.target.value as CoachBoostType };
                      setForm({ ...form, boosts });
                    }}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  >
                    {BOOST_TYPES.map((t) => <option key={t} value={t}>{BOOST_TYPE_LABELS[t]}</option>)}
                  </select>
                  <input
                    type="number" step="0.1" value={boost.magnitude}
                    onChange={(e) => {
                      const boosts = [...form.boosts];
                      boosts[i] = { ...boosts[i], magnitude: Number(e.target.value) };
                      setForm({ ...form, boosts });
                    }}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  />
                  {BOOST_TYPE_UNIT_HINTS[boost.boost_type] && (
                    <p className="col-span-2 text-[10px] text-amber-400">{BOOST_TYPE_UNIT_HINTS[boost.boost_type]}</p>
                  )}
                </div>
              ))}
              {!boostsValid && (
                <p className="text-[11px] text-red-400">
                  Нужно ровно {slotsForRarity} усилени{slotsForRarity === 1 ? "е" : "я"}, все разных типов.
                </p>
              )}

              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input type="checkbox" checked={form.is_pack_droppable} onChange={(e) => setForm({ ...form, is_pack_droppable: e.target.checked })} />
                Может выпасть из пака
              </label>

              {editing && (
                <div className="mt-2 flex items-center gap-2">
                  <img src={staticUrl(editing.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")} className="h-14 w-14 rounded-lg object-cover" />
                  <button onClick={() => fileInputRef.current?.click()} className="rounded-lg bg-white/5 px-3 py-1.5 text-xs">Загрузить фото</button>
                  <input
                    ref={fileInputRef} type="file" accept=".png,.jpg,.jpeg,.webp" className="hidden"
                    onChange={(e) => e.target.files?.[0] && uploadImageMutation.mutate({ id: editing.id, file: e.target.files[0] })}
                  />
                  {editing.image_path && (
                    <button onClick={() => deleteImageMutation.mutate(editing.id)} className="rounded-lg bg-red-500/70 px-3 py-1.5 text-xs">Удалить фото</button>
                  )}
                </div>
              )}
            </div>

            <div className="mt-4 flex gap-2">
              <button onClick={() => { setCreating(false); setEditing(null); setError(null); }} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm">Отмена</button>
              <button
                disabled={!boostsValid}
                onClick={() => (editing ? updateMutation.mutate() : createMutation.mutate())}
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
