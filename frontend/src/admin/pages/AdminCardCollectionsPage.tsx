import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  createCardCollection,
  fetchAdminCardCollections,
  fetchAdminPacks,
  fetchAdminPlayers,
  fetchCardCollectionPlayers,
  setCardCollectionPlayers,
  toggleCardCollectionActive,
  updateCardCollection,
  uploadCardCollectionImage,
} from "@/admin/api";
import type { CardCollection } from "@/admin/types";
import NumberInput from "@/components/common/NumberInput";
import { ApiRequestError, staticUrl } from "@/lib/api";
import type { Player } from "@/types";

interface CollectionForm {
  name: string;
  description: string;
  sort_order: number;
  is_active: boolean;
  image_path: string | null;
  reward_coins: number;
  reward_pack_id: number | "";
}

function collectionToForm(c?: CardCollection): CollectionForm {
  return {
    name: c?.name ?? "",
    description: c?.description ?? "",
    sort_order: c?.sort_order ?? 0,
    is_active: c?.is_active ?? true,
    image_path: c?.image_path ?? null,
    reward_coins: c?.reward_coins ?? 0,
    reward_pack_id: c?.reward_pack_id ?? "",
  };
}

export default function AdminCardCollectionsPage() {
  const queryClient = useQueryClient();
  const { data: collections, isLoading } = useQuery({ queryKey: ["admin-card-collections"], queryFn: fetchAdminCardCollections });
  const { data: packs } = useQuery({ queryKey: ["admin-packs"], queryFn: fetchAdminPacks });
  const [editing, setEditing] = useState<CardCollection | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<CollectionForm>(collectionToForm());
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-card-collections"] });
  const toggleMutation = useMutation({ mutationFn: toggleCardCollectionActive, onSuccess: invalidate });

  const buildPayload = () => ({
    name: form.name,
    description: form.description,
    sort_order: form.sort_order,
    is_active: form.is_active,
    reward_coins: form.reward_coins,
    reward_pack_id: form.reward_pack_id === "" ? null : form.reward_pack_id,
  });

  const createMutation = useMutation({
    mutationFn: () => createCardCollection(buildPayload()),
    onSuccess: () => { invalidate(); setCreating(false); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось создать коллекцию"),
  });
  const updateMutation = useMutation({
    mutationFn: () => updateCardCollection(editing!.id, buildPayload()),
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить изменения"),
  });
  const uploadImageMutation = useMutation({
    mutationFn: (file: File) => uploadCardCollectionImage(editing!.id, file),
    onSuccess: (c) => { invalidate(); setForm((f) => ({ ...f, image_path: c.image_path })); },
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
          <div key={c.id} className="flex gap-3 rounded-2xl border border-white/5 bg-bg-surface p-3">
            {c.image_path && (
              <img src={staticUrl(c.image_path) ?? undefined} className="h-16 w-16 shrink-0 rounded-xl object-cover" />
            )}
            <div className="min-w-0 flex-1">
              <p className="font-display text-sm font-bold">{c.name}</p>
              <p className="text-xs text-slate-400">{c.description}</p>
              <p className="text-xs text-slate-500">{c.is_active ? "Активна (карты выпадают)" : "Отключена (не выпадает)"}</p>
              <p className="text-[11px] text-slate-500">
                Награда: {c.reward_coins} монет{c.reward_pack_id ? ` + пак #${c.reward_pack_id}` : ""}
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                <button onClick={() => openEdit(c)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
                <button onClick={() => toggleMutation.mutate(c.id)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">
                  {c.is_active ? "Отключить" : "Включить"}
                </button>
              </div>
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

              <div className="mt-2 flex flex-col gap-2">
                <span className="text-xs font-semibold text-slate-400">Обложка коллекции</span>
                <div className="flex items-center gap-3">
                  {form.image_path && (
                    <img src={staticUrl(form.image_path) ?? undefined} className="h-20 w-16 rounded-lg border border-white/10 object-cover" />
                  )}
                  {editing && (
                    <div className="flex flex-col gap-1">
                      <button type="button" onClick={() => fileInputRef.current?.click()} className="rounded-lg bg-white/5 px-3 py-1.5 text-xs">
                        Загрузить изображение
                      </button>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".png,.jpg,.jpeg,.webp"
                        className="hidden"
                        onChange={(e) => e.target.files?.[0] && uploadImageMutation.mutate(e.target.files[0])}
                      />
                    </div>
                  )}
                </div>
                {!editing && <span className="text-[11px] text-slate-500">Обложку можно загрузить после создания коллекции.</span>}
              </div>

              <label className="mt-2 flex flex-col gap-1">
                <span className="text-xs text-slate-400">Награда за сбор коллекции, монеты</span>
                <NumberInput value={form.reward_coins} onChange={(v) => setForm({ ...form, reward_coins: v })} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Бонусный пак (необязательно)</span>
                <select
                  value={form.reward_pack_id}
                  onChange={(e) => setForm({ ...form, reward_pack_id: e.target.value ? Number(e.target.value) : "" })}
                  className="rounded-lg bg-bg-surface px-3 py-2 text-sm outline-none"
                >
                  <option value="">Нет</option>
                  {packs?.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </label>
            </div>

            {editing && <CollectionPlayersPanel collectionId={editing.id} />}

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

function CollectionPlayersPanel({ collectionId }: { collectionId: number }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");

  const { data: members } = useQuery({
    queryKey: ["card-collection-players", collectionId],
    queryFn: () => fetchCardCollectionPlayers(collectionId),
  });
  const { data: searchResults } = useQuery({
    queryKey: ["admin-players-search-for-collection", search],
    queryFn: () => fetchAdminPlayers(search, 1),
    enabled: search.length > 0,
  });

  const saveMutation = useMutation({
    mutationFn: (playerIds: number[]) => setCardCollectionPlayers(collectionId, playerIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["card-collection-players", collectionId] });
      queryClient.invalidateQueries({ queryKey: ["admin-card-collections"] });
    },
  });

  const memberIds = new Set((members ?? []).map((p) => p.id));

  const toggle = (player: Player) => {
    const next = new Set(memberIds);
    if (next.has(player.id)) next.delete(player.id);
    else next.add(player.id);
    saveMutation.mutate(Array.from(next));
  };

  // The current members list plus any search results not already shown, so
  // toggling a player off doesn't make them disappear mid-click.
  const shown = [...(members ?? [])];
  for (const p of searchResults?.items ?? []) {
    if (!shown.some((m) => m.id === p.id)) shown.push(p);
  }

  return (
    <div className="mt-4 border-t border-white/10 pt-4">
      <p className="mb-2 text-xs font-semibold text-slate-400">
        Игроки в коллекции ({members?.length ?? 0})
      </p>
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Найти игрока, чтобы добавить..."
        className="mb-2 w-full rounded-lg bg-bg-surface px-3 py-2 text-sm outline-none"
      />
      <div className="max-h-48 overflow-y-auto rounded-lg border border-white/5">
        {shown.length === 0 && <p className="p-3 text-xs text-slate-500">Пока пусто — найди игроков через поиск выше.</p>}
        {shown.map((p) => (
          <label key={p.id} className="flex items-center gap-2 border-b border-white/5 px-3 py-2 text-xs last:border-b-0">
            <input type="checkbox" checked={memberIds.has(p.id)} onChange={() => toggle(p)} disabled={saveMutation.isPending} />
            <span className="flex-1">{p.display_name}</span>
            <span className="text-slate-500">{p.position} · {p.rating}</span>
            {p.collection_id !== null && p.collection_id !== collectionId && (
              <span className="text-amber-400">др. коллекция</span>
            )}
          </label>
        ))}
      </div>
    </div>
  );
}
