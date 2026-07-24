import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createCardCollection, fetchAdminCardCollections, toggleCardCollectionActive, updateCardCollection } from "@/admin/api";
import type { CardCollection } from "@/admin/types";
import NumberInput from "@/components/common/NumberInput";
import { ApiRequestError } from "@/lib/api";

interface CollectionForm {
  name: string;
  description: string;
  sort_order: number;
  is_active: boolean;
}

function collectionToForm(c?: CardCollection): CollectionForm {
  return {
    name: c?.name ?? "",
    description: c?.description ?? "",
    sort_order: c?.sort_order ?? 0,
    is_active: c?.is_active ?? true,
  };
}

export default function AdminCardCollectionsPage() {
  const queryClient = useQueryClient();
  const { data: collections, isLoading } = useQuery({ queryKey: ["admin-card-collections"], queryFn: fetchAdminCardCollections });
  const [editing, setEditing] = useState<CardCollection | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<CollectionForm>(collectionToForm());
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-card-collections"] });
  const toggleMutation = useMutation({ mutationFn: toggleCardCollectionActive, onSuccess: invalidate });

  const createMutation = useMutation({
    mutationFn: () => createCardCollection({ ...form }),
    onSuccess: () => { invalidate(); setCreating(false); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось создать коллекцию"),
  });
  const updateMutation = useMutation({
    mutationFn: () => updateCardCollection(editing!.id, { ...form }),
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить изменения"),
  });

  const openEdit = (c: CardCollection) => { setEditing(c); setForm(collectionToForm(c)); setError(null); };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Коллекции карт</h1>
        <button onClick={() => { setCreating(true); setForm(collectionToForm()); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">
          + Новая коллекция
        </button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {collections?.map((c) => (
          <div key={c.id} className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <p className="font-display text-sm font-bold">{c.name}</p>
            <p className="text-xs text-slate-400">{c.description}</p>
            <p className="text-xs text-slate-500">{c.is_active ? "Активна (карты выпадают)" : "Отключена (не выпадает)"}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              <button onClick={() => openEdit(c)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => toggleMutation.mutate(c.id)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">
                {c.is_active ? "Отключить" : "Включить"}
              </button>
            </div>
          </div>
        ))}
      </div>

      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => { setCreating(false); setEditing(null); }}>
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать коллекцию" : "Новая коллекция"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              <Field label="Название" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
              <Field label="Описание" value={form.description} onChange={(v) => setForm({ ...form, description: v })} />
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Порядок сортировки</span>
                <NumberInput value={form.sort_order} onChange={(v) => setForm({ ...form, sort_order: v })} />
                <span className="text-[11px] text-slate-500">Определяет только порядок показа коллекций в списке (по возрастанию). На вероятность выпадения карт не влияет.</span>
              </label>
              <label className="mt-1 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активна (карты этой коллекции выпадают из паков)
              </label>
            </div>

            <div className="mt-4 flex gap-2">
              <button onClick={() => { setCreating(false); setEditing(null); setError(null); }} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm">Отмена</button>
              <button
                onClick={() => (editing ? updateMutation.mutate() : createMutation.mutate())}
                className="flex-1 rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base"
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

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
    </label>
  );
}
