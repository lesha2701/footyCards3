import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { acceptTradeOffer, cancelTradeOffer, fetchTradeOffer, rejectTradeOffer } from "@/api/trades";
import PlayerCard from "@/components/cards/PlayerCard";
import LoadingScreen from "@/components/common/LoadingScreen";
import { UserBadge } from "@/components/common/UserBadge";
import { IconChevronLeft, IconCoin, IconSwap } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { UserCard } from "@/types";

const STATUS_LABELS: Record<string, string> = {
  pending: "Ожидает",
  accepted: "Принят",
  rejected: "Отклонён",
  cancelled: "Отменён",
  expired: "Истёк",
};

export default function TradeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const tradeId = Number(id);

  const { data: offer, isLoading } = useQuery({
    queryKey: ["trades", "detail", tradeId],
    queryFn: () => fetchTradeOffer(tradeId),
    enabled: Number.isFinite(tradeId),
  });

  const [error, setError] = useState<string | null>(null);

  const invalidateAndReturn = () => {
    queryClient.invalidateQueries({ queryKey: ["trades"] });
    navigate("/trades");
  };
  // Refetches this offer on failure — e.g. the other side already resolved it (accepted/
  // rejected/cancelled) or one of the cards involved was sold/traded away in the meantime —
  // so the stale "pending" buttons don't keep inviting the player to retry an action that
  // can only 409 again.
  const onActionError = (err: unknown) => {
    setError(formatGameError(err, "Не удалось выполнить действие"));
    queryClient.invalidateQueries({ queryKey: ["trades", "detail", tradeId] });
  };

  const acceptMutation = useMutation({
    mutationFn: () => acceptTradeOffer(tradeId),
    onSuccess: (data) => { hapticNotify("success"); updateBalance(data.new_balance); invalidateAndReturn(); },
    onError: onActionError,
  });
  const rejectMutation = useMutation({
    mutationFn: () => rejectTradeOffer(tradeId),
    onSuccess: invalidateAndReturn,
    onError: onActionError,
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelTradeOffer(tradeId),
    onSuccess: invalidateAndReturn,
    onError: onActionError,
  });

  if (isLoading || !offer) return <LoadingScreen />;

  const isReceiver = offer.receiver.id === userId;
  const isSender = offer.sender.id === userId;
  const busy = acceptMutation.isPending || rejectMutation.isPending || cancelMutation.isPending;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/trades")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Обмен #{offer.id}</h1>
        <span className="ml-auto rounded-full bg-white/5 px-3 py-1 text-xs font-semibold text-ink-mist">
          {STATUS_LABELS[offer.status]}
        </span>
      </div>

      <div className="flex items-center justify-center gap-2 rounded-2xl bg-bg-surface p-3 text-sm">
        <span className="flex items-center gap-1 text-ink-chalk">
          {offer.sender.username ?? offer.sender.first_name}
          <UserBadge badge={offer.sender.active_badge} />
        </span>
        <IconSwap size={16} className="shrink-0 text-ink-mist-dim" />
        <span className="flex items-center gap-1 text-ink-chalk">
          {offer.receiver.username ?? offer.receiver.first_name}
          <UserBadge badge={offer.receiver.active_badge} />
        </span>
      </div>

      {offer.message && (
        <p className="rounded-2xl bg-bg-surface p-3 text-center text-sm italic text-ink-mist">«{offer.message}»</p>
      )}

      <TradeSide
        title={isSender ? "Ты отдаёшь" : "Тебе предлагают"}
        cards={offer.offered_cards}
        coins={offer.sender_coins}
      />
      <TradeSide
        title={isSender ? "Ты получаешь" : "С тебя просят"}
        cards={offer.requested_cards}
        coins={offer.receiver_coins}
      />

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {offer.status === "pending" && (
        <div className="flex gap-2">
          {isReceiver && (
            <>
              <button
                onClick={() => acceptMutation.mutate()}
                disabled={busy}
                className="flex-1 rounded-2xl bg-accent-green py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
              >
                Принять
              </button>
              <button
                onClick={() => rejectMutation.mutate()}
                disabled={busy}
                className="flex-1 rounded-2xl bg-red-500/80 py-3 text-sm font-bold text-white active:scale-95 disabled:opacity-40"
              >
                Отклонить
              </button>
            </>
          )}
          {isSender && (
            <button
              onClick={() => cancelMutation.mutate()}
              disabled={busy}
              className="flex-1 rounded-2xl bg-white/5 py-3 text-sm font-bold text-ink-mist active:scale-95 disabled:opacity-40"
            >
              Отменить предложение
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function TradeSide({ title, cards, coins }: { title: string; cards: UserCard[]; coins: number }) {
  return (
    <div className="rounded-2xl bg-bg-surface p-3">
      <p className="mb-2 flex items-center justify-between font-display text-sm font-bold text-ink-chalk">
        {title}
        {coins > 0 && (
          <span className="flex items-center gap-1 font-mono text-sm font-bold text-accent-lime">
            <IconCoin size={14} />+{coins}
          </span>
        )}
      </p>
      {cards.length > 0 ? (
        <div className="grid grid-cols-3 gap-2">
          {cards.map((c) => (
            <PlayerCard key={c.id} player={c.player} size="sm" />
          ))}
        </div>
      ) : (
        coins === 0 && <p className="text-center text-xs text-ink-mist-dim">Ничего</p>
      )}
    </div>
  );
}
