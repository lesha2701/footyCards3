import { SkillIcon } from "@/components/icons/skills";
import type { MatchEvent, MatchSkillNote } from "@/types";

/** One-line roll-up of the skill notes in a finished match log, so a player
 * sees at a glance that their skills did something (the per-event notes are
 * small and easy to miss in the feed). Renders nothing when no skill took
 * part in any event. */
export default function MatchSkillSummary({ events }: { events: MatchEvent[] }) {
  const notes = events.flatMap((e) => (e.payload?.skills as MatchSkillNote[] | undefined) ?? []);
  if (!notes.length) return null;
  const decisive = notes.filter((n) => n.decisive);
  const byName = new Map<string, { code: string; label: string; count: number }>();
  for (const n of decisive) {
    const key = `${n.code}:${n.level_label}`;
    const entry = byName.get(key) ?? { code: n.code, label: `${n.name} ${n.level_label}`, count: 0 };
    entry.count += 1;
    byName.set(key, entry);
  }
  return (
    <div className="mt-2 rounded-xl bg-accent-lime/10 px-3 py-2 text-[11px] text-accent-lime">
      <p className="font-semibold">
        Навыки в матче: учтены {notes.length} раз{decisive.length ? `, решили исход ${decisive.length}` : ""}
      </p>
      {byName.size > 0 && (
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-accent-lime/80">
          {[...byName.values()].map((e) => (
            <span key={e.label} className="inline-flex items-center gap-1">
              <SkillIcon code={e.code} size={11} aria-hidden />
              {e.label}{e.count > 1 ? ` ×${e.count}` : ""}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}
