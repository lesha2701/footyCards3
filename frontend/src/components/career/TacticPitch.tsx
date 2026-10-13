import type { Tactic } from "@/api/career";

// Vertical pitch, our goal at the bottom. Line heights by block.
const LINE_Y: Record<string, Record<"DEF" | "MID" | "FWD", number>> = {
  high: { DEF: 90, MID: 66, FWD: 42 },
  mid: { DEF: 100, MID: 78, FWD: 52 },
  low: { DEF: 110, MID: 92, FWD: 66 },
};

function spread(count: number): number[] {
  if (count <= 0) return [];
  const margin = count >= 5 ? 12 : count === 4 ? 16 : count === 3 ? 22 : 32;
  if (count === 1) return [50];
  return Array.from({ length: count }, (_, i) => margin + ((100 - 2 * margin) * i) / (count - 1));
}

/** Schematic of the chosen tactic: the formation at its block height, the
 * defensive line, and where / how attacks go. Purely illustrative — the
 * numbers live on the server. */
export default function TacticPitch({ formation, tactic }: { formation: string; tactic: Tactic }) {
  const block = tactic.block ?? "mid";
  const y = LINE_Y[block] ?? LINE_Y.mid;
  const [def = 4, mid = 3, fwd = 3] = formation.split("-").map(Number);
  const lines = ([["DEF", def], ["MID", mid], ["FWD", fwd]] as const).map(([cat, n]) => ({ cat, n }));
  const wings = tactic.direction === "wings" || tactic.direction === "mixed";
  const center = tactic.direction === "center" || tactic.direction === "mixed";
  const strong = (on: boolean) => (tactic.direction === "mixed" ? 1.6 : on ? 2.4 : 0);
  const direct = tactic.buildup === "direct";
  const short = tactic.buildup === "short";

  return (
    <svg viewBox="0 0 100 140" className="mx-auto block h-auto w-full max-w-[220px]" role="img" aria-label="Схема тактики">
      <defs>
        <linearGradient id="tp-grass" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#123f2b" />
          <stop offset="100%" stopColor="#0d2f20" />
        </linearGradient>
        <marker id="tp-arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="#c6e63a" />
        </marker>
      </defs>
      <rect x="0" y="0" width="100" height="140" rx="6" fill="url(#tp-grass)" />
      {Array.from({ length: 7 }).map((_, i) => (
        <rect key={i} x="0" y={i * 20} width="100" height="10" fill="#ffffff" opacity="0.025" />
      ))}
      <g fill="none" stroke="#ffffff" strokeOpacity="0.22" strokeWidth="0.6">
        <rect x="3" y="3" width="94" height="134" rx="2" />
        <line x1="3" y1="70" x2="97" y2="70" />
        <circle cx="50" cy="70" r="10" />
        <rect x="26" y="3" width="48" height="18" />
        <rect x="26" y="119" width="48" height="18" />
      </g>

      {/* pressing zone for a high block, deep zone for a low one */}
      {block === "high" && <rect x="3" y="3" width="94" height={y.FWD - 3} fill="#22d3c4" opacity="0.08" />}
      {block === "low" && <rect x="3" y={y.MID - 6} width="94" height={137 - (y.MID - 6)} fill="#22d3c4" opacity="0.07" />}
      <line x1="6" y1={y.DEF + 6} x2="94" y2={y.DEF + 6} stroke="#22d3c4" strokeWidth="0.8" strokeDasharray="2 2" opacity="0.8" />

      {/* attack direction */}
      <g stroke="#c6e63a" fill="none" strokeLinecap="round" markerEnd="url(#tp-arrow)" opacity="0.9">
        {wings && (
          <>
            <path d={`M16 ${y.MID} C 8 ${y.FWD}, 10 30, 30 16`} strokeWidth={strong(true)} />
            <path d={`M84 ${y.MID} C 92 ${y.FWD}, 90 30, 70 16`} strokeWidth={strong(true)} />
          </>
        )}
        {center && <path d={`M50 ${y.MID - 4} L50 18`} strokeWidth={strong(true)} />}
        {direct && <path d={`M38 ${y.DEF - 2} L44 24`} strokeWidth="1" strokeDasharray="3 2" />}
      </g>
      {short && (
        <polyline points={`40,${y.MID + 6} 46,${y.MID} 52,${y.MID + 6} 58,${y.MID}`} fill="none" stroke="#8fe3b8"
          strokeWidth="0.9" strokeDasharray="1.5 1.5" />
      )}

      {/* players */}
      <circle cx="50" cy="128" r="3.2" fill="#e5e7eb" stroke="#0d2f20" strokeWidth="0.8" />
      {lines.map(({ cat, n }) =>
        spread(n).map((x, i) => (
          <circle key={`${cat}${i}`} cx={x} cy={y[cat]} r="3.2" fill={cat === "FWD" ? "#c6e63a" : cat === "MID" ? "#3ed17e" : "#22d3c4"}
            stroke="#0d2f20" strokeWidth="0.8" />
        )),
      )}
    </svg>
  );
}
