import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import {
  chooseProspectPosition, createProspectInvoice,
  type Prospect, type ProspectLine, type ProspectPositionOption, type ProspectView,
} from "@/api/prospect";

import { payWithStars } from "./shared";

/** «Воспитанник Академии»: the position the coach offers by what he trained,
 * the deficit bonus of rare lines, a change for Stars, and how the ★ and
 * the peak grow (backend prospect_service; every number from the view). */

type Ctx = { view: ProspectView; onView: (v: ProspectView) => void; toast: (t: string) => void; fail: (e: unknown) => void };

const LINE_LABEL: Record<ProspectLine, string> = { GK: "Вратарь", DEF: "Защита", MID: "Полузащита", FWD: "Атака" };
const LINE_EMOJI: Record<ProspectLine, string> = { GK: "🧤", DEF: "🛡️", MID: "🧠", FWD: "🎯" };
const LINE_OF: Record<string, ProspectLine> = {
  GK: "GK", CB: "DEF", LB: "DEF", RB: "DEF", CDM: "MID", CM: "MID", CAM: "MID", LM: "MID", RM: "MID", ST: "FWD", LW: "FWD", RW: "FWD",
};

function why(o: ProspectPositionOption): string {
  const parts = [];
  if (o.drills) parts.push(`${o.drills} трен.`);
  if (o.talents.length) parts.push(o.talents.join(", "));
  return parts.join(" · ") || "тренер видит в нём";
}

