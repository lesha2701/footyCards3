import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { fetchFeatureFlags } from "@/api/featureFlags";
import { usePageSwipe } from "@/lib/useSwipe";

const SECTIONS = [
  { to: "/collection", label: "Альбом", match: (p: string, tab: string | null) => p === "/collection" && tab !== "mine" },
  { to: "/collection?tab=mine", label: "Мои", match: (p: string, tab: string | null) => p === "/collection" && tab === "mine" },
  { to: "/trades", label: "Обмены", match: (p: string) => p.startsWith("/trades") },
  { to: "/market", label: "Рынок", match: (p: string) => p.startsWith("/market"), market: true },
  { to: "/upgrade", label: "Апгрейд", match: (p: string) => p.startsWith("/upgrade") },
];

/** One "Карточки" section in the bottom nav, several screens inside it:
 * album, my cards, trades, the transfer market (only while an admin has it
 * open — or while you're already on it, to reach your own lots) and the
 * upgrade forge. A sideways swipe anywhere on these screens moves to the
 * neighbouring one. */
export default function CardsSectionTabs() {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const tab = new URLSearchParams(search).get("tab");
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, staleTime: 30_000 });
  const showMarket = !!flags?.auction_enabled || pathname.startsWith("/market");
  const sections = SECTIONS.filter((s) => !s.market || showMarket);
  const activeIndex = sections.findIndex((s) => s.match(pathname, tab));
  const go = (i: number) => () => navigate(sections[i].to, { replace: true });
  usePageSwipe(
    activeIndex >= 0 && activeIndex < sections.length - 1 ? go(activeIndex + 1) : null,
    activeIndex > 0 ? go(activeIndex - 1) : null,
  );
  return (
    <nav
      className={`grid gap-1 rounded-2xl bg-bg-surface p-1 ${sections.length === 5 ? "grid-cols-5" : "grid-cols-4"}`}
      aria-label="Разделы карточек"
    >
      {sections.map((s) => {
        const active = s.match(pathname, tab);
        return (
          <Link
            key={s.to}
            to={s.to}
            replace
            aria-current={active ? "page" : undefined}
            className={`rounded-xl py-2 text-center text-xs font-semibold transition ${
              active ? "bg-floodlight text-bg-base" : "text-ink-mist"
            }`}
          >
            {s.label}
          </Link>
        );
      })}
    </nav>
  );
}
