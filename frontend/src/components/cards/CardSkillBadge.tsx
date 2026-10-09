import { SkillIcon } from "@/components/icons/skills";
import { SKILL_LEVEL_LABELS, skillByCode, useSkillCatalog } from "@/lib/cardSkills";

/** Small "icon + I/II/III" chip for a card copy's skill. Sits in a card's
 * existing badge slot (bottom-left of the image), so it never covers the
 * face, name, rating or rarity. Renders nothing for a card without a skill. */
export default function CardSkillBadge({
  code,
  level,
  extraCount = 0,
  className = "",
  upgradable = false,
  inactiveReason = null,
}: {
  code?: string | null;
  level?: number | null;
  /** Other skilled copies of the same player (collection tiles). */
  extraCount?: number;
  className?: string;
  /** Enough tokens and coins to upgrade right now — shows a small ▲. */
  upgradable?: boolean;
  /** Set when the skill does nothing in this context (e.g. Dribbler in a
   * Card Arena lineup) — the badge is dimmed and the reason is its tooltip. */
  inactiveReason?: string | null;
}) {
  const { data: catalog } = useSkillCatalog();
  if (!code || !level) return null;
  const skill = skillByCode(catalog?.skills, code);
  return (
    <span
      title={
        skill
          ? `${skill.name} ${SKILL_LEVEL_LABELS[level]}${inactiveReason ? ` — ${inactiveReason}` : upgradable ? " — можно улучшить" : ""}`
          : undefined
      }
      className={`inline-flex items-center gap-0.5 rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-[9px] font-bold leading-none ${
        inactiveReason ? "text-ink-mist-dim line-through" : "text-accent-lime"
      } ${className}`}
    >
      <SkillIcon code={code} size={10} strokeWidth={2.4} aria-hidden />
      {SKILL_LEVEL_LABELS[level]}
      {extraCount > 0 && <span className="text-ink-mist">+{extraCount}</span>}
      {upgradable && !inactiveReason && <span className="text-accent-cyan" aria-label="можно улучшить">▲</span>}
    </span>
  );
}