/** The coach's offer at «Юноши»: 2–3 positions; deficit lines carry a bonus. */
export function PositionPickCard({ view, onView, toast, fail }: Ctx) {
  const pick = view.position_pick;
  const choose = useMutation({
    mutationFn: (pos: string) => chooseProspectPosition(pos),
    onSuccess: (v, pos) => { onView(v); toast(`🧭 Теперь он ${pos}${v.prospect?.deficit ? " — дефицитная позиция, бонус закреплён" : ""}`); },
    onError: fail,
  });
  if (!pick) return null;
  return (
    <section className="rounded-2xl border border-accent-cyan/40 bg-gradient-to-br from-accent-cyan/15 to-bg-surface p-3" aria-label="Выбор позиции">
      <p className="text-micro uppercase tracking-wider text-accent-cyan">Тренер «Юношей»</p>
      <p className="font-display text-base font-bold text-ink-chalk">Где ему играть?</p>
      <p className="text-xs text-ink-mist">Тренер смотрел, что он тренировал и какие таланты взял. Редкие позиции — с бонусом.</p>
      <div className="mt-2 grid grid-cols-3 gap-1.5">
        {pick.options.map((o) => (
          <button key={o.position} disabled={choose.isPending} onClick={() => choose.mutate(o.position)}
            className={`relative flex flex-col items-center gap-0.5 rounded-xl px-1.5 py-2.5 text-center disabled:opacity-50 active:scale-[0.97] ${o.deficit ? "bg-accent-cyan/15 ring-1 ring-accent-cyan/60" : "bg-bg-raised"}`}>
            <span className="text-xl" aria-hidden>{LINE_EMOJI[o.line]}</span>
            <span className="font-mono text-base font-bold text-ink-chalk">{o.position}</span>
            <span className="text-micro text-ink-mist">{o.line_name}</span>
            <span className="text-micro leading-tight text-ink-mist-dim">{why(o)}</span>
            {o.deficit && (
              <span className="mt-0.5 rounded-full bg-accent-cyan px-1.5 py-0.5 text-[10px] font-bold leading-tight text-bg-base">
                дефицит: +{o.xp_pct}% опыта, +{o.value_pct}% цены
              </span>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}

/** «Рост» tab: his position (universal / set, deficit bonus) and a change for Stars. */
export function PositionCard({ view, p, onView, toast, fail }: Ctx & { p: Prospect }) {
  const [open, setOpen] = useState(false);
  const change = view.position_change;
  const buy = useMutation({
    mutationFn: (pos: string) => payWithStars(() => createProspectInvoice(`pos:${pos}`)),
    onSuccess: (v) => { if (v) { onView(v); setOpen(false); toast(`🔁 Новая позиция: ${v.prospect?.position}`); } },
    onError: fail,
  });
  const youth = view.stages[2]?.name ?? "Юноши";
  return (
    <section className="rounded-2xl bg-bg-surface p-3" aria-label="Позиция">
      <div className="flex items-center gap-3">
        <span className="text-2xl" aria-hidden>{p.universal ? "🔄" : LINE_EMOJI[p.line]}</span>
        <div className="min-w-0 flex-1">
          <p className="font-display text-sm font-bold text-ink-chalk">
            {p.universal ? "Универсал" : `Позиция ${p.position} · ${LINE_LABEL[p.line]}`}
          </p>
          <p className="text-xs text-ink-mist">
            {p.universal
              ? view.position_pick
                ? "Тренер ждёт решения — загляни в «Сегодня»"
                : `Пока играет везде. На ступени «${youth}» тренер предложит позиции — по тому, что он тренирует, и по талантам`
              : p.deficit
                ? `Дефицитная линия: +${p.deficit.xp_pct}% опыта и +${p.deficit.value_pct}% к цене в «Менеджере»`
                : "Линия без дефицита"}
          </p>
        </div>
        {change && (
          <button onClick={() => setOpen((o) => !o)} className="shrink-0 rounded-xl bg-amber-400 px-3 py-2 text-xs font-bold text-black">
            Сменить · ⭐ {change.stars}
          </button>
        )}
      </div>
      {open && change && (
        <div className="mt-2 flex flex-col gap-1.5">
          {(Object.keys(LINE_LABEL) as ProspectLine[]).map((line) => (
            <div key={line} className="flex flex-wrap items-center gap-1.5">
              <span className="w-24 text-xs text-ink-mist">{LINE_EMOJI[line]} {LINE_LABEL[line]}</span>
              {change.options.filter((pos) => LINE_OF[pos] === line).map((pos) => (
                <button key={pos} disabled={buy.isPending} onClick={() => buy.mutate(pos)}
                  className="rounded-lg bg-bg-raised px-2.5 py-1 font-mono text-xs font-bold text-ink-chalk disabled:opacity-40">
                  {pos}
                </button>
              ))}
            </div>
          ))}
          <p className="text-micro text-ink-mist-dim">Бонус дефицита пересчитается по новой линии.</p>
        </div>
      )}
    </section>
  );
}

const TRIAL_STATUS: Record<string, string> = {
  passed: "✅ пройдено", failed: "❌ не вышло", missed: "— пропущено", active: "идёт", upcoming: "впереди",
};

/** How the ★ grows (streak, stage trials) and the peak bonuses (dynasty, academy). */
export function PotentialCard({ view, p }: { view: ProspectView; p: Prospect }) {
  const g = view.growth;
  if (!g) return null;
  const s = g.streak;
  const inCycle = s.every ? s.current % s.every : 0;
  const pk = g.peak;
  return (
    <section className="rounded-2xl bg-bg-surface p-3" aria-label="Рост потенциала">
      <p className="font-display text-sm font-bold text-ink-chalk">Как растёт потенциал</p>
      <p className="text-xs text-ink-mist">
        {g.potential_max ? "Потенциал уже максимальный ★★★★★" : "Звёзды не выпадают случайно — их зарабатывают упорством"}
      </p>
      <div className="mt-2 flex flex-col gap-2">
        <div className="rounded-xl bg-bg-raised p-2.5">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-ink-chalk">🔥 Серия {s.every} дней тренировок → +1★</span>
            <span className="text-ink-mist">{s.ups}/{s.max}</span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-black/30">
            <div className="h-full rounded-full bg-orange-400" style={{ width: `${s.ups >= s.max ? 100 : Math.round((inCycle / Math.max(1, s.every)) * 100)}%` }} />
          </div>
          <p className="mt-1 text-micro text-ink-mist">
            {s.ups >= s.max ? "Все звёзды за серию уже получены" : `Сейчас ${s.current} дн. подряд · ещё ${s.every - inCycle} дн.`}
          </p>
        </div>
        <div className="rounded-xl bg-bg-raised p-2.5">
          <p className="text-xs font-semibold text-ink-chalk">
            🏅 Испытания ступеней → +1★
          </p>
          <p className="text-micro text-ink-mist">
            Первые {g.trial.matches} «Ответки» на ступени: {g.trial.wins_needed} победы — испытание пройдено.
            Удача в некоторых историях засчитывает одну победу (📖)
          </p>
          <ul className="mt-1.5 flex flex-col gap-1">
            {g.trial.stages.map((t) => (
              <li key={t.stage} className={`flex items-center justify-between rounded-lg px-2 py-1 text-xs ${t.status === "active" ? "bg-path/15 text-ink-chalk" : "text-ink-mist"}`}>
                <span>{t.name}</span>
                <span>
                  {t.status === "active" ? `${t.wins} поб. из ${t.played}/${g.trial.matches}` : TRIAL_STATUS[t.status]}
                  {t.story && " · 📖"}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl bg-bg-raised p-2.5">
          <p className="text-xs font-semibold text-ink-chalk">📈 Бонус к рейтингу на пике: +{pk.dynasty + pk.academy}</p>
          <ul className="mt-1 flex flex-col gap-0.5 text-micro text-ink-mist">
            <li>👑 Династия: +{pk.dynasty}{p.generation > 1 ? ` (${p.generation}-е поколение)` : ` — каждое следующее поколение +${pk.dynasty_per}`}</li>
            <li>
              🏛️ Академия: +{pk.academy} · уровень {pk.academy_level}
              {pk.per_levels > 0 && pk.next_level !== null ? ` · +1 за каждые ${pk.per_levels} ур. (следующий на ${pk.next_level})` : ""}
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}
