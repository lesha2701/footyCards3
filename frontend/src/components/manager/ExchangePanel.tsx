import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import {
  buyBackManagerShares,
  buyManagerBond,
  fetchManagerExchange,
  floatManagerShares,
  issueManagerBond,
  listManagerShares,
  repayManagerBond,
  tradeManagerShares,
  type ManagerBondRow,
  type ManagerExchange,
  type ManagerStockRow,
} from "@/api/manager";
import exchangeArt from "@/assets/manager/exchange.webp";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { ListSkeleton } from "@/components/common/Skeleton";
import Emblem from "@/components/manager/Emblem";
import { eur } from "@/lib/managerMoney";
import { hapticNotify } from "@/lib/telegram";

type Tab = "market" | "ipo" | "portfolio" | "bonds";
type Ask = (title: string, text: string, run: () => void, label?: string) => void;

const pct = (n: number) => `${Number.isInteger(n) ? n : n.toFixed(1).replace(".", ",")}%`;

/** «📈 Биржа» of «Кабинет президента»: clubs' shares (IPO, trading through
 * the exchange, dividends, buyback) and bonds. The price follows the club's
 * form only — trading never moves it. */
export default function ExchangePanel({ onError }: { onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "exchange"], queryFn: fetchManagerExchange });
  const [tab, setTab] = useState<Tab>("market");
  const [confirm, setConfirm] = useState<{ title: string; text: string; label: string; run: () => void } | null>(null);
  const done = (x: ManagerExchange) => {
    hapticNotify("success");
    queryClient.setQueryData(["manager", "exchange"], x);
    void queryClient.invalidateQueries({ queryKey: ["manager", "office"] });
    void queryClient.invalidateQueries({ queryKey: ["manager"], exact: true });
  };
  const run = useMutation({ mutationFn: (fn: () => Promise<ManagerExchange>) => fn(), onSuccess: done, onError });
  if (!data) return <ListSkeleton />;
  const ask: Ask = (title, text, go, label = "Да") => setConfirm({ title, text, label, run: go });
  const act = (fn: () => Promise<ManagerExchange>) => run.mutate(fn);
  const tabs: [Tab, string][] = [["market", "📈 Рынок"], ["ipo", "🏛 Мой клуб"], ["portfolio", "💰 Портфель"], ["bonds", "📜 Облигации"]];
  return (
    <div className="flex flex-col gap-3" data-testid="exchange-panel">
      <Ticker x={data} />
      <div className="grid grid-cols-2 gap-1 rounded-2xl bg-bg-surface p-1">
        {tabs.map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`rounded-xl py-2 text-xs font-bold ${tab === id ? "bg-gradient-to-r from-emerald-300 to-cyan-300 text-bg-base" : "text-ink-mist"}`}>
            {label}
          </button>
        ))}
      </div>
      {!data.enabled && <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-caption text-amber-200">Биржа сейчас закрыта.</p>}
      {tab === "market" && <Market x={data} busy={run.isPending} ask={ask} act={act} />}
      {tab === "market" && <Tape x={data} />}
      {tab === "ipo" && <MyStock x={data} busy={run.isPending} ask={ask} act={act} />}
      {tab === "portfolio" && <Portfolio x={data} />}
      {tab === "bonds" && <Bonds x={data} busy={run.isPending} ask={ask} act={act} />}
      <ConfirmDialog
        open={!!confirm} title={confirm?.title ?? ""} description={confirm?.text} confirmLabel={confirm?.label ?? "Да"}
        onConfirm={() => { confirm?.run(); setConfirm(null); }} onCancel={() => setConfirm(null)}
      />
    </div>
  );
}

// --- pieces -------------------------------------------------------------------------------------

