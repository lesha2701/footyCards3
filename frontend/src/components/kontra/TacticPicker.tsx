import type { KontraTactic, KontraTacticCode } from "@/types";

const ICON: Record<KontraTacticCode, string> = { pressing: "⚡", tiki: "🔄", bus: "🚌" };

/** The squad's tactic: three schemes in a circle — each beats the next
 *  (+edge% damage against it). Used for attacks and for the defence. */
export default function TacticPicker({ tactics, current, edge, busy, onPick }: {
  tactics: KontraTactic[];
  current: KontraTacticCode | null;
  edge: number;
  busy?: boolean;
  onPick: (code: KontraTacticCode | null) => void;
}) {
  return (
    <section className="rounded-2xl bg-bg-surface p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="font-display text-sm font-bold text-ink-chalk">Тактика отряда</p>
        {current && (
          <button onClick={() => onPick(null)} disabled={busy} className="text-micro text-ink-mist underline-offset-2 active:underline">без схемы</button>
        )}
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {tactics.map((t) => {
          const on = t.code === current;
          return (
            <button
              key={t.code}
              onClick={() => onPick(t.code)}
              disabled={busy || on}
              className={`rounded-xl px-1.5 py-2 text-center transition active:scale-95 ${
                on ? "bg-amber-400 text-bg-base shadow-[0_0_14px_rgba(251,191,36,0.45)]" : "bg-white/5 text-ink-chalk"
              }`}
            >
              <span className="block text-lg leading-none">{ICON[t.code]}</span>
              <span className="mt-1 block text-xs font-black">{t.name}</span>
              <span className={`block text-[10px] ${on ? "text-bg-base/80" : "text-ink-mist"}`}>{t.bonus}</span>
              <span className={`mt-0.5 block text-[10px] font-bold ${on ? "text-bg-base" : "text-emerald-300"}`}>бьёт «{t.beats_name}»</span>
            </button>
          );
        })}
      </div>
      <p className="mt-1.5 text-center text-micro text-ink-mist-dim">
        Тактика, которая бьёт тактику соперника, даёт +{edge}% урона. Она же стоит в твоей защите.
      </p>
    </section>
  );
}
