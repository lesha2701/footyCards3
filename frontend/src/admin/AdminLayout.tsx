import { useQuery } from "@tanstack/react-query";
import { Suspense, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import AdminToastContainer from "@/admin/AdminToastContainer";
import { useStackedTables } from "@/admin/useStackedTables";
import { fetchStarsReceiptProblemCount } from "@/admin/api";
import {
  IconBall,
  IconBan,
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

type Section = { group: string; to: string; label: string; Icon: (props: IconProps) => JSX.Element; end?: boolean };

const SECTIONS: Section[] = [
  { group: "Обзор", to: "/admin", label: "Дашборд", Icon: IconChart, end: true },
  { group: "Обзор", to: "/admin/economy", label: "Экономика", Icon: IconCoin },
  { group: "Обзор", to: "/admin/log", label: "Журнал и ошибки", Icon: IconScroll },
  { group: "Обзор", to: "/admin/analytics", label: "Аналитика", Icon: IconTarget },
  { group: "Игроки", to: "/admin/users", label: "Пользователи", Icon: IconUsers },
  { group: "Игроки", to: "/admin/antifraud", label: "Антифрод", Icon: IconBan },
  { group: "Карточки", to: "/admin/players", label: "Футболисты", Icon: IconBall },
  { group: "Карточки", to: "/admin/coaches", label: "Тренеры", Icon: IconShirt },
  { group: "Карточки", to: "/admin/stadiums", label: "Стадионы", Icon: IconStadium },
  { group: "Паки и магазин", to: "/admin/packs", label: "Паки", Icon: IconPack },
  { group: "Паки и магазин", to: "/admin/club-packs", label: "Клубные паки", Icon: IconPack },
  { group: "Клубы и мир", to: "/admin/clubs", label: "Клубы", Icon: IconFlag },
  { group: "Игры и события", to: "/admin/tournaments", label: "Турниры", Icon: IconTrophy },
  { group: "Карточки", to: "/admin/card-collections", label: "Коллекции", Icon: IconCollection },
  { group: "Игры и события", to: "/admin/tasks", label: "Задания", Icon: IconTarget },
  { group: "Игроки", to: "/admin/trades", label: "Обмены", Icon: IconSwap },
  { group: "Игры и события", to: "/admin/trophies", label: "Трофеи", Icon: IconStar },
  { group: "Игры и события", to: "/admin/leagues", label: "Лиги", Icon: IconFlagCheckered },
  { group: "Паки и магазин", to: "/admin/gifts", label: "Подарки", Icon: IconGift },
  { group: "Клубы и мир", to: "/admin/lifestyle", label: "Имущество", Icon: IconStar },
  { group: "Клубы и мир", to: "/admin/muses", label: "Музы", Icon: IconStar },
  { group: "Паки и магазин", to: "/admin/wheel", label: "Колесо фортуны", Icon: IconGlobe },
  { group: "Паки и магазин", to: "/admin/daily-rewards", label: "Календарь наград", Icon: IconClock },
  { group: "Игры и события", to: "/admin/games", label: "Игры", Icon: IconPlay },
  { group: "Игры и события", to: "/admin/match-day", label: "Матч дня", Icon: IconPlay },
  { group: "Карточки", to: "/admin/upgrades", label: "Апгрейд", Icon: IconUpgrade },
  { group: "Карточки", to: "/admin/diamond-upgrades", label: "Диамант", Icon: IconCard },
  { group: "Карточки", to: "/admin/card-skills", label: "Навыки карточек", Icon: IconBrain },
  { group: "Карточки", to: "/admin/path", label: "Академия", Icon: IconUpgrade },
  { group: "Клубы и мир", to: "/admin/club-base", label: "Клубная база", Icon: IconStadium },
  { group: "Игры и события", to: "/admin/bingo", label: "Бинго недели", Icon: IconTag },
  { group: "Паки и магазин", to: "/admin/shop", label: "Магазин", Icon: IconCoin },
  { group: "Паки и магазин", to: "/admin/monetization", label: "Абонемент, сезон, стиль", Icon: IconStar },
  { group: "Игроки", to: "/admin/broadcasts", label: "Рассылка", Icon: IconChat },
  { group: "Игроки", to: "/admin/transactions", label: "Транзакции", Icon: IconCoin },
];

const GROUPS = [...new Set(SECTIONS.map((s) => s.group))];

/** The section list, grouped, with a search box (35 sections are too many to scan). */
function AdminNav({ badge, onPick }: { badge: number; onPick?: () => void }) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const shown = q ? SECTIONS.filter((s) => s.label.toLowerCase().includes(q) || s.group.toLowerCase().includes(q)) : SECTIONS;
  return (
    <nav className="flex flex-col gap-1">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Найти раздел…"
        className="mb-2 w-full rounded-xl bg-bg-base px-3 py-2 text-sm outline-none placeholder:text-slate-600"
      />
      {GROUPS.map((group) => {
        const items = shown.filter((s) => s.group === group);
        if (!items.length) return null;
        return (
          <div key={group} className="mb-1 flex flex-col gap-0.5">
            <p className="px-3 pb-0.5 pt-2 text-micro font-semibold uppercase tracking-wider text-slate-600">{group}</p>
            {items.map((s) => (
              <NavLink
                key={s.to}
                to={s.to}
                end={s.end}
                onClick={onPick}
                className={({ isActive }) =>
                  `flex min-w-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium ${isActive ? "bg-accent text-bg-base" : "text-slate-300 hover:bg-white/5"}`
                }
              >
                <s.Icon size={16} /> <span className="truncate">{s.label}</span>
                {s.to === "/admin/shop" && <ProblemBadge count={badge} />}
              </NavLink>
            ))}
          </div>
        );
      })}
      {!shown.length && <p className="px-3 py-2 text-xs text-slate-500">Ничего не нашлось</p>}
    </nav>
  );
}

function ProblemBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="ml-auto rounded-full bg-red-500 px-1.5 text-micro font-bold text-white" title="Неначисленные платежи Stars">
      {count}
    </span>
  );
}

