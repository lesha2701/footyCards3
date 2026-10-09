import { useQuery } from "@tanstack/react-query";

import { fetchSkillTokens } from "@/api/cardSkills";
import { SkillTokenIcon } from "@/components/icons/skills";
import { skillByCode, useSkillCatalog } from "@/lib/cardSkills";

/** Owned skill tokens, one chip per skill with a non-zero balance. Hidden
 * entirely while the player has none, so it adds no noise before the
 * feature is used. */
export default function SkillTokensStrip() {
  const { data: catalog } = useSkillCatalog();
  const { data: tokens } = useQuery({ queryKey: ["card-skills", "tokens"], queryFn: fetchSkillTokens });
  const owned = (tokens ?? []).filter((t) => t.quantity > 0);
  if (!owned.length) return null;
  return (
    <div className="rounded-2xl bg-bg-surface p-3">
      <p className="text-[11px] text-ink-mist">
        Жетоны навыков — открой карточку и выбери «Навык», чтобы назначить или улучшить
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {owned.map((t) => {
          const skill = skillByCode(catalog?.skills, t.skill_code);
          return (
            <span key={t.skill_code} className="inline-flex items-center gap-1 rounded-full bg-black/30 px-2 py-1 text-[11px] font-semibold text-ink-chalk">
              <SkillTokenIcon code={t.skill_code} size={15} className="text-accent-lime" aria-hidden />
              {skill?.name ?? t.skill_code} × <span className="font-mono text-accent-lime">{t.quantity}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
