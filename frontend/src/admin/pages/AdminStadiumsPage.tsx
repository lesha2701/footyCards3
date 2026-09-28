import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  createStadium, deleteStadium, deleteStadiumImage, fetchAdminStadiums,
  toggleStadiumActive, toggleStadiumPackDroppable, updateStadium, uploadStadiumImage,
} from "@/admin/api";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { RARITY_LABELS } from "@/lib/rarity";
import type { Rarity, Stadium } from "@/types";

const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];

const emptyForm = {
  display_name: "", rarity: "common" as Rarity, quick_sell_price: 10, is_active: true, is_pack_droppable: true,
  boost_pct: 0,
};

export default function AdminStadiumsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Stadium | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery({ queryKey: ["admin-stadiums", search, page], queryFn: () => fetchAdminStadiums(search, page) });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-stadiums"] });

  const createMutation = useMutation({
    mutationFn: () => createStadium(form),
    onSuccess: () => { invalidate(); setCreating(false); setForm(emptyForm); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Ошибка"),
  });
  const updateMutation = useMutation({
    mutationFn: () => updateStadium(editing!.id, form),
    onSuccess: () => { invalidate(); setEditing(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Ошибка"),
  });
  const toggleMutation = useMutation({ mutationFn: toggleStadiumActive, onSuccess: invalidate });
  const toggleDroppableMutation = useMutation({ mutationFn: toggleStadiumPackDroppable, onSuccess: invalidate });
  const deleteMutation = useMutation({
    mutationFn: deleteStadium, onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить"),
  });
  const uploadImageMutation = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => uploadStadiumImage(id, file), onSuccess: invalidate,
  });
  const deleteImageMutation = useMutation({ mutationFn: deleteStadiumImage, onSuccess: invalidate });

  const openEdit = (s: Stadium) => {
    setEditing(s);
    setForm({
      display_name: s.display_name, rarity: s.rarity, quick_sell_price: s.quick_sell_price,
      is_active: s.is_active, is_pack_droppable: s.is_pack_droppable,
      boost_pct: s.boost_pct,
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-display text-2xl font-bold">Стадионы</h1>
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
              <th className="px-3 py-2">Бонус</th>
              <th className="px-3 py-2">Активен</th>
              <th className="px-3 py-2">В паках</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((s) => (
              <tr key={s.id} className="border-t border-white/5">
                <td className="px-3 py-2">
                  <img src={staticUrl(s.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")} className="h-10 w-10 rounded-lg object-cover" />
                </td>
                <td className="px-3 py-2">{s.display_name}</td>
                <td className="px-3 py-2">{RARITY_LABELS[s.rarity]}</td>
                <td className="px-3 py-2 text-xs text-slate-400">+{Math.round(s.boost_pct * 100)}%</td>
                <td className="px-3 py-2">{s.is_active ? "✅" : "🚫"}</td>
                <td className="px-3 py-2">{s.is_pack_droppable ? "✅" : "🚫"}</td>
                <td className="px-3 py-2">
                  <div className="flex gap-1">
                    <button onClick={() => openEdit(s)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">✏️</button>
                    <button onClick={() => toggleMutation.mutate(s.id)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">
                      {s.is_active ? "🚫" : "✅"}
                    </button>
                    <button onClick={() => toggleDroppableMutation.mutate(s.id)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">
                      {s.is_pack_droppable ? "📦🚫" : "📦"}
                    </button>
                    <button onClick={() => deleteMutation.mutate(s.id)} className="rounded-lg bg-red-500/70 px-2 py-1 text-xs">🗑️</button>
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
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать стадион" : "Новый стадион"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Имя</span>
                <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Редкость</span>
                <select value={form.rarity} onChange={(e) => setForm({ ...form, rarity: e.target.value as Rarity })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none">
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
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Бонус к силе состава (0-1, напр. 0.05 = +5%)</span>
                <input
                  type="number" min={0} max={1} step="0.01" value={form.boost_pct}
                  onChange={(e) => setForm({ ...form, boost_pct: Number(e.target.value) })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                />
              </label>

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
