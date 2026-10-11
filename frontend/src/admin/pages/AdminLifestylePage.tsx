import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  createLifestyleItem,
  deleteLifestyleItem,
  deleteLifestyleItemImage,
  fetchAdminLifestyleItems,
  updateLifestyleItem,
  uploadLifestyleItemImage,
} from "@/admin/api";
import type { AdminLifestyleItem } from "@/admin/types";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { showConfirm } from "@/lib/telegram";

const CATEGORIES = [
  { code: "car", label: "🚗 Гараж" },
  { code: "estate", label: "🏠 Недвижимость" },
  { code: "stocks", label: "📈 Инвестиции" },
  { code: "other", label: "✨ Другое" },
];

type Form = Omit<AdminLifestyleItem, "id" | "image_path" | "sold_count">;

function toForm(item?: AdminLifestyleItem): Form {
  return {
    name: item?.name ?? "",
    description: item?.description ?? "",
    category: item?.category ?? "car",
    emoji: item?.emoji ?? "🚗",
    coins_price: item?.coins_price ?? 0,
    stars_price: item?.stars_price ?? 0,
    prestige: item?.prestige ?? 10,
    max_supply: item?.max_supply ?? null,
    is_active: item?.is_active ?? true,
    sort_order: item?.sort_order ?? 0,
  };
}

/** «Имущество» of «Мой игрок»: status items (cars, real estate, stocks...)
 * players buy for coins and/or Telegram Stars. */
export default function AdminLifestylePage() {
  const queryClient = useQueryClient();
  const { data: items, isLoading } = useQuery({ queryKey: ["admin-lifestyle"], queryFn: fetchAdminLifestyleItems });
  const [editing, setEditing] = useState<AdminLifestyleItem | "new" | null>(null);
  const [form, setForm] = useState<Form>(toForm());
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-lifestyle"] });
  const onError = (fallback: string) => (err: unknown) => setError(err instanceof ApiRequestError ? err.message : fallback);

  const save = useMutation({
    mutationFn: () => (editing === "new" ? createLifestyleItem(form) : updateLifestyleItem((editing as AdminLifestyleItem).id, form)),
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: onError("Не удалось сохранить"),
  });
  const remove = useMutation({ mutationFn: deleteLifestyleItem, onSuccess: invalidate, onError: onError("Не удалось удалить") });
  const upload = useMutation({
    mutationFn: (file: File) => uploadLifestyleItemImage((editing as AdminLifestyleItem).id, file),
    onSuccess: (item) => { invalidate(); setEditing(item); },
    onError: onError("Не удалось загрузить картинку"),
  });
  const removeImage = useMutation({
    mutationFn: () => deleteLifestyleItemImage((editing as AdminLifestyleItem).id),
    onSuccess: (item) => { invalidate(); setEditing(item); },
  });

  const openEdit = (item: AdminLifestyleItem) => { setEditing(item); setForm(toForm(item)); setError(null); };
  const confirmDelete = async (item: AdminLifestyleItem) => {
    if (await showConfirm(`Удалить «${item.name}»? Если его уже покупали — выключи вместо удаления.`)) remove.mutate(item.id);
  };
  const num = (key: "coins_price" | "stars_price" | "prestige" | "sort_order", label: string) => (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        type="number" min={0} value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
        className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
      />
    </label>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">Имущество</h1>
          <p className="text-xs text-slate-500">
            Статусные предметы «Моего игрока»: машины, недвижимость, акции и т. п. Цена в монетах и/или звёздах (0 — не
            продаётся за эту валюту), престиж — очки статуса. Тираж пустой — без ограничений.
          </p>
        </div>
        <button
          onClick={() => { setEditing("new"); setForm(toForm()); setError(null); }}
          className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base"
        >
          + Предмет
        </button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}
      {error && !editing && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {items?.map((item) => (
          <div key={item.id} className="flex items-center justify-between gap-2 rounded-xl border border-white/5 bg-bg-surface px-3 py-2">
            <div className="flex min-w-0 items-center gap-2">
              {item.image_path ? (
                <img src={staticUrl(item.image_path) ?? undefined} className="h-10 w-10 rounded-lg object-cover" />
              ) : (
                <span className="text-2xl">{item.emoji}</span>
              )}
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{item.name}</p>
                <p className="text-[11px] text-slate-500">
                  {CATEGORIES.find((c) => c.code === item.category)?.label} · {item.coins_price > 0 && `🪙 ${item.coins_price} `}
                  {item.stars_price > 0 && `⭐ ${item.stars_price} `}· престиж {item.prestige} · продано {item.sold_count}
                  {item.max_supply != null && ` из ${item.max_supply}`}
                  {!item.is_active && " · выключен"}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 gap-1">
              <button onClick={() => openEdit(item)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => confirmDelete(item)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
        {items?.length === 0 && <p className="text-xs text-slate-500">Предметов пока нет.</p>}
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setEditing(null)}>
          <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing === "new" ? "Новый предмет" : "Редактировать предмет"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="grid grid-cols-2 gap-2 text-sm">
              <label className="col-span-2 flex flex-col gap-1">
                <span className="text-xs text-slate-400">Название</span>
                <input value={form.name} maxLength={64} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>
              <label className="col-span-2 flex flex-col gap-1">
                <span className="text-xs text-slate-400">Описание</span>
                <input value={form.description} maxLength={255} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Категория</span>
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none">
                  {CATEGORIES.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Эмодзи (если нет картинки)</span>
                <input value={form.emoji} maxLength={16} onChange={(e) => setForm({ ...form, emoji: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>
              {num("coins_price", "Цена, монеты")}
              {num("stars_price", "Цена, звёзды ⭐")}
              {num("prestige", "Престиж")}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Тираж (пусто — без лимита)</span>
                <input
                  type="number" min={1} value={form.max_supply ?? ""}
                  onChange={(e) => setForm({ ...form, max_supply: e.target.value ? Number(e.target.value) : null })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                />
              </label>
              {num("sort_order", "Порядок")}
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                В продаже
              </label>
              {editing !== "new" && (
                <div className="col-span-2 flex items-center gap-2">
                  {editing.image_path && <img src={staticUrl(editing.image_path) ?? undefined} className="h-12 w-12 rounded-lg object-cover" />}
                  <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
                  <button onClick={() => fileRef.current?.click()} className="rounded-lg bg-white/5 px-3 py-1.5 text-xs">
                    {editing.image_path ? "Заменить картинку" : "Загрузить картинку"}
                  </button>
                  {editing.image_path && (
                    <button onClick={() => removeImage.mutate()} className="rounded-lg bg-red-500/10 px-3 py-1.5 text-xs text-red-400">Убрать</button>
                  )}
                </div>
              )}
            </div>
            <div className="mt-4 flex gap-2">
              <button onClick={() => setEditing(null)} className="flex-1 rounded-lg bg-white/5 py-2 text-sm">Отмена</button>
              <button
                disabled={save.isPending || !form.name.trim()}
                onClick={() => save.mutate()}
                className="flex-1 rounded-lg bg-accent py-2 text-sm font-bold text-bg-base disabled:opacity-40"
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
