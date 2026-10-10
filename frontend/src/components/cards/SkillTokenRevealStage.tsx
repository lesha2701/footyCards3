import { motion } from "framer-motion";

import { SkillTokenIcon } from "@/components/icons/skills";
import { skillByCode, useSkillCatalog } from "@/lib/cardSkills";
import { type TokenStage } from "@/components/cards/revealStages";
export type { TokenStage } from "@/components/cards/revealStages";

// Reveal for a pack slot that rolled card-skill tokens — same two-beat
// rhythm as the coach/stadium reveals (glow, then the reveal), sized to
// sit in the same full-screen pack-opening flow.

export function SkillTokenRevealStage({
  token,
  stage,
  index,
  total,
  onTap,
}: {
  token: { skill_code: string; quantity: number };
  stage: TokenStage;
  index: number;
  total: number;
  onTap: () => void;
}) {
  const { data: catalog } = useSkillCatalog();
  const skill = skillByCode(catalog?.skills, token.skill_code);
  const revealed = stage === "reveal";

  return (
    <div
      onClick={onTap}
      role="button"
      tabIndex={0}
      className="flex flex-1 cursor-pointer flex-col items-center justify-center gap-5 px-6 text-center"
    >
      {total > 1 && <p className="font-mono text-xs text-ink-mist-dim">Жетон {index + 1} / {total}</p>}

      <motion.div
        initial={{ scale: 0.7, opacity: 0, rotate: -12 }}
        animate={{ scale: revealed ? 1 : 0.9, opacity: 1, rotate: 0 }}
        transition={{ type: "spring", damping: 14, stiffness: 180 }}
        className="relative flex aspect-square w-56 items-center justify-center rounded-full bg-gradient-to-b from-accent-lime/25 to-accent-cyan/10 shadow-[0_0_60px_-10px] shadow-accent-lime/60"
      >
        <motion.div
          animate={revealed ? { scale: [1, 1.08, 1] } : { opacity: [0.4, 1, 0.4] }}
          transition={revealed ? { duration: 0.6 } : { repeat: Infinity, duration: 1.2 }}
          className="text-accent-lime"
        >
          <SkillTokenIcon code={token.skill_code} size={128} strokeWidth={1.4} aria-hidden />
        </motion.div>
      </motion.div>

      <div className="min-h-[70px] space-y-1">
        {revealed ? (
          <>
            <p className="font-display text-lg font-bold text-ink-chalk">Жетон «{skill?.name ?? token.skill_code}» × {token.quantity}</p>
            {skill && <p className="text-xs text-ink-mist">{skill.effect}</p>}
          </>
        ) : (
          <p className="font-display text-base font-semibold text-accent-lime">Жетон навыка!</p>
        )}
      </div>

      {!revealed && <p className="text-xs text-ink-mist-dim">Нажми, чтобы продолжить</p>}
    </div>
  );
}
