import { useState } from "react";

import type { BenchUpgrade } from "@/api/lineups";
import { IconChevronUp } from "@/components/icons";

/** "На скамейке есть сильнее": single-swap hints with a one-tap apply, so a
 * pack's new star ends up in the squad without opening every slot picker. */
export default function BenchUpgradeHints({
  hints,
  onApply,
  busy,
}: {
  hints: BenchUpgrade[] | undefined;
  onApply: (hint: BenchUpgrade) => void;
  busy?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!hints?.length) return null;
  const shown = expanded ? hints : hints.slice(0, 2);
  return (
    <section className="rounded-2xl border border-accent-lime/20 bg-accent-lime/5 p-3">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-accent-lime">
        <IconChevronUp size={14} />
        На скамейке есть сильнее
      </p>
      <ul className="mt-2 flex flex-col gap-1.5">
        {shown.map((h) => (
          <li key={h.slot_code} className="flex items-center gap-2 text-xs">
            <span className="w-9 shrink-0 font-mono text-[10px] text-ink-mist">{h.slot_code}</span>
            <span className="min-w-0 flex-1 truncate text-ink-chalk">
              {h.suggested_name} <span className="font-mono text-ink-mist">{h.suggested_rating}</span>
              {h.current_name ? (
                <span className="text-ink-mist"> вместо {h.current_name} {h.current_rating}</span>
              ) : (
                <span className="text-ink-mist"> в пустой слот</span>
              )}
            </span>
            <span className="shrink-0 font-mono text-[11px] font-bold text-accent-lime">+{h.gain} рейт.</span>
            <button
              onClick={() => onApply(h)}
              disabled={busy}
              className="shrink-0 rounded-full bg-accent-lime/15 px-2 py-0.5 text-[11px] font-semibold text-accent-lime disabled:opacity-50"
            >
              Поставить
            </button>
          </li>
        ))}
      </ul>
      {hints.length > 2 && (
        <button onClick={() => setExpanded((v) => !v)} className="mt-1.5 text-[11px] text-ink-mist">
          {expanded ? "Свернуть" : `Ещё ${hints.length - 2}`}
        </button>
      )}
    </section>
  );
}
