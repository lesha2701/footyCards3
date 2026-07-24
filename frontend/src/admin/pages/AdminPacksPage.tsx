import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { createPack, fetchAdminPacks, previewPack, togglePackActive, updatePack, uploadPackImage } from "@/admin/api";
import type { PackPreview } from "@/admin/types";
import NumberInput from "@/components/common/NumberInput";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { RARITY_LABELS } from "@/lib/rarity";
import type { Pack, Rarity } from "@/types";

const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];

const COVER_TEMPLATES: { rarity: Rarity; path: string }[] = RARITIES.map((rarity) => ({
  rarity,
  path: `packs/templates/${rarity}.svg`,
}));

interface PackForm {
  slug: string;
  name: string;
  description: string;
  price: number;
  card_count: number;
  guaranteed_min_rarity: Rarity | "";
  is_active: boolean;
  image_path: string | null;
  probabilities: Record<Rarity, number>;
}

function packToForm(p?: Pack): PackForm {
  const probabilities: Record<Rarity, number> = { common: 0, rare: 0, epic: 0, legendary: 0 };
  p?.rarity_probabilities.forEach((rp) => { probabilities[rp.rarity] = rp.probability; });
  return {
    slug: p?.slug ?? "",
    name: p?.name ?? "",
    description: p?.description ?? "",
    price: p?.price ?? 100,
    card_count: p?.card_count ?? 3,
    guaranteed_min_rarity: p?.guaranteed_min_rarity ?? "",
    is_active: p?.is_active ?? true,
    image_path: p?.image_path ?? null,
    probabilities,
  };
}

