import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchManagerSummary, type ManagerSummary } from "@/api/manager";
import officeArt from "@/assets/manager/office.webp";
import Emblem from "@/components/manager/Emblem";
import { eur } from "@/lib/managerMoney";

function clock(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date().toDateString() === d.toDateString();
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  return today ? time : `${d.toLocaleDateString("ru-RU", { weekday: "short" })} ${time}`;
}

interface Status {
  kicker: string;
  line: string;
  alert: boolean;
  chips: string[];
}

/** One line of what is happening at my club right now, most urgent first. */
function statusOf(view: ManagerSummary): Status {
  const club = view.club;
  const urgent = view.today.find((i) => i.urgent);
  if (!club) {
    return {
      kicker: "Стань президентом",
      line: urgent?.text ?? "Основай свой клуб и веди его к вершине",
      alert: !!urgent,
      chips: ["Трансферы", "Биржа", "Матчдей"],
    };
  }
  const league = view.league?.status === "active" ? view.league : null;
  const chips = [club.division_name, `Бюджет ${eur(club.budget)}`];
  if (league && league.place > 0) chips.unshift(`${league.place} место`);
  if (urgent && urgent.code !== "edge") return { kicker: club.name, line: `${urgent.icon} ${urgent.text}`, alert: true, chips };
  if (view.season.transfers_open && !club.trade_locked) {
    return { kicker: club.name, line: `🔓 Трансферное окно до ${clock(view.season.preseason_ends_at)}`, alert: true, chips };
  }
  if (league && club.next_match) {
    const m = club.next_match;
    return {
      kicker: `${club.name} · тур ${Math.min(league.rounds_played + 1, league.total_rounds)}/${league.total_rounds}`,
      line: `${m.home ? "Дома" : "В гостях"}: ${m.opponent}${m.at ? ` · ${clock(m.at)}` : ""}`,
      alert: m.edge === "lose",
      chips,
    };
  }
  return { kicker: club.name, line: view.today[0] ? `${view.today[0].icon} ${view.today[0].text}` : "Загляни в клуб", alert: false, chips };
}

/** «Менеджер» on the home screen: a wide tile over the modes grid with the
 * club's live status (the window, the next match, offers). Light summary,
 * not the mode's full view. */
export default function ManagerFeature() {
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["manager", "summary"], queryFn: fetchManagerSummary, staleTime: 60_000, retry: false });
  if (!data || !data.enabled) return null;
  const s = statusOf(data);
  return (
    <button
      onClick={() => navigate("/play/manager")}
      data-testid="manager-feature"
      className="relative mb-2 flex w-full items-center gap-3 overflow-hidden rounded-3xl bg-gradient-to-br from-amber-500/25 via-[#1d1606] to-[#0b1220] p-3.5 pr-28 text-left ring-1 ring-amber-300/40 active:scale-[0.98]"
    >
      <img
        src={officeArt}
        alt=""
        className="pointer-events-none absolute -right-3 top-1/2 h-32 w-32 -translate-y-1/2 object-cover [mask-image:radial-gradient(circle,black_52%,transparent_72%)]"
      />
      {data.club && <Emblem look={data.club.look} size={44} className="relative shrink-0" />}
      <span className="relative min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-micro font-bold uppercase tracking-[0.18em] text-amber-200">
          💼 Менеджер
          {s.alert && <span className="h-2 w-2 animate-pulse rounded-full bg-accent-lime" aria-label="Есть действие" />}
        </span>
        <span className="mt-0.5 block truncate font-display text-base font-black leading-tight text-ink-chalk">{s.kicker}</span>
        <span className={`mt-0.5 block truncate text-xs ${s.alert ? "font-semibold text-accent-lime" : "text-ink-mist"}`}>{s.line}</span>
        <span className="mt-2 flex flex-wrap gap-1">
          {s.chips.map((c) => (
            <span key={c} className="rounded-full bg-black/35 px-2 py-0.5 text-micro font-semibold text-amber-100 ring-1 ring-white/10">{c}</span>
          ))}
        </span>
      </span>
    </button>
  );
}
