import { NavLink, useLocation } from "react-router-dom";

import {
  IconCollection,
  IconHome,
  IconPlay,
  IconProfile,
  IconShop,
  type IconProps,
} from "@/components/icons";
import { useNavBadges } from "@/lib/navBadges";
import { useMatchGuardStore } from "@/store/matchGuardStore";

const TABS: { to: string; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { to: "/", label: "Главная", Icon: IconHome },
  { to: "/packs", label: "Магазин", Icon: IconShop },
  { to: "/play", label: "Играть", Icon: IconPlay },
  // Обмены and Апгрейд live inside "Карточки" (CardsSectionTabs).
  { to: "/collection", label: "Карточки", Icon: IconCollection },
  { to: "/profile", label: "Профиль", Icon: IconProfile },
];

const BADGE_LABELS: Record<string, string> = {
  "/": "Можно забрать",
  "/play": "Вызовы и матчи с друзьями",
  "/collection": "Входящие обмены",
  "/profile": "Новые награды лиги",
};

export default function BottomNav() {
  const guardActive = useMatchGuardStore((s) => s.active);
  const requestNavigate = useMatchGuardStore((s) => s.requestNavigate);
  const { pathname } = useLocation();
  const badges = useNavBadges();
  const cardsSection = pathname.startsWith("/trades") || pathname.startsWith("/upgrade");

  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-white/5 bg-bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-lg items-stretch justify-between px-1">
        {TABS.map(({ to, label, Icon }) => {
          const badge = badges[to] ?? 0;
          return (
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
                      {badge > 0 && (
                        <span
                          aria-label={`${BADGE_LABELS[to]}: ${badge}`}
                          className="absolute -right-2 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-lime px-1 font-mono text-[9px] font-bold text-bg-base"
                        >
                          {badge > 9 ? "9+" : badge}
                        </span>
                      )}
                    </span>
                    <span>{label}</span>
                  </>
                );
              }}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
