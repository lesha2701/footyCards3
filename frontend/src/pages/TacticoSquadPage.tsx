import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchTacticoSquad, setTacticoSquad } from "@/api/tactico";
import { fetchCollection } from "@/api/collection";
import PlayerCard from "@/components/cards/PlayerCard";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import EmptyState from "@/components/common/EmptyState";
import { IconCollection } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { UserCard } from "@/types";

const SQUAD_SIZE = 11;

export default function TacticoSquadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: squad } = useQuery({ queryKey: ["tactico-squad"], queryFn: fetchTacticoSquad });
  const { data: collectionPage, isLoading } = useQuery({
    queryKey: ["collection-for-tactico"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
  });

  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [initialized, setInitialized] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (squad && !initialized) {
      setSelectedIds(squad.cards.map((c) => c.id));
      setInitialized(true);
    }
  }, [squad, initialized]);

  const saveMutation = useMutation({
    mutationFn: () => setTacticoSquad(selectedIds),
    onSuccess: () => {
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["tactico-squad"] });
      navigate("/play/tactico");
    },
    onError: (err) => setError(formatGameError(err, "Не удалось сохранить состав")),
  });

  const cards = collectionPage?.items ?? [];
  const maxLegendary = squad?.max_legendary ?? 3;
  const maxEpic = squad?.max_epic ?? 3;

  const cardsById = new Map<number, UserCard>(cards.map((c) => [c.id, c]));
  const legendaryCount = selectedIds.filter((id) => cardsById.get(id)?.player.rarity === "legendary").length;
  const epicCount = selectedIds.filter((id) => cardsById.get(id)?.player.rarity === "epic").length;

  const toggle = (card: UserCard) => {
    const id = card.id;
    if (selectedIds.includes(id)) {
      setError(null);
      setSelectedIds((prev) => prev.filter((x) => x !== id));
      return;
    }
    if (selectedIds.length >= SQUAD_SIZE) {
      haptic("medium");
      return;
    }
    if (card.player.rarity === "legendary" && legendaryCount >= maxLegendary) {
      haptic("medium");
      setError(`Максимум ${maxLegendary} легендарных карт в составе`);
      return;
    }
    if (card.player.rarity === "epic" && epicCount >= maxEpic) {
      haptic("medium");
      setError(`Максимум ${maxEpic} эпических карт в составе`);
      return;
    }
    setError(null);
    setSelectedIds((prev) => [...prev, id]);
  };

  return (
    <div className="flex flex-col gap-4 pb-24">
      <div>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Состав Тактико</h1>
        <p className="mt-1 text-xs text-ink-mist">
          Выбери ровно {SQUAD_SIZE} карточек — без позиций и формации, только твои сильнейшие. Не более {maxLegendary}{" "}
          легендарных и {maxEpic} эпических, чтобы состав решала не только редкость карт.
        </p>
      </div>

      <div className="flex gap-2 text-[11px] font-semibold">
        <span className={`rounded-full px-2.5 py-1 ${legendaryCount >= maxLegendary ? "bg-rarity-legendary/20 text-rarity-legendary" : "bg-white/5 text-ink-mist"}`}>
          Легендарных: {legendaryCount}/{maxLegendary}
        </span>
        <span className={`rounded-full px-2.5 py-1 ${epicCount >= maxEpic ? "bg-rarity-epic/20 text-rarity-epic" : "bg-white/5 text-ink-mist"}`}>
          Эпических: {epicCount}/{maxEpic}
        </span>
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {isLoading && <CardGridSkeleton count={9} />}

      {!isLoading && !cards.length && (
        <EmptyState icon={IconCollection} title="Пока нет карточек" description="Открой пак, чтобы собрать состав" />
      )}

      <div className="grid grid-cols-3 gap-2.5">
        {cards.map((card) => {
          const selected = selectedIds.includes(card.id);
          const rarityBlocked =
            !selected &&
            ((card.player.rarity === "legendary" && legendaryCount >= maxLegendary) ||
              (card.player.rarity === "epic" && epicCount >= maxEpic));
          return (
            <PlayerCard
              key={card.id}
              player={card.player}
              size="sm"
              selected={selected}
              dimmed={!selected && (selectedIds.length >= SQUAD_SIZE || rarityBlocked)}
              onClick={() => toggle(card)}
            />
          );
        })}
      </div>

      <div className="fixed inset-x-0 bottom-16 z-30 mx-auto flex w-full max-w-md items-center justify-between gap-3 border-t border-white/10 bg-bg-base/95 px-4 py-3 backdrop-blur">
        <p className="font-mono text-sm text-ink-mist">
          <span className={selectedIds.length === SQUAD_SIZE ? "text-accent-lime" : "text-ink-chalk"}>{selectedIds.length}</span>
          /{SQUAD_SIZE} выбрано
        </p>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={selectedIds.length !== SQUAD_SIZE || saveMutation.isPending}
          className="rounded-xl bg-accent-lime px-5 py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
        >
          Сохранить
        </button>
      </div>
    </div>
  );
}
