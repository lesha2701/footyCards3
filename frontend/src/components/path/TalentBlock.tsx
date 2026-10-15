import type { PathTalent } from "@/types";

/** «Талант» block: what it does, its two levels (which one is open, where the
 * next one unlocks) and in which modes it works — «не действует» is said
 * out loud for every mode the engine does not model. */
export default function TalentBlock({ talent, compact = false }: { talent: PathTalent; compact?: boolean }) {
  const next = talent.levels.find((l) => !l.unlocked);
  return (
    <section className="path-ui rounded-2xl border border-emerald-400/25 bg-emerald-400/5 p-3" aria-label="Талант">
      <div className="flex items-start gap-2.5">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-400/15 text-xl" aria-hidden>
          {talent.emoji}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-300/80">Талант</p>
          <p className="font-display text-sm font-bold text-ink-chalk">
            {talent.name}
            {talent.level_label && <span className="ml-1.5 text-emerald-300">{talent.level_label}</span>}
          </p>
          <p className="mt-0.5 text-xs text-ink-mist">{talent.summary}</p>
        </div>
      </div>
      {!talent.enabled && (
        <p className="mt-2 rounded-lg bg-black/20 px-2 py-1 text-[11px] text-amber-300">Талант сейчас выключен администратором</p>
      )}
      <ul className="mt-2.5 space-y-1.5">
        {talent.levels.map((lvl) => (
          <li
            key={lvl.level}
            className={`flex gap-2 rounded-lg px-2 py-1.5 text-xs ${lvl.unlocked ? "bg-emerald-400/10 text-ink-chalk" : "bg-black/20 text-ink-mist"}`}
          >
            <span className={`font-mono font-bold ${lvl.unlocked ? "text-emerald-300" : "text-ink-mist-dim"}`}>{lvl.label}</span>
            <span className="flex-1">
              {lvl.text}
              {!lvl.unlocked && lvl.unlock_stage && (
                <span className="block text-[10px] text-ink-mist-dim">Откроется на этапе «{lvl.unlock_stage}»</span>
              )}
            </span>
            <span aria-hidden>{lvl.unlocked ? "✓" : "🔒"}</span>
          </li>
        ))}
      </ul>
      {!compact && (
        <>
          <p className="mt-3 text-[10px] font-semibold uppercase tracking-wider text-ink-mist-dim">Где действует</p>
          <ul className="mt-1 space-y-1">
            {talent.modes.map((m) => (
              <li key={m.mode} className="flex gap-2 text-xs">
                <span className={`w-28 shrink-0 font-semibold ${m.text ? "text-ink-chalk" : "text-ink-mist-dim"}`}>{m.label}</span>
                <span className={m.text ? "text-ink-mist" : "text-ink-mist-dim"}>{m.text ?? "не действует"}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[10px] text-ink-mist-dim">
            Талант не меняет рейтинг на карточке — он срабатывает в матче, фиксируется на его старте и отмечается в журнале,
            только когда реально сработал.
          </p>
        </>
      )}
      {compact && next && next.unlock_stage && (
        <p className="mt-1.5 text-[10px] text-ink-mist-dim">Следующий уровень — на этапе «{next.unlock_stage}»</p>
      )}
    </section>
  );
}
