/** Training session pieces. The art is picked up from assets/training/<code>.webp;
 * without a file its icon stands in. */
const ART = import.meta.glob("/src/assets/training/*.webp", { eager: true, query: "?url", import: "default" }) as Record<string, string>;

const ICON: Record<string, string> = {
  recovery: "🧘", tactical: "📋", opponent: "🔍", set_pieces: "🚩", fitness: "🏃", attack: "🎯", defence: "🛡", team_building: "🤝",
};

function TrainingArt({ code, size }: { code: string; size: string }) {
  const art = ART[`/src/assets/training/${code}.webp`];
  return art
    ? <img src={art} alt="" className={`${size} shrink-0 rounded-xl object-cover`} />
    : <span className={`${size} flex shrink-0 items-center justify-center rounded-xl bg-bg-base/60 text-xl`} aria-hidden="true">{ICON[code] ?? "•"}</span>;
}

/** One of the plan's two places: what is in it, tap to change. */
export function TrainingSlot({ title, code, label, empty, open, disabled, onClick }: {
  title: string; code: string | null; label?: string; empty: string; open: boolean; disabled: boolean; onClick: () => void;
}) {
  return (
    <button type="button" aria-expanded={open} disabled={disabled} onClick={onClick}
      className={`flex min-w-0 flex-col gap-2 rounded-2xl p-2.5 text-left transition active:scale-[0.98] disabled:opacity-40 ${open ? "bg-accent-lime/10 ring-2 ring-accent-lime/70" : "bg-bg-raised ring-1 ring-white/5"}`}>
      <span className="text-micro font-semibold text-ink-mist">{title}</span>
      {code
        ? <TrainingArt code={code} size="h-16 w-16 self-center" />
        : <span className="flex h-16 w-16 items-center justify-center self-center rounded-xl border border-dashed border-white/20 text-2xl text-ink-mist" aria-hidden="true">+</span>}
      <span className={`truncate text-center text-caption font-semibold ${code ? "text-ink-chalk" : "text-ink-mist"}`}>{label ?? empty}</span>
    </button>
  );
}

/** A choice in the picker: the session, and in a line what it is for. */
export function TrainingRow({ code, label, hint, on, disabled, onClick }: {
  code: string; label: string; hint: string; on: boolean; disabled: boolean; onClick: () => void;
}) {
  return (
    <button type="button" role="radio" aria-checked={on} disabled={disabled} onClick={onClick}
      className={`flex w-full items-center gap-2.5 rounded-2xl p-1.5 text-left transition active:scale-[0.98] ${on ? "bg-accent-lime/10 ring-1 ring-accent-lime/70" : "bg-bg-raised"}`}>
      <TrainingArt code={code} size="h-11 w-11" />
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-bold text-ink-chalk">{label}</span>
        <span className="block text-micro leading-snug text-ink-mist">{hint}</span>
      </span>
      {on && <span className="shrink-0 pr-1.5 text-accent-lime" aria-hidden="true">✓</span>}
    </button>
  );
}
