import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import {
  chooseCoachSpec, setCareerSpeech, type CareerMatchEvents, type CareerSeason, type CareerView,
  type CoachSpecs, type MoraleOption,
} from "@/api/career";
import analystArt from "@/assets/coach/analyst.webp";
import motivatorArt from "@/assets/coach/motivator.webp";
import oratorArt from "@/assets/coach/orator.webp";
import psychologistArt from "@/assets/coach/psychologist.webp";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { haptic } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

const LEVEL_TONE: Record<number, string> = {
  2: "text-accent-lime", 1: "text-accent-green", 0: "text-ink-chalk", [-1]: "text-amber-300", [-2]: "text-red-400",
};
const SPEECH_ICON: Record<string, string> = { inspire: "🔥", calm: "🫶", demand: "☝️" };
const TALK_ICON: Record<string, string> = { praise: "👏", rouse: "📢", calm: "🤫" };

/** Character traits (backend career_morale_service.TRAITS): only about
 * how a player lives with the team's mood. */
const TRAITS: Record<string, { icon: string; label: string; hint: string }> = {
  spark: { icon: "🎉", label: "Заводила", hint: "Сыграл и победили — мораль команды растёт сильнее." },
  stoic: { icon: "🗿", label: "Стоик", hint: "Плохое настроение команды не снижает его рейтинг." },
  emotional: { icon: "🎭", label: "Эмоциональный", hint: "Настроение команды влияет на него вдвое сильнее." },
  peacemaker: { icon: "🕊️", label: "Миротворец", hint: "Сыграл и проиграли — мораль падает слабее." },
  grumbler: { icon: "😤", label: "Ворчун", hint: "Остался без игры — мораль команды после матча ниже." },
};

export function TraitBadge({ trait, className = "" }: { trait?: string | null; className?: string }) {
  const meta = trait ? TRAITS[trait] : undefined;
  if (!meta) return null;
  return (
    <span title={`${meta.label}: ${meta.hint}`} aria-label={`Характер: ${meta.label}`}
      className={`pointer-events-none rounded-full bg-black/60 px-[3px] text-[9px] leading-tight ${className}`}>
      {meta.icon}
    </span>
  );
}

function Gauge({ value, level }: { value: number; level: number }) {
  return (
    <span className="relative block h-2 overflow-hidden rounded-full bg-white/10" aria-label={`Мораль ${value} из 100`}>
      {[20, 40, 70, 90].map((mark) => (
        <span key={mark} className="absolute top-0 h-full w-px bg-bg-base/70" style={{ left: `${mark}%` }} aria-hidden />
      ))}
      <span className={`block h-full rounded-full ${level > 0 ? "bg-floodlight" : level < 0 ? "bg-red-400" : "bg-ink-mist"}`}
        style={{ width: `${value}%` }} />
    </span>
  );
}

/** «Мораль команды» before the next round: the mood and its rating shift,
 * what moved it lately and the pre-match speech (one per round). */
