import { SkillIcon } from "@/components/icons/skills";
import type { MatchEvent, MatchSkillNote, MatchTalentNote } from "@/types";

/** Skill lines under one match-log event. The server only attaches a note
 * when a skill actually took part in that event's roll; "decisive" is set
 * only when the same random draw would have gone the other way without the
 * skill — otherwise the line just says the skill was counted, without
 * claiming it caused the outcome. */
export default function MatchSkillNotes({ event }: { event: MatchEvent }) {
  const notes = (event.payload?.skills as MatchSkillNote[] | undefined) ?? [];
  // «Академия»: a talent line appears only when the talent really changed
  // this event's roll (the server attaches nothing otherwise).
  const talents = (event.payload?.talents as MatchTalentNote[] | undefined) ?? [];
  if (!notes.length && !talents.length) return null;
  return (
    <>
      {talents.map((t, i) => (
        <span key={`t${i}`} className="mt-0.5 block pl-6 text-[10px]"><span className="text-path/90">
          <span className="mr-1" aria-hidden>{t.emoji}</span>
          Талант «{t.name}» {t.level_label}
          {t.player ? ` (${t.player})` : ""}: +{t.bonus} к рейтингу
        </span></span>
      ))}
      {notes.map((note, i) => (
        <span key={i} className="mt-0.5 block pl-6 text-[10px] text-accent-lime/80">
          <SkillIcon code={note.code} size={11} className="mr-1 inline-block align-[-1px]" aria-hidden />
          {note.name} {note.level_label}
          {note.player ? ` (${note.player})` : ""}
          {note.decisive ? " — решил исход эпизода" : ` учтён: ${note.bonus_pp} п.п.`}
        </span>
      ))}
    </>
  );
}
