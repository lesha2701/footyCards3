import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  createBadge,
  createCoinPackage,
  deleteBadge,
  deleteBadgeImage,
  deleteCoinPackage,
  fetchAdminBadges,
  fetchAdminCoinPackages,
  fetchStarsPackPurchases,
  updateBadge,
  updateCoinPackage,
  uploadBadgeImage,
} from "@/admin/api";
import NumberInput from "@/components/common/NumberInput";
import { ApiRequestError, staticUrl } from "@/lib/api";
import type { Badge, CoinPackage } from "@/types";

export default function AdminShopPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold">Магазин</h1>
      <CoinPackagesSection />
      <BadgesSection />
      <StarsPackPurchasesSection />
    </div>
  );
}

function StarsPackPurchasesSection() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({
    queryKey: ["admin-stars-pack-purchases", page],
    queryFn: () => fetchStarsPackPurchases(page),
  });

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <div className="mb-3">
        <p className="font-display text-base font-bold">Открытия паков за Stars</p>
        <p className="text-xs text-slate-500">Кто, какой пак и когда купил за Telegram Stars.</p>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="overflow-x-auto rounded-xl border border-white/5">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-bg-base text-left text-xs text-slate-400">
            <tr>
              <th className="px-3 py-2">Дата</th>
              <th className="px-3 py-2">Игрок</th>
              <th className="px-3 py-2">Пак</th>
              <th className="px-3 py-2">Цена, ⭐</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((purchase) => (
              <tr key={purchase.id} className="border-t border-white/5 align-top">
                <td className="px-3 py-2 text-xs text-slate-400">
                  {new Date(purchase.completed_at).toLocaleString("ru-RU")}
                </td>
                <td className="px-3 py-2 text-xs">
                  {purchase.user_display_name}
                  {purchase.user_username && <span className="text-slate-500"> @{purchase.user_username}</span>}
                  <div className="text-[11px] text-slate-500">id {purchase.user_telegram_id}</div>
                </td>
                <td className="px-3 py-2 text-xs">{purchase.pack_name}</td>
                <td className="px-3 py-2 text-xs">{purchase.stars_amount}</td>
              </tr>
            ))}
            {data?.items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-4 text-center text-xs text-slate-500">Покупок пока нет.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="mt-3 flex gap-2">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">←</button>
          <span className="text-sm text-slate-400">{page} / {data.pages}</span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">→</button>
        </div>
      )}
    </section>
  );
}

interface CoinPackageForm {
  stars_price: number;
  coins_amount: number;
  is_active: boolean;
  sort_order: number;
}

function packageToForm(p?: CoinPackage): CoinPackageForm {
  return {
    stars_price: p?.stars_price ?? 10,
    coins_amount: p?.coins_amount ?? 20,
    is_active: p?.is_active ?? true,
    sort_order: p?.sort_order ?? 0,
  };
}

