import { motion } from "framer-motion";

import { tugShare } from "@/lib/fanBattle";
import type { FanSide } from "@/types";

const fmt = (n: number) => n.toLocaleString("ru-RU");

/** The tug-of-war bar: each side's share of the points, the leader pushing
 *  the spark towards the other end. */
export default function FanTug({
  sides, mine, compact = false, field = "points",
}: {
  sides: FanSide[];
  mine?: string | null;
  compact?: boolean;
  field?: "points" | "today_points";
}) {
  if (sides.length !== 2) return null;
  const [a, b] = sides;
  const share = tugShare(a[field], b[field]);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-end justify-between gap-2">
        <SideLabel side={a} mine={mine === a.code} value={a[field]} compact={compact} />
        <SideLabel side={b} mine={mine === b.code} value={b[field]} compact={compact} right />
      </div>
      <div className={`relative overflow-hidden rounded-full bg-black/40 ring-1 ring-white/10 ${compact ? "h-2.5" : "h-4"}`}>
        <motion.div
          className="absolute inset-y-0 left-0"
          style={{ background: `linear-gradient(90deg, ${a.color}cc, ${a.color})` }}
          initial={false}
          animate={{ width: `${share}%` }}
          transition={{ type: "spring", stiffness: 80, damping: 18 }}
        />
        <motion.div
          className="absolute inset-y-0 right-0"
          style={{ background: `linear-gradient(270deg, ${b.color}cc, ${b.color})` }}
          initial={false}
          animate={{ width: `${100 - share}%` }}
          transition={{ type: "spring", stiffness: 80, damping: 18 }}
        />
        <motion.span
          aria-hidden
          className="fans-spark absolute top-1/2 h-[180%] w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white"
          initial={false}
          animate={{ left: `${share}%` }}
          transition={{ type: "spring", stiffness: 80, damping: 18 }}
        />
      </div>
      {!compact && (
        <div className="flex justify-between font-mono text-micro text-ink-mist">
          <span>{share}%</span>
          <span>{Math.round((100 - share) * 10) / 10}%</span>
        </div>
      )}
      <span className="sr-only">
        {a.name}: {fmt(a[field])}, {b.name}: {fmt(b[field])}
      </span>
    </div>
  );
}

function SideLabel({ side, mine, value, compact, right }: { side: FanSide; mine: boolean; value: number; compact: boolean; right?: boolean }) {
  return (
    <span className={`flex min-w-0 flex-col ${right ? "items-end text-right" : ""}`}>
      <span className={`flex items-center gap-1 font-display font-black uppercase leading-none ${compact ? "text-xs" : "text-sm"}`} style={{ color: side.color }}>
        {!right && <span>{side.emoji}</span>}
        <span className="truncate">{side.name}</span>
        {right && <span>{side.emoji}</span>}
        {mine && <span className="rounded bg-white/15 px-1 py-px text-[9px] font-bold text-white">ТЫ</span>}
      </span>
      <span className={`font-display font-black leading-tight text-white ${compact ? "text-base" : "text-2xl"}`}>{fmt(value)}</span>
    </span>
  );
}
