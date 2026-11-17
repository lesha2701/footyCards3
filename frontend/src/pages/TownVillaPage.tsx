import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  buyVillaItem, chooseVillaCar, collectVillaIncome, createVillaInvoice, fetchTownInvoiceStatus, fetchVilla, saveVillaLayout,
  setVillaStaff, throwVillaParty, upgradeVilla, type VillaItem, type VillaShopItem, type VillaState,
} from "@/api/town";
import { IconCoin } from "@/components/icons";
import VillaPlot from "@/components/town/VillaPlot";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { hapticNotify, openTelegramInvoice } from "@/lib/telegram";
import { KIND_LABEL, cellSet, checkLayout, footprint, freeSpot, isFence, openCells, spriteOf } from "@/lib/villa";
import { useAuthStore } from "@/store/authStore";

const fmt = (n: number) => n.toLocaleString("ru-RU");
type Tab = "plot" | "shop" | "staff" | "garage";

/** «Моя вилла» (/town/villa): the player's own plot — place, turn and store
 * things, buy them, level the villa and the garage, hire residents. */
export default function TownVillaPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [tab, setTab] = useState<Tab>("plot");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const { data, error } = useQuery({ queryKey: ["town-villa"], queryFn: fetchVilla });

  const apply = (text?: string) => (res: VillaState | null) => {
    if (!res) return;
    hapticNotify("success");
    if (res.new_balance != null) updateBalance(res.new_balance);
    queryClient.setQueryData(["town-villa"], res);
    void queryClient.invalidateQueries({ queryKey: ["town"] });
    if (text) setMessage({ ok: true, text });
  };
  const fail = (err: unknown) => { hapticNotify("error"); setMessage({ ok: false, text: formatGameError(err, "Не получилось") }); };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 px-1">
        <span className="text-4xl" aria-hidden>🏡</span>
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-display text-xl font-bold leading-tight text-ink-chalk">Моя вилла</h1>
          <p className="truncate text-xs text-ink-mist">
            {data ? `Престиж ${fmt(data.prestige)} · +${data.prestige_pct}% к ренте · ❤️ ${fmt(data.likes_total)}` : "Загрузка…"}
          </p>
        </div>
        <Link to="/town" className="shrink-0 rounded-full bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist">🏘️ Город</Link>
      </div>
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{formatGameError(error, "Вилла не открылась")}</p>}
      {message && (
        <p className={`rounded-xl px-3 py-2 text-xs ${message.ok ? "bg-accent-lime/10 text-accent-lime" : "bg-red-500/10 text-red-400"}`} role="status">
          {message.text}
        </p>
      )}
      {data && (
        <>
          <VillaLife data={data} onDone={apply} onError={fail} />
          <div className="grid grid-cols-4 gap-1 rounded-2xl bg-white/5 p-1" role="tablist">
            {([["plot", "🏡 Участок"], ["shop", "🛒 Магазин"], ["staff", "👥 Персонал"], ["garage", "🚗 Гараж"]] as [Tab, string][]).map(([key, title]) => (
              <button
                key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => { setTab(key); setMessage(null); }}
                className={`min-h-[40px] rounded-xl text-[11px] font-bold ${tab === key ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
              >
                {title}
              </button>
            ))}
          </div>
          {tab === "plot" && <PlotEditor data={data} onSaved={apply()} onError={fail} />}
          {tab === "shop" && <Shop data={data} onDone={apply} onError={fail} />}
          {tab === "staff" && <Staff data={data} onDone={apply} onError={fail} />}
          {tab === "garage" && <Garage data={data} onDone={apply} onError={fail} />}
        </>
      )}
    </div>
  );
}

type Placement = { id: number; x: number; y: number; rot: number };
type TrayTab = "home" | "yard" | "car" | "premium";

/** The plot, SimCity-like: the «Строить» tray under it (buy or take from
 * storage → the thing lands on a free spot, drag it, ↻ turn, ✓ put), a tap on
 * a standing thing → ↻ / 📦 / drag. Every move is saved at once. */
function PlotEditor({ data, onSaved, onError }: { data: VillaState; onSaved: (res: VillaState) => void; onError: (e: unknown) => void }) {
  const [selected, setSelected] = useState<number | null>(null);
  const [pending, setPending] = useState<Placement | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [popped, setPopped] = useState<number | null>(null);
  const [tray, setTray] = useState<TrayTab>("yard");
  const cells = useMemo(() => openCells(data.cells_open), [data.cells_open]);
  const room = useMemo(() => cellSet(cells), [cells]);
  const items: VillaItem[] = useMemo(
    () => data.items.map((i) => (pending?.id === i.id ? { ...i, x: pending.x, y: pending.y, rot: pending.rot } : i)),
    [data.items, pending],
  );
  const comboIds = useMemo(() => new Set((data.combos ?? []).flatMap((c) => c.ids)), [data.combos]);
  const current = items.find((i) => i.id === (pending?.id ?? selected)) ?? null;
  const fits = (id: number, x: number, y: number, rot: number) =>
    checkLayout(room, items.map((i) => (i.id === id ? { ...i, x, y, rot } : i))) === null;

  const save = useMutation({
    mutationFn: (move: Placement | { id: number; x: null; y: null; rot: number }) => saveVillaLayout([move]),
    onSuccess: (res, move) => {
      setPending(null);
      if (move.x != null) setPopped(move.id);
      onSaved(res);
    },
    onError,
  });
  const put = (move: Placement) => {
    if (!fits(move.id, move.x, move.y, move.rot)) {
      hapticNotify("error");
      setHint("Сюда не встанет — клетки заняты или за краем");
      return;
    }
    setHint(null);
    save.mutate(move);
  };
  /** A thing from storage lands on the nearest free spot, waiting for ✓. */
  const startPlacing = (item: VillaItem, all: VillaItem[]) => {
    const spot = freeSpot(cells, all.map((i) => (i.id === item.id ? { ...i, rot: 0 } : i)), item.id);
    setSelected(null);
    setPending({ id: item.id, x: spot?.[0] ?? 0, y: spot?.[1] ?? 0, rot: 0 });
    setHint(spot ? "Тащи на нужное место и нажми ✓" : "Места нет — убери что-нибудь на склад");
  };

  const buy = useMutation({
    mutationFn: (s: VillaShopItem) => (s.stars ? payWithStars(s.code) : buyVillaItem(s.code, crypto.randomUUID())),
    onSuccess: (res, s) => {
      if (!res) return;
      onSaved(res);
      const fresh = res.items.filter((i) => i.code === s.code && i.x == null).pop();
      if (fresh) startPlacing(fresh, res.items);
    },
    onError,
  });
  const upgrade = useMutation({
    mutationFn: (target: "villa" | "garage") => upgradeVilla(target, crypto.randomUUID()),
    onSuccess: (res) => onSaved(res),
    onError,
  });
  const pick = (s: VillaShopItem) => {
    const stored = data.items.find((i) => i.code === s.code && i.x == null);
    if (stored) { startPlacing(stored, data.items); return; }
    if (!s.can_buy) { hapticNotify("error"); setHint(s.reason || "Пока нельзя"); return; }
    buy.mutate(s);
  };

  const onCell = (x: number, y: number) => {
    if (pending) { setPending({ ...pending, x, y }); return; }
    setSelected(null);
    setHint(null);
  };
  const onItem = (item: VillaItem) => {
    if (pending) return;
    setSelected(item.id === selected ? null : item.id);
    setHint(null);
  };
  const onDrop = (id: number, x: number, y: number) => {
    if (pending?.id === id) { setPending({ ...pending, x, y }); return; }
    const item = items.find((i) => i.id === id);
    if (item) { setSelected(id); put({ id, x, y, rot: item.rot }); }
  };
  const turn = () => {
    if (!current || current.x == null || current.y == null) return;
    const rot = current.rot ? 0 : 1;
    if (pending) { setPending({ ...pending, rot }); return; }
    put({ id: current.id, x: current.x, y: current.y, rot });
  };
  const [cw, ch] = current ? footprint(current) : [1, 1];
  const pendingOk = pending ? fits(pending.id, pending.x, pending.y, pending.rot) : false;
  const busy = save.isPending || buy.isPending || upgrade.isPending;
  const shop = data.shop.filter((s) => s.kind === tray);

  return (
    <section className="flex flex-col gap-2">
      <div className="relative overflow-hidden rounded-3xl border border-white/10">
        <VillaPlot
          open={data.cells_open}
          items={items}
          selectedId={pending?.id ?? selected}
          onCell={onCell}
          onItem={onItem}
          onDrop={onDrop}
          canPlace={(id, x, y) => fits(id, x, y, items.find((i) => i.id === id)?.rot ?? 0)}
          poppedId={popped}
          comboIds={comboIds}
          mark={pending ? { x: pending.x, y: pending.y, w: cw, h: ch, ok: pendingOk } : null}
          showGrid={Boolean(pending || selected)}
          label={`Участок: ${data.cells_open} клеток`}
        />
        {current && (
          <div className="absolute inset-x-2 bottom-2 flex items-center gap-2 rounded-2xl bg-black/70 p-2 backdrop-blur" data-testid="villa-actions">
            <span className="min-w-0 flex-1 truncate text-xs font-bold text-white">{current.emoji} {current.name}</span>
            <button type="button" onClick={turn} disabled={busy} aria-label={isFence(current.code) ? "Калитка" : "Повернуть"} className="h-11 w-11 rounded-xl bg-white/15 text-lg text-white">{isFence(current.code) ? "🚪" : "↻"}</button>
            {pending ? (
              <>
                <button type="button" onClick={() => { setPending(null); setHint(null); }} aria-label="Отмена" className="h-11 w-11 rounded-xl bg-white/15 text-lg text-white">✕</button>
                <button
                  type="button" onClick={() => put(pending)} disabled={!pendingOk || busy} aria-label="Поставить"
                  className="h-11 rounded-xl bg-accent-lime px-4 text-sm font-bold text-bg-base disabled:opacity-40"
                >
                  ✓ Поставить
                </button>
              </>
            ) : (
              <>
                {current.kind !== "villa" && current.kind !== "garage" && (
                  <button
                    type="button" aria-label="На склад" disabled={busy}
                    onClick={() => { save.mutate({ id: current.id, x: null, y: null, rot: current.rot }); setSelected(null); }}
                    className="h-11 w-11 rounded-xl bg-white/15 text-lg text-white"
                  >
                    📦
                  </button>
                )}
                <button type="button" onClick={() => setSelected(null)} aria-label="Готово" className="h-11 w-11 rounded-xl bg-white/15 text-lg text-white">✓</button>
              </>
            )}
          </div>
        )}
      </div>
      <p className="px-1 text-center text-[11px] text-ink-mist" role="status">
        {hint ?? (current ? (isFence(current.code) ? "Ставь секции рядом — забор соединится сам, 🚪 — калитка" : "Тащи пальцем, ↻ — повернуть") : "Выбери внизу, что построить. Нажми на предмет на участке, чтобы двигать")}
      </p>
      <div className="rounded-2xl border border-white/10 bg-bg-surface p-2" aria-label="Строить">
        <div className="mb-2 grid grid-cols-4 gap-1">
          {([["home", "🏡 Дом"], ["yard", "🌴 Двор"], ["car", "🚗 Машины"], ["premium", "⭐ Премиум"]] as [TrayTab, string][]).map(([key, title]) => (
            <button
              key={key} type="button" onClick={() => setTray(key)} aria-pressed={tray === key}
              className={`min-h-[36px] rounded-xl text-[11px] font-bold ${tray === key ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
            >
              {title}
            </button>
          ))}
        </div>
        <div className="-mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1">
          {tray === "home" ? (
            <>
              <BuildCard
                art={spriteOf({ code: "villa", level: Math.min(5, data.villa_level + 1) })} emoji="🏡"
                title={data.next_villa ? `Вилла ${data.next_villa.level} ур.` : "Вилла · макс."}
                sub={data.next_villa ? `участок ${data.next_villa.cells} клеток` : `${data.villa_level} ур.`}
                price={data.next_villa ? <><IconCoin size={11} /> {fmt(data.next_villa.price)}</> : null}
                disabled={!data.next_villa || busy} onTap={() => upgrade.mutate("villa")}
              />
              <BuildCard
                art={spriteOf({ code: "garage", level: Math.min(3, data.garage_level + 1) })} emoji="🅿️"
                title={data.next_garage ? (data.garage_level ? `Гараж ${data.next_garage.level} ур.` : "Построить гараж") : "Гараж · макс."}
                sub={data.next_garage ? `мест ${data.next_garage.slots}` : `${data.garage_level} ур.`}
                price={data.next_garage ? <><IconCoin size={11} /> {fmt(data.next_garage.price)}</> : null}
                disabled={!data.next_garage || busy} onTap={() => upgrade.mutate("garage")}
              />
            </>
          ) : shop.map((s) => {
            const stored = data.items.filter((i) => i.code === s.code && i.x == null).length;
            return (
              <BuildCard
                key={s.code} art={spriteOf({ code: s.code, level: null })} emoji={s.emoji} title={s.name}
                sub={stored ? `📦 на складе: ${stored}` : `${s.w}×${s.h} · +${s.prestige} престижа`}
                price={stored ? "Поставить" : s.stars ? `⭐ ${fmt(s.stars)}` : s.coins ? <><IconCoin size={11} /> {fmt(s.coins)}</> : null}
                dim={!stored && !s.can_buy} disabled={busy} onTap={() => pick(s)}
              />
            );
          })}
        </div>
      </div>
      <Combos data={data} />
    </section>
  );
}

function BuildCard({ art, emoji, title, sub, price, disabled, dim, onTap }: {
  art?: string; emoji: string; title: string; sub: string; price: ReactNode; disabled?: boolean; dim?: boolean; onTap: () => void;
}) {
  return (
    <button
      type="button" onClick={onTap} disabled={disabled} aria-label={title}
      className={`flex w-[104px] shrink-0 snap-start flex-col items-center gap-1 rounded-2xl bg-white/5 p-2 text-center ${dim ? "opacity-50" : ""} disabled:opacity-40`}
    >
      <span className="grid h-16 w-full place-items-center">
        {art ? <img src={art} alt="" className="max-h-16 max-w-full object-contain" /> : <span className="text-3xl">{emoji}</span>}
      </span>
      <span className="line-clamp-2 min-h-[28px] text-[11px] font-bold leading-tight text-ink-chalk">{title}</span>
      <span className="line-clamp-1 text-[9px] text-ink-mist">{sub}</span>
      {price && <span className="flex items-center gap-0.5 rounded-lg bg-floodlight px-2 py-0.5 text-[10px] font-bold text-bg-base">{price}</span>}
    </button>
  );
}

/** Combos standing now and the ones still to build (two things side by side). */
const timeOf = (iso: string) => new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });

