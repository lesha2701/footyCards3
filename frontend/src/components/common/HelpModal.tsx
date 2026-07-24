import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

interface Props {
  open: boolean;
  onClose: () => void;
}

const SECTIONS = [
  {
    icon: "📦",
    title: "Паки",
    text: "Покупай паки за монеты — внутри случайные карточки футболистов разной редкости. Чем дороже пак, тем выше шанс на редкие карты.",
  },
  {
    icon: "🗂️",
    title: "Карточки",
    text: "Твоя коллекция. Можно фильтровать по редкости и тематическим коллекциям (например «Чемпионат мира»), продавать ненужные дубликаты за монеты.",
  },
  {
    icon: "🎮",
    title: "Играть",
    text: "5 мини-игр для заработка монет: Memory Sequence, Card Arena, Футбольный сапёр, Пенальти, Штрафной удар. Каждую можно играть до 3 раз в час.",
  },
  {
    icon: "🎯",
    title: "Задания",
    text: "5 активных заданий из большого пула — выполнил одно, на его место встаёт случайное новое. Есть отдельные премиум-задания за подписку на каналы.",
  },
  {
    icon: "🔄",
    title: "Обмены",
    text: "Предлагай свои карточки другим игрокам в обмен на их карточки.",
  },
  {
    icon: "🎁",
    title: "Бесплатный пак",
    text: "Раз в несколько часов на главной появляется бесплатный пак — не забывай забирать.",
  },
  {
    icon: "👥",
    title: "Пригласи друзей",
    text: "Делись реферальной ссылкой из профиля — за приглашённых друзей начисляются награды в заданиях.",
  },
];

export default function HelpModal({ open, onClose }: Props) {
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
              <p className="font-display text-lg font-bold text-slate-100">Как играть в FootyCards</p>
              <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm text-slate-300">
                Закрыть
              </button>
            </div>
            <div className="flex flex-col gap-4">
              {SECTIONS.map((s) => (
                <div key={s.title} className="flex gap-3">
                  <span className="text-2xl leading-none">{s.icon}</span>
                  <div>
                    <p className="font-display text-sm font-bold text-slate-100">{s.title}</p>
                    <p className="mt-0.5 text-xs text-slate-400">{s.text}</p>
                  </div>
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
