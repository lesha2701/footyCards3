import { Suspense, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import AdminToastContainer from "@/admin/AdminToastContainer";
import {
  IconBall,
  IconBrain,
  IconCard,
  IconChart,
  IconChat,
  IconClock,
  IconCoin,
  IconCollection,
  IconFlag,
  IconFlagCheckered,
  IconGift,
  IconGlobe,
  IconMenu,
  IconPack,
  IconPlay,
  IconScroll,
  IconShirt,
  IconStadium,
  IconStar,
  IconSwap,
  IconTag,
  IconTarget,
  IconTrophy,
  IconUpgrade,
  IconUsers,
  type IconProps,
} from "@/components/icons";

const SECTIONS: { to: string; label: string; Icon: (props: IconProps) => JSX.Element; end?: boolean }[] = [
  { to: "/admin", label: "Дашборд", Icon: IconChart, end: true },
  { to: "/admin/economy", label: "Экономика", Icon: IconCoin },
  { to: "/admin/users", label: "Пользователи", Icon: IconUsers },
  { to: "/admin/players", label: "Футболисты", Icon: IconBall },
  { to: "/admin/coaches", label: "Тренеры", Icon: IconShirt },
  { to: "/admin/stadiums", label: "Стадионы", Icon: IconStadium },
  { to: "/admin/packs", label: "Паки", Icon: IconPack },
  { to: "/admin/club-packs", label: "Клубные паки", Icon: IconPack },
  { to: "/admin/clubs", label: "Клубы", Icon: IconFlag },
  { to: "/admin/tournaments", label: "Турниры", Icon: IconTrophy },
  { to: "/admin/card-collections", label: "Коллекции", Icon: IconCollection },
  { to: "/admin/tasks", label: "Задания", Icon: IconTarget },
  { to: "/admin/trades", label: "Обмены", Icon: IconSwap },
  { to: "/admin/trophies", label: "Трофеи", Icon: IconStar },
  { to: "/admin/leagues", label: "Лиги", Icon: IconFlagCheckered },
  { to: "/admin/gifts", label: "Подарки", Icon: IconGift },
  { to: "/admin/wheel", label: "Колесо фортуны", Icon: IconGlobe },
  { to: "/admin/daily-rewards", label: "Ежедневные награды", Icon: IconClock },
  { to: "/admin/games", label: "Игры", Icon: IconPlay },
  { to: "/admin/upgrades", label: "Апгрейд", Icon: IconUpgrade },
  { to: "/admin/diamond-upgrades", label: "Диамант", Icon: IconCard },
  { to: "/admin/card-skills", label: "Навыки карточек", Icon: IconBrain },
  { to: "/admin/bingo", label: "Бинго недели", Icon: IconTag },
  { to: "/admin/shop", label: "Магазин", Icon: IconCoin },
  { to: "/admin/broadcasts", label: "Рассылка", Icon: IconChat },
  { to: "/admin/log", label: "Журнал", Icon: IconScroll },
];

export default function AdminLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen w-full max-w-full overflow-x-hidden bg-bg-base text-slate-100">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-white/5 bg-bg-surface p-4 md:flex">
        <p className="mb-6 font-display text-lg font-bold">Админка</p>
        <nav className="flex flex-col gap-1">
          {SECTIONS.map((s) => (
            <NavLink
              key={s.to}
              to={s.to}
              end={s.end}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium ${isActive ? "bg-accent text-bg-base" : "text-slate-300 hover:bg-white/5"}`
              }
            >
              <s.Icon size={16} /> {s.label}
            </NavLink>
          ))}
        </nav>
        <button onClick={() => navigate("/")} className="mt-auto rounded-xl bg-white/5 px-3 py-2 text-sm text-slate-300">
          Вернуться в приложение
        </button>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="safe-top flex items-center justify-between border-b border-white/5 bg-bg-surface px-4 py-3 md:hidden">
          <p className="font-display text-base font-bold">Админка</p>
          <button onClick={() => setMenuOpen((v) => !v)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm" aria-label="Меню"><IconMenu size={16} /></button>
        </header>
        {menuOpen && (
          <nav className="flex flex-col gap-1 border-b border-white/5 bg-bg-surface p-3 md:hidden">
            {SECTIONS.map((s) => (
              <NavLink
                key={s.to}
                to={s.to}
                end={s.end}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium ${isActive ? "bg-accent text-bg-base" : "text-slate-300"}`
                }
              >
                <s.Icon size={16} /> {s.label}
              </NavLink>
            ))}
            <button onClick={() => navigate("/")} className="rounded-xl bg-white/5 px-3 py-2 text-left text-sm text-slate-300">
              Вернуться в приложение
            </button>
          </nav>
        )}
        <main className="min-w-0 max-w-full overflow-x-hidden p-4 md:p-6">
          <Suspense fallback={<p className="text-sm text-slate-400">Загрузка...</p>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <AdminToastContainer />
    </div>
  );
}
