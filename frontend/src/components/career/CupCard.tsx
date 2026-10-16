import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { setCareerCupRotation, type CareerSeason, type CareerView } from "@/api/career";
import { IconCoin, IconTrophy } from "@/components/icons";
import { haptic } from "@/lib/telegram";

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}, ${d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

const STATUS: Record<string, { text: string; tone: string }> = {
  alive: { text: "В борьбе", tone: "bg-accent-lime/15 text-accent-lime" },
  out: { text: "Выбыли", tone: "bg-red-500/15 text-red-300" },
  winner: { text: "Обладатели кубка", tone: "bg-rarity-legendary/20 text-rarity-legendary" },
};

/** The cup bracket: rounds after league rounds 4, 6, 10 and 14 (a double
 * match day), my ties highlighted, prizes and the rotation toggle. */
export default function CupCard({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const navigate = useNavigate();
  const cup = season.cup;
  const rotation = useMutation({
    mutationFn: (value: boolean) => setCareerCupRotation(value),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  if (!cup) return null;
  const status = STATUS[cup.status] ?? STATUS.alive;

  return (
    <section className="flex flex-col gap-4 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <IconTrophy size={22} className="text-rarity-legendary" />
          <div>
            <p className="font-display text-base font-bold text-ink-chalk">Кубок</p>
            <p className="text-caption text-ink-mist">16 команд · матчи на вылет · ничья — серия пенальти</p>
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-micro font-bold ${status.tone}`}>{status.text}</span>
      </div>

      <div className="grid grid-cols-3 gap-1.5 text-center">
        {([["Победа", cup.rewards.winner], ["Финал", cup.rewards.final], ["1/2", cup.rewards.semi]] as const).map(([label, coins]) => (
          <div key={label} className="rounded-xl bg-bg-raised py-1.5">
            <p className="flex items-center justify-center gap-1 font-mono text-sm font-bold text-ink-chalk">
              {coins} <IconCoin size={11} className="text-accent-lime" />
            </p>
            <p className="text-micro text-ink-mist">{label}</p>
          </div>
        ))}
      </div>
      {cup.rep_winner > 0 && <p className="-mt-2 text-center text-micro text-ink-mist-dim">Победителю ещё +{cup.rep_winner} к репутации</p>}

      <label className="flex items-center justify-between gap-3 rounded-2xl bg-bg-raised px-3 py-2.5">
        <span>
          <span className="block text-xs font-semibold text-ink-chalk">Ротация в кубке</span>
          <span className="block text-micro leading-snug text-ink-mist">
            Кубок играется вечером после матча лиги — с ротацией выйдут самые свежие из заявки
          </span>
        </span>
        <input type="checkbox" checked={cup.rotation} disabled={rotation.isPending || cup.status !== "alive"}
          onChange={(e) => rotation.mutate(e.target.checked)} className="h-5 w-5 shrink-0 accent-accent-lime" aria-label="Ротация в кубке" />
      </label>

      {cup.rounds.map((round, k) => (
        <div key={round.name}>
          <div className="mb-1.5 flex items-center justify-between">
            <p className="text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">{round.name}</p>
            <p className="text-micro text-ink-mist-dim">{formatWhen(round.at)}</p>
          </div>
          {round.ties.length === 0 ? (
            <p className="rounded-xl bg-bg-raised px-3 py-2 text-caption text-ink-mist-dim">Пары определятся после предыдущего раунда</p>
          ) : (
            <div className="flex flex-col gap-1">
              {round.ties.map((tie, i) => {
                const played = tie.sa !== null && tie.sb !== null;
                const row = (name: string, score: number | null, pen: number | null, win: boolean) => (
                  <span className={`flex items-center justify-between gap-2 ${played && !win ? "text-ink-mist" : "text-ink-chalk"}`}>
                    <span className={`min-w-0 truncate ${win ? "font-bold" : ""}`}>{name}</span>
                    <span className="shrink-0 font-mono">{played ? score : "—"}{pen !== null ? <span className="text-micro text-ink-mist"> ({pen})</span> : null}</span>
                  </span>
                );
                return (
                  <button
                    key={i}
                    disabled={!tie.has_events}
                    onClick={() => navigate(`/play/career/seasons/${season.id}/cup/${k}/${i}`)}
                    className={`flex flex-col gap-0.5 rounded-xl px-3 py-2 text-left text-xs ${tie.mine ? "bg-accent-lime/10 ring-1 ring-accent-lime/40" : "bg-bg-raised"}`}
                  >
                    {row(tie.a_name, tie.sa, tie.pens ? tie.pens[0] : null, tie.winner === tie.a)}
                    {row(tie.b_name, tie.sb, tie.pens ? tie.pens[1] : null, tie.winner === tie.b)}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
