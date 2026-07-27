import { NavLink } from "react-router-dom";

import {
  IconCollection,
  IconHome,
  IconPack,
  IconPlay,
  IconProfile,
  IconSwap,
  type IconProps,
} from "@/components/icons";

const TABS: { to: string; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { to: "/", label: "Главная", Icon: IconHome },
  { to: "/packs", label: "Паки", Icon: IconPack },
  { to: "/play", label: "Играть", Icon: IconPlay },
  { to: "/collection", label: "Карточки", Icon: IconCollection },
  { to: "/trades", label: "Обмены", Icon: IconSwap },
  { to: "/profile", label: "Профиль", Icon: IconProfile },
];

export default function BottomNav() {
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-white/5 bg-bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-lg items-stretch justify-between px-1">
        {TABS.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-semibold transition-colors ${
                isActive ? "text-ink-chalk" : "text-ink-mist-dim"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={20} className={isActive ? "text-accent-lime" : ""} />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
