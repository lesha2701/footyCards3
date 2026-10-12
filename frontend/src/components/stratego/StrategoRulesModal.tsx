import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

import type { StrategoInfo, StrategoRole } from "@/types";

import RoleIcon from "./RoleIcon";
import { ROLE_META } from "./strategoMeta";

interface Props {
  open: boolean;
  onClose: () => void;
  info?: StrategoInfo;
}

const RARITY_ADJ: Record<string, string> = {
  common: "обычной", rare: "редкой", epic: "эпической", legendary: "легендарной", diamond: "диамантовой",
};

const ROLE_ORDER: StrategoRole[] = ["cup", "wall", "star", "provocateur", "tackler", "speedster", "regular"];

/** Every number below comes from /stratego/info (GameConfig), so admin edits
 *  show up here without a deploy. */
export default function StrategoRulesModal({ open, onClose, info }: Props) {
  const n = info?.board_size ?? 8;
  const q = (v: number | undefined) => (v === undefined ? "—" : v);
  const cardPieces = info ? 2 + info.tackler_count + info.speedster_count + info.regular_count : undefined;
  const allPieces = info && cardPieces !== undefined ? cardPieces + 1 + info.wall_count : undefined;
  const roleCount: Partial<Record<StrategoRole, number | undefined>> = {
    cup: 1, wall: info?.wall_count, star: 1, provocateur: 1,
    tackler: info?.tackler_count, speedster: info?.speedster_count, regular: info?.regular_count,
  };

  const sections: { title: string; body: React.ReactNode }[] = [
    {
      title: "Цель",
      body: "Захвати Кубок соперника — или оставь его без единого возможного хода.",
    },
    {
      title: "Поле",
      body: (
        <>
          Поле {n}×{n}. Твои фишки стоят в двух ближних к тебе рядах, соперника — в двух дальних.
          {n >= 8 && " В центре две лужи: на них нельзя встать и через них нельзя пробежать — свободны проходы по краям и посередине."}
        </>
      ),
    },
    {
      title: `Состав — ${q(allPieces)} фишек`,
      body: (
        <div className="flex flex-col gap-1.5">
          {ROLE_ORDER.map((role) => (
            <div key={role} className="flex items-start gap-2">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-bg-raised text-accent-lime">
                <RoleIcon role={role} size={14} />
              </span>
              <span>
                <b className="text-ink-chalk">{ROLE_META[role].label}</b>
                <span className="text-ink-mist-dim"> ×{q(roleCount[role])}</span> — {ROLE_META[role].hint}.
              </span>
            </div>
          ))}
          <p className="mt-1">
            На роли игроков ставятся {q(cardPieces)} твоих карточек (или «Мой игрок»), их сила — рейтинг карточки.
            Подкатчик — защитник или опорник (LB, CB, RB, CDM), Скорость — фланговый (LW, RW, LM, RM), Провокатор —
            полузащитник (CM, CAM, CDM, LM, RM); Звезда — самая сильная карточка состава. В составе не больше{" "}
            {q(info?.max_legendary)} легендарных и {q(info?.max_diamond)} диамантовой, не меньше {q(info?.min_rare)} редких и{" "}
            {q(info?.min_common)} обычных карточек. Подкатчиком может быть карточка не выше{" "}
            {info ? RARITY_ADJ[info.tackler_max_rarity] : "—"} — иначе стенки слишком легко сносить.
          </p>
        </div>
      ),
    },
    {
      title: "Расстановка",
      body: "Готовится заранее на экране «Подготовка»: выбери карточки на роли и расставь фишки — или нажми «Авто». Матч стартует сразу с этой расстановкой. Соперник её не видит: его фишки для тебя — «?», пока не встретятся в бою.",
    },
    {
      title: "Ход",
      body: "Ходите по очереди. За ход одна фишка сдвигается на соседнюю клетку по вертикали или горизонтали (Скорость — на любое число свободных клеток по прямой). Кубок и Стенки не ходят. Нельзя вставать на свою фишку, в лужу и перепрыгивать через фишки. Правило повтора: одна фишка не может ходить туда-обратно между теми же двумя клетками больше 3 раз подряд.",
    },
    {
      title: "Бой",
      body: `Встал на клетку с фишкой соперника — бой, обе фишки раскрываются. Навык карточки добавляет силы: атакующие навыки (Снайпер, Дриблёр, Диспетчер…) — когда фишка атакует, защитные (Перехватчик, Последний рубеж, Реакция…) — когда её атакуют, +${q(info?.skill_bonus_per_level)} за уровень навыка. Побеждает больший рейтинг, при равном — более редкая карточка, при полном равенстве выбывают обе. Победитель атаки занимает клетку. Исключения: Стенка выбивает любого атакующего, кроме Подкатчика; Провокатор, атакуя Звезду, выбивает её; захват Кубка сразу заканчивает матч.`,
    },
    {
      title: "Конец матча",
      body: `Победа — захват Кубка или соперник без ходов. Если за ${q(info?.move_limit)} ходов (обоих игроков вместе) победителя нет, сравнивается сумма рейтингов оставшихся подвижных фишек; равенство — ничья. Сдача — поражение.`,
    },
    {
      title: "Игра с соперником",
      body: `Онлайн-поиск — живой матч: ${q(info?.live_move_seconds)} секунд на ход. С другом и по ссылке матч идёт в своём темпе: на ход ${q(info?.move_timeout_hours)} ч. Не успел — за тебя сходит автопилот; после ${q(info?.max_auto_moves)} автоходов подряд засчитывается поражение. Вызов другу или ссылкой в чат живёт ${q(info?.challenge_expiry_hours)} ч. В вызове через чат можно поставить монеты: обе стороны вносят ставку при принятии, победитель забирает обе, ничья их возвращает.`,
    },
    {
      title: "Боты, задачи, обучение, пометки",
      body: `Лёгкий бот иногда ошибается и платит ${q(info?.easy_reward_pct)}% награды (рейтинг — максимум +1), Сильный охотится за Звездой и бережёт Кубок. «Задача дня» — захвати Кубок за пару ходов, +${q(info?.puzzle_reward)} монет раз в день. «Обучение» — маленькое поле с подсказками, карточки не нужны. Нажми на фишку соперника, чтобы пометить её («Стенка?», «Кубок?») — пометки видишь только ты.`,
    },
    {
      title: "Награды и рейтинг",
      body: `Победа — ${q(info?.reward_win)}, ничья — ${q(info?.reward_draw)}, поражение — ${q(info?.reward_loss)} монет, до ${q(info?.daily_limit)} наградных матчей в день (сегодня ${q(info?.rewarded_today)}). Сдавшийся или проигравший по времени награду не получает. Рейтинг Стратего: победа +3, ничья +1, поражение −1; онлайн-поиск ×2, матч с другом рейтинг не меняет. «Мой игрок» в составе получает +${q(info?.my_player_xp)} опыта за матч.`,
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
              <p className="font-display text-lg font-bold text-ink-chalk">Правила Стратего</p>
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
                    <div className="mt-1 text-xs leading-relaxed text-ink-mist">{s.body}</div>
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
