import type { CareerAnalysis, CareerGoalsByOrigin } from "@/api/career";
import { HINT_TEXT, tacticLabel } from "@/lib/careerTactics";
import { MENTALITIES, PLAYSTYLES } from "@/lib/clubTactics";

function goalsText(g: CareerGoalsByOrigin): string {
  const parts = [
    g.wing && `с флангов ${g.wing}`, g.central && `через центр ${g.central}`,
    g.counter && `с контратак ${g.counter}`, g.penalty && `пенальти ${g.penalty}`,
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : "нет";
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 py-1 text-xs">
      <span className="text-ink-mist">{label}</span>
      <span className="text-right text-ink-chalk">{value}</span>
    </div>
  );
}

/** Tactical analysis of my career match — only counts the engine recorded
 * (phases, won balls, counters, goal origins, instructions, substitutions). */
export default function CareerMatchAnalysis({ analysis }: { analysis: CareerAnalysis }) {
  const { mine, theirs } = analysis;
  const hint = HINT_TEXT[analysis.matchup];
  const planSubs = analysis.plan?.subs ?? [];
  const doneSubs = new Set(analysis.substitutions.map((s) => s.sub));

  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
      <p className="font-display text-base font-bold text-ink-chalk">Тактический разбор</p>

      <div className="divide-y divide-white/5">
        <Row label="Тактика" value={`${analysis.formation} · ${tacticLabel(MENTALITIES, analysis.mentality)} · ${tacticLabel(PLAYSTYLES, analysis.playstyle)}`} />
        <Row label="Стиль соперника" value={tacticLabel(PLAYSTYLES, analysis.opponent_playstyle)} />
        <div className="flex items-center justify-between py-1 text-xs">
          <span className="text-ink-mist">Стиль против стиля</span>
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${hint.tone}`}>{hint.label}</span>
        </div>
        {analysis.familiarity_pct > 0 && <Row label="Сыгранность" value={`+${analysis.familiarity_pct}% к рейтингу`} />}
      </div>

      <div>
        <p className="mb-1 text-xs font-semibold text-ink-mist">Атаки</p>
        <div className="divide-y divide-white/5">
          <Row label="Владели инициативой" value={`${mine.attacks} : ${theirs.attacks}`} />
          <Row label="Ваши атаки" value={`фланги ${mine.wing_attack}, центр ${mine.central_attack}, без продвижения ${mine.recycled}`} />
          <Row label="Прорыв первой линии" value={`${mine.advance} из ${mine.wing_attack + mine.central_attack}`} />
          <Row label="Потеряли мяч в атаке" value={`${mine.breakdown}, из них моментов у соперника с контратаки ${theirs.counter_chances}`} />
          <Row label="Отобрали мяч у соперника" value={`${theirs.breakdown}, из них ваших моментов с контратаки ${mine.counter_chances}`} />
        </div>
      </div>

      <div>
        <p className="mb-1 text-xs font-semibold text-ink-mist">Голы</p>
        <div className="divide-y divide-white/5">
          <Row label="Ваши" value={goalsText(analysis.goals_mine)} />
          <Row label="Соперника" value={goalsText(analysis.goals_theirs)} />
        </div>
      </div>

      {(analysis.instructions.length > 0 || planSubs.length > 0 || (analysis.plan?.rules.length ?? 0) > 0) && (
        <div>
          <p className="mb-1 text-xs font-semibold text-ink-mist">План на матч</p>
          <ul className="flex flex-col gap-1 text-xs text-ink-chalk">
            {analysis.instructions.map((r, i) => (
              <li key={`r${i}`}>
                <span className="font-mono text-ink-mist-dim">{r.minute}&apos;</span>{" "}
                {r.rule === null
                  ? "условие больше не выполняется — базовая тактика"
                  : `указание ${r.rule + 1}: ${tacticLabel(MENTALITIES, r.mentality)} · ${tacticLabel(PLAYSTYLES, r.playstyle)}`}
              </li>
            ))}
            {analysis.plan && analysis.plan.rules.length > 0 && analysis.instructions.length === 0 && (
              <li className="text-ink-mist">Условия указаний в матче не наступили</li>
            )}
            {analysis.substitutions.map((s, i) => (
              <li key={`s${i}`}>
                <span className="font-mono text-ink-mist-dim">{s.minute}&apos;</span>{" "}
                {s.kind === "sub"
                  ? `замена: ${s.in} вместо ${s.out} (усталость ${s.fatigue}%)`
                  : `замена ${s.sub + 1} не проведена — в запасе нет подходящего игрока`}
              </li>
            ))}
            {planSubs.map((_, i) => !doneSubs.has(i) && (
              <li key={`u${i}`} className="text-ink-mist">Замена {i + 1}: условие не наступило</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
