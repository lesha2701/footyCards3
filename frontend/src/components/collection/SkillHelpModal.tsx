import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

import { SkillIcon, SkillTokenIcon } from "@/components/icons/skills";
import { useSkillCatalog } from "@/lib/cardSkills";

/** "How skills work" sheet — same shape as the app's HelpModal, with every
 * number (bonuses, costs) taken from the live server catalog. */
export default function SkillHelpModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: catalog } = useSkillCatalog();
  const costs = catalog?.rules.costs;
  const levels = catalog?.skills[0]?.levels ?? [];

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[70] flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="safe-bottom max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-t-3xl border border-white/10 bg-bg-surface p-6 sm:rounded-3xl"
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <p className="font-display text-lg font-bold text-ink-chalk">Навыки карточек</p>
              <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm text-ink-mist">Закрыть</button>
            </div>

            <div className="flex flex-col gap-4 text-xs text-ink-mist">
              <section>
                <p className="font-display text-sm font-bold text-ink-chalk">Что это</p>
                <p className="mt-0.5">
                  Навык есть у конкретного экземпляра карточки (не у всех её копий) и усиливает одно действие в матче:
                  удар, пас, сейв и т.д. Рейтинг карточки не меняется. У карточки может быть только один навык.
                </p>
              </section>
              <section>
                <p className="font-display text-sm font-bold text-ink-chalk">Уровни</p>
                <p className="mt-0.5">
                  {levels.map((l) => `${l.level_label} — +${l.bonus_pp}%`).join(" · ")}. Бонус прибавляется к шансу
                  своего действия, например 40% → 44%.
                </p>
              </section>
              <section>
                <p className="flex items-center gap-1.5 font-display text-sm font-bold text-ink-chalk">
                  <SkillTokenIcon code="sniper" size={16} className="text-accent-lime" /> Жетоны
                </p>
                <p className="mt-0.5">
                  Каждый жетон — для своего навыка. Их дают задания, места в турнире игроков, паки и администрация.
                </p>
                {costs && (
                  <ul className="mt-1 list-disc pl-4">
                    <li>Назначить: {costs.assign.token_cost} жет.{costs.assign.coin_cost ? ` + ${costs.assign.coin_cost} монет` : ""}</li>
                    <li>Улучшить до II: {costs.upgrade_to_2.token_cost} жет. + {costs.upgrade_to_2.coin_cost} монет</li>
                    <li>Улучшить до III: {costs.upgrade_to_3.token_cost} жет. + {costs.upgrade_to_3.coin_cost} монет</li>
                    <li>Заменить: {costs.replace.token_cost} жет. нового навыка + {costs.replace.coin_cost} монет</li>
                  </ul>
                )}
              </section>
              <section>
                <p className="font-display text-sm font-bold text-ink-chalk">Что важно знать</p>
                <ul className="mt-0.5 list-disc pl-4">
                  <li>При замене старый навык пропадает, потраченные на него жетоны не возвращаются.</li>
                  <li>При продаже, апгрейде редкости или скармливании карточки её навык теряется.</li>
                  <li>При обмене навык переходит вместе с карточкой.</li>
                  <li>Навык работает только на подходящей позиции и только в отмеченных режимах.</li>
                </ul>
              </section>
              {catalog && (
                <section>
                  <p className="font-display text-sm font-bold text-ink-chalk">Все навыки</p>
                  <div className="mt-1.5 flex flex-col gap-2">
                    {catalog.skills.filter((s) => s.is_available).map((s) => (
                      <div key={s.code} className="flex gap-2">
                        <SkillIcon code={s.code} size={18} className="mt-0.5 shrink-0 text-accent-lime" />
                        <div>
                          <p className="font-semibold text-ink-chalk">{s.name} <span className="font-normal text-ink-mist-dim">· {s.positions.join(", ")}</span></p>
                          <p>+{s.levels[0]?.bonus_pp}…{s.levels[s.levels.length - 1]?.bonus_pp}% {s.bonus_phrase}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