function CoinPackagesSection() {
  const queryClient = useQueryClient();
  const { data: packages, isLoading } = useQuery({ queryKey: ["admin-coin-packages"], queryFn: fetchAdminCoinPackages });
  const [editing, setEditing] = useState<CoinPackage | "new" | null>(null);
  const [form, setForm] = useState<CoinPackageForm>(packageToForm());
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-coin-packages"] });

  const saveMutation = useMutation({
    mutationFn: () => (editing === "new" ? createCoinPackage({ ...form }) : updateCoinPackage((editing as CoinPackage).id, { ...form })),
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить пакет"),
  });
  const deleteMutation = useMutation({ mutationFn: deleteCoinPackage, onSuccess: invalidate });

  const openEdit = (p: CoinPackage) => { setEditing(p); setForm(packageToForm(p)); setError(null); };
  const openCreate = () => { setEditing("new"); setForm(packageToForm()); setError(null); };

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="font-display text-base font-bold">Покупка монет за Telegram Stars</p>
          <p className="text-xs text-slate-500">Точные пакеты монет за звёзды — заменяет старую формулу курса.</p>
        </div>
        <button onClick={openCreate} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">+ Пакет</button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="flex flex-col gap-2">
        {packages?.map((p) => (
          <div key={p.id} className="flex items-center justify-between rounded-xl bg-bg-base px-3 py-2">
            <div>
              <p className="text-sm font-semibold">{p.stars_price} ⭐ → {p.coins_amount} монет</p>
              <p className="text-[11px] text-slate-500">{p.is_active ? "Активен" : "Отключён"} · порядок {p.sort_order}</p>
            </div>
            <div className="flex gap-1">
              <button onClick={() => openEdit(p)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => deleteMutation.mutate(p.id)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
        {packages?.length === 0 && <p className="text-xs text-slate-500">Пакетов пока нет.</p>}
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setEditing(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing === "new" ? "Новый пакет" : "Редактировать пакет"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Цена, ⭐</span>
                <NumberInput value={form.stars_price} onChange={(v) => setForm({ ...form, stars_price: v })} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Монет</span>
                <NumberInput value={form.coins_amount} onChange={(v) => setForm({ ...form, coins_amount: v })} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Порядок сортировки</span>
                <NumberInput value={form.sort_order} onChange={(v) => setForm({ ...form, sort_order: v })} />
              </label>
              <label className="mt-1 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен (виден игрокам)
              </label>
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
    </section>
  );
}

interface BadgeForm {
  name: string;
  icon: string;
  is_active: boolean;
  sort_order: number;
}

function badgeToForm(b?: Badge): BadgeForm {
  return {
    name: b?.name ?? "",
    icon: b?.icon ?? "⭐",
    is_active: b?.is_active ?? true,
    sort_order: b?.sort_order ?? 0,
  };
}

function BadgesSection() {
  const queryClient = useQueryClient();
  const { data: badges, isLoading } = useQuery({ queryKey: ["admin-badges"], queryFn: fetchAdminBadges });
  const [editing, setEditing] = useState<Badge | "new" | null>(null);
  const [form, setForm] = useState<BadgeForm>(badgeToForm());
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-badges"] });

  const saveMutation = useMutation({
    mutationFn: () => (editing === "new" ? createBadge({ ...form }) : updateBadge((editing as Badge).id, { ...form })),
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить значок"),
  });
  const deleteMutation = useMutation({ mutationFn: deleteBadge, onSuccess: invalidate });
  const uploadImageMutation = useMutation({
    mutationFn: (file: File) => uploadBadgeImage((editing as Badge).id, file),
    onSuccess: (b) => { invalidate(); setEditing(b); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось загрузить изображение"),
  });
  const removeImageMutation = useMutation({
    mutationFn: () => deleteBadgeImage((editing as Badge).id),
    onSuccess: (b) => { invalidate(); setEditing(b); },
  });

  const openEdit = (b: Badge) => { setEditing(b); setForm(badgeToForm(b)); setError(null); };
  const openCreate = () => { setEditing("new"); setForm(badgeToForm()); setError(null); };

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="font-display text-base font-bold">Значки</p>
          <p className="text-xs text-slate-500">Значки, выдаваемые как награда за паки за звёзды. Показываются рядом с именем игрока везде.</p>
        </div>
        <button onClick={openCreate} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">+ Значок</button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="flex flex-col gap-2">
        {badges?.map((b) => (
          <div key={b.id} className="flex items-center justify-between rounded-xl bg-bg-base px-3 py-2">
            <div className="flex items-center gap-2">
              {b.image_path ? (
                <img src={staticUrl(b.image_path) ?? undefined} className="h-7 w-7 rounded-full object-cover" />
              ) : (
                <span className="text-lg">{b.icon}</span>
              )}
              <div>
                <p className="text-sm font-semibold">{b.name}</p>
                <p className="text-[11px] text-slate-500">{b.is_active ? "Активен" : "Отключён"} · порядок {b.sort_order}</p>
              </div>
            </div>
            <div className="flex gap-1">
              <button onClick={() => openEdit(b)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => deleteMutation.mutate(b.id)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
        {badges?.length === 0 && <p className="text-xs text-slate-500">Значков пока нет.</p>}
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setEditing(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing === "new" ? "Новый значок" : "Редактировать значок"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Название (для админки)</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
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
                  <span className="text-xs font-semibold text-slate-400">Картинка значка</span>
                  <div className="flex items-center gap-3">
                    {(editing as Badge).image_path ? (
                      <img src={staticUrl((editing as Badge).image_path!) ?? undefined} className="h-12 w-12 rounded-full border border-white/10 object-cover" />
                    ) : (
                      <span className="flex h-12 w-12 items-center justify-center rounded-full border border-white/10 text-xl">{(editing as Badge).icon}</span>
                    )}
                    <div className="flex flex-col gap-1">
                      <button type="button" onClick={() => fileInputRef.current?.click()} className="rounded-lg bg-white/5 px-3 py-1.5 text-xs">
                        Загрузить картинку
                      </button>
                      {(editing as Badge).image_path && (
                        <button type="button" onClick={() => removeImageMutation.mutate()} className="rounded-lg bg-red-500/10 px-3 py-1.5 text-xs text-red-400">
                          Удалить картинку
                        </button>
                      )}
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".png,.jpg,.jpeg,.webp"
                        className="hidden"
                        onChange={(e) => e.target.files?.[0] && uploadImageMutation.mutate(e.target.files[0])}
                      />
                    </div>
                  </div>
                </div>
              )}
              {editing === "new" && <span className="text-[11px] text-slate-500">Картинку можно загрузить после создания значка.</span>}
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
    </section>
  );
}
