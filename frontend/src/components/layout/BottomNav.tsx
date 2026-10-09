import { NavLink, useLocation } from "react-router-dom";

import {
  IconCollection,
  IconHome,
  IconPack,
  IconPlay,
  IconProfile,
  type IconProps,
} from "@/components/icons";
import { useTodayState } from "@/lib/today";
import { useMatchGuardStore } from "@/store/matchGuardStore";

const TABS: { to: string; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { to: "/", label: "Главная", Icon: IconHome },
  { to: "/packs", label: "Паки", Icon: IconPack },
  { to: "/play", label: "Играть", Icon: IconPlay },
  // Обмены and Апгрейд live inside "Карточки" (CardsSectionTabs).
  { to: "/collection", label: "Карточки", Icon: IconCollection },
  { to: "/profile", label: "Профиль", Icon: IconProfile },
];

export default function BottomNav() {
  const guardActive = useMatchGuardStore((s) => s.active);
  const requestNavigate = useMatchGuardStore((s) => s.requestNavigate);
  const { pathname } = useLocation();
  const { claimableCount } = useTodayState();
  const cardsSection = pathname.startsWith("/trades") || pathname.startsWith("/upgrade");

  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-white/5 bg-bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-lg items-stretch justify-between px-1">
        {TABS.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={(e) => {
              if (guardActive) {
                e.preventDefault();
                requestNavigate(to);
              }
            }}
            className={({ isActive: routeActive }) =>
              `flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-semibold transition-colors ${
                routeActive || (to === "/collection" && cardsSection) ? "text-ink-chalk" : "text-ink-mist-dim"
              }`
            }
          >
            {({ isActive: routeActive }) => {
              const isActive = routeActive || (to === "/collection" && cardsSection);
              return (
              <>
                <span className="relative">
                  <Icon size={20} className={isActive ? "text-accent-lime" : ""} />
                  {to === "/" && claimableCount > 0 && (
                    <span
                      aria-label={`Можно забрать: ${claimableCount}`}
                      className="absolute -right-2 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-lime px-1 font-mono text-[9px] font-bold text-bg-base"
                    >
                      {claimableCount}
                    </span>
                  )}
                </span>
                <span>{label}</span>
              </>
              );
            }}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
