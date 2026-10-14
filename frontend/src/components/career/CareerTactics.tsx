import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  previewCareerTactic,
  setCareerLineup,
  setCareerPlan,
  type CareerPlan,
  type CareerPlanRule,
  type CareerPlanSub,
  type CareerScouting,
  type CareerSeason,
  type CareerView,
  type MatchupHint,
  type MatchupReport,
  type ScoreState,
  type Tactic,
  type TacticsCatalog,
} from "@/api/career";
import TacticPitch from "@/components/career/TacticPitch";
import {
  AXIS_PHASES,
  HINT_TEXT,
  axisValueLabel,
  presetOf,
  previewFamiliarity,
  sameTactic,
  tacticLabel,
} from "@/lib/careerTactics";
import { FORMATIONS, MENTALITIES } from "@/lib/clubTactics";
import { haptic } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

function HintBadge({ hint }: { hint: MatchupHint }) {
  const h = HINT_TEXT[hint];
  return <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${h.tone}`}>{h.label}</span>;
}

function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`flex flex-col gap-3 rounded-3xl bg-bg-surface p-4 ${className}`}>{children}</section>;
}

/** A compact set of tags describing a tactic, one per axis. */
export function TacticTags({ catalog, tactic, highlight }: { catalog: TacticsCatalog; tactic: Tactic; highlight?: Tactic | null }) {
  return (
    <div className="flex flex-wrap gap-1">
      {catalog.axes.map((a) => (
        <span
          key={a.key}
          title={a.label}
          className={`rounded-lg px-2 py-0.5 text-[10px] font-semibold ${
            highlight && highlight[a.key] !== tactic[a.key] ? "bg-amber-400/15 text-amber-300" : "bg-white/5 text-ink-chalk"
          }`}
        >
          {axisValueLabel(catalog, a.key, tactic[a.key])}
        </span>
      ))}
    </div>
  );
}

const FORM_TONE: Record<string, string> = { W: "bg-accent-lime/80", D: "bg-white/30", L: "bg-red-400/80" };
const FORM_LABEL: Record<string, string> = { W: "В", D: "Н", L: "П" };

export function ScoutingCard({ scouting, catalog, difficultyLabel }: {
  scouting: CareerScouting; catalog: TacticsCatalog | null | undefined; difficultyLabel: string;
}) {
  const preset = presetOf(catalog, scouting.tactic);
  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wider text-ink-mist">Разведка · тур {scouting.round_index + 1}</p>
          <p className="truncate font-display text-base font-bold text-ink-chalk">{scouting.opponent_name}</p>
        </div>
        {scouting.strength !== null && (
          <span className="shrink-0 rounded-xl bg-bg-raised px-2 py-1 text-center">
            <span className="block font-mono text-sm font-bold text-ink-chalk">{scouting.strength}</span>
            <span className="block text-[9px] text-ink-mist">сила</span>
          </span>
        )}
      </div>

      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-ink-mist">Форма</span>
        {scouting.form.length === 0 ? (
          <span className="text-[11px] text-ink-mist-dim">ещё не играл</span>
        ) : (
          scouting.form.map((r, i) => (
            <span key={i} className={`flex h-5 w-5 items-center justify-center rounded-md text-[10px] font-bold text-bg-base ${FORM_TONE[r]}`}>
              {FORM_LABEL[r] ?? r}
            </span>
          ))
        )}
      </div>

      {scouting.head_to_head && scouting.head_to_head.meetings > 0 && (
        <p className="text-[11px] text-ink-mist">
          Личные встречи: {scouting.head_to_head.meetings + 1}-я встреча · В{scouting.head_to_head.w} Н{scouting.head_to_head.d} П{scouting.head_to_head.l}
        </p>
      )}
      {scouting.tactic && catalog ? (
        <div className="rounded-2xl bg-bg-raised p-3">
          <p className="mb-1.5 text-[11px] text-ink-mist">
            {scouting.source === "last_match" ? "В прошлом туре" : "Заявка на сезон"}: {scouting.formation} ·{" "}
            {tacticLabel(MENTALITIES, scouting.mentality)}
            {preset && <> · <span className="text-ink-chalk">{preset}</span></>}
          </p>
          <TacticTags catalog={catalog} tactic={scouting.tactic} />
        </div>
      ) : scouting.playstyle ? (
        <p className="text-xs text-ink-mist">Стиль: {scouting.playstyle}</p>
      ) : (
        <p className="text-xs text-ink-mist">Тактика друга станет известна после его первого матча.</p>
      )}

      {scouting.adaptive && scouting.threat && catalog && (
        <div className="rounded-2xl bg-amber-400/10 p-3 text-[11px] text-amber-200">
          <p className="font-semibold text-amber-300">Соперник уровня «{difficultyLabel}» читает игру</p>
          <p className="mt-0.5">
            Против твоей прошлой тактики он скорее всего выберет «
            {catalog.presets.find((p) => p.code === scouting.threat!.preset)?.label ?? scouting.threat.preset}». Твой выбор
            на этот тур он не видит.
          </p>
        </div>
      )}
    </Card>
  );
}

export function MatchupList({ report, compact = false }: { report: MatchupReport; compact?: boolean }) {
  const items = [...report.items].sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  if (!items.length) {
    return <p className="text-[11px] text-ink-mist">Тактики не пересекаются — решат игроки.</p>;
  }
  return (
    <ul className="flex flex-col gap-1">
      {items.slice(0, compact ? 3 : items.length).map((item) => {
        const good = item.favours === "me";
        return (
          <li key={`${item.id}-${item.attacker}`} className="flex items-start gap-2 text-[11px] leading-snug">
            <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold ${
              good ? "bg-accent-lime/20 text-accent-lime" : "bg-red-500/20 text-red-400"}`}
            >
              {good ? "+" : "−"}
            </span>
            <span className="text-ink-chalk">
              {item.label}
              <span className="text-ink-mist-dim"> · {item.attacker === "me" ? "ваши атаки" : "атаки соперника"}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function Segmented({ value, options, onChange, label }: {
  value: string; options: { value: string; label: string }[]; onChange: (v: string) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={`grid gap-1 rounded-xl bg-bg-raised p-1 ${
      options.length === 2 ? "grid-cols-2" : options.length === 3 ? "grid-cols-3" : "grid-cols-4"}`}
    >
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-lg px-1 py-1.5 text-[11px] font-semibold leading-tight transition-colors ${
            value === o.value ? "bg-floodlight text-bg-base" : "text-ink-mist active:bg-white/5"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Round prep: formation, mentality and the tactical axes (or a preset),
 * with a pitch schematic, the matchup against the scouted opponent
 * previewed before saving, and familiarity. */
export function TacticsBoard({ season, catalog, onView, onError }: {
  season: CareerSeason; catalog: TacticsCatalog;
} & Handlers) {
  const savedTactic = useMemo(() => season.tactic ?? {}, [season.tactic]);
  const savedKey = JSON.stringify([season.formation, season.mentality, savedTactic]);
  const [formation, setFormation] = useState(season.formation);
  const [mentality, setMentality] = useState(season.mentality);
  const [tactic, setTactic] = useState<Tactic>(savedTactic);
  useEffect(() => {
    const [f, m, t] = JSON.parse(savedKey) as [string, string, Tactic];
    setFormation(f); setMentality(m); setTactic(t);
  }, [savedKey]);

  const dirty = savedKey !== JSON.stringify([formation, mentality, tactic]);
  const opponentKnown = !!season.scouting?.tactic;
  const { data: preview } = useQuery({
    queryKey: ["career", "preview", season.id, season.rounds_played, JSON.stringify(tactic)],
    queryFn: () => previewCareerTactic(tactic),
    enabled: opponentKnown && !sameTactic(tactic, savedTactic),
    staleTime: 60_000,
  });
  const report = sameTactic(tactic, savedTactic) ? season.scouting?.matchup ?? null : preview ?? null;

  const save = useMutation({
    mutationFn: () =>
      setCareerLineup({
        slots: formation === season.formation ? season.lineup : {},
        formation, mentality, playstyle: season.playstyle, tactic, round_index: season.rounds_played,
      }),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });

  const fam = season.familiarity;
  const famPreview = fam
    ? previewFamiliarity(fam.stored_pct, fam.keep_pct, fam.axis_keep_pct, fam.last_formation, fam.last_tactic, formation, tactic)
    : 0;
  const activePreset = catalog.presets.find((p) => sameTactic(p.tactic, tactic));

  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-ink-mist">Тактика на тур {season.rounds_played + 1}</p>
          <p className="font-display text-base font-bold text-ink-chalk">{activePreset?.label ?? "Своя тактика"}</p>
        </div>
        {report && <HintBadge hint={report.hint} />}
      </div>

      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1" style={{ scrollbarWidth: "none" }} role="radiogroup" aria-label="Готовые тактики">
        {catalog.presets.map((p) => {
          const on = sameTactic(p.tactic, tactic);
          return (
            <button
              key={p.code}
              role="radio"
              aria-checked={on}
              onClick={() => { setTactic({ ...p.tactic }); haptic("light"); }}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${on ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"}`}
            >
              {p.label}
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] items-start gap-3">
        <TacticPitch formation={formation} tactic={tactic} />
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-ink-mist">Схема</span>
            <select
              aria-label="Схема"
              value={formation}
              onChange={(e) => setFormation(e.target.value)}
              className="rounded-xl bg-bg-raised px-2 py-2 text-xs text-ink-chalk outline-none"
            >
              {FORMATIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-ink-mist">Настрой</span>
            <select
              aria-label="Настрой"
              value={mentality}
              onChange={(e) => setMentality(e.target.value)}
              className="rounded-xl bg-bg-raised px-2 py-2 text-xs text-ink-chalk outline-none"
            >
              {MENTALITIES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          {fam && (
            <div className="rounded-xl bg-bg-raised p-2">
              <div className="flex items-center justify-between text-[10px]">
                <span className="uppercase tracking-wider text-ink-mist">Сыгранность</span>
                <span className="font-mono font-bold text-ink-chalk">+{famPreview.toFixed(1)}%</span>
              </div>
              <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-white/10">
                <span className="block h-full bg-floodlight" style={{ width: `${Math.min(100, (famPreview / (fam.max_pct || 1)) * 100)}%` }} />
              </span>
              <p className="mt-1 text-[9px] leading-tight text-ink-mist-dim">
                до {fam.max_pct}% · +{fam.step_pct}% за матч без изменений
              </p>
            </div>
          )}
        </div>
      </div>

      {AXIS_PHASES.map((phase) => (
        <div key={phase.title} className="flex flex-col gap-2">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-accent-cyan">{phase.title}</p>
          {phase.axes.map((axis) => {
            const def = catalog.axes.find((a) => a.key === axis);
            if (!def) return null;
            const current = def.values.find((v) => v.value === tactic[axis]);
            return (
              <div key={axis} className="flex flex-col gap-1">
                <span className="text-[11px] font-semibold text-ink-chalk">{def.label}</span>
                <Segmented label={def.label} value={tactic[axis] ?? ""} options={def.values}
                  onChange={(v) => setTactic({ ...tactic, [axis]: v })} />
                {current && <p className="text-[10px] leading-snug text-ink-mist">{current.hint}</p>}
              </div>
            );
          })}
        </div>
      ))}

      {report && season.scouting && (
        <div className="rounded-2xl bg-bg-raised p-3">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <p className="text-[11px] font-semibold text-ink-chalk">Против «{season.scouting.opponent_name}»</p>
            <HintBadge hint={report.hint} />
          </div>
          <MatchupList report={report} />
          {season.scouting.source === "last_match" && (
            <p className="mt-1.5 text-[10px] text-ink-mist-dim">По тактике, которую он сыграл в прошлом туре.</p>
          )}
        </div>
      )}

      {formation !== season.formation && (
        <p className="text-[11px] text-amber-300">Новая схема — расстановка заполнится автоматически, её можно поправить во вкладке «Состав».</p>
      )}
      <button
        onClick={() => save.mutate()}
        disabled={!dirty || save.isPending}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {save.isPending ? "Сохраняем..." : dirty ? "Сохранить тактику" : "Тактика сохранена"}
      </button>
    </Card>
  );
}

const SCORE_OPTIONS: { value: ScoreState; label: string }[] = [
  { value: "behind", label: "Проигрываем" },
  { value: "level", label: "Ничья" },
  { value: "ahead", label: "Ведём" },
];
const MINUTES = [15, 30, 45, 55, 60, 65, 70, 75, 80, 85];
const FATIGUE_THRESHOLDS = [0, 50, 60, 70, 80];
const KEEP = "";

function Select({ value, options, onChange, label }: {
  value: string; options: { value: string; label: string }[]; onChange: (v: string) => void; label: string;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="min-w-0 rounded-xl bg-bg-base/60 px-2 py-2 text-[11px] text-ink-chalk outline-none"
    >
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function newRule(): CareerPlanRule {
  return { score: "behind", margin: 1, from_minute: 60, mentality: "ATTACKING", tactic: {} };
}

function newSub(): CareerPlanSub {
  return { minute: 65, slot: null, card_id: null, min_fatigue: 60 };
}

/** Conditional instructions + substitutions; the server validates and
 * applies them phase by phase during the match. */
export function PlanEditor({ season, catalog, onView, onError }: {
  season: CareerSeason; catalog: TacticsCatalog;
} & Handlers) {
  const saved: CareerPlan = season.match_plan ?? { rules: [], subs: [] };
  const savedKey = JSON.stringify(saved);
  const [rules, setRules] = useState<CareerPlanRule[]>(saved.rules);
  const [subs, setSubs] = useState<CareerPlanSub[]>(saved.subs);
  useEffect(() => {
    const plan = JSON.parse(savedKey) as CareerPlan;
    setRules(plan.rules.map((r) => ({ ...r, tactic: r.tactic ?? {} })));
    setSubs(plan.subs);
  }, [savedKey]);
  const maxRules = season.plan_limits?.rules ?? 3;
  const maxSubs = season.plan_limits?.subs ?? 3;
  const save = useMutation({
    mutationFn: () => setCareerPlan({ rules, subs, round_index: season.rounds_played }),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  const dirty = JSON.stringify({ rules, subs }) !== savedKey;
  const updRule = (i: number, patch: Partial<CareerPlanRule>) => setRules(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const setRuleAxis = (i: number, axis: string, value: string) => {
    const tactic = { ...rules[i].tactic };
    if (value) tactic[axis] = value;
    else delete tactic[axis];
    updRule(i, { tactic });
  };
  const updSub = (i: number, patch: Partial<CareerPlanSub>) => setSubs(subs.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const squadOptions = season.squad
    .filter((s) => s.owned)
    .map((s) => ({
      value: String(s.card_id),
      label: s.card ? `${s.card.player.display_name} · ${s.card.player.position}` : s.my_player ? `${s.my_player.name} · ${s.my_player.position}` : `#${s.card_id}`,
    }));

  return (
    <Card>
      <div>
        <p className="font-display text-base font-bold text-ink-chalk">План на матч</p>
        <p className="text-[11px] leading-snug text-ink-mist">
          Указание действует, пока выполняется условие, потом команда возвращается к базовой тактике. Нижнее указание важнее верхнего.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-accent-cyan">Указания · {rules.length}/{maxRules}</p>
        {rules.map((rule, i) => (
          <div key={i} className="flex flex-col gap-2 rounded-2xl bg-bg-raised p-3" aria-label={`Указание ${i + 1}`}>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-ink-chalk">Указание {i + 1}</span>
              <button onClick={() => setRules(rules.filter((_, j) => j !== i))} className="text-[11px] text-red-400">Удалить</button>
            </div>
            <div className="grid grid-cols-3 gap-1.5">
              <Select label="Счёт" value={rule.score} options={SCORE_OPTIONS}
                onChange={(v) => updRule(i, { score: v as ScoreState, margin: v === "level" ? 0 : Math.max(1, rule.margin) })} />
              {rule.score === "level" ? <span /> : (
                <Select label="Разница" value={String(rule.margin)} options={[1, 2, 3].map((m) => ({ value: String(m), label: `на ${m}+` }))}
                  onChange={(v) => updRule(i, { margin: Number(v) })} />
              )}
              <Select label="С минуты" value={String(rule.from_minute)} options={MINUTES.map((m) => ({ value: String(m), label: `с ${m}'` }))}
                onChange={(v) => updRule(i, { from_minute: Number(v) })} />
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <Select label="Настрой" value={rule.mentality ?? KEEP} options={[{ value: KEEP, label: "Настрой —" }, ...MENTALITIES]}
                onChange={(v) => updRule(i, { mentality: v || null })} />
              {catalog.axes.map((a) => (
                <Select key={a.key} label={a.label} value={rule.tactic[a.key] ?? KEEP}
                  options={[{ value: KEEP, label: `${a.label} —` }, ...a.values]}
                  onChange={(v) => setRuleAxis(i, a.key, v)} />
              ))}
            </div>
          </div>
        ))}
        {rules.length < maxRules && (
          <button onClick={() => setRules([...rules, newRule()])} className="rounded-xl border border-dashed border-white/15 py-2 text-xs font-semibold text-ink-chalk">
            + Указание
          </button>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-accent-cyan">Замены · {subs.length}/{maxSubs}</p>
        {subs.map((sub, i) => (
          <div key={i} className="flex flex-col gap-2 rounded-2xl bg-bg-raised p-3" aria-label={`Замена ${i + 1}`}>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-ink-chalk">Замена {i + 1}</span>
              <button onClick={() => setSubs(subs.filter((_, j) => j !== i))} className="text-[11px] text-red-400">Удалить</button>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <Select label="Минута" value={String(sub.minute)} options={MINUTES.map((m) => ({ value: String(m), label: `с ${m}'` }))}
                onChange={(v) => updSub(i, { minute: Number(v) })} />
              <Select label="Усталость" value={String(sub.min_fatigue)}
                options={FATIGUE_THRESHOLDS.map((f) => ({ value: String(f), label: f ? `усталость ≥ ${f}%` : "в любом случае" }))}
                onChange={(v) => updSub(i, { min_fatigue: Number(v) })} />
              <Select label="Кого менять" value={sub.slot ?? KEEP}
                options={[{ value: KEEP, label: "Самого уставшего" }, ...season.slots.map((s) => ({ value: s.code, label: `Позиция ${s.code}` }))]}
                onChange={(v) => updSub(i, { slot: v || null })} />
              <Select label="Кто выходит" value={sub.card_id === null ? KEEP : String(sub.card_id)}
                options={[{ value: KEEP, label: "Лучший из запаса" }, ...squadOptions]}
                onChange={(v) => updSub(i, { card_id: v ? Number(v) : null })} />
            </div>
          </div>
        ))}
        {subs.length < maxSubs && (
          <button onClick={() => setSubs([...subs, newSub()])} className="rounded-xl border border-dashed border-white/15 py-2 text-xs font-semibold text-ink-chalk">
            + Замена
          </button>
        )}
        <p className="text-[10px] leading-snug text-ink-mist-dim">
          Усталость растёт по ходу матча — быстрее при высоком прессинге и контрпрессинге. Если выбранный игрок не может выйти, выйдет лучший подходящий из запаса.
        </p>
      </div>

      <button
        onClick={() => save.mutate()}
        disabled={!dirty || save.isPending}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {save.isPending ? "Сохраняем..." : dirty ? "Сохранить план" : "План сохранён"}
      </button>
    </Card>
  );
}

