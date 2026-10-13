import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  setCareerLineup,
  setCareerPlan,
  type CareerPlan,
  type CareerPlanRule,
  type CareerPlanSub,
  type CareerScouting,
  type CareerSeason,
  type CareerView,
  type MatchupHint,
  type ScoreState,
} from "@/api/career";
import { HINT_TEXT, tacticLabel } from "@/lib/careerTactics";
import { FORMATIONS, MENTALITIES, PLAYSTYLES } from "@/lib/clubTactics";
import { haptic } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

/** Same rule the server applies (career_tactics_service.matchup_hint), from
 * the lists the server sent for this opponent — no local counter table. */
function previewHint(scouting: CareerScouting, playstyle: string): MatchupHint | null {
  if (scouting.hint === null || !scouting.playstyle) return null;
  if (scouting.counters.includes(playstyle)) return "advantage";
  if (scouting.beats.includes(playstyle)) return "disadvantage";
  return "neutral";
}

function HintBadge({ hint }: { hint: MatchupHint }) {
  const h = HINT_TEXT[hint];
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${h.tone}`}>{h.label}</span>;
}

const FORM_TONE: Record<string, string> = { W: "bg-accent-lime/80", D: "bg-white/30", L: "bg-red-400/80" };
const FORM_LABEL: Record<string, string> = { W: "В", D: "Н", L: "П" };

export function ScoutingCard({ scouting, difficultyLabel }: { scouting: CareerScouting; difficultyLabel: string }) {
  const known = !!scouting.playstyle;
  return (
    <section className="flex flex-col gap-2 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-display text-base font-bold text-ink-chalk">Разведка: {scouting.opponent_name}</p>
        {scouting.strength !== null && <span className="shrink-0 text-xs text-ink-mist">сила ~{scouting.strength}</span>}
      </div>
      {known ? (
        <>
          <p className="text-xs text-ink-mist">
            {scouting.source === "last_match" ? "В прошлом туре играл" : "Заявка на сезон"}:{" "}
            <span className="text-ink-chalk">
              {scouting.formation} · {tacticLabel(MENTALITIES, scouting.mentality)} · {tacticLabel(PLAYSTYLES, scouting.playstyle)}
            </span>
          </p>
          {scouting.counters.length > 0 && (
            <p className="text-[11px] text-ink-mist">
              Его стиль контрят: {scouting.counters.map((s) => tacticLabel(PLAYSTYLES, s)).join(", ")}
            </p>
          )}
        </>
      ) : (
        <p className="text-xs text-ink-mist">Тактика друга станет известна после его первого матча.</p>
      )}
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-ink-mist">Форма:</span>
        {scouting.form.length === 0 ? (
          <span className="text-[11px] text-ink-mist-dim">ещё не играл</span>
        ) : (
          scouting.form.map((r, i) => (
            <span key={i} className={`flex h-5 w-5 items-center justify-center rounded text-[10px] font-bold text-bg-base ${FORM_TONE[r]}`}>
              {FORM_LABEL[r] ?? r}
            </span>
          ))
        )}
      </div>
      {scouting.adaptive && scouting.my_last_playstyle && (
        <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-[11px] text-amber-300">
          Соперник уровня «{difficultyLabel}» может подстроиться под твою прошлую тактику
          ({tacticLabel(PLAYSTYLES, scouting.my_last_playstyle)}). Опасные для неё стили:{" "}
          {scouting.threat_styles.map((s) => tacticLabel(PLAYSTYLES, s)).join(", ")}. Твой выбор на этот тур он не видит.
        </p>
      )}
    </section>
  );
}

function Select({ value, options, onChange, label }: {
  value: string; options: { value: string; label: string }[]; onChange: (v: string) => void; label?: string;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="min-w-0 rounded-xl bg-bg-raised px-2 py-2 text-xs text-ink-chalk outline-none"
    >
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

/** Round prep: formation / mentality / style for the coming round, with the
 * matchup hint and familiarity previewed before saving. */
export function TacticsCard({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const [formation, setFormation] = useState(season.formation);
  const [mentality, setMentality] = useState(season.mentality);
  const [playstyle, setPlaystyle] = useState(season.playstyle);
  const savedKey = `${season.formation}|${season.mentality}|${season.playstyle}`;
  useEffect(() => {
    const [f, m, p] = savedKey.split("|");
    setFormation(f); setMentality(m); setPlaystyle(p);
  }, [savedKey]);
  const save = useMutation({
    mutationFn: () =>
      setCareerLineup({
        slots: formation === season.formation ? season.lineup : {},
        formation, mentality, playstyle, round_index: season.rounds_played,
      }),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  const dirty = savedKey !== `${formation}|${mentality}|${playstyle}`;
  const hint = season.scouting ? previewHint(season.scouting, playstyle) : null;
  const fam = season.familiarity;
  let famPreview = fam?.stored_pct ?? 0;
  if (fam?.last_formation && formation !== fam.last_formation) famPreview = (famPreview * fam.keep_pct) / 100;
  if (fam?.last_playstyle && playstyle !== fam.last_playstyle) famPreview = (famPreview * fam.keep_pct) / 100;

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="font-display text-base font-bold text-ink-chalk">Тактика на тур {season.rounds_played + 1}</p>
        {hint && <HintBadge hint={hint} />}
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Select label="Схема" value={formation} options={FORMATIONS} onChange={setFormation} />
        <Select label="Настрой" value={mentality} options={MENTALITIES} onChange={setMentality} />
        <Select label="Стиль" value={playstyle} options={PLAYSTYLES} onChange={setPlaystyle} />
      </div>
      {hint && season.scouting?.playstyle && (
        <p className="text-[11px] text-ink-mist">
          {tacticLabel(PLAYSTYLES, playstyle)} против «{tacticLabel(PLAYSTYLES, season.scouting.playstyle)}»:{" "}
          {HINT_TEXT[hint].label.toLowerCase()}
          {hint !== "neutral" && " — в каждой дуэли матча"}
          {formation !== season.formation && ". Смена схемы сбросит расстановку на авто"}
        </p>
      )}
      {fam && (
        <div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-ink-mist">Сыгранность</span>
            <span className="font-mono font-bold text-ink-chalk">+{famPreview.toFixed(1)}% / {fam.max_pct}%</span>
          </div>
          <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-white/10">
            <span className="block h-full bg-accent-lime" style={{ width: `${Math.min(100, (famPreview / (fam.max_pct || 1)) * 100)}%` }} />
          </span>
          <p className="mt-1 text-[10px] text-ink-mist-dim">
            +{fam.step_pct}% к рейтингу за каждый матч с той же схемой и стилем. Смена схемы или стиля оставляет {fam.keep_pct}% (каждое).
          </p>
        </div>
      )}
      <button
        onClick={() => save.mutate()}
        disabled={!dirty || save.isPending}
        className="rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {save.isPending ? "Сохраняем..." : dirty ? "Сохранить тактику" : "Тактика сохранена"}
      </button>
    </section>
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

function newRule(): CareerPlanRule {
  return { score: "behind", margin: 1, from_minute: 60, mentality: "ATTACKING", playstyle: null };
}

function newSub(): CareerPlanSub {
  return { minute: 65, slot: null, card_id: null, min_fatigue: 60 };
}

/** Conditional instructions + substitutions; the server validates and
 * applies them phase by phase during the match. */
export function PlanEditor({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const saved: CareerPlan = season.match_plan ?? { rules: [], subs: [] };
  const savedKey = JSON.stringify(saved);
  const [rules, setRules] = useState<CareerPlanRule[]>(saved.rules);
  const [subs, setSubs] = useState<CareerPlanSub[]>(saved.subs);
  useEffect(() => {
    const plan = JSON.parse(savedKey) as CareerPlan;
    setRules(plan.rules); setSubs(plan.subs);
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
  const updSub = (i: number, patch: Partial<CareerPlanSub>) => setSubs(subs.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const squadOptions = season.squad
    .filter((s) => s.owned)
    .map((s) => ({
      value: String(s.card_id),
      label: s.card ? `${s.card.player.display_name} (${s.card.player.position})` : s.my_player ? `${s.my_player.name} (${s.my_player.position})` : `#${s.card_id}`,
    }));

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div>
        <p className="font-display text-base font-bold text-ink-chalk">План на матч</p>
        <p className="text-[11px] text-ink-mist">
          Указания проверяются по ходу матча: пока условие выполняется — действует указание, иначе базовая тактика.
          Позднее указание важнее раннего.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-xs font-semibold text-ink-mist">Указания · {rules.length}/{maxRules}</p>
        {rules.map((rule, i) => (
          <div key={i} className="grid grid-cols-2 gap-1.5 rounded-2xl bg-bg-raised p-2" aria-label={`Указание ${i + 1}`}>
            <Select label="Счёт" value={rule.score} options={SCORE_OPTIONS}
              onChange={(v) => updRule(i, { score: v as ScoreState, margin: v === "level" ? 0 : Math.max(1, rule.margin) })} />
            {rule.score === "level" ? <span /> : (
              <Select label="Разница" value={String(rule.margin)} options={[1, 2, 3].map((m) => ({ value: String(m), label: `на ${m}+` }))}
                onChange={(v) => updRule(i, { margin: Number(v) })} />
            )}
            <Select label="С минуты" value={String(rule.from_minute)} options={MINUTES.map((m) => ({ value: String(m), label: `с ${m}'` }))}
              onChange={(v) => updRule(i, { from_minute: Number(v) })} />
            <span />
            <Select label="Настрой" value={rule.mentality ?? KEEP} options={[{ value: KEEP, label: "Настрой без изменений" }, ...MENTALITIES]}
              onChange={(v) => updRule(i, { mentality: v || null })} />
            <Select label="Стиль" value={rule.playstyle ?? KEEP} options={[{ value: KEEP, label: "Стиль без изменений" }, ...PLAYSTYLES]}
              onChange={(v) => updRule(i, { playstyle: v || null })} />
            <button onClick={() => setRules(rules.filter((_, j) => j !== i))} className="col-span-2 text-left text-[11px] text-red-400">
              Удалить указание
            </button>
          </div>
        ))}
        {rules.length < maxRules && (
          <button onClick={() => setRules([...rules, newRule()])} className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-chalk">
            + Указание
          </button>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-xs font-semibold text-ink-mist">Замены · {subs.length}/{maxSubs}</p>
        {subs.map((sub, i) => (
          <div key={i} className="grid grid-cols-2 gap-1.5 rounded-2xl bg-bg-raised p-2" aria-label={`Замена ${i + 1}`}>
            <Select label="Минута" value={String(sub.minute)} options={MINUTES.map((m) => ({ value: String(m), label: `с ${m}'` }))}
              onChange={(v) => updSub(i, { minute: Number(v) })} />
            <Select label="Усталость" value={String(sub.min_fatigue)}
              options={FATIGUE_THRESHOLDS.map((f) => ({ value: String(f), label: f ? `если усталость ≥ ${f}%` : "в любом случае" }))}
              onChange={(v) => updSub(i, { min_fatigue: Number(v) })} />
            <Select label="Кого менять" value={sub.slot ?? KEEP}
              options={[{ value: KEEP, label: "Самого уставшего" }, ...season.slots.map((s) => ({ value: s.code, label: `Позиция ${s.code}` }))]}
              onChange={(v) => updSub(i, { slot: v || null })} />
            <Select label="Кто выходит" value={sub.card_id === null ? KEEP : String(sub.card_id)}
              options={[{ value: KEEP, label: "Лучший из запаса" }, ...squadOptions]}
              onChange={(v) => updSub(i, { card_id: v ? Number(v) : null })} />
            <button onClick={() => setSubs(subs.filter((_, j) => j !== i))} className="col-span-2 text-left text-[11px] text-red-400">
              Удалить замену
            </button>
          </div>
        ))}
        {subs.length < maxSubs && (
          <button onClick={() => setSubs([...subs, newSub()])} className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-chalk">
            + Замена
          </button>
        )}
        <p className="text-[10px] text-ink-mist-dim">
          Усталость растёт и по ходу матча. Если выбранный игрок не может выйти (травма, уже на поле, не та линия) — выйдет лучший подходящий из запаса.
        </p>
      </div>

      <button
        onClick={() => save.mutate()}
        disabled={!dirty || save.isPending}
        className="rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {save.isPending ? "Сохраняем..." : dirty ? "Сохранить план" : "План сохранён"}
      </button>
    </section>
  );
}
