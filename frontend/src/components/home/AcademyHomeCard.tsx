import NewBadge from "@/components/common/NewBadge";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchAcademy } from "@/api/academy";
import { IconChevronRight } from "@/components/icons";

/** Home entry to «Академия»: level, what is being built and whether a free
 * scouting report is waiting. */
export default function AcademyHomeCard() {
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["academy"], queryFn: fetchAcademy, staleTime: 30_000 });
  if (data && !data.enabled) return null;
  const building = data?.construction ? data.wings.find((w) => w.code === data.construction!.building_code) : null;
  const status = !data
    ? "Молодые игроки и база клуба"
    : data.scout_report?.available
      ? "🔭 Скаутский отчёт готов!"
      : building
        ? `🏗️ Строится: ${building.name}`
        : data.level === 0
          ? "Построй первый корпус"
          : `Игроков: ${data.academy_cards} · стройка свободна`;
  return (
    <button
      type="button"
      onClick={() => navigate("/academy")}
      className="flex min-h-[64px] items-center gap-3 rounded-2xl border border-path/30 bg-gradient-to-r from-path/15 to-transparent p-3 text-left active:scale-[0.99]"
    >
      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-path/15 text-2xl" aria-hidden>🌱</span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-bold text-ink-chalk">
          Академия{data ? ` · ур. ${data.level}` : ""} <NewBadge section="academy" className="ml-1" />
        </span>
        <span className={`block truncate text-xs ${data?.scout_report?.available ? "font-semibold text-path" : "text-ink-mist"}`}>
          {status}
        </span>
      </span>
      <IconChevronRight size={18} className="shrink-0 text-ink-mist" />
    </button>
  );
}
