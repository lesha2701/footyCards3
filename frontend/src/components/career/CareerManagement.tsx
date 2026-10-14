import { useMutation } from "@tanstack/react-query";

import { setCareerAmbition, setCareerTraining, type CareerProfile, type CareerSeason, type CareerView } from "@/api/career";
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
          <p className="text-[10px] uppercase tracking-wider text-ink-mist">Тренер · уровень {profile.rep_level}</p>
          <p className="font-display text-base font-bold text-ink-chalk">{profile.rep_name}</p>
        </div>
        <span className="rounded-xl bg-bg-base/60 px-2.5 py-1 text-center">
          <span className="block font-mono text-sm font-bold text-accent-lime">{profile.reputation}</span>
          <span className="block text-[9px] text-ink-mist">репутация</span>
        </span>
      </div>
      <span className="mt-2 block h-1.5 overflow-hidden rounded-full bg-white/10" aria-label="Прогресс до следующего уровня">
        <span className="block h-full bg-floodlight" style={{ width: `${progress}%` }} />
      </span>
      <p className="mt-1 text-[10px] text-ink-mist-dim">
        {profile.rep_next_at !== null ? `До следующего уровня: ${profile.rep_next_at - profile.reputation}` : "Высший уровень"} ·
        репутация растёт за титулы, повышения и выполненные задачи руководства
      </p>
      <div className="mt-3 grid grid-cols-4 gap-1.5">
        {stats.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-bg-base/50 py-1.5 text-center">
            <p className="font-mono text-sm font-bold text-ink-chalk">{value}</p>
            <p className="text-[9px] text-ink-mist">{label}</p>
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
          <p className="text-[10px] uppercase tracking-wider text-ink-mist">Задача руководства</p>
          <p className="text-sm font-semibold text-ink-chalk">{chosen.label}: {chosen.text}</p>
          <p className={`text-[11px] ${onTrack ? "text-accent-lime" : "text-red-300"}`}>
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
        <p className="text-[11px] text-ink-mist">Выбери амбицию до первого тура. Выше цель — больше бонус, но и провал стоит дороже.</p>
      </div>
      <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Амбиция на сезон">
        {options.map((o) => {
          const on = o.code === season.ambition;
          return (
            <button key={o.code} role="radio" aria-checked={on} disabled={choose.isPending} onClick={() => choose.mutate(o.code)}
              className={`flex flex-col gap-1 rounded-2xl p-2 text-left ${on ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"}`}
            >
              <span className="text-[11px] font-bold leading-tight">{o.label}</span>
              <span className={`text-[9px] leading-tight ${on ? "text-bg-base/80" : "text-ink-mist"}`}>{o.text}</span>
              <span className={`mt-auto font-mono text-[9px] ${on ? "text-bg-base" : "text-accent-lime"}`}>+{o.bonus_pct}% · реп +{o.rep_success}</span>
              <span className={`font-mono text-[9px] ${on ? "text-bg-base/80" : "text-red-300"}`}>провал {o.rep_fail}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

const TRAINING_ICON: Record<string, string> = { recovery: "🧘", tactical: "📋", opponent: "🔍", set_pieces: "🚩" };

/** Training focus before the next round (kept until changed). */
export function TrainingCard({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const save = useMutation({
    mutationFn: (code: string | null) => setCareerTraining(code, season.rounds_played),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  const options = season.trainings ?? [];
  if (!options.length) return null;
  const current = options.find((o) => o.code === season.training);
  return (
    <section className="flex flex-col gap-2 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="font-display text-base font-bold text-ink-chalk">Тренировка перед туром</p>
        {season.training && (
          <button onClick={() => save.mutate(null)} disabled={save.isPending} className="text-[11px] text-ink-mist underline underline-offset-2">
            без фокуса
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Тренировка">
        {options.map((o) => {
          const on = o.code === season.training;
          return (
            <button key={o.code} role="radio" aria-checked={on} disabled={save.isPending} onClick={() => save.mutate(o.code)}
              className={`flex items-center gap-2 rounded-2xl px-3 py-2.5 text-left ${on ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"}`}
            >
              <span className="text-base">{TRAINING_ICON[o.code] ?? "•"}</span>
              <span className="text-[11px] font-semibold leading-tight">{o.label}</span>
            </button>
          );
        })}
      </div>
      <p className="text-[11px] leading-snug text-ink-mist">{current ? current.hint : "Выбери фокус — он действует на каждый следующий тур, пока не сменишь."}</p>
    </section>
  );
}
