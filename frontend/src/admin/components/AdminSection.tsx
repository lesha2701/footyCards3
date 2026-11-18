import { createContext, useContext, useState, type ReactNode } from "react";

/** The admin «Игры» page: groups of collapsible sections (closed by default,
 * a chevron opens them downwards) and a search over the section titles. */

const STORAGE_KEY = "admin-games-open";
const SearchContext = createContext("");

function readOpen(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function writeOpen(title: string, open: boolean) {
  try {
    const set = new Set(readOpen());
    if (open) set.add(title);
    else set.delete(title);
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
  } catch {
    // storage blocked — the section just won't be remembered
  }
}

const norm = (s: string) => s.toLowerCase().replace(/[«»"]/g, "");

export function AdminSearchProvider({ query, children }: { query: string; children: ReactNode }) {
  return <SearchContext.Provider value={norm(query.trim())}>{children}</SearchContext.Provider>;
}

/** A group header («Игры и режимы», «Клубы», …) over its sections. Hidden
 * while a search matches none of them. */
export function AdminGroup({ title, titles, children }: { title: string; titles: string[]; children: ReactNode }) {
  const query = useContext(SearchContext);
  if (query && !norm(title).includes(query) && !titles.some((t) => norm(t).includes(query))) return null;
  return (
    <div className="flex flex-col gap-2">
      <h2 className="mt-2 font-display text-lg font-bold text-slate-200">{title}</h2>
      {children}
    </div>
  );
}

export function AdminSection({
  title, group, warning, children,
}: { title: string; group?: string; warning?: boolean; children: ReactNode }) {
  const query = useContext(SearchContext);
  const [open, setOpen] = useState(() => readOpen().includes(title));
  const matches = !query || norm(title).includes(query) || (group ? norm(group).includes(query) : false);
  if (!matches) return null;
  // A search opens what it found; closing it again is the user's own toggle.
  const shown = open || (query.length > 0 && norm(title).includes(query));

  const toggle = () => {
    setOpen(!shown);
    writeOpen(title, !shown);
  };

  return (
    <section
      className={`rounded-2xl border ${warning ? "border-amber-500/20 bg-amber-500/5" : "border-white/5 bg-bg-surface"}`}
    >
      <button
        type="button"
        onClick={toggle}
        aria-expanded={shown}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="font-display text-base font-bold">{title}</span>
        <svg
          width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
          strokeLinecap="round" strokeLinejoin="round"
          className={`shrink-0 text-slate-400 transition-transform ${shown ? "rotate-180" : ""}`}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {shown && <div className="flex flex-col gap-4 px-4 pb-4">{children}</div>}
    </section>
  );
}
