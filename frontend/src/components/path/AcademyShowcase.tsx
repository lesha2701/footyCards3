import { useQuery } from "@tanstack/react-query";

import { fetchAcademyShowcase } from "@/api/path";
import PlayerCard from "@/components/cards/PlayerCard";

/** Profile showcase: the user's most prestigious «Академия» copies. Hidden
 * when there are none. */
export default function AcademyShowcase({ userId }: { userId: number }) {
  const { data: cards } = useQuery({ queryKey: ["academy-showcase", userId], queryFn: () => fetchAcademyShowcase(userId) });
  if (!cards?.length) return null;
  return (
    <section className="rounded-2xl bg-bg-surface p-4" aria-label="Витрина Академии">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">🌱 Витрина Академии</p>
      <div className="grid grid-cols-3 gap-2">
        {cards.map((card) => (
          <div key={card.id}>
            <PlayerCard
              player={card.player}
              size="sm"
              pathStage={card.path_stage}
              prestige={card.prestige}
              talentOverride={card.talent_override}
            />
            {card.prestige_icon_number != null && (
              <p className="mt-1 text-center text-[10px] font-bold text-fuchsia-300">Икона №{card.prestige_icon_number}</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
