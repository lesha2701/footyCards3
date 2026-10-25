import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAdminPlayers } from "@/admin/api";
import { deleteAdminCardOffer, fetchAdminCardOffers, saveAdminCardOffer } from "@/api/cardOffers";
import { formatGameError } from "@/lib/errors";
import type { CardOfferAdmin, CardOfferAdminInput, Player } from "@/types";

const input = "w-full rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none";

/** datetime-local value (local time) <-> ISO. */
const toLocal = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};
const fromLocal = (v: string) => (v ? new Date(v).toISOString() : null);

type Draft = CardOfferAdminInput & { id?: number; player?: Player };

const EMPTY: Draft = {
  player_id: 0, stars_price: 100, title: null, starts_at: null, ends_at: null, stock: null,
  per_user_limit: 1, is_active: true, sort_order: 0,
};

/** «Карты за звёзды»: the admin picks any card (typically a retired one —
 * «не выпадает из паков» in Игроки) and sells it for Stars, optionally for
 * a limited time / stock. */
export default function AdminCardOffers() {
  const queryClient = useQueryClient();
  const { data: offers } = useQuery({ queryKey: ["admin-card-offers"], queryFn: fetchAdminCardOffers });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin-card-offers"] });
  const save = useMutation({
    mutationFn: (d: Draft) => {
      const { id, player: _player, ...body } = d;
      return saveAdminCardOffer(body, id);
    },
    onSuccess: () => { setDraft(null); setError(null); refresh(); },
    onError: (e) => setError(formatGameError(e, "Не сохранилось")),
  });
  const remove = useMutation({
    mutationFn: deleteAdminCardOffer,
    onSuccess: refresh,
    onError: (e) => setError(formatGameError(e, "Не удалилось")),
  });

  const edit = (o: CardOfferAdmin) => setDraft({ ...o, player_id: o.player.id });

  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-white/5 bg-bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-display text-sm font-bold">Карты за звёзды</p>
        <button onClick={() => setDraft({ ...EMPTY })} className="rounded-lg bg-accent-lime/20 px-3 py-1.5 text-xs font-semibold text-accent-lime">
          + Добавить карточку
        </button>
      </div>
      <p className="text-xs text-slate-500">
        Любая включённая карточка продаётся в магазине (вкладка «Карты ⭐») за Stars. Для лимиток: в «Игроках» сними у карточки
        «выпадает из паков», и купить её можно будет только здесь. Время, тираж и лимит на игрока — по желанию.
      </p>
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {draft && <OfferForm draft={draft} onChange={setDraft} onSave={() => save.mutate(draft)} onCancel={() => setDraft(null)} busy={save.isPending} />}

      <div className="flex flex-col gap-1.5">
        {offers?.map((o) => (
          <div key={o.id} className="flex items-center gap-3 rounded-xl bg-bg-base px-3 py-2 text-sm">
            <span className={`h-2 w-2 shrink-0 rounded-full ${o.live ? "bg-accent-lime" : "bg-slate-600"}`} title={o.live ? "В продаже" : "Не в продаже"} />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-semibold">{o.player.display_name} · {o.player.rating}{o.title ? ` · ${o.title}` : ""}</span>
              <span className="block text-xs text-slate-500">
                {o.stars_price} ⭐ · продано {o.sold_count}{o.stock ? `/${o.stock}` : ""}
                {o.ends_at ? ` · до ${new Date(o.ends_at).toLocaleString("ru-RU")}` : ""}
                {o.is_active ? "" : " · выключено"}
              </span>
            </span>
            <button onClick={() => edit(o)} className="text-xs text-accent-cyan">Изменить</button>
            {o.sold_count === 0 && (
              <button onClick={() => confirm("Удалить предложение?") && remove.mutate(o.id)} className="text-xs text-red-400">Удалить</button>
            )}
          </div>
        ))}
        {offers && !offers.length && <p className="text-xs text-slate-500">Пока нет ни одной карточки за звёзды</p>}
      </div>
    </section>
  );
}

