import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createWheelPrize, deleteWheelPrize, fetchAdminBadges, fetchAdminPacks, fetchAdminWheelPrizes,
  toggleWheelPrizeActive, updateWheelPrize,
} from "@/admin/api";
import type { AdminWheelPrize } from "@/admin/types";
import { ApiRequestError } from "@/lib/api";

type PrizeType = AdminWheelPrize["prize_type"];
type CardRarity = NonNullable<AdminWheelPrize["card_rarity"]>;

interface PrizeForm {
  prize_type: PrizeType;
  weight: number;
  coins_amount: number;
  pack_id: number | "";
  card_rarity: CardRarity;
  badge_id: number | "";
  is_active: boolean;
  sort_order: number;
}

function prizeToForm(p?: AdminWheelPrize): PrizeForm {
  return {
    prize_type: p?.prize_type ?? "coins",
    weight: p?.weight ?? 10,
    coins_amount: p?.coins_amount ?? 50,
    pack_id: p?.pack_id ?? "",
    card_rarity: p?.card_rarity ?? "rare",
    badge_id: p?.badge_id ?? "",
    is_active: p?.is_active ?? true,
    sort_order: p?.sort_order ?? 0,
  };
}

const TYPE_LABELS: Record<PrizeType, string> = { coins: "Монеты", pack: "Пак", card_rarity: "Карта редкости", badge: "Значок" };
const RARITY_LABELS: Record<CardRarity, string> = { common: "Обычная", rare: "Редкая", epic: "Эпическая", legendary: "Легендарная" };

export default function AdminWheelPage() {
  const queryClient = useQueryClient();
  const { data: prizes, isLoading } = useQuery({ queryKey: ["admin-wheel-prizes"], queryFn: fetchAdminWheelPrizes });
  const { data: packs } = useQuery({ queryKey: ["admin-packs"], queryFn: fetchAdminPacks });
  const { data: badges } = useQuery({ queryKey: ["admin-badges"], queryFn: fetchAdminBadges });
  const [editing, setEditing] = useState<AdminWheelPrize | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<PrizeForm>(prizeToForm());
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-wheel-prizes"] });
  const toggleMutation = useMutation({ mutationFn: toggleWheelPrizeActive, onSuccess: invalidate });
  const deleteMutation = useMutation({
    mutationFn: deleteWheelPrize,
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить приз"),
  });

  const confirmDelete = (p: AdminWheelPrize) => {
    if (window.confirm("Удалить этот приз из колеса навсегда?")) deleteMutation.mutate(p.id);
  };

  const buildPayload = () => ({
    prize_type: form.prize_type,
    weight: form.weight,
    coins_amount: form.prize_type === "coins" ? form.coins_amount : null,
    pack_id: form.prize_type === "pack" ? form.pack_id || null : null,
    card_rarity: form.prize_type === "card_rarity" ? form.card_rarity : null,
    badge_id: form.prize_type === "badge" ? form.badge_id || null : null,
    is_active: form.is_active,
    sort_order: form.sort_order,
  });

  const createMutation = useMutation({ mutationFn: () => createWheelPrize(buildPayload()), onSuccess: () => { invalidate(); setCreating(false); } });
  const updateMutation = useMutation({ mutationFn: () => updateWheelPrize(editing!.id, buildPayload()), onSuccess: () => { invalidate(); setEditing(null); } });

  const openEdit = (p: AdminWheelPrize) => { setEditing(p); setForm(prizeToForm(p)); setError(null); };

  // Mirrors the backend's admin_wheel._validate_prize_fields invariant
  // (exactly one of coins_amount/pack_id/card_rarity/badge_id must match
  // prize_type) so a malformed submission is caught before it round-trips
  // to a 409 — card_rarity always has a value here (its <select> has no
  // empty option), so only pack/badge need the check.
  const missingRequiredField =
    (form.prize_type === "pack" && form.pack_id === "") || (form.prize_type === "badge" && form.badge_id === "");

  const prizeSummary = (p: AdminWheelPrize) => {
    if (p.prize_type === "coins") return `+${p.coins_amount} монет`;
    if (p.prize_type === "pack") return `Пак #${p.pack_id}`;
    if (p.prize_type === "card_rarity") return `Карта: ${RARITY_LABELS[p.card_rarity ?? "rare"]}`;
    return `Значок #${p.badge_id}`;
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Колесо фортуны</h1>
        <button onClick={() => { setCreating(true); setForm(prizeToForm()); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">
          + Новый приз
        </button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}
      {error && !creating && !editing && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {prizes?.map((p) => (
          <div key={p.id} className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="flex items-center justify-between">
              <p className="font-display text-sm font-bold">{TYPE_LABELS[p.prize_type]}</p>
              <p className="text-xs text-slate-500">Вес: {p.weight}</p>
            </div>
            <p className="text-xs text-slate-400">{prizeSummary(p)}</p>
            <p className="text-xs text-slate-500">{p.is_active ? "Активен" : "Отключён"}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              <button onClick={() => openEdit(p)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => toggleMutation.mutate(p.id)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">
                {p.is_active ? "Отключить" : "Включить"}
              </button>
              <button onClick={() => confirmDelete(p)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
      </div>

      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => { setCreating(false); setEditing(null); }}>
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать приз" : "Новый приз"}</p>
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Тип приза</span>
                <select
                  value={form.prize_type}
                  onChange={(e) => setForm({ ...form, prize_type: e.target.value as PrizeType })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                >
                  {(Object.keys(TYPE_LABELS) as PrizeType[]).map((t) => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Вес (относительный — больше = чаще выпадает)</span>
                <input type="number" value={form.weight} onChange={(e) => setForm({ ...form, weight: Number(e.target.value) })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>

              {form.prize_type === "coins" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Количество монет</span>
                  <input type="number" value={form.coins_amount} onChange={(e) => setForm({ ...form, coins_amount: Number(e.target.value) })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
                </label>
              )}

              {form.prize_type === "pack" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Пак</span>
                  <select
                    value={form.pack_id}
                    onChange={(e) => setForm({ ...form, pack_id: e.target.value ? Number(e.target.value) : "" })}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  >
                    <option value="">Выбери пак</option>
                    {packs?.map((pk) => <option key={pk.id} value={pk.id}>{pk.name}</option>)}
                  </select>
                </label>
              )}

              {form.prize_type === "card_rarity" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Редкость</span>
                  <select
                    value={form.card_rarity}
                    onChange={(e) => setForm({ ...form, card_rarity: e.target.value as CardRarity })}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  >
                    {(["rare", "epic", "legendary"] as CardRarity[]).map((r) => <option key={r} value={r}>{RARITY_LABELS[r]}</option>)}
                  </select>
                </label>
              )}

              {form.prize_type === "badge" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Значок</span>
                  <select
                    value={form.badge_id}
                    onChange={(e) => setForm({ ...form, badge_id: e.target.value ? Number(e.target.value) : "" })}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  >
                    <option value="">Выбери значок</option>
                    {badges?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                  <p className="text-[11px] text-slate-500">Заведи отдельный значок специально для колеса — не выбирай значки, уже привязанные к платным пакам.</p>
                </label>
              )}

              <label className="mt-1 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен
              </label>
            </div>

            <div className="mt-4 flex gap-2">
              <button onClick={() => { setCreating(false); setEditing(null); }} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm">Отмена</button>
              <button
                onClick={() => (editing ? updateMutation.mutate() : createMutation.mutate())}
                disabled={missingRequiredField}
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