/** «Вилла в игре»: the daily income, the week's party and what the buildings
 * give in other modes (one perk a kind — two pitches are still one). */
function VillaLife({ data, onDone, onError }: Handlers) {
  const [open, setOpen] = useState(false);
  const income = useMutation({
    mutationFn: collectVillaIncome,
    onSuccess: (res) => onDone(res.income_paid ? `Доход виллы: +${fmt(res.income_paid)} монет` : "Доход забран")(res),
    onError,
  });
  const party = useMutation({
    mutationFn: throwVillaParty,
    onSuccess: (res) => onDone("Вечеринка началась — гости, которые лайкнут виллу, получат монеты 🎉")(res),
    onError,
  });
  const active = new Set((data.perks ?? []).map((p) => p.code));
  const all = data.all_perks ?? [];
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-bg-surface p-3" aria-label="Вилла в игре">
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button" disabled={!data.income.ready || income.isPending} onClick={() => income.mutate()}
          className={`flex min-h-[52px] flex-col items-center justify-center rounded-xl px-2 text-center ${data.income.ready ? "bg-amber-400 text-bg-base" : "bg-white/5 text-ink-mist"}`}
        >
          <span className="flex items-center gap-1 text-sm font-bold">💰 {data.income.ready ? <>+{fmt(data.income.coins)} <IconCoin size={12} /></> : "Забрано"}</span>
          <span className="text-[10px] opacity-80">{data.income.ready ? "доход виллы за сегодня" : "завтра снова"}</span>
        </button>
        <button
          type="button" disabled={!data.party.can_throw || party.isPending} onClick={() => party.mutate()}
          className={`flex min-h-[52px] flex-col items-center justify-center rounded-xl px-2 text-center ${data.party.can_throw ? "bg-fuchsia-500 text-white" : "bg-white/5 text-ink-mist"}`}
        >
          <span className="flex items-center gap-1 text-sm font-bold">
            🎉 {data.party_until ? `до ${timeOf(data.party_until)}` : data.party.can_throw ? "Вечеринка" : "Была"}
          </span>
          <span className="flex items-center gap-0.5 text-[10px] opacity-80">
            {data.party_until ? "вечеринка идёт" : data.party.can_throw
              ? <>{fmt(data.party.cost)} <IconCoin size={9} /> · гостям +{fmt(data.party.guest_coins)} за лайк</>
              : "следующая с понедельника"}
          </span>
        </button>
      </div>
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex items-center justify-between text-left">
        <span className="text-xs font-bold text-ink-chalk">🎯 Бонусы в игре · {active.size} из {all.length}</span>
        <span className="text-[10px] text-ink-mist">{open ? "▲" : "▼"}</span>
      </button>
      {(data.perks ?? []).length > 0 && !open && (
        <div className="flex flex-wrap gap-1">
          {data.perks.map((p) => (
            <span key={p.code} className="rounded-full bg-accent-lime/15 px-2 py-0.5 text-[11px] font-semibold text-accent-lime">{p.emoji} {p.text}</span>
          ))}
        </div>
      )}
      {open && (
        <ul className="flex flex-col gap-1.5">
          {all.map((p) => (
            <li key={p.code} className={`text-[11px] leading-snug ${active.has(p.code) ? "text-accent-lime" : "text-ink-mist"}`}>
              {active.has(p.code) ? "✓" : "·"} {p.emoji} <b>{p.name}</b>: {p.text}. Даёт: {p.buildings.join(" или ")} на участке
            </li>
          ))}
          <li className="text-[10px] text-ink-mist">Каждый бонус работает один раз, даже если таких зданий несколько. Со склада бонуса нет.</li>
        </ul>
      )}
    </section>
  );
}

