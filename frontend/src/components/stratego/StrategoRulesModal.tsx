import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

import type { StrategoInfo } from "@/types";

import { ROLE_META } from "./strategoMeta";

interface Props {
  open: boolean;
  onClose: () => void;
  info?: StrategoInfo;
}

export default function StrategoRulesModal({ open, onClose, info }: Props) {
  const n = info?.board_size ?? 6;
  const sections = [
    {
      title: "Подготовка",
      text: `Поле ${n}×${n}${n >= 8 ? ", в центре две лужи 2×2 — через них не ходят и не перепрыгивают" : ""}. У каждого ${info ? 3 + info.wall_count + info.tackler_count + info.speedster_count + info.regular_count : "—"} фишек: Кубок, ${info?.wall_count ?? "—"} Стенки, Звезда, Провокатор, ${info?.tackler_count ?? "—"} Подкатчика, ${info?.speedster_count ?? "—"} Скорости и ${info?.regular_count ?? "—"} Игроков. Заранее, до вызова соперника, на экране «Подготовка» выбери карточки на роли и расставь фишки в два своих ближних ряда — или нажми «Авто». Соперник твою расстановку не видит, как и ты его.`,
    },
    {
      title: "Фишки",
      text: (Object.keys(ROLE_META) as (keyof typeof ROLE_META)[])
        .map((r) => `${ROLE_META[r].glyph} ${ROLE_META[r].label} — ${ROLE_META[r].hint}`)
        .join(". "),
    },
    {
      title: "Ход",
      text: "За ход одна фишка сдвигается на клетку по горизонтали или вертикали (Скорость — на любое расстояние по прямой). Встал на фишку соперника — бой: обе фишки раскрываются. Побеждает больший рейтинг карты, при равенстве — редкость, при полном равенстве уходят обе.",
    },
    {
      title: "Победа",
      text: `Захвати Кубок соперника или оставь его без ходов. Если за ${info?.move_limit ?? "—"} ходов (суммарно) никто не победил, считается сила оставшихся фишек.`,
    },
    {
      title: "С другом",
      text: `Ходы асинхронные: на ход ${info?.move_timeout_hours ?? "—"} ч. Не успел — за тебя походит автопилот; после ${info?.max_auto_moves ?? "—"} автоходов подряд засчитывается поражение.`,
    },
    {
      title: "Рейтинг и ставки",
      text: "Победа +3, ничья +1, поражение −1 к рейтингу Стратего. Онлайн-поиск даёт ×2, матчи с другом рейтинг не меняют. Вызов через чат можно сделать со ставкой: обе стороны вносят её при принятии, победитель забирает обе, ничья возвращает ставки.",
    },
    {
      title: "Награды",
      text: info
        ? `Победа ${info.reward_win}, ничья ${info.reward_draw}, поражение ${info.reward_loss} монет — до ${info.daily_limit} наградных матчей в день (сегодня: ${info.rewarded_today}). Сдача — без награды.`
        : "Монеты за победу, ничью и поражение в пределах дневного лимита.",
    },
  ];

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
              <p className="font-display text-lg font-bold text-ink-chalk">Правила Стратего</p>
              <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm text-ink-mist">
                Закрыть
              </button>
            </div>
            <div className="flex flex-col gap-4">
              {sections.map((s) => (
                <div key={s.title}>
                  <p className="font-display text-sm font-bold text-ink-chalk">{s.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-ink-mist">{s.text}</p>
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
