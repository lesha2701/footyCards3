import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { setCareerAmbition, setCareerProgram, setCareerTraining, type CareerProfile, type CareerSeason, type CareerView } from "@/api/career";
import { TrainingRow, TrainingSlot } from "@/components/career/TrainingTile";
import { haptic } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

/** Coach reputation level, progress to the next one and career counters. */
export function CoachProfileCard({ profile }: { profile: CareerProfile }) {
  const span = profile.rep_next_at !== null ? profile.rep_next_at - profile.rep_floor : 0;
  const progress = span > 0 ? Math.min(100, ((profile.reputation - profile.rep_floor) / span) * 100) : 100;
  const stats: [string, number][] = [
    ["Сезонов", profile.seasons_played], ["Титулов", profile.titles], ["Повышений", profile.promotions], ["Задач", profile.objectives_met],
  ];
  return (
    <section className="rounded-3xl bg-gradient-to-br from-bg-surface to-bg-raised p-4 ring-1 ring-white/5">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-micro uppercase tracking-wider text-ink-mist">Тренер · уровень {profile.rep_level}</p>
          <p className="font-display text-base font-bold text-ink-chalk">{profile.rep_name}</p>
        </div>
        <span className="rounded-xl bg-bg-base/60 px-2.5 py-1 text-center">
          <span className="block font-mono text-sm font-bold text-accent-lime">{profile.reputation}</span>
          <span className="block text-micro text-ink-mist">репутация</span>
        </span>
      </div>
      <span className="mt-2 block h-1.5 overflow-hidden rounded-full bg-white/10" aria-label="Прогресс до следующего уровня">
        <span className="block h-full bg-floodlight" style={{ width: `${progress}%` }} />
      </span>
      <p className="mt-1 text-micro text-ink-mist-dim">
        {profile.rep_next_at !== null ? `До следующего уровня: ${profile.rep_next_at - profile.reputation}` : "Высший уровень"} ·
        репутация растёт за титулы, повышения и выполненные задачи руководства
      </p>
      <div className="mt-3 grid grid-cols-4 gap-1.5">
        {stats.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-bg-base/50 py-1.5 text-center">
            <p className="font-mono text-sm font-bold text-ink-chalk">{value}</p>
            <p className="text-micro text-ink-mist">{label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/** Board objective: picked before round 1, then tracked against the table. */
export function ObjectiveCard({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const choose = useMutation({
    mutationFn: (code: string) => setCareerAmbition(code),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  const options = season.ambitions ?? [];
  if (!options.length) return null;
  const chosen = options.find((o) => o.code === season.ambition);
  const place = season.table.findIndex((r) => r.team_index === season.my_team_index) + 1;
  const editable = season.rounds_played === 0;

  if (!editable && chosen) {
    const onTrack = place > 0 && place <= chosen.place;
    return (
      <section className="flex items-center gap-3 rounded-3xl bg-bg-surface p-4">
        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-lg ${onTrack ? "bg-accent-lime/15" : "bg-red-500/15"}`}>
          {onTrack ? "🎯" : "⚠️"}
        </span>
        <div className="min-w-0">
          <p className="text-micro uppercase tracking-wider text-ink-mist">Задача руководства</p>
          <p className="text-sm font-semibold text-ink-chalk">{chosen.label}: {chosen.text}</p>
          <p className={`text-caption ${onTrack ? "text-accent-lime" : "text-red-300"}`}>
            Сейчас {place}-е место — {onTrack ? "в графике" : "отстаём от цели"} · бонус +{chosen.bonus_pct}% к награде
          </p>
        </div>
      </section>
    );
  }
  return (
    <section className="flex flex-col gap-2 rounded-3xl bg-bg-surface p-4">
      <div>
        <p className="font-display text-base font-bold text-ink-chalk">Задача руководства</p>
        <p className="text-caption text-ink-mist">Выбери амбицию до первого тура. Выше цель — больше бонус, но и провал стоит дороже.</p>
      </div>
      <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Амбиция на сезон">
        {options.map((o) => {
          const on = o.code === season.ambition;
          return (
            <button key={o.code} role="radio" aria-checked={on} disabled={choose.isPending || !!season.hot_seat} onClick={() => choose.mutate(o.code)}
              className={`flex flex-col gap-1 rounded-2xl p-2 text-left ${on ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"}`}
            >
              <span className="text-caption font-bold leading-tight">{o.label}</span>
              <span className={`text-micro leading-tight ${on ? "text-bg-base/80" : "text-ink-mist"}`}>{o.text}</span>
              <span className={`mt-auto font-mono text-micro ${on ? "text-bg-base" : "text-accent-lime"}`}>+{o.bonus_pct}% · реп +{o.rep_success}</span>
              <span className={`font-mono text-micro ${on ? "text-bg-base/80" : "text-red-300"}`}>провал {o.rep_fail}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

const PLAY_SESSIONS = new Set(["attack", "defence", "set_pieces", "tactical", "opponent"]);
const INTENSITY_HINTS: Record<string, string> = {
  light: "Слабее эффект, меньше усталости",
  normal: "Без надбавок",
  hard: "Сильнее эффект, больше усталости и риск травм",
};

/** The plan before the next round (kept until changed): two places, one list
 * of sessions for the place being filled, then how hard to work and what it
 * all gives. The effects are worked out by the backend. */
export function TrainingCard({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const [picking, setPicking] = useState<"main" | "extra" | null>(null);
  const save = useMutation({
    mutationFn: (next: { main: string | null; extra: string | null; intensity: string }) =>
      setCareerTraining(next.main, season.rounds_played, { extra: next.extra, intensity: next.intensity }),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  const options = season.trainings ?? [];
  const plan = season.training_plan;
  if (!options.length || !plan) return null;
  const main = season.training ?? null;
  const extra = plan.extra;
  const put = (next: Partial<{ main: string | null; extra: string | null; intensity: string }>) =>
    save.mutate({ main, extra, intensity: plan.intensity, ...next });
  const label = (code: string | null) => options.find((o) => o.code === code)?.label;
  // With nothing planned there is only one thing to do, so the list is open.
  const shown = !main ? "main" : picking;
  const taken = shown === "main" ? main : extra;
  const other = shown === "main" ? extra : main;
  const pick = (code: string) => {
    setPicking(null);
    if (shown === "extra") put({ extra: code === extra ? null : code });
    else if (code === main) put({ main: null, extra: null });
    else put({ main: code, extra: code === extra ? null : extra });
  };
  const choices = options.filter((o) => shown === "main" || o.code !== other);
  const groups = [
    { title: "Усилить игру", rows: choices.filter((o) => PLAY_SESSIONS.has(o.code)) },
    { title: "Сберечь силы и настрой", rows: choices.filter((o) => !PLAY_SESSIONS.has(o.code)) },
  ];

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4" aria-label="План тренировок">
      <div>
        <p className="font-display text-base font-bold text-ink-chalk">План тренировок</p>
        <p className="text-caption text-ink-mist">Действует перед каждым туром, пока не поменяешь.</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <TrainingSlot title="Основное" code={main} label={label(main)} empty="Выбери занятие" open={shown === "main"}
          disabled={save.isPending} onClick={() => setPicking(shown === "main" ? null : "main")} />
        <TrainingSlot title={`Дополнительное · ${plan.second_pct}%`} code={extra} label={label(extra)} empty={main ? "Добавить" : "После основного"}
          open={shown === "extra"} disabled={save.isPending || !main} onClick={() => setPicking(shown === "extra" ? null : "extra")} />
      </div>

      {shown && (
        <div className="flex flex-col gap-2" role="radiogroup" aria-label={shown === "main" ? "Основное занятие" : "Дополнительное занятие"}>
          {groups.filter((g) => g.rows.length > 0).map((g) => (
            <div key={g.title} className="flex flex-col gap-1.5">
              <p className="text-micro font-semibold uppercase tracking-wide text-ink-mist">{g.title}</p>
              {g.rows.map((o) => (
                <TrainingRow key={o.code} code={o.code} label={o.label} hint={o.hint.split(". ")[0].replace(/\.$/, "")} on={o.code === taken}
                  disabled={save.isPending} onClick={() => pick(o.code)} />
              ))}
            </div>
          ))}
        </div>
      )}

      {main && !shown && (
        <>
          <div className="flex flex-col gap-1.5">
            <p className="text-caption font-semibold text-ink-chalk">Нагрузка</p>
            <div className="grid grid-cols-3 gap-1 rounded-2xl bg-bg-base/40 p-1" role="radiogroup" aria-label="Интенсивность">
              {plan.intensities.map((i) => (
                <button key={i.code} role="radio" aria-checked={i.code === plan.intensity} disabled={save.isPending} onClick={() => put({ intensity: i.code })}
                  className={`rounded-xl py-1.5 text-caption font-semibold ${i.code === plan.intensity ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}>
                  {i.label}
                </button>
              ))}
            </div>
            <p className="text-micro text-ink-mist">{INTENSITY_HINTS[plan.intensity]}</p>
          </div>

          <div className="rounded-2xl bg-bg-base/50 p-3">
            <p className="mb-1.5 text-micro font-semibold uppercase tracking-wide text-ink-mist">Что получишь к матчу</p>
            <ul className="flex flex-col gap-1">
              {plan.lines.map((line) => <li key={line} className="text-caption font-semibold text-ink-chalk">{line}</li>)}
            </ul>
          </div>
        </>
      )}
    </section>
  );
}

/** One squad player works individually for a few matches and comes out
 * stronger until the season's end. */
export function ProgramCard({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const [choosing, setChoosing] = useState(false);
  const save = useMutation({
    mutationFn: (cardId: number | null) => setCareerProgram(cardId, season.rounds_played),
    onSuccess: (v) => { haptic("light"); setChoosing(false); onView(v); },
    onError,
  });
  const program = season.training_program;
  if (!program) return null;
  const finished = new Set(program.done.map((d) => d.card_id));
  const left = program.limit - program.done.length;
  const candidates = season.squad
    .filter((e) => e.card && e.owned && !finished.has(e.card_id))
    .sort((a, b) => (b.card?.player.rating ?? 0) - (a.card?.player.rating ?? 0));
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4" aria-label="Индивидуальная программа">
      <div>
        <p className="font-display text-base font-bold text-ink-chalk">Индивидуальная программа</p>
        <p className="text-caption text-ink-mist">
          {program.rounds} матча на поле дают +{program.bonus} к рейтингу до конца сезона. Игрок устаёт на {program.fatigue} больше. Осталось программ: {left}.
        </p>
      </div>
      {program.active ? (
        <div className="flex flex-col gap-2 rounded-2xl bg-bg-base/50 p-3">
          <div className="flex items-baseline justify-between gap-2">
            <p className="min-w-0 truncate text-sm font-bold text-ink-chalk">{program.active.name}</p>
            <p className="shrink-0 font-mono text-caption font-bold text-accent-lime">{program.active.played} из {program.rounds}</p>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-label="Прогресс программы"
            aria-valuenow={program.active.played} aria-valuemin={0} aria-valuemax={program.rounds}>
            <div className="h-full rounded-full bg-accent-lime" style={{ width: `${(program.active.played / program.rounds) * 100}%` }} />
          </div>
          <p className="text-caption text-ink-mist">Засчитываются только матчи, где он вышел на поле.</p>
          <button type="button" disabled={save.isPending} onClick={() => save.mutate(null)} className="self-start text-caption text-ink-mist underline underline-offset-2">
            Отменить программу
          </button>
        </div>
      ) : left > 0 && !choosing ? (
        <button type="button" onClick={() => setChoosing(true)} className="rounded-2xl bg-bg-raised py-2.5 text-caption font-semibold text-ink-chalk active:scale-[0.98]">
          Выбрать игрока
        </button>
      ) : left > 0 ? (
        <div className="grid grid-cols-2 gap-1.5">
          {candidates.map((e) => (
            <button key={e.card_id} type="button" disabled={save.isPending} onClick={() => save.mutate(e.card_id)}
              className="flex items-center justify-between gap-2 rounded-xl bg-bg-raised px-2.5 py-2 text-left text-caption text-ink-chalk active:scale-[0.98]">
              <span className="min-w-0 truncate font-semibold">{e.card?.player.display_name}</span>
              <span className="shrink-0 font-mono text-micro text-ink-mist">{e.card?.player.position} {e.card?.player.rating}</span>
            </button>
          ))}
        </div>
      ) : null}
      {program.done.length > 0 && (
        <p className="text-caption text-accent-lime">Прошли программу: {program.done.map((d) => `${d.name} +${d.bonus}`).join(", ")}</p>
      )}
    </section>
  );
}
