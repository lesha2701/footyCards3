import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAdminCoaches, fetchAdminMuses, fetchAdminPlayers, fetchAdminStadiums } from "@/admin/api";
import { announceAdminCardOffer, deleteAdminCardOffer, fetchAdminCardOffers, saveAdminCardOffer } from "@/api/cardOffers";
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

type Kind = "player" | "coach" | "stadium" | "muse";
const KIND_LABELS: Record<Kind, string> = { player: "Футболист", coach: "Тренер", stadium: "Стадион", muse: "Муза" };
const KIND_ID: Record<Kind, "player_id" | "coach_id" | "stadium_id" | "muse_id"> = {
  player: "player_id", coach: "coach_id", stadium: "stadium_id", muse: "muse_id",
};

/** The form: one kind, one chosen card (`label` is what the admin sees). */
type Draft = CardOfferAdminInput & { id?: number; kind: Kind; label?: string; player?: Player };

const EMPTY: Draft = {
  kind: "player", stars_price: 100, title: null, starts_at: null, ends_at: null, stock: null,
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
      const { id, kind, label: _label, player: _player, ...body } = d;
      const ids = { player_id: null, coach_id: null, stadium_id: null, muse_id: null, [KIND_ID[kind]]: d[KIND_ID[kind]] };
      return saveAdminCardOffer({ ...body, ...ids }, id);
    },
    onSuccess: () => { setDraft(null); setError(null); refresh(); },
    onError: (e) => setError(formatGameError(e, "Не сохранилось")),
  });
  const remove = useMutation({
    mutationFn: deleteAdminCardOffer,
    onSuccess: refresh,
    onError: (e) => setError(formatGameError(e, "Не удалилось")),
  });

  const [notice, setNotice] = useState<string | null>(null);
  const announce = useMutation({
    mutationFn: announceAdminCardOffer,
    onSuccess: (r) => { setNotice(`Разослано: ${r.sent} игрокам — бот отправит в течение нескольких минут`); setError(null); refresh(); },
    onError: (e) => setError(formatGameError(e, "Не разослалось")),
  });
  const askAnnounce = (o: CardOfferAdmin) =>
    confirm(`Отправить всем игрокам сообщение от бота про «${offerName(o)}»? Это можно сделать один раз.`) && announce.mutate(o.id);

  const edit = (o: CardOfferAdmin) => {
    const kind = (o.kind ?? "player") as Kind;
    setDraft({
      ...o, kind, label: offerName(o), player: o.player ?? undefined,
      [KIND_ID[kind]]: o.player ? o.player.id : o.item?.id,
    });
  };

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
      {notice && <p className="rounded-lg bg-accent-lime/10 px-3 py-2 text-xs text-accent-lime">{notice}</p>}

      {draft && <OfferForm draft={draft} onChange={setDraft} onSave={() => save.mutate(draft)} onCancel={() => setDraft(null)} busy={save.isPending} />}

      <div className="flex flex-col gap-1.5">
        {offers?.map((o) => (
          <div key={o.id} className="flex items-center gap-3 rounded-xl bg-bg-base px-3 py-2 text-sm">
            <span className={`h-2 w-2 shrink-0 rounded-full ${o.live ? "bg-accent-lime" : "bg-slate-600"}`} title={o.live ? "В продаже" : "Не в продаже"} />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-semibold">
                {o.kind && o.kind !== "player" ? `${KIND_LABELS[o.kind]}: ` : ""}{offerName(o)}{o.title ? ` · ${o.title}` : ""}
              </span>
              <span className="block text-xs text-slate-500">
                {o.stars_price} ⭐ · продано {o.sold_count}{o.stock ? `/${o.stock}` : ""}
                {o.ends_at ? ` · до ${new Date(o.ends_at).toLocaleString("ru-RU")}` : ""}
                {o.is_active ? "" : " · выключено"}
                {o.announced_at ? " · разослано" : ""}
              </span>
              <span className="block text-xs text-slate-400">
                Выручка {o.stars_total.toLocaleString("ru-RU")} ⭐ · смотрели {o.viewers} · купили {o.buyers}
                {o.viewers > 0 ? ` (${Math.round((o.buyers / o.viewers) * 100)}%)` : ""}
              </span>
            </span>
            {o.live && !o.announced_at && (
              <button onClick={() => askAnnounce(o)} disabled={announce.isPending} className="text-xs text-amber-300">Разослать</button>
            )}
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

function offerName(o: CardOfferAdmin): string {
  return o.player ? `${o.player.display_name} · ${o.player.rating}` : o.item?.name ?? "—";
}

/** Search results of the chosen kind, as {id, label}. */
function useCandidates(kind: Kind, search: string) {
  const enabled = search.length >= 2;
  const players = useQuery({
    queryKey: ["admin-players-search", search], queryFn: () => fetchAdminPlayers(search, 1), enabled: enabled && kind === "player",
  });
  const coaches = useQuery({
    queryKey: ["admin-coaches-search", search], queryFn: () => fetchAdminCoaches(search, 1), enabled: enabled && kind === "coach",
  });
  const stadiums = useQuery({
    queryKey: ["admin-stadiums-search", search], queryFn: () => fetchAdminStadiums(search, 1), enabled: enabled && kind === "stadium",
  });
  const muses = useQuery({ queryKey: ["admin-muses"], queryFn: fetchAdminMuses, enabled: kind === "muse" });
  if (kind === "player") {
    return (players.data?.items ?? []).map((p) => ({
      id: p.id, player: p,
      label: `${p.display_name} · ${p.rating} · ${p.position} · ${p.rarity}${p.is_pack_droppable === false ? " · лимитка" : ""}${p.is_active === false ? " · выключена" : ""}`,
    }));
  }
  if (kind === "coach") return (coaches.data?.items ?? []).map((c) => ({ id: c.id, player: undefined, label: `${c.display_name} · ${c.rarity}` }));
  if (kind === "stadium") return (stadiums.data?.items ?? []).map((s) => ({ id: s.id, player: undefined, label: `${s.display_name} · ${s.rarity}` }));
  const q = search.toLowerCase();
  return (muses.data?.muses ?? [])
    .filter((m) => m.id && (!q || m.name.toLowerCase().includes(q)))
    .map((m) => ({ id: m.id!, player: undefined, label: `${m.icon} ${m.name} · ${m.rarity}` }));
}

function OfferForm({ draft, onChange, onSave, onCancel, busy }: {
  draft: Draft; onChange: (d: Draft) => void; onSave: () => void; onCancel: () => void; busy: boolean;
}) {
  const [search, setSearch] = useState("");
  const found = useCandidates(draft.kind, search);
  const chosenId = draft[KIND_ID[draft.kind]];
  const set = (patch: Partial<Draft>) => onChange({ ...draft, ...patch });
  const numOrNull = (v: string) => (v ? Number(v) : null);

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-accent-lime/20 bg-bg-base p-3">
      {!draft.id && (
        <div className="flex gap-1">
          {(Object.keys(KIND_LABELS) as Kind[]).map((k) => (
            <button
              key={k}
              onClick={() => onChange({ ...draft, kind: k, label: undefined, player: undefined, [KIND_ID[draft.kind]]: null })}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${draft.kind === k ? "bg-accent-lime text-bg-base" : "bg-white/5 text-slate-400"}`}
            >
              {KIND_LABELS[k]}
            </button>
          ))}
        </div>
      )}
      {chosenId ? (
        <div className="flex items-center justify-between text-sm">
          <span><b>{KIND_LABELS[draft.kind]}:</b> {draft.label ?? `#${chosenId}`}</span>
          <button onClick={() => set({ label: undefined, player: undefined, [KIND_ID[draft.kind]]: null })} className="text-xs text-slate-400 underline">
            сменить
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          <input
            placeholder={draft.kind === "muse" ? "Имя музы (можно пусто — все)" : "Найти по имени (от 2 букв)"}
            value={search} onChange={(e) => setSearch(e.target.value)} className={input}
          />
          <div className="flex max-h-48 flex-col overflow-y-auto">
            {found.map((c) => (
              <button key={c.id} onClick={() => set({ label: c.label, player: c.player, [KIND_ID[draft.kind]]: c.id })}
                className="rounded px-2 py-1 text-left text-xs hover:bg-white/5">
                {c.label}
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
        <button onClick={onSave} disabled={busy || !chosenId} className="rounded-lg bg-accent-lime px-4 py-2 text-sm font-bold text-bg-base disabled:opacity-40">
          Сохранить
        </button>
        <button onClick={onCancel} className="rounded-lg px-4 py-2 text-sm text-slate-400">Отмена</button>
      </div>
    </div>
  );
}
