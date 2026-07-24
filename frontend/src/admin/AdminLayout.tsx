import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

const SECTIONS = [
  { to: "/admin", label: "Дашборд", icon: "📊", end: true },
  { to: "/admin/users", label: "Пользователи", icon: "👥" },
  { to: "/admin/players", label: "Футболисты", icon: "⚽" },
  { to: "/admin/packs", label: "Паки", icon: "📦" },
  { to: "/admin/card-collections", label: "Коллекции", icon: "🗃️" },
  { to: "/admin/tasks", label: "Задания", icon: "🎯" },
  { to: "/admin/trades", label: "Обмены", icon: "🔄" },
  { to: "/admin/games", label: "Игры", icon: "🎮" },
  { to: "/admin/log", label: "Журнал", icon: "📜" },
];

export default function AdminLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen bg-bg-base text-slate-100">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-white/5 bg-bg-surface p-4 md:flex">
        <p className="mb-6 font-display text-lg font-bold">🛠 Админка</p>
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
              <span>{s.icon}</span> {s.label}
            </NavLink>
          ))}
        </nav>
        <button onClick={() => navigate("/")} className="mt-auto rounded-xl bg-white/5 px-3 py-2 text-sm text-slate-300">
          ← Вернуться в приложение
        </button>
      </aside>

      <div className="flex-1">
        <header className="safe-top flex items-center justify-between border-b border-white/5 bg-bg-surface px-4 py-3 md:hidden">
          <p className="font-display text-base font-bold">🛠 Админка</p>
          <button onClick={() => setMenuOpen((v) => !v)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm">☰</button>
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
                <span>{s.icon}</span> {s.label}
              </NavLink>
            ))}
            <button onClick={() => navigate("/")} className="rounded-xl bg-white/5 px-3 py-2 text-left text-sm text-slate-300">
              ← Вернуться в приложение
            </button>
          </nav>
        )}
        <main className="p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