function OfferForm({ draft, onChange, onSave, onCancel, busy }: {
  draft: Draft; onChange: (d: Draft) => void; onSave: () => void; onCancel: () => void; busy: boolean;
}) {
  const [search, setSearch] = useState("");
  const { data: found } = useQuery({
    queryKey: ["admin-players-search", search], queryFn: () => fetchAdminPlayers(search, 1), enabled: search.length >= 2,
  });
  const set = (patch: Partial<Draft>) => onChange({ ...draft, ...patch });
  const numOrNull = (v: string) => (v ? Number(v) : null);

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-accent-lime/20 bg-bg-base p-3">
      {draft.player ? (
        <div className="flex items-center justify-between text-sm">
          <span>
            <b>{draft.player.display_name}</b> · {draft.player.rating} · {draft.player.rarity}
            {draft.player.is_pack_droppable === false && <span className="ml-1 text-amber-300">(лимитка)</span>}
          </span>
          <button onClick={() => set({ player: undefined, player_id: 0 })} className="text-xs text-slate-400 underline">сменить</button>
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          <input placeholder="Найти карточку по имени (от 2 букв)" value={search} onChange={(e) => setSearch(e.target.value)} className={input} />
          <div className="flex max-h-48 flex-col overflow-y-auto">
            {found?.items.map((p) => (
              <button key={p.id} onClick={() => set({ player: p, player_id: p.id })} className="rounded px-2 py-1 text-left text-xs hover:bg-white/5">
                {p.display_name} · {p.rating} · {p.position} · {p.rarity}
                {p.is_pack_droppable === false ? " · лимитка" : ""}{p.is_active === false ? " · выключена" : ""}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Цена, ⭐</span>
          <input type="number" min={1} value={draft.stars_price} onChange={(e) => set({ stars_price: Number(e.target.value) || 1 })} className={input} /></label>
        <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Тираж (пусто — без лимита)</span>
          <input type="number" min={1} value={draft.stock ?? ""} onChange={(e) => set({ stock: numOrNull(e.target.value) })} className={input} /></label>
        <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">На игрока (0 — без лимита)</span>
          <input type="number" min={0} value={draft.per_user_limit} onChange={(e) => set({ per_user_limit: Number(e.target.value) || 0 })} className={input} /></label>
        <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Порядок</span>
          <input type="number" value={draft.sort_order} onChange={(e) => set({ sort_order: Number(e.target.value) || 0 })} className={input} /></label>
        <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Начало продаж (пусто — сразу)</span>
          <input type="datetime-local" value={toLocal(draft.starts_at)} onChange={(e) => set({ starts_at: fromLocal(e.target.value) })} className={input} /></label>
        <label className="flex flex-col gap-0.5"><span className="text-micro text-slate-500">Конец продаж (пусто — бессрочно)</span>
          <input type="datetime-local" value={toLocal(draft.ends_at)} onChange={(e) => set({ ends_at: fromLocal(e.target.value) })} className={input} /></label>
        <label className="col-span-2 flex flex-col gap-0.5"><span className="text-micro text-slate-500">Подпись на карточке (необязательно)</span>
          <input maxLength={64} value={draft.title ?? ""} onChange={(e) => set({ title: e.target.value || null })} placeholder="Например: Переиздание" className={input} /></label>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft.is_active} onChange={(e) => set({ is_active: e.target.checked })} /> Включено
      </label>
      <div className="flex gap-2">
        <button onClick={onSave} disabled={busy || !draft.player_id} className="rounded-lg bg-accent-lime px-4 py-2 text-sm font-bold text-bg-base disabled:opacity-40">
          Сохранить
        </button>
        <button onClick={onCancel} className="rounded-lg px-4 py-2 text-sm text-slate-400">Отмена</button>
      </div>
    </div>
  );
}
