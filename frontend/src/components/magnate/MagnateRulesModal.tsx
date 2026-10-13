import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

import type { MagnateInfo } from "@/types";

interface Props {
  open: boolean;
  onClose: () => void;
  info?: MagnateInfo;
}

/** Every number comes from /magnate/info (GameConfig), so admin edits show
 *  up here without a deploy. */
export default function MagnateRulesModal({ open, onClose, info }: Props) {
  const q = (v: number | undefined) => (v === undefined ? "—" : v.toLocaleString("ru-RU"));
  const rewards = info?.place_rewards ?? [];
  const sections: { title: string; body: string }[] = [
    {
      title: "Цель",
      body: `Стань самым богатым владельцем клубов. Партия идёт ${q(info?.max_rounds)} кругов (каждый ходит по разу за круг) или ${q(info?.time_limit_minutes)} минут — побеждает тот, у кого больше капитал: деньги + цена клубов и стадионов + вложенное в постройки. Если все остальные обанкротились — побеждаешь сразу.`,
    },
    {
      title: "Ход",
      body: `Бросаешь два кубика и идёшь по кругу из 32 клеток. Дубль — бросаешь ещё раз, третий дубль подряд — дисквалификация. Каждый проход «Стартового свистка» — +${q(info?.pass_start_bonus)} М. У всех на старте ${q(info?.start_money)} М — это валюта партии, не монеты.`,
    },
    {
      title: "Клубы и стадионы",
      body: "Встал на свободный клуб или стадион — можешь купить. Чужой — платишь аренду владельцу. Клубы одной страны — группа: собрал всю группу — аренда двойная и можно строить «Трибуны» (до трёх) и «Арену». Строить можно до броска или в конце хода, по одной постройке за нажатие, в любом порядке. Чем больше у владельца стадионов, тем дороже аренда каждого.",
    },
    {
      title: "Особые клетки",
      body: `«VAR» и «Трансферное окно» — карточки событий: деньги, перемещения, карточка апелляции. «Штраф федерации» — ${q(info?.fine_amount)} М, «Налог на зарплаты» — сумма указана на клетке. «Красная карточка» отправляет в «Дисквалификацию»: выйти можно дублем, штрафом ${q(info?.jail_fine)} М или карточкой апелляции; после трёх неудачных бросков штраф платится сам.`,
    },
    {
      title: "Банкротство",
      body: "Не хватает денег на платёж — постройки продаются банку за полцены. Если и этого мало, игрок выбывает: всё оставшееся уходит тому, кому он был должен, а клубы возвращаются в банк. В этой версии нет аукционов, залогов и обмена между игроками.",
    },
    {
      title: "Время",
      body: `На решение — ${q(info?.turn_seconds)} секунд, иначе ход сыграет автопилот. После ${q(info?.max_missed_turns)} пропущенных ходов подряд твоё место займёт бот, и награды за партию не будет. В онлайн-лобби свободные места через ${q(info?.lobby_wait_seconds)} с займут боты. Комната друзей ждёт ${q(info?.room_wait_minutes)} мин.`,
    },
    {
      title: "Награды",
      body: `Монеты по месту: ${rewards.map((r, i) => `${i + 1}-е — ${r}`).join(", ") || "—"}. За столом с ботами без других людей — ${q(info?.bot_reward_pct)}% от этого. Наградных партий в день: ${q(info?.daily_limit)} (сегодня ${q(info?.rewarded_today)}). Ушедший из партии награду не получает.`,
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
            className="safe-bottom max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-t-3xl border border-white/10 bg-bg-surface p-6 sm:rounded-3xl"
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <p className="font-display text-lg font-bold text-ink-chalk">Правила «Магната»</p>
              <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm text-ink-mist">
                Закрыть
              </button>
            </div>
            <div className="flex flex-col gap-4">
              {sections.map((s, i) => (
                <div key={s.title} className="flex gap-3">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-floodlight font-mono text-[10px] font-bold text-bg-base">
                    {i + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="font-display text-sm font-bold text-ink-chalk">{s.title}</p>
                    <p className="mt-1 text-xs leading-relaxed text-ink-mist">{s.body}</p>
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
