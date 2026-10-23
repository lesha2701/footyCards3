import { useIsNew, markSeen } from "@/lib/seenSections";

/** A short «how it works» card shown on a section's first visit only, with
 * «Понятно» to hide it for good. */
export default function FirstVisitHint({ id, title, lines }: { id: string; title: string; lines: string[] }) {
  const key = `hint:${id}`;
  const show = useIsNew(key);
  if (!show) return null;
  return (
    <section className="rounded-2xl border border-accent-cyan/25 bg-accent-cyan/5 p-3" aria-label={title}>
      <p className="text-sm font-bold text-ink-chalk">💡 {title}</p>
      <ul className="mt-1.5 flex flex-col gap-1 text-xs text-ink-mist">
        {lines.map((l) => <li key={l}>• {l}</li>)}
      </ul>
      <button
        type="button"
        onClick={() => markSeen(key)}
        className="mt-2 rounded-lg bg-accent-cyan/15 px-3 py-1.5 text-xs font-semibold text-accent-cyan"
      >
        Понятно
      </button>
    </section>
  );
}
