import { useNavigate } from "react-router-dom";

import { IconBrain, IconChevronLeft, IconChevronRight, IconGoal, IconShirt } from "@/components/icons";

const GAMES = [
  {
    to: "/clubs/game",
    icon: IconBrain,
    title: "Повтори порядок",
    description: "Запомни, в каком порядке загораются иконки, и повтори последовательность",
  },
  {
    to: "/clubs/penalty",
    icon: IconGoal,
    title: "Пенальти",
    description: "Серия пенальти против бота — выбери игрока из состава клуба",
  },
  {
    to: "/clubs/position-match",
    icon: IconShirt,
    title: "Своя позиция",
    description: "Сопоставь футболистов с их позициями на поле",
  },
];

export default function ClubGamesPage() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Клубные игры</h1>
      </div>

      <p className="text-xs text-ink-mist">
        На все три игры вместе — 2 попытки в час на участника, можно тратить на любую комбинацию (например, дважды
        сыграть в пенальти). Награда пополняет бюджет клуба.
      </p>

      <div className="flex flex-col gap-3">
        {GAMES.map((game) => (
          <button
            key={game.to}
            onClick={() => navigate(game.to)}
            className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.99]"
          >
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-accent-lime/15 text-accent-lime">
              <game.icon size={22} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-display text-sm font-bold text-ink-chalk">{game.title}</p>
              <p className="mt-0.5 text-xs leading-snug text-ink-mist">{game.description}</p>
            </div>
            <IconChevronRight size={18} className="shrink-0 text-ink-mist-dim" />
          </button>
        ))}
      </div>
    </div>
  );
}
