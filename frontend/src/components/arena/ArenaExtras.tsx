/** Around the match: the weekend cup and who has been attacking your squad. */
import { IconCoin, IconTrophy } from "@/components/icons";
import type { ArenaCupStatus, ArenaDefenseItem } from "@/types";

/** «Кубок выходных»: a short knockout, the division points aren't at stake. */
export function ArenaCupPanel({ cup, onPlay, pending, limitReached }: { cup: ArenaCupStatus; onPlay: () => void; pending: boolean; limitReached: boolean }) {
  const finished = cup.status === "lost" || cup.status === "champion";
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-mist">
        {!cup.open
          ? "Открывается в субботу и воскресенье"
          : cup.status === "champion"
            ? "Кубок этой недели твой!"
            : cup.status === "lost"
              ? `Вылет. Раундов: ${cup.rounds_won} из ${cup.total_rounds}`
              : `Раунд ${cup.rounds_won + 1} из ${cup.total_rounds}. Проиграл — вылетел, очки дивизиона не меняются`}
      </p>
      <div className="flex items-center gap-1">
        {cup.rewards.map((coins, i) => (
          <span
            key={i}
            className={`flex flex-1 items-center justify-center gap-0.5 rounded-lg py-1.5 font-mono text-caption font-bold ${
              i < cup.rounds_won ? "bg-accent-green/20 text-accent-green" : i === cup.rounds_won && !finished ? "bg-amber-400/20 text-amber-300" : "bg-white/5 text-ink-mist-dim"
            }`}
          >
            {coins} <IconCoin size={10} />
          </span>
        ))}
      </div>
      {cup.open && !finished && (
        <button
          onClick={onPlay}
          disabled={pending || limitReached}
          className="flex items-center justify-center gap-1.5 rounded-2xl bg-amber-400 py-3 font-display text-sm font-bold text-black active:scale-95 disabled:opacity-40"
        >
          <IconTrophy size={15} /> {limitReached ? "Матчи на этот час закончились" : "Играть раунд"}
        </button>
      )}
    </div>
  );
}

/** Who played against your squad: «Реванш» makes the attacker your next match. */
export function ArenaDefenseList({ items, onRevenge, revengePending }: {
  items: ArenaDefenseItem[];
  onRevenge: (matchId: number) => void;
  revengePending: boolean;
}) {
  if (!items.length) return <p className="py-4 text-center text-sm text-ink-mist-dim">Пока никто не нападал</p>;
  return (
    <div className="flex flex-col gap-1.5">
      {items.map((item) => (
        <div key={item.match_id} className="flex items-center justify-between gap-2 rounded-xl bg-white/5 px-2.5 py-2 text-sm">
          <span className="min-w-0 truncate text-ink-mist">{item.attacker_name}</span>
          <span className="flex shrink-0 items-center gap-2">
            <span className={`font-mono font-bold ${item.result === "win" ? "text-accent-green" : item.result === "loss" ? "text-red-400" : "text-ink-mist"}`}>
              {item.my_score}:{item.their_score}
            </span>
            {item.can_revenge && (
              <button
                onClick={() => onRevenge(item.match_id)}
                disabled={revengePending}
                className="rounded-lg bg-red-500/80 px-2 py-1 text-micro font-bold text-white active:scale-95 disabled:opacity-40"
              >
                Реванш
              </button>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}
