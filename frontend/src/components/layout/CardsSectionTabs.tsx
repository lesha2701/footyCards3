import { Link, useLocation } from "react-router-dom";

const SECTIONS = [
  { to: "/collection", label: "Альбом", match: (p: string, tab: string | null) => p === "/collection" && tab !== "mine" },
  { to: "/collection?tab=mine", label: "Мои", match: (p: string, tab: string | null) => p === "/collection" && tab === "mine" },
  { to: "/trades", label: "Обмены", match: (p: string) => p.startsWith("/trades") },
  { to: "/upgrade", label: "Апгрейд", match: (p: string) => p.startsWith("/upgrade") },
];

/** One "Карточки" section in the bottom nav, four screens inside it:
 * album, my cards, trades and the upgrade forge. */
export default function CardsSectionTabs() {
  const { pathname, search } = useLocation();
  const tab = new URLSearchParams(search).get("tab");
  return (
    <nav className="grid grid-cols-4 gap-1 rounded-2xl bg-bg-surface p-1" aria-label="Разделы карточек">
      {SECTIONS.map((s) => {
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
