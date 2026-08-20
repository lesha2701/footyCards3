import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

interface Props {
  open: boolean;
  onClose: () => void;
}

const SECTIONS = [
  {
    title: "Что такое лига",
    text: "Лига — это твой общий уровень в игре. Она растёт вместе с суммарным рейтингом трёх режимов: Card Arena, Тактико и Пенальти. Чем выше сумма — тем выше лига.",
  },
  {
    title: "Как считается рейтинг",
    text: "Рейтинг = рейтинг Card Arena + рейтинг Тактико + рейтинг Пенальти. За победу обычно даётся +3, за поражение -1, за ничью +1 — но у некоторых режимов есть особые правила (ниже).",
  },
  {
    title: "Игры с другом не дают рейтинг",
    text: "В Тактико и Пенальти матчи с друзьями (по вызову) не меняют рейтинг вообще — только опыт игры. Иначе было бы слишком легко катать рейтинг между своими же аккаунтами.",
  },
  {
    title: "Онлайн-матчи дают рейтинг x2",
    text: "Подбор соперника (кнопка «Играть») в Тактико и Пенальти даёт вдвое больше рейтинга за любой исход — это самый быстрый способ расти в лигах.",
  },
  {
    title: "Лёгкий бот в Тактико",
    text: "Победа над ботом уровня «Лёгкий» в Тактико даёт только +1 рейтинга (вместо обычных +3) — эта сложность слишком лёгкая, чтобы давать полный рейтинг.",
  },
  {
    title: "Награды за лигу",
    text: "При переходе в новую лигу ты сразу получаешь награду — монеты, а иногда и пак. Проверить свою лигу и прогресс можно всегда на этом экране.",
  },
];

export default function LeagueRulesModal({ open, onClose }: Props) {
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="safe-bottom max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-t-3xl border border-white/10 bg-bg-surface p-6 sm:rounded-3xl"
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <p className="font-display text-lg font-bold text-ink-chalk">Правила лиг</p>
              <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm text-ink-mist">
                Закрыть
              </button>
            </div>
            <div className="flex flex-col gap-4">
              {SECTIONS.map((s) => (
                <div key={s.title}>
                  <p className="font-display text-sm font-bold text-ink-chalk">{s.title}</p>
                  <p className="mt-0.5 text-xs text-ink-mist">{s.text}</p>
                </div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
