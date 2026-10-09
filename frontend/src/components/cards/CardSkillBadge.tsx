import { SKILL_LEVEL_LABELS, skillByCode, useSkillCatalog } from "@/lib/cardSkills";

/** Small "icon + I/II/III" chip for a card copy's skill. Sits in a card's
 * existing badge slot (bottom-left of the image), so it never covers the
 * face, name, rating or rarity. Renders nothing for a card without a skill. */
export default function CardSkillBadge({
  code,
  level,
  extraCount = 0,
  className = "",
}: {
  code?: string | null;
  level?: number | null;
  /** Other skilled copies of the same player (collection tiles). */
  extraCount?: number;
  className?: string;
}) {
  const { data: catalog } = useSkillCatalog();
  if (!code || !level) return null;
  const skill = skillByCode(catalog?.skills, code);
  return (
    <span
      title={skill ? `${skill.name} ${SKILL_LEVEL_LABELS[level]}` : undefined}
      className={`inline-flex items-center gap-0.5 rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-[9px] font-bold leading-none text-accent-lime ${className}`}
    >
      <span aria-hidden>{skill?.icon ?? "✨"}</span>
      {SKILL_LEVEL_LABELS[level]}
      {extraCount > 0 && <span className="text-ink-mist">+{extraCount}</span>}
    </span>
  );
}