function Ticker({ x }: { x: ManagerExchange }) {
  const top = x.market.slice(0, 6);
  return (
    <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#06281f] via-[#0b1f33] to-[#1c0f33] p-4 ring-1 ring-emerald-300/30">
      <img src={exchangeArt} alt="" className="pointer-events-none absolute -right-2 -top-3 h-28 w-28 object-cover [mask-image:radial-gradient(circle,black_52%,transparent_72%)]" />
      <p className="relative text-micro font-bold uppercase tracking-[0.2em] text-emerald-300">📈 Биржа клубов</p>
      <p className="relative mt-1 max-w-[65%] text-caption text-ink-mist">Цена акции — стоимость клуба × форма. Меняется после каждого тура.</p>
      <div className="relative mt-3 grid grid-cols-2 gap-2 text-center">
        <span className="rounded-xl bg-black/30 px-2 py-2 ring-1 ring-white/5">
          <b className="block font-display text-sm text-accent-lime">{eur(x.free_budget)}</b>
          <span className="block text-micro text-ink-mist">свободно</span>
        </span>
        <span className="rounded-xl bg-black/30 px-2 py-2 ring-1 ring-white/5">
          <b className="block font-display text-sm text-cyan-200">{x.market.length}</b>
          <span className="block text-micro text-ink-mist">клубов на бирже</span>
        </span>
      </div>
      {top.length > 0 && (
        <div className="relative mt-3 flex gap-1.5 overflow-x-auto pb-1">
          {top.map((s) => (
            <span key={s.club_id} className="shrink-0 rounded-full bg-black/30 px-2.5 py-1 text-micro text-ink-chalk ring-1 ring-white/10">
              {s.name.slice(0, 10)} <b>{eur(s.price)}</b> <Change pct={s.change_pct} />
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function Change({ pct: p }: { pct: number | null }) {
  if (p == null) return <span className="text-ink-mist">•</span>;
  return <span className={p >= 0 ? "text-emerald-300" : "text-red-300"}>{p >= 0 ? "▲" : "▼"}{Math.abs(p).toFixed(1).replace(".", ",")}%</span>;
}

function Spark({ points, className = "h-8 w-20" }: { points: number[]; className?: string }) {
  if (points.length < 2) return <span className={`${className} block rounded bg-white/5`} />;
  const lo = Math.min(...points), hi = Math.max(...points), span = hi - lo || 1;
  const path = points.map((p, i) => `${(i / (points.length - 1)) * 100},${30 - ((p - lo) / span) * 26 - 2}`).join(" ");
  const up = points[points.length - 1] >= points[0];
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className={className} aria-hidden>
      <polyline points={`0,30 ${path} 100,30`} fill={up ? "rgba(52,211,153,0.15)" : "rgba(248,113,113,0.15)"} stroke="none" />
      <polyline points={path} fill="none" stroke={up ? "#34d399" : "#f87171"} strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Card({ title, children }: { title?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      {title && <h2 className="mb-2 font-display text-base font-bold text-ink-chalk">{title}</h2>}
      {children}
    </section>
  );
}

function Slider({ label, value, min, max, step = 1, onChange, show }: {
  label: string; value: number; min: number; max: number; step?: number; onChange: (n: number) => void; show: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-ink-mist">
      <span className="flex justify-between">{label} <b className="text-ink-chalk">{show}</b></span>
      <input type="range" min={min} max={Math.max(min, max)} step={step} value={Math.min(Math.max(value, min), Math.max(min, max))}
        onChange={(e) => onChange(Number(e.target.value))} disabled={max < min} />
    </label>
  );
}

const btn = "rounded-xl py-2.5 text-sm font-bold disabled:opacity-40";

// --- market -------------------------------------------------------------------------------------

function Market({ x, busy, ask, act }: { x: ManagerExchange; busy: boolean; ask: Ask; act: (fn: () => Promise<ManagerExchange>) => void }) {
  const [open, setOpen] = useState<number | null>(null);
  const rows = x.market.filter((s) => !s.mine);
  if (rows.length === 0) {
    return <Card><p className="text-caption text-ink-mist">На бирже пока никого. Выведи свой клуб на IPO во вкладке «Мой клуб» — и стань первым.</p></Card>;
  }
  return (
    <div className="flex flex-col gap-2">
      {rows.map((s) => (
        <div key={s.club_id} className="rounded-2xl bg-bg-surface p-3">
          <button onClick={() => setOpen(open === s.club_id ? null : s.club_id)} className="flex w-full items-center gap-2 text-left">
            <Emblem look={s.look} size={34} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-ink-chalk">{s.name}</span>
              <span className="block truncate text-micro text-ink-mist">
                {s.division_name} · на бирже {s.available}
              </span>
              {s.held > 0 && <span className="mt-0.5 inline-block rounded-full bg-cyan-300/15 px-2 text-micro font-bold text-cyan-200">у тебя {s.held}</span>}
            </span>
            <Spark points={s.history} className="h-8 w-16" />
            <span className="shrink-0 whitespace-nowrap text-right">
              <b className="block font-display text-sm text-accent-lime">{eur(s.price)}</b>
              <span className="block text-micro"><Change pct={s.change_pct} /></span>
            </span>
          </button>
          {open === s.club_id && <TradeForm s={s} x={x} busy={busy} ask={ask} act={act} />}
        </div>
      ))}
    </div>
  );
}

/** What `n` shares cost walking the offers cheapest first, and how much goes to the issuing club. */
function fill(offers: ManagerStockRow["offers"], n: number) {
  let left = n, cost = 0, toClub = 0, toHolders = 0;
  for (const o of offers) {
    const take = Math.min(left, o.shares);
    if (take <= 0) break;
    cost += take * o.price;
    if (o.kind === "ipo") toClub += take * o.price;
    if (o.kind === "ask") toHolders += take * o.price;
    left -= take;
  }
  return { cost, toClub, toHolders };
}

const OFFER_KIND: Record<ManagerStockRow["offers"][number]["kind"], string> = {
  ask: "👤 продаёт клуб", ipo: "🔔 IPO — деньги клубу", pool: "🏦 биржа",
};

function TradeForm({ s, x, busy, ask, act }: { s: ManagerStockRow; x: ManagerExchange; busy: boolean; ask: Ask; act: (fn: () => Promise<ManagerExchange>) => void }) {
  const fee = x.rules.exchange_fee_pct;
  const room = Math.max(0, Math.min(s.available, s.holder_cap - s.held));
  let canBuy = 0;
  while (canBuy < room && fill(s.offers, canBuy + 1).cost * (1 + fee / 100) <= x.free_budget) canBuy++;
  const [n, setN] = useState(Math.min(10, canBuy) || 1);
  const [m, setM] = useState(Math.min(10, s.held) || 1);
  const [mode, setMode] = useState<"now" | "ask">("ask");
  const [price, setPrice] = useState(s.ask || s.price);
  const f = fill(s.offers, n);
  const cost = Math.round(f.cost * (1 + fee / 100));
  const gets = Math.round(m * s.bid * (1 - fee / 100));
  const step = Math.max(1, Math.round(s.price / 100));
  return (
    <div className="mt-3 flex flex-col gap-2.5 rounded-xl bg-bg-raised p-3">
      <p className="text-micro text-ink-mist">
        Капитализация {eur(s.cap)} · выпущено {s.floated} из 1000 · дивиденды за всё время {eur(s.dividends_paid)}.
        В одних руках — до {s.holder_cap} акций, комиссия {pct(fee)}.
      </p>
      {s.offers.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-lg bg-bg-base/40 p-2 text-micro" data-testid="offers">
          {s.offers.slice(0, 4).map((o, i) => (
            <li key={i} className="flex justify-between text-ink-mist">
              <span>{OFFER_KIND[o.kind]}</span><span><b className="text-ink-chalk">{o.shares}</b> × {eur(o.price)}</span>
            </li>
          ))}
        </ul>
      )}
      {canBuy > 0 ? (
        <>
          <Slider label="Купить акций" value={n} min={1} max={canBuy} onChange={setN} show={`${n} · ${eur(cost)}`} />
          <button disabled={busy} className={`${btn} bg-gradient-to-r from-emerald-300 to-lime-300 text-bg-base`}
            onClick={() => ask(`Купить ${n} акций «${s.name}»?`,
              `${eur(cost)} с комиссией. Самые дешёвые предложения — первыми.`
              + (f.toClub ? ` Клубу «${s.name}» достанется ${eur(f.toClub)}.` : "")
              + (f.toHolders ? ` Продавцам-клубам — ${eur(f.toHolders)}.` : ""),
              () => act(() => tradeManagerShares(s.club_id, "buy", n)), "Купить")}>
            Купить · {eur(cost)}
          </button>
        </>
      ) : (
        <p className="text-micro text-amber-200">
          {s.available === 0 ? "Сейчас никто не продаёт." : s.held >= s.holder_cap ? "У тебя максимум акций этого клуба." : "Не хватает свободного бюджета."}
        </p>
      )}
      {s.held > 0 && (
        <>
          <div className="grid grid-cols-2 gap-1 rounded-xl bg-bg-base/40 p-1">
            {([["ask", "📋 Заявка"], ["now", "⚡ Бирже сразу"]] as const).map(([id, label]) => (
              <button key={id} onClick={() => setMode(id)}
                className={`rounded-lg py-1.5 text-xs font-bold ${mode === id ? "bg-bg-surface text-ink-chalk" : "text-ink-mist"}`}>{label}</button>
            ))}
          </div>
          <Slider label="Продать акций" value={m} min={1} max={s.held} onChange={setM}
            show={mode === "now" ? `${m} · +${eur(gets)}` : `${m} · ≈+${eur(Math.round(m * price * (1 - fee / 100)))}`} />
          {mode === "ask" ? (
            <>
              <Slider label="Цена за акцию" value={price} min={s.band[0]} max={s.band[1]} step={step} onChange={setPrice}
                show={`${eur(price)} (${price >= s.price ? "+" : ""}${(((price - s.price) / s.price) * 100).toFixed(0)}%)`} />
              <p className="text-micro text-ink-mist">
                Деньги придут, когда другой клуб купит. Чем ближе к цене биржи ({eur(s.price)}), тем быстрее.
                {s.listed > 0 && <b className="text-cyan-200"> Сейчас в заявке: {s.listed} по {eur(s.ask)}.</b>}
              </p>
              <div className="flex gap-2">
                <button disabled={busy} className={`${btn} flex-1 bg-gradient-to-r from-cyan-300 to-sky-400 text-bg-base`}
                  onClick={() => act(() => listManagerShares(s.club_id, m, price))}>
                  {s.listed > 0 ? "Обновить заявку" : "Выставить"}
                </button>
                {s.listed > 0 && (
                  <button disabled={busy} className={`${btn} bg-bg-surface px-3 text-ink-mist`} onClick={() => act(() => listManagerShares(s.club_id, 0, 0))}>
                    Снять
                  </button>
                )}
              </div>
            </>
          ) : (
            <button disabled={busy} className={`${btn} bg-bg-surface text-red-200 ring-1 ring-red-300/30`}
              onClick={() => ask(`Продать ${m} акций «${s.name}» бирже?`,
                `Сразу по ${eur(s.bid)} (на ${pct(x.rules.exchange_spread_pct)} ниже цены), минус комиссия: +${eur(gets)}.`,
                () => act(() => tradeManagerShares(s.club_id, "sell", m)), "Продать")}>
              Продать сейчас · +{eur(gets)}
            </button>
          )}
        </>
      )}
    </div>
  );
}

// --- tape ---------------------------------------------------------------------------------------

const SIDE: Record<ManagerExchange["tape"][number]["side"], [string, string]> = {
  ipo: ["🔔", "IPO"], buy: ["🟢", "куплено"], sell: ["🔴", "продано"], buyback: ["↩️", "выкуп"],
};

function Tape({ x }: { x: ManagerExchange }) {
  if (x.tape.length === 0) return null;
  return (
    <Card title="🧾 Сделки на бирже">
      <ul className="flex flex-col gap-1">
        {x.tape.slice(0, 12).map((t) => (
          <li key={t.id} className="flex items-center justify-between gap-2 text-caption text-ink-mist">
            <span className="truncate">{SIDE[t.side][0]} «{t.club}» · {SIDE[t.side][1]} {t.shares} акц.</span>
            <b className="shrink-0 text-ink-chalk">{eur(t.price)}</b>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// --- my stock -----------------------------------------------------------------------------------

function MyStock({ x, busy, ask, act }: { x: ManagerExchange; busy: boolean; ask: Ask; act: (fn: () => Promise<ManagerExchange>) => void }) {
  const st = x.my_stock;
  const [n, setN] = useState(Math.min(100, st.ipo_left) || 1);
  const [b, setB] = useState(Math.min(50, st.floated) || 1);
  const unsoldBack = Math.min(b, st.unsold);
  const poolBack = Math.min(b - unsoldBack, st.pool);
  const fromHolders = b - unsoldBack - poolBack;
  const backCost = poolBack * st.price + fromHolders * st.buyback_price;
  return (
    <div className="flex flex-col gap-3">
      <Card title={st.listed ? "🏛 Твой клуб на бирже" : "🔔 Выведи клуб на биржу"}>
        <div className="flex items-end justify-between gap-3">
          <span>
            <span className="block text-micro uppercase tracking-wide text-ink-mist">{st.listed ? "цена акции" : "цена на старте"}</span>
            <b className="font-display text-2xl font-black text-accent-lime">{eur(st.price)}</b>
            <span className="block text-micro text-ink-mist">капитализация {eur(st.price * st.shares_total)}</span>
          </span>
          <Spark points={st.history} className="h-12 w-28" />
        </div>
        {st.listed && (
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            {([["выпущено", st.floated], ["у инвесторов", st.held_by_others], ["на бирже", st.unsold + st.pool]] as const).map(([l, v]) => (
              <span key={l} className="rounded-xl bg-bg-base/40 p-2"><b className="block font-display text-sm text-ink-chalk">{v}</b><span className="text-micro text-ink-mist">{l}</span></span>
            ))}
          </div>
        )}
        <p className="mt-3 text-micro text-ink-mist">
          Можно выпустить до {pct(x.rules.ipo_max_pct)} акций — контроль всегда за тобой. Деньги за проданные IPO-акции идут в бюджет:
          в этом сезоне {eur(st.raised_this_season)} из {eur(st.raise_cap)}. Акционеры получают {pct(x.rules.dividend_pct)} прибыли сезона.
        </p>
        {st.ipo_left > 0 && (
          <div className="mt-3 flex flex-col gap-2">
            <Slider label={st.listed ? "Выпустить ещё" : "Выпустить акций"} value={n} min={1} max={st.ipo_left} step={10} onChange={setN}
              show={`${n} · ≈${eur(n * st.price)}`} />
            <button disabled={busy || !x.window_open} className={`${btn} bg-gradient-to-r from-amber-300 to-yellow-400 text-bg-base`}
              onClick={() => ask(`Выпустить ${n} акций?`, `Они появятся на бирже по ${eur(st.price)}. Деньги придут, когда их купят другие клубы.`,
                () => act(() => floatManagerShares(n)), "Выпустить")}>
              {st.listed ? "Выпустить ещё" : "🔔 Провести IPO"}
            </button>
          </div>
        )}
      </Card>
      {st.listed && (
        <Card title="↩️ Выкуп акций">
          <Slider label="Выкупить" value={b} min={1} max={st.floated} onChange={setB} show={`${b} · ${eur(backCost)}`} />
          <p className="mt-1 text-micro text-ink-mist">
            Сначала бесплатно снимаются непроданные ({st.unsold}), потом с биржи по {eur(st.price)} ({st.pool}),
            потом у акционеров по {eur(st.buyback_price)} (+{pct(x.rules.buyback_premium_pct)}).
          </p>
          <button disabled={busy || !x.window_open || backCost > x.free_budget}
            className={`${btn} mt-2 w-full bg-bg-raised text-ink-chalk`}
            onClick={() => ask(`Выкупить ${b} акций?`, `Обойдётся в ${eur(backCost)}.`, () => act(() => buyBackManagerShares(b)), "Выкупить")}>
            Выкупить · {eur(backCost)}
          </button>
          {st.holders.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1 text-caption text-ink-mist">
              {st.holders.map((h) => <li key={h.name} className="flex justify-between"><span>«{h.name}»</span><b className="text-ink-chalk">{h.shares} акц.</b></li>)}
            </ul>
          )}
        </Card>
      )}
      {!x.window_open && <p className="text-micro text-amber-200">IPO и выкуп — в межсезонье. Торговать чужими акциями можно всегда.</p>}
    </div>
  );
}

// --- portfolio ----------------------------------------------------------------------------------

function Portfolio({ x }: { x: ManagerExchange }) {
  const total = x.portfolio.reduce((s, p) => s + p.value, 0);
  const cost = x.portfolio.reduce((s, p) => s + p.cost, 0);
  const divs = x.portfolio.reduce((s, p) => s + p.dividends, 0);
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-3 gap-2 rounded-2xl bg-gradient-to-br from-cyan-400/15 to-emerald-400/10 p-3 text-center">
        <span><b className="block font-display text-sm text-ink-chalk">{eur(total)}</b><span className="text-micro text-ink-mist">стоит</span></span>
        <span><b className={`block font-display text-sm ${total - cost >= 0 ? "text-emerald-300" : "text-red-300"}`}>{total - cost >= 0 ? "+" : ""}{eur(total - cost)}</b><span className="text-micro text-ink-mist">прибыль</span></span>
        <span><b className="block font-display text-sm text-amber-200">{eur(divs)}</b><span className="text-micro text-ink-mist">дивиденды</span></span>
      </div>
      {x.portfolio.length === 0 ? (
        <Card><p className="text-caption text-ink-mist">Акций пока нет. Купи долю клуба, который хорошо играет, — цена растёт вместе с формой, а в конце сезона приходят дивиденды.</p></Card>
      ) : x.portfolio.map((p) => (
        <div key={p.club_id} className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3">
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-ink-chalk">«{p.name}»</span>
            <span className="block text-micro text-ink-mist">{p.shares} акц. по {eur(p.price)} · дивиденды {eur(p.dividends)}</span>
          </span>
          <span className="text-right">
            <b className="block font-display text-sm text-ink-chalk">{eur(p.value)}</b>
            <span className={`text-micro ${p.value - p.cost >= 0 ? "text-emerald-300" : "text-red-300"}`}>{p.value - p.cost >= 0 ? "+" : ""}{eur(p.value - p.cost)}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

// --- bonds --------------------------------------------------------------------------------------

const BOND_STATUS: Record<ManagerBondRow["status"], string> = {
  selling: "продаются", active: "в обращении", default: "⚠️ дефолт", repaid: "погашены",
};

function Bonds({ x, busy, ask, act }: { x: ManagerExchange; busy: boolean; ask: Ask; act: (fn: () => Promise<ManagerExchange>) => void }) {
  const r = x.rules;
  const room = Math.max(0, x.bonds.limit - x.bonds.owed);
  const maxUnits = Math.floor(room / r.bond_unit_eur);
  const [units, setUnits] = useState(Math.min(5, maxUnits) || 1);
  const [rate, setRate] = useState(Math.round((r.bond_rate_min_pct + r.bond_rate_max_pct) / 2));
  const [seasons, setSeasons] = useState(1);
  const coupon = Math.round(units * r.bond_unit_eur * rate / 100);
  return (
    <div className="flex flex-col gap-3">
      <Card title="📜 Выпустить облигации">
        <p className="mb-2 text-micro text-ink-mist">
          Заём у других клубов: купон в конце каждого сезона, номинал — в конце срока. Не заплатишь — дефолт и закрытые трансферы.
          Можно занять ещё {eur(room)} (долг {eur(x.bonds.owed)} из {eur(x.bonds.limit)}).
        </p>
        {maxUnits > 0 ? (
          <div className="flex flex-col gap-2">
            <Slider label={`Облигаций по ${eur(r.bond_unit_eur)}`} value={units} min={1} max={maxUnits} onChange={setUnits} show={`${units} · ${eur(units * r.bond_unit_eur)}`} />
            <Slider label="Купон за сезон" value={rate} min={r.bond_rate_min_pct} max={r.bond_rate_max_pct} onChange={setRate} show={`${rate}% · ${eur(coupon)}`} />
            <div className="flex gap-1.5">
              {Array.from({ length: r.bond_seasons_max }, (_, i) => i + 1).map((s) => (
                <button key={s} onClick={() => setSeasons(s)}
                  className={`flex-1 rounded-lg py-1.5 text-xs font-semibold ${seasons === s ? "bg-accent-cyan text-bg-base" : "bg-bg-raised text-ink-mist"}`}>{s} сез.</button>
              ))}
            </div>
            <p className="text-micro text-ink-mist">Чем выше купон, тем охотнее покупают. Непроданные к старту сезона сгорают.</p>
            <button disabled={busy || !x.window_open} className={`${btn} bg-gradient-to-r from-violet-300 to-cyan-300 text-bg-base`}
              onClick={() => ask("Выпустить облигации?", `${units} шт. на ${eur(units * r.bond_unit_eur)}, купон ${rate}% за сезон, ${seasons} сез.`,
                () => act(() => issueManagerBond({ units, rate_pct: rate, seasons })), "Выпустить")}>
              Выпустить
            </button>
          </div>
        ) : <p className="text-micro text-amber-200">Лимит займа исчерпан.</p>}
      </Card>
      {x.bonds.mine.length > 0 && (
        <Card title="Мои выпуски">
          {x.bonds.mine.map((b) => (
            <div key={b.id} className="flex items-center justify-between gap-2 border-b border-white/5 py-2 last:border-0">
              <span className="text-caption text-ink-mist">
                <b className="text-ink-chalk">{b.units_sold}/{b.units_total}</b> по {eur(b.unit_eur)} · {pct(b.rate_pct)} · {BOND_STATUS[b.status]}
              </span>
              {b.status === "default" && (
                <button disabled={busy} onClick={() => ask("Погасить облигации?", "Номинал и купон уйдут держателям, трансферы откроются.",
                  () => act(() => repayManagerBond(b.id)), "Погасить")}
                  className="rounded-lg bg-red-400/20 px-3 py-1.5 text-xs font-bold text-red-200">Погасить</button>
              )}
            </div>
          ))}
        </Card>
      )}
      <Card title="🛒 Облигации других клубов">
        {x.bonds.market.length === 0 ? <p className="text-caption text-ink-mist">Сейчас никто не занимает.</p> : x.bonds.market.map((b) => (
          <BondRow key={b.id} b={b} x={x} busy={busy} ask={ask} act={act} />
        ))}
      </Card>
      {x.bonds.held.length > 0 && (
        <Card title="💼 Мои облигации">
          {x.bonds.held.map((b) => (
            <p key={b.id} className="flex justify-between py-1 text-caption text-ink-mist">
              <span>«{b.name}» · {b.held} шт. · {pct(b.rate_pct)} · {BOND_STATUS[b.status]}</span>
              <b className="text-emerald-300">+{eur(b.received)}</b>
            </p>
          ))}
        </Card>
      )}
    </div>
  );
}

function BondRow({ b, x, busy, ask, act }: { b: ManagerBondRow; x: ManagerExchange; busy: boolean; ask: Ask; act: (fn: () => Promise<ManagerExchange>) => void }) {
  const can = Math.max(0, Math.min(b.units_total - b.units_sold, b.holder_cap - b.held, Math.floor(x.free_budget / b.unit_eur)));
  const [n, setN] = useState(1);
  return (
    <div className="flex flex-col gap-2 border-b border-white/5 py-2 last:border-0">
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0">
          <b className="block truncate text-sm text-ink-chalk">«{b.name}»</b>
          <span className="text-micro text-ink-mist">{b.seasons_total} сез. · продано {b.units_sold}/{b.units_total} · по {eur(b.unit_eur)}</span>
        </span>
        <span className="rounded-full bg-violet-400/20 px-2.5 py-1 font-display text-sm font-black text-violet-200">{pct(b.rate_pct)}</span>
      </div>
      {can > 0 && (
        <div className="flex items-center gap-2">
          <input type="range" min={1} max={can} value={Math.min(n, can)} onChange={(e) => setN(Number(e.target.value))} className="flex-1" />
          <button disabled={busy} onClick={() => ask(`Купить ${n} обл. «${b.name}»?`,
            `${eur(n * b.unit_eur)}. Купон ${pct(b.rate_pct)} за сезон, номинал вернётся в конце срока.`,
            () => act(() => buyManagerBond(b.id, n)), "Купить")}
            className="rounded-lg bg-violet-300 px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40">
            {n} · {eur(n * b.unit_eur)}
          </button>
        </div>
      )}
    </div>
  );
}
