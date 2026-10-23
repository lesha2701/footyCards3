import { useQuery } from "@tanstack/react-query";

import { fetchSkillTokens } from "@/api/cardSkills";
import { SkillTokenIcon } from "@/components/icons/skills";
import { skillByCode, useSkillCatalog } from "@/lib/cardSkills";

/** Owned skill tokens in one scrollable line (open a card → «Навык» to use
 * them). Hidden entirely while the player has none. */
export default function SkillTokensStrip() {
  const { data: catalog } = useSkillCatalog();
  const { data: tokens } = useQuery({ queryKey: ["card-skills", "tokens"], queryFn: fetchSkillTokens });
  const owned = (tokens ?? []).filter((t) => t.quantity > 0);
  if (!owned.length) return null;
  return (
    <div
      className="flex items-center gap-1.5 overflow-x-auto pb-0.5"
      title="Жетоны навыков — открой карточку и выбери «Навык», чтобы назначить или улучшить"
    >
      <span className="shrink-0 text-micro font-semibold uppercase tracking-wider text-ink-mist-dim">Жетоны</span>
      {owned.map((t) => {
        const skill = skillByCode(catalog?.skills, t.skill_code);
        return (
          <span
            key={t.skill_code}
            className="inline-flex shrink-0 items-center gap-1 rounded-full bg-bg-surface px-2 py-1 text-caption font-semibold text-ink-chalk"
            aria-label={`${skill?.name ?? t.skill_code}: ${t.quantity}`}
          >
            <SkillTokenIcon code={t.skill_code} size={14} className="text-accent-lime" aria-hidden />
            {skill?.name ?? t.skill_code} <span className="font-mono text-accent-lime">×{t.quantity}</span>
          </span>
        );
      })}
    </div>
  );
}
