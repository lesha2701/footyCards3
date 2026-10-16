import type { ReactNode } from "react";

import type { CareerAnalysis, CareerGoalsByOrigin, TacticsCatalog } from "@/api/career";
import { MatchupList, TacticTags } from "@/components/career/CareerTactics";
import { HINT_TEXT, axisValueLabel, presetOf, tacticLabel } from "@/lib/careerTactics";
import { MENTALITIES } from "@/lib/clubTactics";

function goalsText(g: CareerGoalsByOrigin): string {
  const parts = [
    g.wing && `с флангов ${g.wing}`, g.central && `через центр ${g.central}`,
    g.counter && `с контратак ${g.counter}`, g.set_piece && `со стандартов ${g.set_piece}`, g.penalty && `пенальти ${g.penalty}`,
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : "нет";
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 py-1.5 text-xs">
      <span className="text-ink-mist">{label}</span>
      <span className="text-right text-ink-chalk">{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">{title}</p>
      {children}
    </div>
  );
}

/** Tactical analysis of my career match — only what the engine recorded:
 * phase counts, won balls, counters, goal origins, which tactical
 * interactions applied in duels and how they went, instructions and subs. */
export default function CareerMatchAnalysis({ analysis, catalog }: { analysis: CareerAnalysis; catalog: TacticsCatalog | null }) {
  const { mine, theirs } = analysis;
  const hint = HINT_TEXT[analysis.matchup.hint];
  const planSubs = analysis.plan?.subs ?? [];
  const doneSubs = new Set(analysis.substitutions.map((s) => s.sub));
  const myPreset = presetOf(catalog, analysis.tactic);
  const theirPreset = presetOf(catalog, analysis.opponent_tactic);

  return (
    <section className="flex flex-col gap-4 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-display text-base font-bold text-ink-chalk">Тактический разбор</p>
        <span className={`rounded-full px-2 py-0.5 text-micro font-bold ${hint.tone}`}>{hint.label}</span>
      </div>

      {catalog && (
        <div className="grid gap-2">
          <div className="rounded-2xl bg-bg-raised p-3">
            <p className="mb-1.5 text-caption text-ink-mist">
              Вы: {analysis.formation} · {tacticLabel(MENTALITIES, analysis.mentality)}
              {myPreset && <> · <span className="text-ink-chalk">{myPreset}</span></>}
              {analysis.familiarity_pct > 0 && <> · сыгранность +{analysis.familiarity_pct}%</>}
            </p>
            <TacticTags catalog={catalog} tactic={analysis.tactic} />
          </div>
          <div className="rounded-2xl bg-bg-raised p-3">
            <p className="mb-1.5 text-caption text-ink-mist">Соперник{theirPreset && <> · <span className="text-ink-chalk">{theirPreset}</span></>}</p>
            <TacticTags catalog={catalog} tactic={analysis.opponent_tactic} />
          </div>
        </div>
      )}

      <Section title="Расклад до матча">
        <MatchupList report={analysis.matchup} />
      </Section>

      {analysis.duels.length > 0 && (
        <Section title="Что сработало в матче">
          <ul className="flex flex-col gap-2">
            {analysis.duels.map((d) => {
              const share = d.applied ? Math.round((d.attacker_won / d.applied) * 100) : 0;
              return (
                <li key={`${d.id}-${d.attacker}`} className="rounded-2xl bg-bg-raised p-2.5">
                  <p className="text-caption text-ink-chalk">{d.label}</p>
                  <p className="mt-0.5 text-micro text-ink-mist">
                    {d.attacker === "me" ? "Ваши атаки" : "Атаки соперника"}: {d.applied} дуэлей, прорыв в {d.attacker_won}
                  </p>
                  <span className="mt-1 block h-1 overflow-hidden rounded-full bg-white/10">
                    <span className={`block h-full ${d.attacker === "me" ? "bg-accent-lime" : "bg-red-400"}`} style={{ width: `${share}%` }} />
                  </span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      <Section title="Атаки">
        <div className="divide-y divide-white/5">
          <Row label="Владели инициативой" value={`${mine.attacks} : ${theirs.attacks}`} />
          <Row label="Ваши атаки" value={`фланги ${mine.wing_attack}, центр ${mine.central_attack}, перекат ${mine.recycled}`} />
          <Row label="Прорыв первой линии" value={`${mine.advance} из ${mine.wing_attack + mine.central_attack}`} />
          <Row label="Потеряли мяч в атаке" value={`${mine.breakdown} · моментов у соперника с контратак ${theirs.counter_chances}`} />
          <Row label="Отобрали мяч" value={`${theirs.breakdown} · ваших моментов с контратак ${mine.counter_chances}`} />
        </div>
      </Section>

      {analysis.set_pieces_mine && analysis.set_pieces_theirs && (
        <Section title="Стандарты">
          <div className="divide-y divide-white/5">
            {([["corner", "Угловые"], ["free_kick", "Штрафные"], ["penalty", "Пенальти"]] as const).map(([key, label]) => (
              <Row key={key} label={label}
                value={`${analysis.set_pieces_mine![key]} (голов ${analysis.set_pieces_mine![`${key}_goals`]}) : ${analysis.set_pieces_theirs![key]} (${analysis.set_pieces_theirs![`${key}_goals`]})`} />
            ))}
          </div>
        </Section>
      )}

      <Section title="Голы">
        <div className="divide-y divide-white/5">
          <Row label="Ваши" value={goalsText(analysis.goals_mine)} />
          <Row label="Соперника" value={goalsText(analysis.goals_theirs)} />
        </div>
      </Section>

      {(analysis.instructions.length > 0 || planSubs.length > 0 || (analysis.plan?.rules.length ?? 0) > 0) && (
        <Section title="План на матч">
          <ul className="flex flex-col gap-1 text-xs text-ink-chalk">
            {analysis.instructions.map((r, i) => (
              <li key={`r${i}`}>
                <span className="font-mono text-ink-mist-dim">{r.minute}&apos;</span>{" "}
                {r.rule === null
                  ? "условие больше не выполняется — базовая тактика"
                  : `${r.halftime ? "указания в перерыве" : `указание ${r.rule + 1}`}: ${tacticLabel(MENTALITIES, r.mentality)}${
                    catalog ? catalog.axes.filter((a) => r.tactic[a.key] !== analysis.tactic[a.key])
                      .map((a) => ` · ${axisValueLabel(catalog, a.key, r.tactic[a.key]).toLowerCase()}`).join("") : ""}`}
              </li>
            ))}
            {analysis.plan && analysis.plan.rules.length > 0 && analysis.instructions.length === 0 && (
              <li className="text-ink-mist">Условия указаний в матче не наступили</li>
            )}
            {analysis.substitutions.map((s, i) => (
              <li key={`s${i}`}>
                <span className="font-mono text-ink-mist-dim">{s.minute}&apos;</span>{" "}
                {s.kind === "sub"
                  ? `${s.halftime ? "замена в перерыве" : "замена"}: ${s.in} вместо ${s.out} (усталость ${s.fatigue}%)`
                  : `замена ${(s.sub ?? 0) + 1} не проведена — в запасе нет подходящего игрока`}
              </li>
            ))}
            {planSubs.map((_, i) => !doneSubs.has(i) && (
              <li key={`u${i}`} className="text-ink-mist">Замена {i + 1}: условие не наступило</li>
            ))}
          </ul>
        </Section>
      )}
    </section>
  );
}