function Combos({ data }: { data: VillaState }) {
  const [open, setOpen] = useState(false);
  const done = new Set((data.combos ?? []).map((c) => `${c.a}:${c.b}`));
  const all = data.all_combos ?? [];
  return (
    <div className="rounded-2xl border border-white/10 bg-bg-surface p-3" aria-label="Комбо">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between text-left">
        <span className="text-xs font-bold text-ink-chalk">✨ Комбо · {done.size} из {all.length}</span>
        <span className="text-[10px] text-ink-mist">+{data.prestige_combo} престижа за каждое {open ? "▲" : "▼"}</span>
      </button>
      {(data.combos ?? []).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {data.combos.map((c) => (
            <span key={`${c.a}:${c.b}`} className="rounded-full bg-accent-lime/15 px-2 py-0.5 text-[11px] font-semibold text-accent-lime">{c.emoji} {c.name}</span>
          ))}
        </div>
      )}
      {open && (
        <ul className="mt-2 flex flex-col gap-1">
          {all.map((c) => (
            <li key={`${c.a}:${c.b}`} className={`text-[11px] ${done.has(`${c.a}:${c.b}`) ? "text-accent-lime" : "text-ink-mist"}`}>
              {done.has(`${c.a}:${c.b}`) ? "✓" : "·"} {c.emoji} {c.name}: {c.a_name} рядом с «{c.b_name}»
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

async function payWithStars(code: string): Promise<VillaState | null> {
  const invoice = await createVillaInvoice(code);
  const status = await openTelegramInvoice(invoice.invoice_link, invoice.payload_token);
  if (status === "cancelled") return null;
  if (status === "failed") throw new Error("Платёж не прошёл");
  for (let i = 0; i < 20; i++) {
    if ((await fetchTownInvoiceStatus(invoice.payload_token)).status === "completed") return fetchVilla();
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("Оплата ещё обрабатывается — загляни через минуту");
}

type Handlers = { data: VillaState; onDone: (text?: string) => (res: VillaState | null) => void; onError: (e: unknown) => void };

function Shop({ data, onDone, onError }: Handlers) {
  const buy = useMutation({
    mutationFn: (item: VillaShopItem) => (item.stars ? payWithStars(item.code) : buyVillaItem(item.code, crypto.randomUUID())),
    onSuccess: (res, item) => onDone(`«${item.name}» на складе — поставь на участок 📦`)(res),
    onError,
  });
  const upgrade = useMutation({
    mutationFn: (target: "villa" | "garage") => upgradeVilla(target, crypto.randomUUID()),
    onSuccess: (res, target) => onDone(target === "villa" ? "Вилла стала больше 🏡" : "Гараж готов 🅿️")(res),
    onError,
  });
  return (
    <section className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2">
        <UpgradeCard
          title={`🏡 Вилла · ${data.villa_level} ур.`}
          next={data.next_villa ? `${data.next_villa.level} ур. · участок ${data.next_villa.cells} клеток` : null}
          price={data.next_villa?.price ?? 0}
          busy={upgrade.isPending}
          onBuy={() => upgrade.mutate("villa")}
        />
        <UpgradeCard
          title={data.garage_level ? `🅿️ Гараж · ${data.garage_level} ур.` : "🅿️ Гаража нет"}
          next={data.next_garage ? `${data.next_garage.level} ур. · мест ${data.next_garage.slots}` : null}
          price={data.next_garage?.price ?? 0}
          busy={upgrade.isPending}
          onBuy={() => upgrade.mutate("garage")}
        />
      </div>
      {(["car", "yard", "premium"] as const).map((kind) => (
        <div key={kind} className="rounded-2xl border border-white/10 bg-bg-surface p-3">
          <p className="mb-2 text-xs font-bold text-ink-chalk">{KIND_LABEL[kind]}</p>
          <div className="flex flex-col gap-2">
            {data.shop.filter((s) => s.kind === kind).map((s) => (
              <div key={s.code} className="flex items-center gap-2">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/5 text-xl" aria-hidden>{s.emoji}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-ink-chalk">{s.name}</p>
                  <p className="truncate text-[10px] text-ink-mist">
                    {s.w}×{s.h} · престиж +{s.prestige}
                    {s.owned ? ` · у тебя ${s.owned}` : ""}
                    {s.supply ? ` · осталось ${fmt(Math.max(0, s.supply - s.sold))} из ${fmt(s.supply)}` : ""}
                    {!s.can_buy && s.reason ? ` · ${s.reason}` : ""}
                  </p>
                </div>
                <button
                  type="button" disabled={!s.can_buy || buy.isPending} onClick={() => buy.mutate(s)}
                  aria-label={`Купить: ${s.name}`}
                  className={`flex shrink-0 items-center gap-0.5 rounded-lg px-2 py-1.5 text-[11px] font-bold ${s.can_buy ? (s.stars ? "bg-sky-400 text-bg-base" : "bg-floodlight text-bg-base") : "bg-white/5 text-ink-mist"}`}
                >
                  {s.stars ? `⭐ ${fmt(s.stars)}` : <><IconCoin size={11} /> {fmt(s.coins)}</>}
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
      <p className="px-1 text-center text-[11px] text-ink-mist">
        Каждые {fmt(data.prestige_per_pct)} престижа — +1% к ренте домов города (до {data.prestige_max_pct}%). Вид предмета считается один раз.
      </p>
    </section>
  );
}

function UpgradeCard({ title, next, price, busy, onBuy }: { title: string; next: string | null; price: number; busy: boolean; onBuy: () => void }) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-white/10 bg-bg-surface p-3">
      <p className="text-xs font-bold text-ink-chalk">{title}</p>
      <p className="min-h-[28px] text-[10px] text-ink-mist">{next ? `Дальше: ${next}` : "Максимальный уровень"}</p>
      {next && (
        <button type="button" onClick={onBuy} disabled={busy} className="flex min-h-[36px] items-center justify-center gap-1 rounded-xl bg-floodlight text-xs font-bold text-bg-base">
          <IconCoin size={12} /> {fmt(price)}
        </button>
      )}
    </div>
  );
}

function Staff({ data, onDone, onError }: Handlers) {
  const hire = useMutation({
    mutationFn: ({ post, id }: { post: string; id: number | null }) => setVillaStaff(post, id),
    onSuccess: (res) => onDone()(res),
    onError,
  });
  return (
    <section className="flex flex-col gap-2">
      <p className="px-1 text-[11px] text-ink-mist">
        Жители работают на вилле по профессии. Каждый работающий даёт +{data.prestige_staff} престижа — но только если на участке стоит его рабочее место. Жителей собирают в паках и в магазине города.
      </p>
      {data.posts.map((p) => {
        const on = data.staff.find((s) => s.post === p.post);
        const fits = data.candidates.filter((c) => c.posts.includes(p.post));
        return (
          <div key={p.post} className="flex items-center gap-2 rounded-2xl border border-white/10 bg-bg-surface p-2">
            <span className="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-xl bg-white/5 text-2xl">
              {on?.resident.image_path ? <img src={staticUrl(on.resident.image_path)} alt="" className="h-full w-full object-cover" /> : p.emoji}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-bold text-ink-chalk">
                {p.emoji} {p.name}
                {on && <span className={`ml-1 text-[10px] font-semibold ${on.working ? "text-accent-lime" : "text-amber-300"}`}>{on.working ? "· работает" : "· нет рабочего места"}</span>}
              </p>
              <p className="truncate text-[10px] text-ink-mist">{p.workplace?.length ? `Рабочее место: ${p.workplace.join(" / ")}` : "Работает всегда"}</p>
              <select
                aria-label={`Пост: ${p.name}`}
                value={on?.resident.id ?? ""}
                disabled={hire.isPending || (fits.length === 0 && !on)}
                onChange={(e) => hire.mutate({ post: p.post, id: e.target.value ? Number(e.target.value) : null })}
                className="mt-1 w-full rounded-lg bg-white/5 px-2 py-1.5 text-xs text-ink-chalk"
              >
                <option value="">{fits.length ? "— свободно —" : "Нет подходящих жителей"}</option>
                {fits.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.title}</option>)}
              </select>
            </div>
          </div>
        );
      })}
    </section>
  );
}

function Garage({ data, onDone, onError }: Handlers) {
  const choose = useMutation({
    mutationFn: (id: number | null) => chooseVillaCar(id),
    onSuccess: (res) => onDone("Машина выехала в город 🚗")(res),
    onError,
  });
  const cars = data.items.filter((i) => i.kind === "car");
  return (
    <section className="flex flex-col gap-2">
      <p className="px-1 text-[11px] text-ink-mist">
        {data.garage_level
          ? `Гараж ${data.garage_level} ур. · машин ${data.cars} из ${data.garage_slots}. Выбранная машина ездит по карте твоего города — её видят гости.`
          : "Гаража пока нет — построй его в «Магазине»."}
      </p>
      {cars.map((c) => (
        <button
          key={c.id} type="button" onClick={() => choose.mutate(data.car?.id === c.id ? null : c.id)} disabled={choose.isPending}
          aria-pressed={data.car?.id === c.id}
          className={`flex min-h-[52px] items-center gap-2 rounded-2xl border p-2 text-left ${data.car?.id === c.id ? "border-floodlight bg-floodlight/10" : "border-white/10 bg-bg-surface"}`}
        >
          <span className="text-3xl" aria-hidden>{c.emoji}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-bold text-ink-chalk">{c.name}{c.serial ? ` · № ${c.serial}` : ""}</span>
            <span className="block text-[10px] text-ink-mist">{data.car?.id === c.id ? "Ездит по городу" : "Нажми, чтобы выехать в город"}</span>
          </span>
          {data.car?.id === c.id && <span className="text-sm font-bold text-floodlight">✓</span>}
        </button>
      ))}
      {data.garage_level > 0 && cars.length === 0 && <p className="px-1 text-xs text-ink-mist">Машин пока нет — загляни в «Магазин».</p>}
    </section>
  );
}
