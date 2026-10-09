import { SkillTokenIcon } from "@/components/icons/skills";
import { skillByCode, useSkillCatalog } from "@/lib/cardSkills";

/** A pack slot that rolled card-skill tokens instead of a card (pack recap
 * grids and gift results). */
export default function SkillTokenTile({ skillCode, quantity }: { skillCode: string; quantity: number }) {
  const { data: catalog } = useSkillCatalog();
  const skill = skillByCode(catalog?.skills, skillCode);
  return (
    <div className="relative overflow-hidden rounded-2xl bg-gradient-to-b from-accent-lime/60 to-accent-cyan/40 p-[2px]">
      <div className="flex aspect-[3/4] flex-col items-center justify-center gap-1.5 rounded-[14px] bg-bg-surface p-2 text-center">
        <SkillTokenIcon code={skillCode} size={48} className="text-accent-lime" aria-hidden />
        <p className="font-display text-sm font-bold text-ink-chalk">× {quantity}</p>
        <p className="truncate text-[10px] text-ink-mist">Жетон «{skill?.name ?? skillCode}»</p>
      </div>
    </div>
  );
}
