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
import { hapticSelection } from "@/lib/telegram";
import { useKeyboardOpen } from "@/lib/useKeyboardOpen";
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
  "/play": "Вызовы, матчи с друзьями и приглашения в карьеру",
  "/collection": "Входящие обмены",
  "/profile": "Заявки в друзья и награды лиги",
};

export default function BottomNav() {
  const guardActive = useMatchGuardStore((s) => s.active);
  const requestNavigate = useMatchGuardStore((s) => s.requestNavigate);
  const { pathname } = useLocation();
  const badges = useNavBadges();
  const cardsSection = pathname.startsWith("/trades") || pathname.startsWith("/upgrade");
  // Out of the way while typing: otherwise it rides up on the keyboard.
  const keyboardOpen = useKeyboardOpen();
  if (keyboardOpen) return null;

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
                  return;
                }
                if (to !== pathname) hapticSelection();
              }}
              className={({ isActive: routeActive }) =>
                `flex flex-1 flex-col items-center gap-1 py-2.5 text-caption font-semibold transition-colors ${
                  routeActive || (to === "/collection" && cardsSection) ? "text-ink-chalk" : "text-ink-mist-dim"
                }`
              }
            >
              {({ isActive: routeActive }) => {
                const isActive = routeActive || (to === "/collection" && cardsSection);
                // «Играть» is the main action: a raised floodlight circle.
                const play = to === "/play";
                return (
                  <>
                    <span
                      className={
                        play
                          ? `relative -mt-6 flex h-14 w-14 items-center justify-center rounded-full border-4 border-bg-base bg-floodlight text-bg-base shadow-lg shadow-accent-lime/20 transition-transform ${
                              isActive ? "scale-105" : ""
                            }`
                          : "relative"
                      }
                    >
                      <Icon size={play ? 24 : 20} className={!play && isActive ? "text-accent-lime" : ""} />
                      {badge > 0 && (
                        <span
                          aria-label={`${BADGE_LABELS[to]}: ${badge}`}
                          className={`absolute flex ${play ? "-right-1 -top-1" : "-right-2 -top-1"} h-4 min-w-4 items-center justify-center rounded-full bg-accent-lime px-1 font-mono text-micro font-bold text-bg-base ${play ? "ring-2 ring-bg-base" : ""}`}
                        >
                          {badge > 9 ? "9+" : badge}
                        </span>
                      )}
                    </span>
                    <span className={play ? "-mt-0.5 text-ink-chalk" : ""}>{label}</span>
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
