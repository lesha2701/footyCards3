import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchMyProfile } from "@/api/profile";
import { setShowcase } from "@/api/collection";
import PlayerCard from "@/components/cards/PlayerCard";
import { formatGameError } from "@/lib/errors";
import { haptic } from "@/lib/telegram";
import type { UserCard } from "@/types";

export const SHOWCASE_SIZE = 3;

/** «Витрина»: the three copies the owner shows off on the profile. */
export function ShowcaseRow({ cards, title = "Витрина", onOpen }: { cards: UserCard[]; title?: string; onOpen?: (card: UserCard) => void }) {
  if (!cards.length) return null;
  return (
    <section
      className="rounded-2xl border border-amber-200/15 bg-gradient-to-b from-amber-300/10 to-transparent p-3"
      data-testid="profile-showcase"
    >
      <p className="mb-2 text-micro font-bold uppercase tracking-[0.2em] text-amber-200/80">✨ {title}</p>
      <div className="grid grid-cols-3 gap-2">
        {cards.map((card) => (
          <PlayerCard
            key={card.id}
            player={card.player}
            size="sm"
            stars={card.stars}
            serial={card.serial_number}
            finish={card.finish}
            prestige={card.prestige}
            pathStage={card.path_stage}
            onClick={onOpen ? () => onOpen(card) : undefined}
          />
        ))}
      </div>
    </section>
  );
}

/** «В витрину» on a card's sheet: puts the copy on the profile or takes it off. */
export function ShowcaseToggle({ cardId }: { cardId: number }) {
  const queryClient = useQueryClient();
  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const ids = (profile?.showcase ?? []).map((c) => c.id);
  const on = ids.includes(cardId);
  const full = !on && ids.length >= SHOWCASE_SIZE;
  const mutation = useMutation({
    mutationFn: () => setShowcase(on ? ids.filter((i) => i !== cardId) : [...ids, cardId]),
    onSuccess: () => {
      haptic("light");
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      queryClient.invalidateQueries({ queryKey: ["public-profile"] });
    },
  });
  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={() => mutation.mutate()}
        disabled={!profile || full || mutation.isPending}
        className={`min-h-[44px] rounded-xl px-3 py-2 text-left text-xs font-semibold disabled:opacity-50 ${
          on ? "bg-amber-300/20 text-amber-200" : "bg-black/20 text-ink-chalk"
        }`}
        data-testid="showcase-toggle"
      >
        {on ? "✨ В витрине профиля — убрать" : full ? `Витрина заполнена (${SHOWCASE_SIZE} из ${SHOWCASE_SIZE}) — сначала убери карту` : `✨ Поставить в витрину профиля (${ids.length}/${SHOWCASE_SIZE})`}
      </button>
      {mutation.error && <p className="text-micro text-red-400">{formatGameError(mutation.error, "Не получилось обновить витрину")}</p>}
    </div>
  );
}
