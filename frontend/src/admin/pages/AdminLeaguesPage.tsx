import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  backfillLeagueRewards,
  createLeagueTier,
  deleteLeagueTier,
  deleteLeagueTierImage,
  fetchAdminLeagues,
  fetchAdminPacks,
  updateLeagueTier,
  uploadLeagueTierImage,
} from "@/admin/api";
import NumberInput from "@/components/common/NumberInput";
import { IconTrophy } from "@/components/icons";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { showConfirm } from "@/lib/telegram";
import type { LeagueTier } from "@/types";

interface TierForm {
  name: string;
  min_rating: number;
  color: string;
  reward_coins: number;
  reward_pack_id: number | "";
  sort_order: number;
}

function tierToForm(t?: LeagueTier): TierForm {
  return {
    name: t?.name ?? "",
    min_rating: t?.min_rating ?? 0,
    color: t?.color ?? "#94a3b8",
    reward_coins: t?.reward_coins ?? 0,
    reward_pack_id: t?.reward_pack_id ?? "",
    sort_order: t?.sort_order ?? 0,
  };
}

export default function AdminLeaguesPage() {
  const queryClient = useQueryClient();
  const { data: tiers, isLoading } = useQuery({ queryKey: ["admin-leagues"], queryFn: fetchAdminLeagues });
  const { data: packs } = useQuery({ queryKey: ["admin-packs"], queryFn: fetchAdminPacks });
  const [editing, setEditing] = useState<LeagueTier | "new" | null>(null);
  const [form, setForm] = useState<TierForm>(tierToForm());
  const [error, setError] = useState<string | null>(null);
  const [backfillResult, setBackfillResult] = useState<number | null>(null);
  const [backfillError, setBackfillError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-leagues"] });

  const buildPayload = () => ({
    ...form,
    reward_pack_id: form.reward_pack_id === "" ? null : form.reward_pack_id,
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      editing === "new" ? createLeagueTier(buildPayload()) : updateLeagueTier((editing as LeagueTier).id, buildPayload()),
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить лигу"),
  });
  const deleteMutation = useMutation({ mutationFn: deleteLeagueTier, onSuccess: invalidate });
  const uploadImageMutation = useMutation({
    mutationFn: (file: File) => uploadLeagueTierImage((editing as LeagueTier).id, file),
    onSuccess: (t) => { invalidate(); setEditing(t); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось загрузить картинку"),
  });
  const removeImageMutation = useMutation({
    mutationFn: () => deleteLeagueTierImage((editing as LeagueTier).id),
    onSuccess: (t) => { invalidate(); setEditing(t); },
  });
  const backfillMutation = useMutation({
    mutationFn: backfillLeagueRewards,
    onSuccess: (res) => { setBackfillResult(res.rewarded_count); setBackfillError(null); },
    onError: (err) => setBackfillError(err instanceof ApiRequestError ? err.message : "Не удалось начислить награды"),
  });

  const openEdit = (t: LeagueTier) => { setEditing(t); setForm(tierToForm(t)); setError(null); };
  const openCreate = () => { setEditing("new"); setForm(tierToForm()); setError(null); };

  const confirmDelete = async (t: LeagueTier) => {
    if (await showConfirm(`Удалить лигу «${t.name}» навсегда?`)) {
      deleteMutation.mutate(t.id);
    }
  };

  const runBackfill = async () => {
    if (await showConfirm("Начислить награды за лиги всем игрокам, кто уже набрал нужный рейтинг, но ещё не получил награду? Можно нажимать повторно — уже выданное не выдастся снова.")) {
      setBackfillResult(null);
      setBackfillError(null);
      backfillMutation.mutate();
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">Лиги</h1>
          <p className="text-xs text-slate-500">
            Лестница лиг по суммарному рейтингу (Arena + Тактико + Пенальти). Награда выдаётся один раз при
            достижении нужного рейтинга.
          </p>
        </div>
        <button onClick={openCreate} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">+ Лига</button>
      </div>

      <div className="flex flex-col gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3">
        <div className="flex items-center gap-2">
          <button
            onClick={runBackfill}
            disabled={backfillMutation.isPending}
            className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
          >
            {backfillMutation.isPending ? "Начисление..." : "Начислить награды за прошлые лиги"}
          </button>
          {backfillResult !== null && (
            <span className="text-xs text-slate-300">Награждено игроков: {backfillResult}</span>
          )}
        </div>
        {backfillError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{backfillError}</p>}
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {tiers?.map((t) => (
          <div key={t.id} className="flex items-center justify-between rounded-xl border border-white/5 bg-bg-surface px-3 py-2">
            <div className="flex items-center gap-2">
              {t.image_path ? (
                <img src={staticUrl(t.image_path) ?? undefined} className="h-10 w-10 rounded-lg object-cover" />
              ) : (
                <IconTrophy size={20} style={{ color: t.color }} />
              )}
              <div>
                <p className="text-sm font-semibold">{t.name}</p>
                <p className="text-[11px] text-slate-500">от {t.min_rating} рейтинга · +{t.reward_coins} монет</p>
              </div>
            </div>
            <div className="flex gap-1">
              <button onClick={() => openEdit(t)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => confirmDelete(t)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
        {tiers?.length === 0 && <p className="text-xs text-slate-500">Лиг пока нет.</p>}
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setEditing(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing === "new" ? "Новая лига" : "Редактировать лигу"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Название</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Минимальный суммарный рейтинг</span>
                <NumberInput value={form.min_rating} onChange={(v) => setForm({ ...form, min_rating: v })} min={0} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Цвет кубка</span>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={form.color}
                    onChange={(e) => setForm({ ...form, color: e.target.value })}
                    className="h-9 w-14 cursor-pointer rounded-lg border border-white/10 bg-bg-surface p-1"
                  />
                  <IconTrophy size={20} style={{ color: form.color }} />
                </div>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Награда, монеты</span>
                <NumberInput value={form.reward_coins} onChange={(v) => setForm({ ...form, reward_coins: v })} min={0} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Награда: пак (необязательно)</span>
                <select
                  value={form.reward_pack_id}
                  onChange={(e) => setForm({ ...form, reward_pack_id: e.target.value ? Number(e.target.value) : "" })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                >
                  <option value="">Нет</option>
                  {packs?.map((pk) => <option key={pk.id} value={pk.id}>{pk.name}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Порядок сортировки</span>
                <NumberInput value={form.sort_order} onChange={(v) => setForm({ ...form, sort_order: v })} />
              </label>

              {editing !== "new" && (
                <div className="mt-2 flex flex-col gap-2">
                  <span className="text-xs font-semibold text-slate-400">Картинка лиги — используется вместо кубка, пока не загружена</span>
                  <div className="flex items-center gap-3">
                    {(editing as LeagueTier).image_path ? (
                      <img
                        src={staticUrl((editing as LeagueTier).image_path!) ?? undefined}
                        className="h-14 w-14 rounded-lg border border-white/10 object-cover"
                      />
                    ) : (
                      <span className="flex h-14 w-14 items-center justify-center rounded-lg bg-black/30">
                        <IconTrophy size={24} style={{ color: form.color }} />
                      </span>
                    )}
                    <div className="flex flex-col gap-1">
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploadImageMutation.isPending}
                        className="rounded-lg bg-white/5 px-2 py-1 text-[11px]"
                      >
                        {uploadImageMutation.isPending ? "Загрузка..." : "Загрузить"}
                      </button>
                      {(editing as LeagueTier).image_path && (
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
