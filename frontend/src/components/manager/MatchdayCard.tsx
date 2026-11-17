import type { ManagerClub, ManagerLeague, ManagerView } from "@/api/manager";
import { formationLabel } from "@/lib/formationLayout";
import { eur } from "@/lib/managerMoney";
import Emblem from "@/components/manager/Emblem";

const STYLE_LABEL: Record<string, string> = { attacking: "Атака", possession: "Владение", defensive: "Оборона", counter: "Контратака" };

function when(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  const day = d.toDateString() === today.toDateString() ? "сегодня" : d.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "short" });
  return `${day} в ${d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

/** Last results of my club in the league: W / D / L, newest last. */
function form(league: ManagerLeague, name: string): ("W" | "D" | "L")[] {
  const out: ("W" | "D" | "L")[] = [];
  for (const round of league.rounds) {
    for (const m of round.matches) {
      if (!m.mine || m.hs == null || m.away_score == null) continue;
      const [own, opp] = m.home === name ? [m.hs, m.away_score] : [m.away_score, m.hs];
      out.push(own > opp ? "W" : own === opp ? "D" : "L");
    }
  }
  return out.slice(-5);
}

/** The top of the mode: what happens next — the next match (who, when, how
 * we play it), the place in the table and the form — instead of the club's
 * static card. Budget and division sit in one line. */
export default function MatchdayCard({ view, club, onTactics, onLeague }: {
  view: ManagerView; club: ManagerClub; onTactics: () => void; onLeague: () => void;
}) {
  const league = view.league;
  const next = club.next_match;
  const row = league?.table.find((r) => r.is_mine);
  const place = row ? (league?.table.indexOf(row) ?? 0) + 1 : null;
  const last = league && row ? form(league, club.name) : [];
  const coach = club.coach;
  const myStyle = next?.my_style ?? club.style;
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-gradient-to-br from-emerald-500/15 via-bg-surface to-bg-surface p-3.5 ring-1 ring-white/10" data-testid="matchday">
      <div className="flex items-center gap-2.5">
        <Emblem look={club.look} size={36} />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-display text-base font-bold leading-tight text-ink-chalk">{club.name}</span>
          <span className="block truncate text-[11px] text-ink-mist">{club.division_name} · рейтинг {club.squad.rating}</span>
        </span>
        <span className="shrink-0 rounded-full bg-black/30 px-2.5 py-1 text-xs font-bold text-accent-lime" data-testid="matchday-budget">{eur(club.budget)}</span>
      </div>

      {next ? (
        <button onClick={onTactics} className="flex flex-col gap-1.5 rounded-2xl bg-bg-base/50 p-3 text-left active:scale-[0.99]" data-testid="matchday-next">
          <span className="flex items-center justify-between text-micro font-bold uppercase tracking-[0.16em] text-emerald-200">
            <span>⚽ Следующий матч · {next.home ? "дома" : "в гостях"}</span>
            <span className="normal-case tracking-normal text-ink-mist">{when(next.at)}</span>
          </span>
          <span className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate font-display text-lg font-black text-ink-chalk">{next.opponent}</span>
            {next.rating != null && <span className="shrink-0 rounded-lg bg-white/10 px-2 py-0.5 text-xs font-bold text-ink-chalk">{next.rating} vs {club.squad.rating}</span>}
          </span>
          <span className="text-[11px] text-ink-mist">
            Они: {STYLE_LABEL[next.style] ?? next.style} · {formationLabel(next.formation)}
            {" · "}мы: <b className={next.edge === "win" ? "text-accent-lime" : next.edge === "lose" ? "text-red-300" : "text-ink-chalk"}>{STYLE_LABEL[myStyle] ?? myStyle}</b>
            {next.edge === "win" ? " — наш стиль сильнее" : next.edge === "lose" ? " — их стиль бьёт наш" : ""}
          </span>
          <span className="flex items-center justify-between gap-2 text-[11px]">
            <span className="min-w-0 truncate text-ink-mist">{coach?.auto ? `🧢 Тактику ставит ${coach.name}` : coach ? "🧢 Тактику ставишь ты" : "📋 Тактику ставишь ты"}</span>
            <span className="shrink-0 rounded-lg bg-floodlight px-2.5 py-1 text-[11px] font-bold text-bg-base">Тактика ›</span>
          </span>
        </button>
      ) : (
        <button onClick={onTactics} className="flex items-center gap-3 rounded-2xl bg-bg-base/50 p-3 text-left active:scale-[0.99]" data-testid="matchday-next">
          <span className="text-2xl">🗓</span>
          <span className="min-w-0 flex-1 text-xs text-ink-mist">
            <b className="block text-sm text-ink-chalk">{club.playing ? "Тур сыгран" : `Первый тур — ${when(view.season.first_round_at)}`}</b>
            {club.playing ? "Следующий соперник появится после жеребьёвки тура" : "Собери состав и выбери тактику до старта"}
          </span>
          <span className="shrink-0 text-ink-mist">›</span>
        </button>
      )}

      {league && row && place && (
        <button onClick={onLeague} className="flex items-center gap-2 rounded-2xl bg-bg-base/30 px-3 py-2 text-left text-xs active:scale-[0.99]" data-testid="matchday-table">
          <span className="font-display text-lg font-black text-ink-chalk">{place}</span>
          <span className="min-w-0 flex-1 text-ink-mist">
            место · <b className="text-ink-chalk">{row.points} очк.</b> · тур {league.rounds_played}/{league.total_rounds}
            {row.zone === "up" && <span className="text-accent-lime"> · зона повышения</span>}
            {row.zone === "down" && <span className="text-red-300"> · зона вылета</span>}
          </span>
          {last.length > 0 && (
            <span className="flex gap-0.5">
              {last.map((r, i) => (
                <span key={i} className={`flex h-4 w-4 items-center justify-center rounded text-[9px] font-black ${r === "W" ? "bg-accent-lime text-bg-base" : r === "D" ? "bg-white/20 text-ink-chalk" : "bg-red-400/80 text-bg-base"}`}>
                  {r === "W" ? "В" : r === "D" ? "Н" : "П"}
                </span>
              ))}
            </span>
          )}
          <span className="text-ink-mist">›</span>
        </button>
      )}
    </section>
  );
}
