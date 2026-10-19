import NewBadge from "@/components/common/NewBadge";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchClubBase } from "@/api/clubBase";
import { IconChevronRight } from "@/components/icons";

/** Home entry to «Клубная база»: level, what is being built and whether
 * sponsor/merchandise income is waiting. */
export default function BaseHomeCard() {
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["club-base"], queryFn: fetchClubBase, staleTime: 30_000 });
  if (data && !data.enabled) return null;
  const status = !data
    ? "Стадион, корпуса и Академия"
    : data.income.pending > 0
      ? `💼 Доход готов: +${data.income.pending}`
      : data.construction
        ? `🏗️ Строится: ${data.construction.name}`
        : data.level === 0
          ? "Начни со штаб-квартиры"
          : "Бригада свободна — что строим?";
  return (
    <button
      type="button"
      onClick={() => navigate("/base")}
      className="flex min-h-[64px] items-center gap-3 rounded-2xl border border-legend/30 bg-gradient-to-r from-legend/15 to-transparent p-3 text-left active:scale-[0.99]"
    >
      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-legend/15 text-2xl" aria-hidden>🏟️</span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-bold text-ink-chalk">
          Клубная база{data ? ` · ур. ${data.total_level}` : ""} <NewBadge section="club-base" className="ml-1" />
        </span>
        <span className={`block truncate text-xs ${data && data.income.pending > 0 ? "font-semibold text-legend" : "text-ink-mist"}`}>
          {status}
        </span>
      </span>
      <IconChevronRight size={18} className="shrink-0 text-ink-mist" />
    </button>
  );
}