export default function AdminPacksPage() {
  const queryClient = useQueryClient();
  const { data: packs, isLoading } = useQuery({ queryKey: ["admin-packs"], queryFn: fetchAdminPacks });
  const [editing, setEditing] = useState<Pack | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<PackForm>(packToForm());
  const [preview, setPreview] = useState<{ pack: Pack; result: PackPreview } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-packs"] });
  const toggleMutation = useMutation({ mutationFn: togglePackActive, onSuccess: invalidate });

  const buildPayload = () => ({
    name: form.name,
    description: form.description,
    price: form.price,
    card_count: form.card_count,
    guaranteed_min_rarity: form.guaranteed_min_rarity || null,
    is_active: form.is_active,
    image_path: form.image_path,
    rarity_probabilities: RARITIES.filter((r) => form.probabilities[r] > 0).map((r) => ({ rarity: r, probability: form.probabilities[r] })),
  });

  const createMutation = useMutation({
    mutationFn: () => createPack({ ...buildPayload(), slug: form.slug }),
    onSuccess: () => { invalidate(); setCreating(false); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось создать пак"),
  });
  const updateMutation = useMutation({
    mutationFn: () => updatePack(editing!.id, buildPayload()),
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить изменения"),
  });
  const uploadImageMutation = useMutation({
    mutationFn: (file: File) => uploadPackImage(editing!.id, file),
    onSuccess: (p) => { invalidate(); setForm((f) => ({ ...f, image_path: p.image_path })); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось загрузить изображение"),
  });

  const openEdit = (p: Pack) => { setEditing(p); setForm(packToForm(p)); setError(null); };

  const probabilitySum = RARITIES.reduce((sum, r) => sum + (form.probabilities[r] || 0), 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Паки</h1>
        <button onClick={() => { setCreating(true); setForm(packToForm()); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">
          + Новый пак
        </button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {packs?.map((p) => (
          <div key={p.id} className="flex gap-3 rounded-2xl border border-white/5 bg-bg-surface p-3">
            <img src={staticUrl(p.image_path ?? undefined)} className="h-24 w-20 rounded-xl object-cover" />
            <div className="flex-1">
              <p className="font-display text-sm font-bold">{p.name}</p>
              <p className="text-xs text-slate-400">🪙{p.price} · {p.card_count} карт</p>
              <p className="text-xs text-slate-500">{p.is_active ? "Активен" : "Отключён"}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                <button onClick={() => openEdit(p)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
                <button onClick={() => toggleMutation.mutate(p.id)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">
                  {p.is_active ? "Отключить" : "Включить"}
                </button>
                <button
                  onClick={async () => setPreview({ pack: p, result: await previewPack(p.id) })}
                  className="rounded-lg bg-white/5 px-2 py-1 text-[11px]"
                >
                  Предпросмотр
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => { setCreating(false); setEditing(null); }}>
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать пак" : "Новый пак"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              {!editing && <Field label="Slug (латиницей)" value={form.slug} onChange={(v) => setForm({ ...form, slug: v })} />}
              <Field label="Название" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
              <Field label="Описание" value={form.description} onChange={(v) => setForm({ ...form, description: v })} />
              <div className="grid grid-cols-2 gap-2">
                <NumField label="Цена" value={form.price} min={0} onChange={(v) => setForm({ ...form, price: v })} />
                <NumField label="Карт в паке" value={form.card_count} min={1} max={12} onChange={(v) => setForm({ ...form, card_count: v })} />
              </div>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Гарантированная минимальная редкость</span>
                <select
                  value={form.guaranteed_min_rarity}
                  onChange={(e) => setForm({ ...form, guaranteed_min_rarity: e.target.value as Rarity | "" })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                >
                  <option value="">Нет</option>
                  {RARITIES.map((r) => <option key={r} value={r}>{RARITY_LABELS[r]}</option>)}
                </select>
              </label>

              <p className="mt-2 text-xs font-semibold text-slate-400">Вероятности редкостей (сумма: {probabilitySum.toFixed(2)})</p>
              {RARITIES.map((r) => (
                <div key={r} className="flex items-center gap-2">
                  <span className="w-24 text-xs">{RARITY_LABELS[r]}</span>
                  <NumberInput
                    step={0.01}
                    min={0}
                    max={1}
                    value={form.probabilities[r]}
                    onChange={(v) => setForm({ ...form, probabilities: { ...form.probabilities, [r]: v } })}
                    className="flex-1 rounded-lg bg-bg-surface px-3 py-1.5 outline-none"
                  />
                </div>
              ))}
              {Math.abs(probabilitySum - 1) > 0.02 && (
                <p className="text-xs text-amber-400">Сумма вероятностей должна быть ≈ 1.0, иначе сохранить нельзя</p>
              )}
              <label className="mt-1 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен
              </label>

              <div className="mt-2 flex flex-col gap-2">
                <span className="text-xs font-semibold text-slate-400">Обложка пака</span>
                <div className="flex items-center gap-3">
                  <img
                    src={staticUrl(form.image_path ?? undefined)}
                    className="h-20 w-16 rounded-lg border border-white/10 object-cover"
                  />
                  {editing && (
                    <div className="flex flex-col gap-1">
                      <button type="button" onClick={() => fileInputRef.current?.click()} className="rounded-lg bg-white/5 px-3 py-1.5 text-xs">
                        Загрузить своё изображение
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
                <span className="text-[11px] text-slate-500">Или выбери готовый шаблон:</span>
                <div className="flex gap-2">
                  {COVER_TEMPLATES.map((t) => (
                    <button
                      type="button"
                      key={t.rarity}
                      onClick={() => setForm({ ...form, image_path: t.path })}
                      className={`overflow-hidden rounded-lg border-2 ${form.image_path === t.path ? "border-accent" : "border-transparent"}`}
                      title={RARITY_LABELS[t.rarity]}
                    >
                      <img src={staticUrl(t.path)} className="h-16 w-12 object-cover" />
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-4 flex gap-2">
              <button onClick={() => { setCreating(false); setEditing(null); setError(null); }} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm">Отмена</button>
              <button
                onClick={() => (editing ? updateMutation.mutate() : createMutation.mutate())}
                disabled={Math.abs(probabilitySum - 1) > 0.02}
                className="flex-1 rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
              >
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}

      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setPreview(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-3 font-display text-lg font-bold">Предпросмотр: {preview.pack.name}</p>
            <p className="mb-2 text-xs text-slate-400">{preview.result.simulations} симуляций открытий</p>
            <div className="flex flex-col gap-1">
              {preview.result.rarity_distribution.map((d) => (
                <div key={d.rarity} className="flex items-center justify-between text-sm">
                  <span>{RARITY_LABELS[d.rarity]}</span>
                  <span className="font-bold">{d.percentage}%</span>
                </div>
              ))}
            </div>
            <button onClick={() => setPreview(null)} className="mt-4 w-full rounded-xl bg-white/5 py-2.5 text-sm">Закрыть</button>
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

function NumField({ label, value, onChange, min, max }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <NumberInput value={value} onChange={onChange} min={min} max={max} />
    </label>
  );
}
