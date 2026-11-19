import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  buildManagerFilial,
  buyManagerAlumnus,
  fetchManagerAlumniMarket,
  fetchManagerFilial,
  openManagerFilial,
  pickManagerFilial,
  priceManagerAlumnus,
  releaseManagerAlumnus,
  sellManagerAlumnus,
  setManagerFilialName,
  setManagerFilialSkin,
  type ManagerAlumnus,
  type ManagerFilialView,
} from "@/api/manager";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { ListSkeleton } from "@/components/common/Skeleton";
import { MIcon } from "@/lib/managerIcons";
import { eur } from "@/lib/managerMoney";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { hapticNotify } from "@/lib/telegram";

// assets/manager/filial/: <region>.webp — the header of a region, world_map.webp — the map to
// choose one, skin_<code>.webp — a Stars header skin (a missing picture → a gradient only).
const REGION_ART = Object.fromEntries(
  Object.entries(import.meta.glob("../../assets/manager/filial/*.webp", { eager: true, import: "default" }) as Record<string, string>)
    .map(([path, url]) => [path.slice(path.lastIndexOf("/") + 1, -".webp".length), url]),
);

const coins = (n: number) => `${n.toLocaleString("ru-RU")} 🪙`;
const starsOf = (n: number) => "★".repeat(n) + "☆".repeat(Math.max(0, 5 - n));
const seasons = (n: number) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? "сезон" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "сезона" : "сезонов"}`;
const STATUS: Record<string, string> = { retired: "завершил карьеру", released: "отпущен", sold: "продан рынку", club: "в клубе" };

type Ask = { title: string; text: string; label: string; run: () => void };

/** «🌍 Филиал академии» of «Кабинет президента»: a youth branch in a region
 * of the world. A release of candidates every few seasons while a contract
 * is free, buildings for coins, the alumni's careers (1 season = 1 year) and
 * their market — the market buys back once a season, other presidents only
 * between the floor and the ceiling of his value. */
export default function FilialPanel({ onError }: { onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "filial"], queryFn: fetchManagerFilial });
  const [ask, setAsk] = useState<Ask | null>(null);
  const [market, setMarket] = useState(false);
  const done = (v: ManagerFilialView) => {
    hapticNotify("success");
    queryClient.setQueryData(["manager", "filial"], v);
    void queryClient.invalidateQueries({ queryKey: ["manager"], exact: true });
  };
  const act = useMutation({ mutationFn: (run: () => Promise<ManagerFilialView>) => run(), onSuccess: done, onError });
  if (!data) return <ListSkeleton />;
  if (!data.enabled) return <p className="rounded-xl bg-bg-surface px-3 py-3 text-caption text-ink-mist">Филиалы пока закрыты.</p>;
  const confirm = (a: Ask) => setAsk(a);
  return (
    <div className="flex flex-col gap-3" data-testid="filial-panel">
      {data.filial ? (
        <>
          <FilialHero view={data} />
          <Release view={data} busy={act.isPending} confirm={confirm} run={(f) => act.mutate(f)} />
          <Alumni view={data} busy={act.isPending} confirm={confirm} run={(f) => act.mutate(f)} />
          <Buildings view={data} busy={act.isPending} confirm={confirm} run={(f) => act.mutate(f)} />
          <FilialStars view={data} busy={act.isPending} onError={onError} run={(f) => act.mutate(f)} />
          <Hall view={data} />
          <button onClick={() => setMarket((m) => !m)} className="rounded-xl bg-bg-surface px-3 py-2 text-caption font-bold text-ink-chalk">
            🛒 Рынок выпускников {market ? "▴" : "▾"}
          </button>
          {market && <AlumniMarket onError={onError} confirm={confirm} />}
          {data.history.length > 0 && (
            <div className="flex flex-col gap-1 rounded-2xl bg-bg-surface p-3">
              <p className="text-micro font-bold uppercase tracking-wide text-ink-mist">📜 Бывшие выпускники</p>
              {data.history.map((h, i) => (
                <p key={i} className="text-micro text-ink-mist">{h.flag} {h.name} · {h.position} · {h.age} лет · {STATUS[h.status] ?? h.status}</p>
              ))}
            </div>
          )}
        </>
      ) : (
        <OpenFilial view={data} busy={act.isPending} confirm={confirm}
          open={(region, country) => act.mutate(() => openManagerFilial(region, country))} />
      )}
      <ConfirmDialog open={!!ask} title={ask?.title ?? ""} description={ask?.text} confirmLabel={ask?.label}
        onConfirm={() => { ask?.run(); setAsk(null); }} onCancel={() => setAsk(null)} />
    </div>
  );
}

function OpenFilial({ view, busy, confirm, open }: {
  view: ManagerFilialView; busy: boolean; confirm: (a: Ask) => void; open: (region: string, country: string) => void;
}) {
  const [region, setRegion] = useState("");
  const r = view.regions.find((x) => x.code === region);
  const [country, setCountry] = useState("");
  const chosen = r?.countries.find((c) => c.name === country) ?? r?.countries[0];
  const art = REGION_ART[region];
  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-3" data-testid="filial-open">
      <p className="text-body font-bold text-ink-chalk">🌍 Открой филиал академии</p>
      <p className="text-caption text-ink-mist">
        Раз в несколько сезонов филиал выпускает молодых футболистов из стран региона. Они растут, выходят на пик,
        стареют и уходят на пенсию: 1 сезон = 1 год. Регион выбирается один раз.
      </p>
      {!region ? (
        <WorldMap view={view} onPick={(code) => { setRegion(code); setCountry(""); }} />
      ) : (
        <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-teal-900/70 to-bg-raised" data-testid="filial-region">
          {art ? <img src={art} alt="" className="aspect-video w-full object-cover" /> : <div className="aspect-video w-full" />}
          <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-2 bg-gradient-to-b from-black/70 to-transparent p-2">
            <span className="text-caption font-bold text-ink-chalk [text-shadow:0_1px_3px_rgba(0,0,0,0.9)]">{r?.emoji} {r?.name}</span>
            <button onClick={() => setRegion("")} className="rounded-lg bg-black/50 px-2 py-1 text-micro font-bold text-ink-chalk">🗺 Карта</button>
          </div>
        </div>
      )}
      {r && (
        <div className="flex flex-wrap gap-1">
          {r.countries.map((c) => (
            <button key={c.name} onClick={() => setCountry(c.name)}
              className={`rounded-lg px-2 py-1 text-micro ${chosen?.name === c.name ? "bg-amber-300 text-bg-base" : "bg-bg-raised text-ink-mist"}`}>
              {c.flag} {c.name}
            </button>
          ))}
        </div>
      )}
      {r && <p className="text-micro text-ink-mist">Страна — где стоит филиал; выпускники будут из всего региона.</p>}
      <FilialPromise view={view} />
      <button disabled={busy || !chosen || view.balance < view.open_coins}
        onClick={() => chosen && confirm({ title: `Открыть филиал: ${chosen.flag} ${chosen.name}?`, label: "Открыть",
          text: `${coins(view.open_coins)}. Регион потом не меняется.`, run: () => open(region, chosen.name) })}
        className="rounded-xl bg-gradient-to-b from-amber-300 to-amber-500 px-3 py-2.5 text-caption font-bold text-bg-base disabled:opacity-50">
        Открыть за {coins(view.open_coins)}
      </button>
    </div>
  );
}

// Where each region's pin stands on the world map (% of its width / height).
const PINS: Record<string, { x: number; y: number }> = {
  north_america: { x: 21, y: 34 }, south_america: { x: 31, y: 70 }, europe: { x: 51, y: 27 },
  africa: { x: 52, y: 58 }, asia: { x: 75, y: 37 },
};

/** The world map with a pin per region: a tap opens the region. */
function WorldMap({ view, onPick }: { view: ManagerFilialView; onPick: (code: string) => void }) {
  const map = REGION_ART.world_map;
  return (
    <div className="relative aspect-[16/10] w-full overflow-hidden rounded-xl bg-gradient-to-br from-sky-900 via-teal-900 to-indigo-950 ring-1 ring-white/10"
      data-testid="filial-map">
      {map && <img src={map} alt="" className="absolute inset-0 h-full w-full object-cover" />}
      {!map && <p className="absolute inset-x-0 bottom-1 text-center text-[10px] text-white/40">выбери регион на карте</p>}
      {view.regions.map((x) => {
        const pin = PINS[x.code] ?? { x: 50, y: 50 };
        return (
          <button key={x.code} onClick={() => onPick(x.code)} aria-label={x.name}
            style={{ left: `${pin.x}%`, top: `${pin.y}%` }}
            className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-0.5 transition active:scale-95">
            <span className="grid h-11 w-11 place-items-center rounded-full bg-black/35 ring-2 ring-amber-300/80 shadow-[0_0_18px_rgba(251,191,36,0.55)]">
              <MIcon code={`filial_pin_${x.code}`} emoji={x.emoji} className="h-10 w-10" emojiClass="text-2xl" />
            </span>
            <span className="max-w-[6.5rem] rounded-md bg-black/60 px-1.5 py-0.5 text-center text-[9px] font-bold leading-tight text-white">{x.name}</span>
          </button>
        );
      })}
    </div>
  );
}

/** What the 8 000 coins buy: contracts, the release schedule and the buildings. */
function FilialPromise({ view }: { view: ManagerFilialView }) {
  const st = view.start;
  return (
    <div className="flex flex-col gap-1.5 rounded-xl bg-bg-raised p-2.5" data-testid="filial-promise">
      <p className="text-micro font-bold uppercase tracking-wide text-amber-200">Что даёт филиал</p>
      <p className="text-micro text-ink-chalk">📝 Контракты выпускников: {st.contracts} на старте, до {st.contracts_max} с «Интернатом»</p>
      <p className="text-micro text-ink-chalk">🎓 Выпуск раз в {seasons(st.every)} (с «Интернатом» — раз в {seasons(st.every_min)}), кандидатов на выбор: {st.candidates}, им по {st.start_age} лет</p>
      <p className="text-micro text-ink-chalk">📈 Выпускник растёт к пику, играет за клуб, его можно продать рынку или другому президенту</p>
      <div className="mt-0.5 grid grid-cols-2 gap-1">
        {view.buildings.map((b) => (
          <div key={b.code} className="flex items-center gap-1.5 rounded-lg bg-bg-surface px-1.5 py-1">
            <MIcon code={`filial_${b.code}`} emoji={b.emoji} className="h-7 w-7" emojiClass="text-base" />
            <div className="min-w-0">
              <p className="text-[10px] font-bold leading-tight text-ink-chalk">{b.name}</p>
              <p className="text-[9px] leading-tight text-ink-mist">{b.about}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FilialHero({ view }: { view: ManagerFilialView }) {
  const f = view.filial!;
  const art = (f.skin && REGION_ART[`skin_${f.skin}`]) || REGION_ART[f.region];
  return (
    <section className="relative min-h-[8rem] overflow-hidden rounded-2xl bg-gradient-to-br from-teal-900/70 to-bg-surface p-3 ring-1 ring-teal-300/30">
      {art && <img src={art} alt="" className="absolute inset-0 h-full w-full object-cover opacity-60" />}
      <div className="relative flex flex-col gap-1 [text-shadow:0_1px_3px_rgba(0,0,0,0.9)]">
        <p className="text-body font-bold text-ink-chalk">{f.flag} {f.name ? `Академия «${f.name}»` : "Филиал"} · {f.country}</p>
        <p className="text-micro text-ink-mist">{f.region_name}</p>
        <div className="mt-1 flex flex-wrap gap-1.5 text-micro">
          <span className="rounded-lg bg-black/40 px-2 py-1 text-ink-chalk">📝 Контракты {f.used}/{f.contracts}</span>
          <span className="rounded-lg bg-black/40 px-2 py-1 text-ink-chalk">🎓 Выпуск раз в {seasons(f.every)}</span>
          {f.next_in != null && f.next_in > 0 && <span className="rounded-lg bg-black/40 px-2 py-1 text-ink-chalk">⏳ следующий через {seasons(f.next_in)}</span>}
        </div>
      </div>
    </section>
  );
}

type Part = { view: ManagerFilialView; busy: boolean; confirm: (a: Ask) => void; run: (f: () => Promise<ManagerFilialView>) => void };

function Release({ view, busy, confirm, run }: Part) {
  const f = view.filial!;
  if (f.pending.length === 0) {
    const why = f.used >= f.contracts ? "Все контракты заняты — новый выпуск придёт, когда освободится место." : "Новый выпуск — в межсезонье по графику.";
    return <p className="rounded-xl bg-bg-surface px-3 py-2 text-caption text-ink-mist">🎓 {why}</p>;
  }
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3" data-testid="filial-release">
      <p className="text-micro font-bold uppercase tracking-wide text-amber-200">🎓 Выпуск: выбери одного</p>
      {f.pending.map((c, i) => (
        <div key={i} className="flex items-center gap-2 rounded-xl bg-bg-raised px-2.5 py-2">
          <span className="text-lg">{c.flag}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-caption font-bold text-ink-chalk">{c.name} · {c.position}</p>
            <p className="text-micro text-ink-mist">рейтинг {c.rating} · потенциал <span className="text-amber-300">{starsOf(c.stars)}</span> · пик к {c.peak_age}</p>
            {c.peak != null && <p className="text-micro font-bold text-emerald-300">📋 пик {c.peak} в {c.peak_age} лет</p>}
          </div>
          <button disabled={busy} onClick={() => confirm({ title: `Подписать ${c.name}?`, label: "Подписать",
            text: "Остальные кандидаты уйдут. Зарплата — в начале каждого сезона, как у всех.", run: () => run(() => pickManagerFilial(i)) })}
            className="rounded-lg bg-amber-400 px-2.5 py-1.5 text-micro font-bold text-bg-base disabled:opacity-50">Взять</button>
        </div>
      ))}
      <button disabled={busy} onClick={() => confirm({ title: "Отпустить весь выпуск?", label: "Отпустить",
        text: "Никто не подпишет контракт, следующий выпуск — по графику.", run: () => run(() => pickManagerFilial(null)) })}
        className="text-micro text-ink-mist underline">отпустить всех</button>
    </div>
  );
}

function Alumni({ view, busy, confirm, run }: Part) {
  if (view.alumni.length === 0) return null;
  return (
    <div className="flex flex-col gap-2" data-testid="filial-alumni">
      <p className="px-1 text-micro font-bold uppercase tracking-wide text-ink-mist">🧑‍🎓 Выпускники в клубе</p>
      {view.alumni.map((a) => <AlumnusRow key={a.id} a={a} view={view} busy={busy} confirm={confirm} run={run} />)}
    </div>
  );
}

function AlumnusRow({ a, view, busy, confirm, run }: Part & { a: ManagerAlumnus }) {
  const [price, setPrice] = useState(a.price ?? a.price_min);
  const [sell, setSell] = useState(false);
  const f = view.filial!;
  const phase = a.phase === "рост" ? "text-emerald-300" : a.phase === "пик" ? "text-amber-300" : "text-rose-300";
  return (
    <div className="flex flex-col gap-1.5 rounded-2xl bg-bg-surface p-3">
      <div className="flex items-center gap-2">
        <MIcon code="filial_graduate" emoji={a.flag} className="h-8 w-8" emojiClass="text-xl" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-caption font-bold text-ink-chalk">{a.flag} {a.name} · {a.position}</p>
          <p className="text-micro text-ink-mist">
            {a.age} лет · <b className="text-ink-chalk">{a.rating}</b> · <span className={phase}>{a.phase}</span> · {eur(a.value)}
            {a.goals > 0 && ` · ⚽ ${a.goals}`}
          </p>
          <p className="text-micro text-ink-mist">потенциал <span className="text-amber-300">{starsOf(a.stars)}</span> · до пенсии {seasons(a.retire_in)}</p>
        </div>
        <button onClick={() => setSell((s) => !s)} className="rounded-lg bg-bg-raised px-2 py-1 text-micro text-ink-chalk">⋯</button>
      </div>
      {a.price != null && <p className="text-micro text-teal-200">🛒 На рынке за {eur(a.price)}</p>}
      {sell && (
        <div className="flex flex-col gap-1.5 rounded-xl bg-bg-raised p-2">
          {!view.window_open && <p className="text-micro text-amber-200">🔒 Окно закрыто — сделки в межсезонье.</p>}
          <div className="flex items-center gap-1.5">
            <input type="range" min={a.price_min} max={a.price_max} step={Math.max(1, Math.round((a.price_max - a.price_min) / 40))}
              value={price} onChange={(e) => setPrice(Number(e.target.value))} className="flex-1" aria-label="Цена" />
            <span className="w-20 text-right text-micro font-bold text-ink-chalk">{eur(price)}</span>
          </div>
          <p className="text-micro text-ink-mist">Президентам — от {eur(a.price_min)} до {eur(a.price_max)}: дешевле нельзя, чтобы не сливать игроков своим.</p>
          <div className="flex flex-wrap gap-1.5">
            <button disabled={busy} onClick={() => run(() => priceManagerAlumnus(a.id, price))}
              className="rounded-lg bg-teal-300 px-2 py-1 text-micro font-bold text-bg-base disabled:opacity-50">Выставить</button>
            {a.price != null && <button disabled={busy} onClick={() => run(() => priceManagerAlumnus(a.id, null))}
              className="rounded-lg bg-bg-surface px-2 py-1 text-micro text-ink-chalk">Снять</button>}
            {a.sell_back != null && <button disabled={busy || f.sold_this_season || !view.window_open}
              onClick={() => confirm({ title: `Продать ${a.name} рынку?`, label: "Продать",
                text: `Рынок заплатит ${eur(a.sell_back!)}. Рынку — один выпускник за сезон.`, run: () => run(() => sellManagerAlumnus(a.id)) })}
              className="rounded-lg bg-amber-400 px-2 py-1 text-micro font-bold text-bg-base disabled:opacity-50">
              {f.sold_this_season ? "рынку — уже в этом сезоне" : `Рынку за ${eur(a.sell_back)}`}
            </button>}
            <button disabled={busy || !view.window_open} onClick={() => confirm({ title: `Отпустить ${a.name}?`, label: "Отпустить",
              text: "Он уйдёт бесплатно, контракт освободится.", run: () => run(() => releaseManagerAlumnus(a.id)) })}
              className="rounded-lg bg-bg-surface px-2 py-1 text-micro text-rose-300">Отпустить</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Buildings({ view, busy, confirm, run }: Part) {
  return (
    <div className="flex flex-col gap-1.5" data-testid="filial-buildings">
      <p className="px-1 text-micro font-bold uppercase tracking-wide text-ink-mist">🏗 Постройки · баланс {coins(view.balance)}</p>
      <div className="grid grid-cols-2 gap-1.5">
        {view.buildings.map((b) => (
          <div key={b.code} className="flex flex-col gap-1 rounded-2xl bg-bg-surface p-2.5">
            <div className="flex items-center gap-1.5">
              <MIcon code={`filial_${b.code}`} emoji={b.emoji} className="h-9 w-9" emojiClass="text-xl" />
              <div className="min-w-0">
                <p className="truncate text-micro font-bold text-ink-chalk">{b.name}</p>
                <p className="text-[10px] text-ink-mist">ур. {b.level}/{b.max}</p>
              </div>
            </div>
            <p className="text-[10px] leading-tight text-ink-mist">{b.about}</p>
            {b.price != null ? (
              <button disabled={busy || view.balance < b.price}
                onClick={() => confirm({ title: `${b.name}: уровень ${b.level + 1}?`, label: "Построить", text: coins(b.price!),
                  run: () => run(() => buildManagerFilial(b.code)) })}
                className="mt-auto rounded-lg bg-amber-400 px-2 py-1 text-[10px] font-bold text-bg-base disabled:opacity-50">{coins(b.price)}</button>
            ) : <p className="mt-auto text-center text-[10px] font-bold text-emerald-300">максимум</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

function AlumniMarket({ onError, confirm }: { onError: (e: unknown) => void; confirm: (a: Ask) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "filial", "market"], queryFn: fetchManagerAlumniMarket });
  const buy = useMutation({
    mutationFn: buyManagerAlumnus,
    onSuccess: (m) => {
      hapticNotify("success");
      queryClient.setQueryData(["manager", "filial", "market"], m);
      void queryClient.invalidateQueries({ queryKey: ["manager"] });
    },
    onError,
  });
  if (!data) return <ListSkeleton />;
  if (data.lots.length === 0) return <p className="rounded-xl bg-bg-surface px-3 py-2 text-caption text-ink-mist">Сейчас никто не продаёт выпускников.</p>;
  return (
    <div className="flex flex-col gap-1.5" data-testid="filial-market">
      {data.lots.map((l) => (
        <div key={l.id} className="flex items-center gap-2 rounded-xl bg-bg-surface px-2.5 py-2">
          <span className="text-lg">{l.flag}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-caption font-bold text-ink-chalk">{l.name} · {l.position} · {l.rating}</p>
            <p className="text-micro text-ink-mist">{l.age} лет · {l.phase} · {l.club}</p>
          </div>
          <button disabled={buy.isPending || !l.valid}
            onClick={() => confirm({ title: `Купить ${l.name}?`, label: "Купить", text: `${eur(l.price ?? 0)} из бюджета клуба.`, run: () => buy.mutate(l.id) })}
            className="rounded-lg bg-teal-300 px-2 py-1.5 text-micro font-bold text-bg-base disabled:opacity-50">{eur(l.price ?? 0)}</button>
        </div>
      ))}
    </div>
  );
}

/** «⭐ За звёзды»: convenience and style only — never the strength. */
function FilialStars({ view, busy, onError, run }: {
  view: ManagerFilialView; busy: boolean; onError: (e: unknown) => void; run: (f: () => Promise<ManagerFilialView>) => void;
}) {
  const queryClient = useQueryClient();
  const [paying, setPaying] = useState<string | null>(null);
  const [name, setName] = useState("");
  const f = view.filial!;
  const st = view.stars;
  const pay = async (code: string) => {
    setPaying(code);
    try {
      if ((await payMyPlayerWithStars({ purchase: "manager", code })) === "paid") {
        hapticNotify("success");
        await queryClient.invalidateQueries({ queryKey: ["manager", "filial"] });
      }
    } catch (err) {
      onError(err);
    } finally {
      setPaying(null);
    }
  };
  const pending = f.pending.length > 0;
  const full = f.used >= f.contracts;
  const why: Record<string, string | null> = {
    rush: pending ? "выпуск уже ждёт" : full ? "нет свободного контракта" : f.rush_in > 0 ? `через ${seasons(f.rush_in)}` : null,
    reroll: !pending ? "нет выпуска" : f.rerolled ? "уже было" : null,
    report: !pending ? "нет выпуска" : f.revealed ? "уже открыт" : null,
    name: null,
  };
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-gradient-to-b from-amber-400/10 to-bg-surface p-3 ring-1 ring-amber-300/20" data-testid="filial-stars">
      <p className="text-micro font-bold uppercase tracking-wide text-amber-200">⭐ За звёзды</p>
      {(["rush", "reroll", "report", "name"] as const).map((k) => {
        const item = st[k];
        const credit = f.credits[k] ?? 0;
        return (
          <div key={k} className="flex items-center gap-2 rounded-xl bg-bg-raised px-2.5 py-2">
            <MIcon code={`filial_${k}`} emoji={item.emoji} className="h-9 w-9" emojiClass="text-xl" />
            <div className="min-w-0 flex-1">
              <p className="text-caption font-bold text-ink-chalk">{item.name}</p>
              <p className="text-micro leading-tight text-ink-mist">{item.about}</p>
            </div>
            {credit > 0 && k !== "name" ? (
              <span className="text-micro font-bold text-emerald-300">оплачено</span>
            ) : credit > 0 ? null : (
              <button disabled={busy || !!paying || !!why[k]} onClick={() => void pay(`filial:${k}`)}
                className="shrink-0 rounded-lg bg-amber-400 px-2 py-1.5 text-micro font-bold text-bg-base disabled:bg-bg-surface disabled:text-ink-mist">
                {why[k] ?? `${item.stars} ⭐`}
              </button>
            )}
          </div>
        );
      })}
      {(f.credits.name ?? 0) > 0 && (
        <div className="flex gap-1.5">
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={24} placeholder="Название академии"
            className="min-w-0 flex-1 rounded-lg bg-bg-raised px-2 py-1.5 text-caption text-ink-chalk" />
          <button disabled={busy || name.trim().length < 2} onClick={() => run(() => setManagerFilialName(name.trim()))}
            className="rounded-lg bg-amber-400 px-2.5 py-1.5 text-micro font-bold text-bg-base disabled:opacity-50">Назвать</button>
        </div>
      )}
      <p className="pt-1 text-micro font-bold text-ink-mist">🎨 Оформление филиала</p>
      <div className="grid grid-cols-3 gap-1.5">
        {st.skins.map((sk) => {
          const owned = f.skins.includes(sk.code);
          const on = f.skin === sk.code;
          const art = REGION_ART[`skin_${sk.code}`];
          return (
            <button key={sk.code} disabled={busy || !!paying}
              onClick={() => (owned ? run(() => setManagerFilialSkin(on ? null : sk.code)) : void pay(`filial:skin:${sk.code}`))}
              className={`flex flex-col items-center gap-1 rounded-xl p-1.5 text-[10px] font-bold ${on ? "bg-amber-400 text-bg-base" : "bg-bg-raised text-ink-chalk"}`}>
              {art ? <img src={art} alt="" className="aspect-video w-full rounded-lg object-cover" /> : <span className="text-2xl">{sk.emoji}</span>}
              <span className="leading-tight">{sk.name}</span>
              <span className={on ? "" : "text-ink-mist"}>{on ? "надето" : owned ? "надеть" : `${sk.stars} ⭐`}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** «🏛 Зал выпускников»: the best of the filial ever, by the peak. */
function Hall({ view }: { view: ManagerFilialView }) {
  if (view.hall.length === 0) return null;
  return (
    <div className="flex flex-col gap-1 rounded-2xl bg-bg-surface p-3" data-testid="filial-hall">
      <div className="flex items-center gap-1.5">
        <MIcon code="filial_hall" emoji="🏛" className="h-7 w-7" emojiClass="text-lg" />
        <p className="text-micro font-bold uppercase tracking-wide text-ink-mist">Зал выпускников</p>
      </div>
      {view.hall.map((h, i) => (
        <p key={i} className="flex items-center gap-1.5 text-micro text-ink-chalk">
          <b className="w-4 text-amber-300">{i + 1}</b>
          <span className="min-w-0 flex-1 truncate">{h.flag} {h.name} · {h.position}</span>
          <span className="text-ink-mist">пик <b className="text-ink-chalk">{h.peak}</b>{h.goals > 0 && ` · ⚽ ${h.goals}`} · {STATUS[h.status] ?? h.status}</span>
        </p>
      ))}
    </div>
  );
}