export function MoraleCard({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const m = season.morale;
  const speech = useMutation({
    mutationFn: (code: string | null) => setCareerSpeech(code, season.rounds_played),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  if (!m) return null;
  const last = m.log[m.log.length - 1];
  const chosen = m.speeches.find((s) => s.code === m.speech);
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-display text-base font-bold text-ink-chalk">Мораль команды</p>
          <p className={`text-caption font-semibold ${LEVEL_TONE[m.level] ?? "text-ink-chalk"}`}>
            {m.label}{m.rating ? ` · ${m.rating > 0 ? "+" : ""}${m.rating} к рейтингу игроков` : " · без влияния на рейтинг"}
          </p>
        </div>
        <span className="font-mono text-lg font-bold text-ink-chalk">{m.value}</span>
      </div>
      <Gauge value={m.value} level={m.level} />
      {last && (
        <p className="text-micro leading-snug text-ink-mist">
          Тур {last.round + 1}: {last.before} → {last.after}
          {last.reasons.length > 0 && ` · ${last.reasons.join(", ")}`}
        </p>
      )}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <p className="text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">Речь перед матчем</p>
          {m.speech && (
            <button type="button" onClick={() => speech.mutate(null)} disabled={speech.isPending}
              className="text-micro text-ink-mist underline underline-offset-2">без речи</button>
          )}
        </div>
        <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Речь перед матчем">
          {m.speeches.map((s) => {
            const on = s.code === m.speech;
            return (
              <button key={s.code} type="button" role="radio" aria-checked={on} disabled={speech.isPending}
                onClick={() => speech.mutate(s.code)}
                className={`flex flex-col items-center gap-0.5 rounded-2xl px-2 py-2 text-center ${on ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"}`}>
                <span className="text-base" aria-hidden>{SPEECH_ICON[s.code] ?? "🗣"}</span>
                <span className="text-micro font-semibold leading-tight">{s.label}</span>
              </button>
            );
          })}
        </div>
        <p className="text-caption leading-snug text-ink-mist">
          {chosen ? chosen.hint : "Одна речь на тур. Что сработает — зависит от настроения команды и от того, кто фаворит."}
        </p>
      </div>
      <p className="text-micro text-ink-mist-dim">
        Мораль растёт от побед (особенно над фаворитом), падает от поражений и понемногу возвращается к норме.
        Тренировка «Сплочение» — +{m.team_building} перед матчем.
      </p>
    </section>
  );
}

/** «Разговор в перерыве» in the live match centre: goes with the orders. */
export function HalftimeTalk({ talks, value, onChange }: {
  talks: MoraleOption[]; value: string | null; onChange: (talk: string | null) => void;
}) {
  if (!talks.length) return null;
  const chosen = talks.find((t) => t.code === value);
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">Разговор в перерыве</p>
      <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Разговор в перерыве">
        {talks.map((t) => {
          const on = t.code === value;
          return (
            <button key={t.code} type="button" role="radio" aria-checked={on} onClick={() => onChange(on ? null : t.code)}
              className={`flex flex-col items-center gap-0.5 rounded-xl px-2 py-1.5 ${on ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"}`}>
              <span aria-hidden>{TALK_ICON[t.code] ?? "🗣"}</span>
              <span className="text-micro font-semibold">{t.label}</span>
            </button>
          );
        })}
      </div>
      <p className="text-micro leading-snug text-ink-mist">{chosen ? chosen.hint : "Зависит от счёта и настроения команды."}</p>
    </div>
  );
}

/** After the match: how the team's morale moved and why. */
export function MatchMorale({ morale }: { morale: CareerMatchEvents["morale"] }) {
  if (!morale) return null;
  const delta = morale.after - morale.before;
  return (
    <section className="flex flex-col gap-1.5 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="font-display text-base font-bold text-ink-chalk">Мораль команды</p>
        <span className={`font-mono text-sm font-bold ${delta > 0 ? "text-accent-lime" : delta < 0 ? "text-red-400" : "text-ink-mist"}`}>
          {morale.before} → {morale.after}
        </span>
      </div>
      {morale.match.length > 0 && <p className="text-micro text-ink-mist">В матче: {morale.match.join(", ")}</p>}
      {morale.reasons.length > morale.match.length && (
        <p className="text-micro text-ink-mist">После: {morale.reasons.slice(morale.match.length).join(", ")}</p>
      )}
    </section>
  );
}

const SPEC_ART: Record<string, string> = {
  motivator: motivatorArt, psychologist: psychologistArt, orator: oratorArt, analyst: analystArt,
};

/** A specialization's art, the emoji when there is none. */
function SpecArt({ code, icon, className }: { code: string; icon: string; className: string }) {
  const art = SPEC_ART[code];
  return art
    ? <img src={art} alt="" aria-hidden decoding="async" className={`shrink-0 object-cover ${className}`} />
    : <span className="text-xl" aria-hidden>{icon}</span>;
}

/** «Специализация тренера»: one of four, levelled slowly with experience
 * (league matches and the season's final place); switching keeps the
 * experience of each, but is allowed once in `switch_days`. */
export function CoachSpecCard({ coach, onView, onError }: { coach: CoachSpecs } & Handlers) {
  const [open, setOpen] = useState<string>(coach.spec ?? coach.specs[0]?.code ?? "");
  const [confirm, setConfirm] = useState(false);
  const choose = useMutation({
    mutationFn: (code: string) => chooseCoachSpec(code),
    onSuccess: (v) => { haptic("medium"); onView(v); },
    onError,
  });
  const spec = coach.specs.find((s) => s.code === open) ?? coach.specs[0];
  if (!spec) return null;
  const chosen = coach.specs.find((s) => s.code === coach.spec);
  const isMine = spec.code === coach.spec;
  const locked = !!coach.spec && !!coach.switch_at;
  const pick = () => (coach.spec ? setConfirm(true) : choose.mutate(spec.code));
  const span = spec.next_xp != null ? spec.next_xp - spec.level_xp : 0;
  const pct = span > 0 ? Math.min(100, Math.round(((spec.xp - spec.level_xp) / span) * 100)) : 100;
  const [first, podium, rest] = coach.xp_season;
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div>
        <p className="font-display text-base font-bold text-ink-chalk">Специализация тренера</p>
        <p className="text-micro leading-snug text-ink-mist">
          {chosen
            ? `${chosen.icon} ${chosen.label} · уровень ${chosen.level} из ${coach.max_level}`
            : "Выбери одну — работает только она. Прогресс каждой сохраняется, сменить можно раз в "
              + `${coach.switch_days} дней.`}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-1.5" role="tablist" aria-label="Специализации">
        {coach.specs.map((s) => (
          <button key={s.code} type="button" role="tab" aria-selected={s.code === spec.code} onClick={() => setOpen(s.code)}
            className={`relative flex items-center gap-2 rounded-2xl px-2.5 py-2 text-left ring-1 ${
              s.code === spec.code ? "bg-bg-raised ring-floodlight/60" : "bg-bg-raised/60 ring-transparent"}`}>
            <SpecArt code={s.code} icon={s.icon} className={`h-10 w-10 rounded-xl ${s.code === coach.spec || s.level ? "" : "opacity-60"}`} />
            <span className="min-w-0">
              <span className="block text-caption font-semibold text-ink-chalk">{s.label}</span>
              <span className={`block text-micro ${s.code === coach.spec ? "text-accent-lime" : "text-ink-mist"}`}>
                {s.code === coach.spec ? `выбрана · ур. ${s.level}` : s.level ? `ур. ${s.level} · отложена` : "не изучена"}
              </span>
            </span>
          </button>
        ))}
      </div>
      <div className="flex flex-col gap-2 rounded-2xl bg-bg-base/50 p-3">
        <div className="flex items-center gap-3">
          <SpecArt code={spec.code} icon={spec.icon} className="h-16 w-16 rounded-2xl" />
          <p className="text-caption leading-snug text-ink-chalk">{spec.about}</p>
        </div>
        {isMine && (
          <div className="flex flex-col gap-1">
            <span className="relative block h-2 overflow-hidden rounded-full bg-white/10"
              aria-label={spec.next_xp != null ? `Опыт ${spec.xp} из ${spec.next_xp}` : "Максимальный уровень"}>
              <span className="block h-full rounded-full bg-floodlight" style={{ width: `${pct}%` }} />
            </span>
            <p className="text-micro text-ink-mist">
              {spec.next_xp != null
                ? `Опыт ${spec.xp} · до уровня ${spec.level + 1} — ещё ${spec.next_xp - spec.xp}`
                : `Опыт ${spec.xp} · максимальный уровень`}
            </p>
          </div>
        )}
        <ol className="flex flex-col gap-0.5">
          {spec.levels.map((text, i) => {
            const n = i + 1;
            const reached = n <= spec.level;
            const current = isMine && n === spec.level;
            return (
              <li key={n} className={`flex items-baseline gap-2 rounded-lg px-1.5 py-0.5 text-micro ${
                current ? "bg-floodlight/15 text-ink-chalk" : reached ? "text-ink-chalk" : "text-ink-mist-dim"}`}>
                <span className={`w-5 shrink-0 font-mono font-bold ${reached ? "text-accent-lime" : ""}`}>{n}</span>
                <span className="leading-snug">{text}</span>
              </li>
            );
          })}
        </ol>
        {!isMine && (
          <button type="button" onClick={pick} disabled={locked || choose.isPending}
            className="rounded-xl bg-floodlight px-3 py-2 text-caption font-bold text-bg-base disabled:opacity-40">
            {locked && coach.switch_at
              ? `Сменить можно с ${new Date(coach.switch_at).toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}`
              : coach.spec ? `Сменить на «${spec.label}»` : `Выбрать «${spec.label}»`}
          </button>
        )}
      </div>
      <p className="text-micro leading-snug text-ink-mist-dim">
        Опыт за матч лиги: победа +{coach.xp_win}, ничья +{coach.xp_draw}, поражение +{coach.xp_loss}; за сезон:
        1-е место +{first}, 2–3-е +{podium}, остальные +{rest}. Мотиватор, Психолог и Оратор работают в сезонах с
        моралью, Аналитик — с дуэлями на флангах.
      </p>
      <ConfirmDialog
        open={confirm}
        title={`Сменить специализацию на «${spec.label}»?`}
        description={`Работать будет только она, опыт пойдёт в неё. Прогресс «${chosen?.label ?? ""}» сохранится, `
          + `но вернуться можно будет не раньше чем через ${coach.switch_days} дней.`}
        confirmLabel="Сменить"
        onConfirm={() => { setConfirm(false); choose.mutate(spec.code); }}
        onCancel={() => setConfirm(false)}
      />
    </section>
  );
}
