import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { setManagerTickets, type ManagerOffice } from "@/api/manager";
import { eur } from "@/lib/managerMoney";

type Tickets = ManagerOffice["tickets"];

/** The same curve as the backend (manager_finance.attendance_pct / ticket_factor / support_pct). */
function ticketCurve(t: Tickets, pct: number) {
  const attendance = Math.max(t.attendance_min, Math.min(t.attendance_max, 100 - (pct - 100) * t.elasticity));
  return {
    attendance,
    factor: Math.round((pct * attendance) / 100),
    support: Math.round((attendance - 100) * t.support_per_pct * 100) / 100,
    fans: Math.round((attendance - 100) * t.fans_per_pct),
  };
}

const signed = (n: number, unit = "") => `${n > 0 ? "+" : ""}${String(n).replace(".", ",")}${unit}`;

/** «🎟 Матчдей» of «Кабинет президента»: the ticket price of the coming
 * season (money vs a full stadium and fans), injuries and their insurance. */
export default function MatchdayPanel({ office, onDone, onError, busy, onInsure }: {
  office: ManagerOffice; onDone: (o: ManagerOffice) => void; onError: (e: unknown) => void; busy: boolean; onInsure: () => void;
}) {
  const t = office.tickets;
  const [pct, setPct] = useState(t.pct);
  const save = useMutation({ mutationFn: (v: number) => setManagerTickets(v), onSuccess: onDone, onError });
  const c = ticketCurve(t, pct);
  const perMatch = Math.round((t.base_per_match * c.factor) / 100);
  const fill = Math.min(100, c.attendance);
  const ins = office.offers.insurance;
  return (
    <div className="flex flex-col gap-3" data-testid="matchday">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#1a1035] via-[#0f2a2a] to-[#062018] p-4 ring-1 ring-fuchsia-300/25">
        <Stands fill={fill} className="pointer-events-none absolute -right-3 -top-2 h-24 w-36 opacity-90" />
        <p className="relative text-micro font-bold uppercase tracking-[0.2em] text-fuchsia-200">🎟 Цена билета</p>
        <p className="relative mt-1 max-w-[60%] text-caption text-ink-mist">Дороже — больше денег с каждого зрителя, но меньше людей и тише трибуны.</p>
        <div className="relative mt-3 flex items-end justify-between">
          <b className="font-display text-3xl font-black text-ink-chalk">{pct}%</b>
          <span className="text-right text-micro text-ink-mist">базовой цены<br />на следующий сезон</span>
        </div>
        <input type="range" className="relative mt-2 w-full" min={t.min} max={t.max} step={5} value={pct}
          onChange={(e) => setPct(Number(e.target.value))} disabled={!office.window_open} aria-label="Цена билета" />
        <div className="relative mt-3 grid grid-cols-2 gap-2">
          <Stat label="зрителей" value={`${Math.round(c.attendance)}%`} tone={c.attendance >= 100 ? "text-emerald-300" : "text-amber-200"} />
          <Stat label="билеты за дом. матч" value={eur(perMatch)} tone="text-accent-lime" />
          <Stat label="поддержка дома" value={signed(c.support, "%")} tone={c.support >= 0 ? "text-emerald-300" : "text-red-300"} />
          <Stat label="болельщиков за сезон" value={signed(c.fans)} tone={c.fans >= 0 ? "text-emerald-300" : "text-red-300"} />
        </div>
        <button disabled={!office.window_open || save.isPending || pct === t.pct} onClick={() => save.mutate(pct)}
          className="relative mt-3 w-full rounded-xl bg-gradient-to-r from-fuchsia-300 to-amber-300 py-2.5 text-sm font-bold text-bg-base disabled:opacity-40">
          {pct === t.pct ? "Цена установлена" : `Установить ${pct}%`}
        </button>
        {!office.window_open && <p className="relative mt-2 text-micro text-amber-200">Цену меняют в межсезонье — сейчас она заморожена.</p>}
      </section>

      <section className="rounded-2xl bg-bg-surface p-4">
        <h2 className="mb-1 font-display text-base font-bold text-ink-chalk">🚑 Травмы и страховка</h2>
        <p className="text-micro text-ink-mist">
          После матча кто-то из игроков может получить травму (шанс {String(ins.chance_pct).replace(".", ",")}% за матч,
          «Медцентр» ур. {ins.medical} его снижает): пропустит {ins.rounds[0]}–{ins.rounds[1]} тура, лечение — {ins.treatment_pct}% его стоимости.
        </p>
        {office.injuries.length > 0 && (
          <ul className="mt-2 flex flex-col gap-1">
            {office.injuries.map((i, n) => (
              <li key={n} className="flex justify-between rounded-lg bg-red-400/10 px-2.5 py-1.5 text-caption">
                <span className="text-ink-chalk">🤕 {i.name}</span>
                <span className="text-red-200">ещё {i.rounds_left} тур. · {eur(i.cost)}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3 flex items-center justify-between gap-3 rounded-xl bg-gradient-to-r from-sky-400/15 to-emerald-400/10 p-3">
          <span>
            <b className="block text-sm text-ink-chalk">Страховка на сезон</b>
            <span className="text-micro text-ink-mist">оплатит {ins.cover_pct}% лечения · взнос {eur(ins.premium)}</span>
          </span>
          {ins.taken ? (
            <span className="rounded-full bg-emerald-400/20 px-3 py-1.5 text-xs font-bold text-emerald-200">✓ застрахованы</span>
          ) : (
            <button disabled={busy || !office.window_open || ins.premium > office.free_budget} onClick={onInsure}
              className="shrink-0 rounded-xl bg-sky-300 px-3 py-2 text-xs font-bold text-bg-base disabled:opacity-40">Застраховать</button>
          )}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <span className="rounded-xl bg-black/30 px-2 py-2 text-center ring-1 ring-white/5">
      <b className={`block font-display text-sm ${tone}`}>{value}</b>
      <span className="block text-micro text-ink-mist">{label}</span>
    </span>
  );
}

/** Stands that fill up with the crowd. */
function Stands({ fill, className }: { fill: number; className?: string }) {
  const rows = 4, cols = 9;
  const seats = rows * cols;
  const taken = Math.round((seats * fill) / 100);
  return (
    <svg viewBox="0 0 144 96" className={className} aria-hidden>
      <path d="M8 88 L24 20 L120 20 L136 88 Z" fill="#1e1b4b" opacity="0.7" />
      {Array.from({ length: seats }, (_, i) => {
        const r = Math.floor(i / cols), col = i % cols;
        const on = seats - 1 - i < taken;
        const y = 30 + r * 14, inset = (3 - r) * 4;
        const x = 22 + inset + col * ((100 - inset * 2) / (cols - 1));
        return <circle key={i} cx={x} cy={y} r="4" fill={on ? ["#f0abfc", "#fde68a", "#86efac", "#7dd3fc"][(r + col) % 4] : "#334155"} />;
      })}
      <rect x="20" y="86" width="104" height="6" rx="3" fill="#22c55e" />
    </svg>
  );
}
