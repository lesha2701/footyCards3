import { useMemo, useState } from "react";

type Option = { card_id: number; name: string; position: string; rating: number };

/** Search appears once the list stops fitting at a glance. */
const SEARCH_FROM = 6;

/** «Игрок академии»: the chosen card in one line, the whole list only on demand
 * and in a box of its own, so a big collection doesn't push the page down. */
export default function AcademyPicker({ options, selected, locked, busy, onPick, onClear }: {
  options: Option[]; selected: number | null; locked: boolean; busy: boolean;
  onPick: (cardId: number) => void; onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const current = options.find((o) => o.card_id === selected) ?? null;

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return options
      .filter((o) => !q || o.name.toLowerCase().includes(q) || o.position.toLowerCase().includes(q))
      .sort((a, b) => b.rating - a.rating || a.name.localeCompare(b.name));
  }, [options, query]);

  // Nothing chosen yet: the choice is what the section is for.
  const listed = open || (!current && !locked);

  return (
    <div className="flex flex-col gap-1.5">
      {current ? (
        <div className="flex items-center gap-2 rounded-xl bg-violet-400/15 p-2.5 ring-2 ring-violet-400">
          <span className="w-10 font-mono text-micro text-ink-mist">{current.position}</span>
          <span className="min-w-0 flex-1 truncate text-sm text-ink-chalk">{current.name}</span>
          <b className="text-sm text-violet-300">{current.rating}</b>
          {!locked && (
            <button type="button" onClick={() => setOpen(!open)} className="shrink-0 rounded-lg bg-bg-surface px-2.5 py-1.5 text-micro text-ink-mist">
              {open ? "Свернуть" : "Сменить"}
            </button>
          )}
        </div>
      ) : (
        !listed && <p className="text-caption text-ink-mist">Игрок академии не выбран. Выбрать можно в предсезонку.</p>
      )}

      {listed && (
        <>
          {options.length >= SEARCH_FROM && (
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={`Поиск среди ${options.length}: имя или позиция`}
              className="rounded-xl bg-bg-raised px-3 py-2 text-sm text-ink-chalk placeholder:text-ink-mist focus:outline-none" />
          )}
          <div className="flex max-h-72 flex-col gap-1.5 overflow-y-auto overscroll-contain">
            {shown.map((o) => {
              const on = selected === o.card_id;
              return (
                <button key={o.card_id} type="button" disabled={locked || busy}
                  onClick={() => { if (on) onClear(); else onPick(o.card_id); setOpen(false); setQuery(""); }}
                  className={`flex shrink-0 items-center gap-2 rounded-xl p-2.5 text-left disabled:opacity-60 ${on ? "bg-violet-400/15" : "bg-bg-raised"}`}>
                  <span className="w-10 font-mono text-micro text-ink-mist">{o.position}</span>
                  <span className="min-w-0 flex-1 truncate text-sm text-ink-chalk">{o.name}</span>
                  <b className="text-sm text-violet-300">{o.rating}</b>
                  <span className="w-5 text-right text-xs text-violet-300">{on ? "✓" : ""}</span>
                </button>
              );
            })}
            {shown.length === 0 && <p className="p-2 text-caption text-ink-mist">Никого не нашли.</p>}
          </div>
        </>
      )}
    </div>
  );
}
