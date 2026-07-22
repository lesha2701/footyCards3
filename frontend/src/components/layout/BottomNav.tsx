import { NavLink } from "react-router-dom";

const TABS = [
  { to: "/", label: "Главная", icon: "🏠" },
  { to: "/packs", label: "Паки", icon: "📦" },
  { to: "/play", label: "Играть", icon: "🎮" },
  { to: "/collection", label: "Карточки", icon: "🗂️" },
  { to: "/trades", label: "Обмены", icon: "🔄" },
  { to: "/profile", label: "Профиль", icon: "👤" },
];

export default function BottomNav() {
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-white/5 bg-bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-lg items-stretch justify-between px-1">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.to === "/"}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium transition-colors ${
                isActive ? "text-accent" : "text-slate-500"
              }`
            }
          >
            <span className="text-xl leading-none">{tab.icon}</span>
            <span>{tab.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
