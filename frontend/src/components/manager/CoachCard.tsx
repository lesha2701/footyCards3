import type { ManagerCoach } from "@/api/manager";
import { staffArt } from "@/lib/staffArt";

/** «Главный тренер» with a character: who he is, how his team plays, what
 * he asks for, and who sets the tactics — him or the president. */
export default function CoachCard({ coach, busy, onAuto, onAsk, compact = false }: {
  coach: ManagerCoach;
  busy?: boolean;
  /** Give the tactics to the coach (true) or take them back (false). */
  onAuto?: (auto: boolean) => void;
  /** Open what he asks for (transfers / the sporting director). */
  onAsk?: () => void;
  compact?: boolean;
}) {
  const art = staffArt(`coach_${coach.trait}`);
  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-gradient-to-br from-emerald-500/15 via-bg-surface to-bg-surface p-3 ring-1 ring-emerald-300/30" data-testid="coach-card">
      <div className="flex items-center gap-3">
        <span className="relative h-14 w-14 shrink-0 overflow-hidden rounded-2xl bg-bg-raised ring-2 ring-emerald-300/50">
          {art ? <img src={art} alt="" className="h-full w-full object-cover" /> : <span className="flex h-full w-full items-center justify-center text-3xl">{coach.emoji}</span>}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-micro font-bold uppercase tracking-[0.16em] text-emerald-200">🧢 Главный тренер · {coach.nation}</span>
          <span className="block truncate font-display text-base font-bold text-ink-chalk">{coach.name}</span>
          <span className="block text-micro text-ink-mist">«{coach.title}» · {coach.formation} · {coach.style}</span>
        </span>
      </div>
      {!compact && <p className="text-caption italic leading-snug text-ink-chalk/90">“{coach.quote}”</p>}
      <p className="text-micro leading-snug text-ink-mist">{coach.about}</p>
      {coach.ask && onAsk && (
        <button onClick={onAsk} className="flex items-center gap-2 rounded-xl bg-bg-base/50 px-2.5 py-2 text-left text-xs text-ink-chalk active:scale-[0.98]" data-testid="coach-ask">
          <span className="text-micro font-bold uppercase text-emerald-200">Просит:</span>
          <span className="min-w-0 flex-1">{coach.ask.text}</span>
          <span className="text-ink-mist">›</span>
        </button>
      )}
      {onAuto && (
        <div className="grid grid-cols-2 gap-1 rounded-xl bg-bg-base/40 p-1" data-testid="coach-auto">
          <button disabled={busy} onClick={() => !coach.auto && onAuto(true)}
            className={`rounded-lg py-1.5 text-micro font-bold ${coach.auto ? "bg-emerald-300 text-bg-base" : "text-ink-mist"}`}>
            Ставит тренер
          </button>
          <button disabled={busy} onClick={() => coach.auto && onAuto(false)}
            className={`rounded-lg py-1.5 text-micro font-bold ${!coach.auto ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}>
            Ставлю сам
          </button>
        </div>
      )}
      {onAuto && (
        <p className="text-[10px] leading-snug text-ink-mist">
          {coach.auto
            ? "Тренер сам выбирает схему и стиль на каждый матч, «Установку на матч» и замены. Твои настройки ниже — запасной план."
            : "Схему и стиль ставишь ты, тренер делает только замены. Алиса может взять «Установку на матч»."}
        </p>
      )}
    </section>
  );
}
