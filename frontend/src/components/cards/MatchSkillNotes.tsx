import type { MatchEvent, MatchSkillNote } from "@/types";

/** Skill lines under one match-log event. The server only attaches a note
 * when a skill actually took part in that event's roll; "decisive" is set
 * only when the same random draw would have gone the other way without the
 * skill — otherwise the line just says the skill was counted, without
 * claiming it caused the outcome. */
export default function MatchSkillNotes({ event }: { event: MatchEvent }) {
  const notes = (event.payload?.skills as MatchSkillNote[] | undefined) ?? [];
  if (!notes.length) return null;
  return (
    <>
      {notes.map((note, i) => (
        <span key={i} className="mt-0.5 block pl-6 text-[10px] text-accent-lime/80">
          ✨ {note.name} {note.level_label}
          {note.player ? ` (${note.player})` : ""}
          {note.decisive ? " — решил исход эпизода" : ` учтён: ${note.bonus_pp} п.п.`}
        </span>
      ))}
    </>
  );
}
