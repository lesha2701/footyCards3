import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  createTrophy,
  deleteTrophy,
  deleteTrophyImage,
  fetchAdminTrophies,
  updateTrophy,
  uploadTrophyImage,
} from "@/admin/api";
import NumberInput from "@/components/common/NumberInput";
import { ApiRequestError, staticUrl } from "@/lib/api";
import type { TrophyDefinition } from "@/types";

interface TrophyForm {
  code: string;
  name: string;
  description: string;
  icon: string;
  is_active: boolean;
  sort_order: number;
}

function trophyToForm(t?: TrophyDefinition): TrophyForm {
  return {
    code: t?.code ?? "",
    name: t?.name ?? "",
    description: t?.description ?? "",
    icon: t?.icon ?? "🏆",
    is_active: t?.is_active ?? true,
    sort_order: t?.sort_order ?? 0,
  };
}

export default function AdminTrophiesPage() {
  const queryClient = useQueryClient();
  const { data: trophies, isLoading } = useQuery({ queryKey: ["admin-trophies"], queryFn: fetchAdminTrophies });
  const [editing, setEditing] = useState<TrophyDefinition | "new" | null>(null);
  const [form, setForm] = useState<TrophyForm>(trophyToForm());
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-trophies"] });

  const saveMutation = useMutation({
    mutationFn: () =>
      editing === "new" ? createTrophy({ ...form }) : updateTrophy((editing as TrophyDefinition).id, { ...form }),
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить трофей"),
  });
  const deleteMutation = useMutation({ mutationFn: deleteTrophy, onSuccess: invalidate });
  const uploadImageMutation = useMutation({
    mutationFn: (file: File) => uploadTrophyImage((editing as TrophyDefinition).id, file),
    onSuccess: (t) => { invalidate(); setEditing(t); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось загрузить изображение"),
  });
  const removeImageMutation = useMutation({
    mutationFn: () => deleteTrophyImage((editing as TrophyDefinition).id),
    onSuccess: (t) => { invalidate(); setEditing(t); },
  });

  const openEdit = (t: TrophyDefinition) => { setEditing(t); setForm(trophyToForm(t)); setError(null); };
  const openCreate = () => { setEditing("new"); setForm(trophyToForm()); setError(null); };

  const confirmDelete = (t: TrophyDefinition) => {
    if (window.confirm(`Удалить трофей «${t.name}» навсегда? У всех игроков, кому он был вручён, он тоже пропадёт.`)) {
      deleteMutation.mutate(t.id);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">Трофеи</h1>
          <p className="text-xs text-slate-500">
            Каталог трофеев для витрины в профиле игроков. Выдаются вручную — кнопка «Подарить» в разделе «Подарки»
            мини-аппа, с личной подписью.
          </p>
        </div>
        <button onClick={openCreate} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">+ Трофей</button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {trophies?.map((t) => (
          <div key={t.id} className="flex items-center justify-between rounded-xl border border-white/5 bg-bg-surface px-3 py-2">
            <div className="flex items-center gap-2">
              {t.image_path ? (
                <img src={staticUrl(t.image_path) ?? undefined} className="h-10 w-10 rounded-lg object-cover" />
              ) : (
                <span className="text-2xl">{t.icon}</span>
              )}
              <div>
                <p className="text-sm font-semibold">{t.name}</p>
                <p className="text-[11px] text-slate-500">{t.is_active ? "Активен" : "Отключён"} · порядок {t.sort_order}</p>
              </div>
            </div>
            <div className="flex gap-1">
              <button onClick={() => openEdit(t)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => confirmDelete(t)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
        {trophies?.length === 0 && <p className="text-xs text-slate-500">Трофеев пока нет.</p>}
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setEditing(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing === "new" ? "Новый трофей" : "Редактировать трофей"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              {editing === "new" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Code (латиницей, уникальный)</span>
                  <input
                    value={form.code}
                    onChange={(e) => setForm({ ...form, code: e.target.value })}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  />
                </label>
              )}
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
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Иконка (эмодзи) — используется, пока не загружена картинка</span>
                <input
                  value={form.icon}
                  onChange={(e) => setForm({ ...form, icon: e.target.value })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Порядок сортировки</span>
                <NumberInput value={form.sort_order} onChange={(v) => setForm({ ...form, sort_order: v })} />
              </label>
              <label className="mt-1 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен (можно выдавать)
              </label>

              {editing !== "new" && (
                <div className="mt-2 flex flex-col gap-2">
                  <span className="text-xs font-semibold text-slate-400">Картинка трофея</span>
                  <div className="flex items-center gap-3">
                    {(editing as TrophyDefinition).image_path ? (
                      <img
                        src={staticUrl((editing as TrophyDefinition).image_path!) ?? undefined}
                        className="h-14 w-14 rounded-lg border border-white/10 object-cover"
                      />
                    ) : (
                      <span className="flex h-14 w-14 items-center justify-center rounded-lg bg-black/30 text-2xl">{form.icon}</span>
                    )}
                    <div className="flex flex-col gap-1">
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploadImageMutation.isPending}
                        className="rounded-lg bg-white/5 px-2 py-1 text-[11px]"
                      >
                        {uploadImageMutation.isPending ? "Загрузка..." : "Загрузить"}
                      </button>
                      {(editing as TrophyDefinition).image_path && (
                        <button onClick={() => removeImageMutation.mutate()} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">
                          Удалить картинку
                        </button>
                      )}
                    </div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
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
