import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

interface Props {
  open: boolean;
  onClose: () => void;
}

const SECTIONS = [
  {
    icon: "🎴",
    title: "Состав",
    text: "Выбери ровно 11 карточек из своей коллекции — свободно, без позиций и формации. Состав начинается пустым, собери его сам на вкладке «Состав» перед первым матчем.",
  },
  {
    icon: "⚔️🛡",
    title: "Фаза раунда",
    text: "Матч состоит из 11 раундов — по одному на каждую карту состава. Перед каждым раундом сервер случайно объявляет фазу — атакующую или оборонительную — и обе стороны видят её заранее.",
  },
  {
    icon: "🎯",
    title: "Выбор карты",
    text: "Зная фазу, выбери одну карту из ещё не сыгранных. В атакующей фазе сравнивается АТК, в оборонительной — ЗЩТ. Карта нападающего (LW/ST/RW) получает +20% к АТК в атакующей фазе, карта защитника или вратаря — +20% к ЗЩТ в оборонительной. У полузащитников бонуса нет ни в одной из фаз — их сила в сбалансированных характеристиках.",
  },
  {
    icon: "🏆",
    title: "Победа в раунде",
    text: "Итоговый показатель карты в раунде = общий рейтинг + подходящий под фазу показатель (с бонусом за позицию, если он есть). Побеждает тот, у кого этот итог выше — то есть сильная карта высокого рейтинга может выиграть даже без бонуса за позицию. Если значения совпали — раунд считается ничьей, очко не получает никто.",
  },
  {
    icon: "📊",
    title: "Итог матча",
    text: "Побеждает тот, кто выиграл больше раундов из 11. Возможна ничья.",
  },
  {
    icon: "🤖",
    title: "Против бота",
    text: "Матч играется вживую, раунд за раундом, в одну сессию. Сложность влияет на силу состава бота и на то, насколько разумно он выбирает карты. За победу, ничью и поражение начисляются монеты и меняется рейтинг Тактико.",
  },
  {
    icon: "🧑‍🤝‍🧑",
    title: "Против друга",
    text: "Вызови друга через поиск — он должен принять вызов. Дальше каждый выбирает карту для раунда в своё время: выбор соперника скрыт, пока не походят оба. Монеты за такие матчи не начисляются — только рейтинг, чтобы нельзя было договориться и накручивать монеты.",
  },
  {
    icon: "⏳",
    title: "Если соперник не отвечает",
    text: "Если друг долго не делает ход, сервер автоматически сыграет за него случайную карту из оставшихся, чтобы матч не завис навсегда.",
  },
  {
    icon: "🚪",
    title: "Выход из матча",
    text: "Пока матч не завершён, начинать новый нельзя. Если выйти из активного матча — он засчитывается как поражение, даже если ты вёл в счёте. Специально сдаваться при проигрыше, чтобы избежать поражения, бессмысленно.",
  },
];

export default function TacticoRulesModal({ open, onClose }: Props) {
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
              <p className="font-display text-lg font-bold text-ink-chalk">Правила Тактико</p>
              <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm text-ink-mist">
                Закрыть
              </button>
            </div>
            <div className="flex flex-col gap-4">
              {SECTIONS.map((s) => (
                <div key={s.title} className="flex gap-3">
                  <span className="text-2xl leading-none">{s.icon}</span>
                  <div>
                    <p className="font-display text-sm font-bold text-ink-chalk">{s.title}</p>
                    <p className="mt-0.5 text-xs text-ink-mist">{s.text}</p>
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