export default function AdminLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  useStackedTables(mainRef);
  const navigate = useNavigate();
  // Paid-but-undelivered Stars payments — shown on «Магазин» so they get noticed.
  const { data: paymentProblems = 0 } = useQuery({
    queryKey: ["admin-stars-receipt-problems"],
    queryFn: fetchStarsReceiptProblemCount,
    refetchInterval: 60_000,
  });

  return (
    <div className="admin-root flex min-h-screen w-full max-w-full overflow-x-hidden bg-bg-base text-slate-100">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col overflow-y-auto border-r border-white/5 bg-bg-surface p-4 md:flex">
        <p className="mb-6 font-display text-lg font-bold">Админка</p>
        <AdminNav badge={paymentProblems} />
        <button onClick={() => navigate("/")} className="mt-4 shrink-0 rounded-xl bg-white/5 px-3 py-2 text-sm text-slate-300">
          Вернуться в приложение
        </button>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="safe-top flex items-center justify-between border-b border-white/5 bg-bg-surface px-4 py-3 md:hidden">
          <p className="font-display text-base font-bold">Админка</p>
          <button onClick={() => setMenuOpen((v) => !v)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm" aria-label="Меню"><IconMenu size={16} /></button>
        </header>
        {menuOpen && (
          <div className="flex flex-col gap-1 border-b border-white/5 bg-bg-surface p-3 md:hidden">
            <AdminNav badge={paymentProblems} onPick={() => setMenuOpen(false)} />
            <button onClick={() => navigate("/")} className="rounded-xl bg-white/5 px-3 py-2 text-left text-sm text-slate-300">
              Вернуться в приложение
            </button>
          </div>
        )}
        <main ref={mainRef} className="min-w-0 max-w-full overflow-x-hidden p-4 md:p-6">
          <Suspense fallback={<p className="text-sm text-slate-400">Загрузка...</p>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <AdminToastContainer />
    </div>
  );
}
