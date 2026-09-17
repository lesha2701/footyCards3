import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { acceptPenaltyOpenChallenge, fetchPenaltyOpenChallenge } from "@/api/penalty";
import { fetchCollection } from "@/api/collection";
import CardPickerModal from "@/components/cards/CardPickerModal";
import { IconCoin, IconGoal } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

const STATUS_MESSAGES: Record<string, string> = {
  finished: "Эта серия уже сыграна.",
  declined: "Этот вызов отклонён.",
  cancelled: "Этот вызов отменён создателем.",
  expired: "Срок действия этого вызова истёк.",
  in_progress: "Этот вызов уже принят — серия идёт.",
};

export default function PenaltyOpenChallengePage() {
  const { matchId } = useParams<{ matchId: string }>();
  const id = Number(matchId);
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [pickingCard, setPickingCard] = useState(false);
  const [cardSearch, setCardSearch] = useState("");

  const { data: preview, isLoading } = useQuery({
    queryKey: ["penalty-open-challenge", id],
    queryFn: () => fetchPenaltyOpenChallenge(id),
    enabled: Number.isFinite(id),
  });
  const { data: collection } = useQuery({
    queryKey: ["collection", "penalty-open-accept", cardSearch],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: cardSearch || undefined }),
    enabled: pickingCard,
  });

  const acceptMutation = useMutation({
    mutationFn: (userCardId: number) => acceptPenaltyOpenChallenge(id, userCardId),
    onSuccess: (match) => {
      hapticNotify("success");
      navigate(`/play/penalty/matches/${match.id}`, { replace: true });
    },
    onError: (err) => {
      setPickingCard(false);
      setError(formatGameError(err, "Не удалось принять вызов"));
    },
  });

  if (isLoading) return null;
  if (!preview) {
    return (
      <div className="flex flex-col items-center gap-3 pt-16 text-center">
        <IconGoal size={32} className="text-ink-mist-dim" />
        <p className="text-sm text-ink-mist">Вызов не найден.</p>
      </div>
    );
  }

  if (preview.is_own_challenge) {
    return (
      <div className="flex flex-col items-center gap-4 pt-16 text-center">
        <IconGoal size={32} className="text-ink-mist-dim" />
        <p className="text-sm text-ink-mist">Это твой собственный вызов — дождись, пока кто-нибудь его примет.</p>
        <button
          onClick={() => navigate(`/play/penalty/matches/${preview.id}`)}
          className="rounded-xl bg-floodlight px-5 py-2.5 text-sm font-bold text-bg-base active:scale-95"
        >
          Открыть вызов
        </button>
      </div>
    );
  }

  if (preview.status !== "pending_accept") {
    return (
      <div className="flex flex-col items-center gap-3 pt-16 text-center">
        <IconGoal size={32} className="text-ink-mist-dim" />
        <p className="text-sm text-ink-mist">{STATUS_MESSAGES[preview.status] ?? "Этот вызов больше не активен."}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-5 pt-10 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-accent/10">
        <IconGoal size={28} className="text-accent" />
      </div>
      <div>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Вызов на серию пенальти</h1>
        <p className="mt-1 text-sm text-ink-mist">от {preview.creator_name}</p>
      </div>

      {preview.stake_coins > 0 ? (
        <div className="flex flex-col items-center gap-1 rounded-2xl bg-bg-surface px-6 py-4">
          <span className="flex items-center gap-1.5 font-mono text-lg font-bold text-accent-lime">
            {preview.stake_coins} <IconCoin size={16} />
          </span>
          <p className="text-xs text-ink-mist-dim">
            ставка с каждой стороны · победитель заберёт {preview.stake_coins * 2}
          </p>
        </div>
      ) : (
        <p className="rounded-2xl bg-bg-surface px-6 py-4 text-sm text-ink-mist">Обычная игра, без ставки</p>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="flex gap-2">
        <button
          onClick={() => navigate("/play/penalty/matches")}
          className="rounded-xl bg-white/5 px-5 py-2.5 text-sm font-bold text-ink-mist active:scale-95"
        >
          Отмена
        </button>
        <button
          onClick={() => setPickingCard(true)}
          disabled={acceptMutation.isPending}
          className="rounded-xl bg-accent-green px-5 py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          Согласиться
        </button>
      </div>

      {pickingCard && (
        <CardPickerModal
          open
          title="Выбери карточку для удара"
          cards={collection?.items ?? []}
          onSelect={(card) => acceptMutation.mutate(card.id)}
          onClose={() => { setPickingCard(false); setCardSearch(""); }}
          searchValue={cardSearch}
          onSearchChange={setCardSearch}
        />
      )}
    </div>
  );
}
