import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import EmptyState from "@/components/common/EmptyState";
import { UserBadge } from "@/components/common/UserBadge";
import { IconCoin, IconPlus, IconSwap } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { acceptTradeOffer, cancelTradeOffer, fetchTradeOffers, rejectTradeOffer } from "@/api/trades";
import { staticUrl } from "@/lib/api";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { TradeOffer } from "@/types";

type Tab = "incoming" | "outgoing" | "history";

const STATUS_LABELS: Record<string, string> = {
  pending: "Ожидает",
  accepted: "Принят",
  rejected: "Отклонён",
  cancelled: "Отменён",
  expired: "Истёк",
};

export default function TradesPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("incoming");
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id);

  const params = tab === "history" ? {} : { direction: tab, status: "pending" };
  const { data: offers, isLoading } = useQuery({ queryKey: ["trades", tab], queryFn: () => fetchTradeOffers(params) });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["trades"] });

  const acceptMutation = useMutation({ mutationFn: acceptTradeOffer, onSuccess: () => { hapticNotify("success"); invalidate(); } });
  const rejectMutation = useMutation({ mutationFn: rejectTradeOffer, onSuccess: invalidate });
  const cancelMutation = useMutation({ mutationFn: cancelTradeOffer, onSuccess: invalidate });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Обмены</h1>
        <button
          onClick={() => navigate("/trades/new")}
          className="flex items-center gap-1 rounded-full bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95"
        >
          <IconPlus size={13} />
          Новый
        </button>
      </div>

      <div className="flex gap-2">
        <TabButton active={tab === "incoming"} label="Входящие" onClick={() => setTab("incoming")} />
        <TabButton active={tab === "outgoing"} label="Исходящие" onClick={() => setTab("outgoing")} />
        <TabButton active={tab === "history"} label="История" onClick={() => setTab("history")} />
      </div>

      {isLoading && <ListSkeleton />}
      {!isLoading && !offers?.length && <EmptyState icon={IconSwap} title="Обменов нет" description="Предложи обмен другому игроку" />}

      <div className="flex flex-col gap-3">
        {offers?.map((offer) => (
          <TradeCard
            key={offer.id}
            offer={offer}
            myUserId={userId}
            onAccept={() => acceptMutation.mutate(offer.id)}
            onReject={() => rejectMutation.mutate(offer.id)}
            onCancel={() => cancelMutation.mutate(offer.id)}
          />
        ))}
      </div>
    </div>
  );
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 rounded-xl py-2 text-xs font-semibold ${active ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
    >
      {label}
    </button>
  );
}

function TradeCard({
  offer,
  myUserId,
  onAccept,
  onReject,
  onCancel,
}: {
  offer: TradeOffer;
  myUserId?: number;
  onAccept: () => void;
  onReject: () => void;
  onCancel: () => void;
}) {
  const isReceiver = offer.receiver.id === myUserId;
  const isSender = offer.sender.id === myUserId;

  return (
    <div className="rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-1 text-ink-mist">
          {isSender ? `Кому: ${offer.receiver.username ?? offer.receiver.first_name}` : `От: ${offer.sender.username ?? offer.sender.first_name}`}
          <UserBadge badge={isSender ? offer.receiver.active_badge : offer.sender.active_badge} />
        </span>
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-ink-mist-dim">{STATUS_LABELS[offer.status]}</span>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <MiniCardRow cards={offer.offered_cards} label={isSender ? "Отдаёшь" : "Предлагает"} coins={offer.sender_coins} />
        <IconSwap size={16} className="shrink-0 text-ink-mist-dim" />
        <MiniCardRow cards={offer.requested_cards} label={isSender ? "Получаешь" : "Просит"} coins={offer.receiver_coins} />
      </div>

      {offer.message && <p className="mt-2 text-xs italic text-ink-mist">«{offer.message}»</p>}

      {offer.status === "pending" && (
        <div className="mt-3 flex gap-2">
          {isReceiver && (
            <>
              <button onClick={onAccept} className="flex-1 rounded-xl bg-accent-green py-2 text-xs font-bold text-bg-base active:scale-95">
                Принять
              </button>
              <button onClick={onReject} className="flex-1 rounded-xl bg-red-500/80 py-2 text-xs font-bold text-white active:scale-95">
                Отклонить
              </button>
            </>
          )}
          {isSender && (
            <button onClick={onCancel} className="flex-1 rounded-xl bg-white/5 py-2 text-xs font-bold text-ink-mist active:scale-95">
              Отменить предложение
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function MiniCardRow({ cards, label, coins }: { cards: TradeOffer["offered_cards"]; label: string; coins: number }) {
  return (
    <div className="flex-1">
      <p className="mb-1 text-[10px] text-ink-mist-dim">{label}</p>
      <div className="flex -space-x-2">
        {cards.slice(0, 3).map((c) => (
          <img
            key={c.id}
            src={staticUrl(c.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
            alt={c.player.display_name}
            className="h-10 w-10 rounded-lg border-2 border-bg-surface object-cover"
          />
        ))}
        {cards.length === 0 && coins === 0 && <span className="text-xs text-ink-mist-dim">—</span>}
      </div>
      {coins > 0 && (
        <p className="mt-1 flex items-center gap-0.5 font-mono text-[11px] font-semibold text-accent-lime">
          +{coins}
          <IconCoin size={10} />
        </p>
      )}
    </div>
  );
}
