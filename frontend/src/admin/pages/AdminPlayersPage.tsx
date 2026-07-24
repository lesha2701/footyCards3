import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  createPlayer,
  deletePlayer,
  deletePlayerImage,
  exportPlayersCsv,
  fetchAdminCardCollections,
  fetchAdminPlayers,
  importPlayersCsv,
  togglePlayerActive,
  updatePlayer,
  uploadPlayerImage,
} from "@/admin/api";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { RARITY_LABELS } from "@/lib/rarity";
import type { Player, Position, Rarity } from "@/types";

const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];
const POSITIONS: Position[] = ["GK", "LB", "CB", "RB", "CDM", "CM", "CAM", "LM", "RM", "LW", "RW", "ST"];

const emptyForm = {
  first_name: "", last_name: "", display_name: "", rating: 70, rarity: "common" as Rarity,
  country: "", club: "", position: "ST" as Position, quick_sell_price: 10, is_active: true,
  collection_id: "" as number | "",
};

export default function AdminPlayersPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Player | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery({ queryKey: ["admin-players", search, page], queryFn: () => fetchAdminPlayers(search, page) });
  const { data: collections } = useQuery({ queryKey: ["admin-card-collections"], queryFn: fetchAdminCardCollections });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-players"] });

  const buildPayload = () => ({ ...form, collection_id: form.collection_id === "" ? null : form.collection_id });

  const createMutation = useMutation({
    mutationFn: () => createPlayer(buildPayload()),
    onSuccess: () => { invalidate(); setCreating(false); setForm(emptyForm); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Ошибка"),
  });
  const updateMutation = useMutation({
    mutationFn: () => updatePlayer(editing!.id, buildPayload()),
    onSuccess: () => { invalidate(); setEditing(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Ошибка"),
  });
  const toggleMutation = useMutation({ mutationFn: togglePlayerActive, onSuccess: invalidate });
  const deleteMutation = useMutation({
    mutationFn: deletePlayer,
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить"),
  });
  const uploadImageMutation = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => uploadPlayerImage(id, file),
    onSuccess: invalidate,
  });
  const deleteImageMutation = useMutation({ mutationFn: deletePlayerImage, onSuccess: invalidate });
  const importMutation = useMutation({
    mutationFn: importPlayersCsv,
    onSuccess: (res) => { setImportResult(`Создано: ${res.created}, обновлено: ${res.updated}, ошибок: ${res.errors.length}`); invalidate(); },
  });

  const openEdit = (p: Player) => {
    setEditing(p);
    setForm({
      first_name: p.first_name, last_name: p.last_name, display_name: p.display_name, rating: p.rating,
      rarity: p.rarity, country: p.country, club: p.club, position: p.position,
      quick_sell_price: p.quick_sell_price, is_active: p.is_active,
      collection_id: p.collection_id ?? "",
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-display text-2xl font-bold">Футболисты</h1>
        <div className="flex gap-2">
          <button
            onClick={async () => { const csv = await exportPlayersCsv(); downloadCsv(csv); }}
            className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold"
          >
            Экспорт CSV
          </button>
          <button onClick={() => csvInputRef.current?.click()} className="rounded-lg bg-white/5 px-3 py-2 text-xs font-semibold">
            Импорт CSV
          </button>
          <input ref={csvInputRef} type="file" accept=".csv" className="hidden" onChange={(e) => e.target.files?.[0] && importMutation.mutate(e.target.files[0])} />
          <button onClick={() => { setCreating(true); setForm(emptyForm); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">
            + Добавить
          </button>
        </div>
      </div>

      {importResult && <p className="text-xs text-slate-400">{importResult}</p>}

      <input
        value={search}
        onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        placeholder="Поиск по имени..."
        className="max-w-sm rounded-xl bg-bg-surface px-4 py-2.5 text-sm outline-none"
      />

      <div className="overflow-x-auto rounded-2xl border border-white/5">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-bg-surface text-left text-xs text-slate-400">
            <tr>
              <th className="px-3 py-2" />
              <th className="px-3 py-2">Имя</th>
              <th className="px-3 py-2">Рейтинг</th>
              <th className="px-3 py-2">Редкость</th>
              <th className="px-3 py-2">Позиция</th>
              <th className="px-3 py-2">Клуб</th>
              <th className="px-3 py-2">Активен</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((p) => (
              <tr key={p.id} className="border-t border-white/5">
                <td className="px-3 py-2">
                  <img src={staticUrl(p.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")} className="h-10 w-10 rounded-lg object-cover" />
                </td>
                <td className="px-3 py-2">{p.display_name}</td>
                <td className="px-3 py-2">{p.rating}</td>
                <td className="px-3 py-2">{RARITY_LABELS[p.rarity]}</td>
                <td className="px-3 py-2">{p.position}</td>
                <td className="px-3 py-2">{p.club}</td>
                <td className="px-3 py-2">{p.is_active ? "✅" : "🚫"}</td>
                <td className="px-3 py-2">
                  <div className="flex gap-1">
                    <button onClick={() => openEdit(p)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">✏️</button>
                    <button onClick={() => toggleMutation.mutate(p.id)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">
                      {p.is_active ? "🚫" : "✅"}
                    </button>
                    <button onClick={() => deleteMutation.mutate(p.id)} className="rounded-lg bg-red-500/70 px-2 py-1 text-xs">🗑️</button>
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
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать игрока" : "Новый игрок"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              <TextField label="Имя" value={form.first_name} onChange={(v) => setForm({ ...form, first_name: v })} />
              <TextField label="Фамилия" value={form.last_name} onChange={(v) => setForm({ ...form, last_name: v })} />
              <TextField label="Отображаемое имя" value={form.display_name} onChange={(v) => setForm({ ...form, display_name: v })} />
              <TextField label="Страна" value={form.country} onChange={(v) => setForm({ ...form, country: v })} />
              <TextField label="Клуб" value={form.club} onChange={(v) => setForm({ ...form, club: v })} />
              <div className="grid grid-cols-2 gap-2">
                <NumberField label="Рейтинг" value={form.rating} onChange={(v) => setForm({ ...form, rating: v })} min={1} max={99} />
                <NumberField label="Цена продажи" value={form.quick_sell_price} onChange={(v) => setForm({ ...form, quick_sell_price: v })} min={0} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <SelectField label="Редкость" value={form.rarity} options={RARITIES.map((r) => ({ value: r, label: RARITY_LABELS[r] }))} onChange={(v) => setForm({ ...form, rarity: v as Rarity })} />
                <SelectField label="Позиция" value={form.position} options={POSITIONS.map((p) => ({ value: p, label: p }))} onChange={(v) => setForm({ ...form, position: v as Position })} />
              </div>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Коллекция</span>
                <select
                  value={form.collection_id}
                  onChange={(e) => setForm({ ...form, collection_id: e.target.value ? Number(e.target.value) : "" })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                >
                  <option value="">Без коллекции</option>
                  {collections?.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен
              </label>

              {editing && (
                <div className="mt-2 flex items-center gap-2">
                  <img src={staticUrl(editing.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")} className="h-14 w-14 rounded-lg object-cover" />
                  <button onClick={() => fileInputRef.current?.click()} className="rounded-lg bg-white/5 px-3 py-1.5 text-xs">Загрузить фото</button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".png,.jpg,.jpeg,.webp"
                    className="hidden"
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

function downloadCsv(content: string) {
  const blob = new Blob([content], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "players.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
    </label>
  );
}

function NumberField({ label, value, onChange, min, max }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input type="number" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
    </label>
  );
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: { value: string; label: string }[]; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="rounded-lg bg-bg-surface px-3 py-2 outline-none">
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  );
}
