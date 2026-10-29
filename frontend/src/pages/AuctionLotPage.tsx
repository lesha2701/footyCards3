import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import ConfirmDialog from "@/components/common/ConfirmDialog";
import NumberInput from "@/components/common/NumberInput";
import { ListSkeleton } from "@/components/common/Skeleton";
import CardSkillBadge from "@/components/cards/CardSkillBadge";
import PlayerCard from "@/components/cards/PlayerCard";
import AgentBadge from "@/components/market/AgentBadge";
import { IconClock, IconCoin } from "@/components/icons";
import {
  buyAuctionLotNow,
  cancelAuctionLot,
  fetchAuctionInfo,
  fetchAuctionLot,
  formatTimeLeft,
  LOT_STATUS_LABELS,
  newIdempotencyKey,
  placeAuctionBid,
  serverOffsetMs,
  type AuctionActionResult,
} from "@/api/auction";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { useNow } from "@/lib/useNow";
import { useAuthStore } from "@/store/authStore";

const POLL_ACTIVE_MS = 4000;

type Pending = { kind: "bid"; amount: number } | { kind: "buy"; amount: number } | { kind: "cancel" } | null;

export default function AuctionLotPage() {
  const lotId = Number(useParams().id);
  const queryClient = useQueryClient();
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const now = useNow();

  const { data: lot, isLoading, error: loadError } = useQuery({
    queryKey: ["auction", "lot", lotId],
    queryFn: () => fetchAuctionLot(lotId),
    // Poll while bidding is open: new bids, anti-sniping extensions and the
    // close (which the read itself triggers lazily once time is up).
    refetchInterval: (q) => (q.state.data?.status === "active" ? POLL_ACTIVE_MS : false),
  });
  const { data: info } = useQuery({ queryKey: ["auction", "info"], queryFn: fetchAuctionInfo });

  const [amount, setAmount] = useState(0);
  const [pending, setPending] = useState<Pending>(null);
  const [error, setError] = useState<string | null>(null);
  // One key per intended bid: a retry/double tap of the same bid replays
  // server-side instead of escrowing twice; a new amount gets a new key.
  const bidKey = useRef<{ amount: number; key: string } | null>(null);

  // Keep the input at least at the current minimum as others outbid.
  const minNext = lot?.min_next_bid ?? 0;
  useEffect(() => {
    setAmount((a) => (a < minNext ? minNext : a));
  }, [minNext]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["auction"] });
  const onMoneyDone = (data: AuctionActionResult) => {
    hapticNotify("success");
    updateBalance(data.new_balance);
    queryClient.setQueryData(["auction", "lot", lotId], data.lot);
    setError(null);
    refresh();
  };
  const onFail = (err: unknown) => {
    hapticNotify("error");
    setError(formatGameError(err, "Не удалось выполнить действие"));
    refresh();
  };

  const bidMutation = useMutation({
    mutationFn: (value: number) => {
      if (!bidKey.current || bidKey.current.amount !== value) bidKey.current = { amount: value, key: newIdempotencyKey() };
      return placeAuctionBid(lotId, value, bidKey.current.key);
    },
    onSuccess: (data) => { bidKey.current = null; onMoneyDone(data); },
    onError: onFail,
  });
  const buyMutation = useMutation({
    mutationFn: (price: number) => buyAuctionLotNow(lotId, price),
    onSuccess: onMoneyDone,
    onError: onFail,
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelAuctionLot(lotId),
    onSuccess: (data) => { queryClient.setQueryData(["auction", "lot", lotId], data); setError(null); refresh(); },
    onError: onFail,
  });

  if (isLoading) return <ListSkeleton />;
  if (!lot) return <p className="text-sm text-ink-mist">{formatGameError(loadError, "Лот не найден")}</p>;

  const card = lot.card;
  const left = new Date(lot.ends_at).getTime() - (now + serverOffsetMs(lot.server_now));
  const active = lot.status === "active";
  const canTrade = !!info?.enabled && !info.restriction;
  const busy = bidMutation.isPending || buyMutation.isPending || cancelMutation.isPending;
  const buyNowBelow = lot.buy_now_price ?? Infinity;
  const confirm = () => {
    const p = pending;
    setPending(null);
    if (!p) return;
    if (p.kind === "bid") bidMutation.mutate(p.amount);
    else if (p.kind === "buy") buyMutation.mutate(p.amount);
    else cancelMutation.mutate();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-4">
        <div className="w-32 shrink-0">
          <PlayerCard
            player={card.player}
            size="md"
            stars={card.stars}
            pathStage={card.path_stage}
            prestige={card.prestige}
            talentOverride={card.talent_override}
            badge={<CardSkillBadge code={card.skill_code} level={card.skill_level} />}
          />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h1 className="font-display text-lg font-bold leading-tight text-ink-chalk">{card.player.display_name}</h1>
          <p className="flex flex-wrap items-center gap-1 text-caption text-ink-mist">
            Копия #{card.serial_number} · продавец {lot.seller_name}
            {lot.seller_is_agent && <AgentBadge />}
          </p>
          <span className="mt-1 w-fit rounded-full bg-white/5 px-2 py-0.5 text-caption text-ink-mist">
            {lot.kind === "fixed" && active ? "Купить сразу" : LOT_STATUS_LABELS[lot.status]}
          </span>
          {active && lot.kind === "fixed" && (
            <p className="mt-1 text-caption text-ink-mist-dim">Снимется через {formatTimeLeft(left)}</p>
          )}
          {active && lot.kind !== "fixed" && (
            <p className={`mt-1 flex items-center gap-1 font-mono text-base font-bold ${left < 120_000 ? "text-red-300" : "text-ink-chalk"}`}>
              <IconClock size={14} />
              {formatTimeLeft(left)}
            </p>
          )}
          <p className="text-caption text-ink-mist-dim">Срок {lot.duration_hours} ч · комиссия {lot.fee_pct}%</p>
        </div>
      </div>

      {lot.kind === "fixed" ? (
        <Stat label={lot.status === "sold" ? "Продано за" : "Цена"} value={lot.final_price ?? lot.buy_now_price} />
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <Stat label={lot.current_bid ? "Текущая ставка" : "Стартовая цена"} value={lot.final_price ?? lot.current_bid ?? lot.start_price} />
          <Stat label="Купить сейчас" value={lot.buy_now_price} />
        </div>
      )}
      {lot.leader_name && active && (
        <p className="text-sm text-ink-mist">
          Лидирует: <b className="text-ink-chalk">{lot.i_am_leading ? "ты" : lot.leader_name}</b>
        </p>
      )}
      {lot.i_won && <p className="rounded-xl bg-accent-green/10 px-3 py-2 text-sm text-accent-green">Лот твой — карточка уже в коллекции.</p>}
      {lot.is_mine && lot.status === "sold" && lot.final_price != null && (
        <p className="rounded-xl bg-accent-green/10 px-3 py-2 text-sm text-accent-green">
          Продано за {lot.final_price.toLocaleString("ru-RU")}, комиссия {lot.fee_amount?.toLocaleString("ru-RU")}, тебе начислено{" "}
          {(lot.final_price - (lot.fee_amount ?? 0)).toLocaleString("ru-RU")}.
        </p>
      )}
      {lot.status === "removed" && lot.close_reason && (
        <p className="rounded-xl bg-white/5 px-3 py-2 text-sm text-ink-mist">Причина: {lot.close_reason}</p>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      {active && !lot.is_mine && lot.kind === "fixed" && (
        <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
          {!canTrade && <p className="text-sm text-amber-300">{info?.restriction ?? "Рынок сейчас закрыт"}</p>}
          <button
            disabled={!canTrade || busy || (lot.buy_now_price ?? 0) > balance}
            onClick={() => setPending({ kind: "buy", amount: lot.buy_now_price! })}
            className="flex items-center justify-center gap-1 rounded-xl bg-accent-green py-3 text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            Купить за {(lot.buy_now_price ?? 0).toLocaleString("ru-RU")}
            <IconCoin size={13} />
          </button>
          {(lot.buy_now_price ?? 0) > balance && (
            <p className="text-caption text-red-300">Не хватает монет (баланс {balance.toLocaleString("ru-RU")})</p>
          )}
        </div>
      )}

      {active && !lot.is_mine && lot.kind !== "fixed" && (
        <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
          {!canTrade && (
            <p className="text-sm text-amber-300">{info?.restriction ?? "Рынок сейчас закрыт"}</p>
          )}
          {lot.i_am_leading ? (
            <p className="text-sm text-accent-green">Твоя ставка лидирует. Если её перебьют, монеты вернутся.</p>
          ) : (
            <>
              <label className="text-sm font-semibold text-ink-mist">Твоя ставка (мин. {lot.min_next_bid.toLocaleString("ru-RU")})</label>
              <div className="flex gap-2">
                <NumberInput
                  min={lot.min_next_bid}
                  value={amount}
                  onChange={setAmount}
                  className="min-w-0 flex-1 rounded-xl bg-white/5 px-4 py-2.5 text-sm text-ink-chalk outline-none"
                />
                <button
                  disabled={!canTrade || busy || amount < lot.min_next_bid || amount >= buyNowBelow || amount > balance}
                  onClick={() => setPending({ kind: "bid", amount })}
                  className="rounded-xl bg-floodlight px-4 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
                >
                  Ставка
                </button>
              </div>
              {amount > balance && <p className="text-caption text-red-300">Не хватает монет (баланс {balance.toLocaleString("ru-RU")})</p>}
              {amount >= buyNowBelow && <p className="text-caption text-amber-300">Не меньше цены «Купить сейчас» — купи лот сразу</p>}
            </>
          )}
          {lot.buy_now_price != null && (
            <button
              disabled={!canTrade || busy || lot.buy_now_price > balance + (lot.i_am_leading ? lot.current_bid ?? 0 : 0)}
              onClick={() => setPending({ kind: "buy", amount: lot.buy_now_price! })}
              className="mt-1 flex items-center justify-center gap-1 rounded-xl bg-accent-green py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              Купить сейчас за {lot.buy_now_price.toLocaleString("ru-RU")}
              <IconCoin size={12} />
            </button>
          )}
        </div>
      )}

      {active && lot.is_mine && (
        <div className="rounded-2xl bg-bg-surface p-4 text-sm text-ink-mist">
          {lot.bid_count === 0 ? (
            <button
              disabled={busy}
              onClick={() => setPending({ kind: "cancel" })}
              className="w-full rounded-xl bg-white/5 py-2.5 text-sm font-bold text-ink-mist active:scale-95 disabled:opacity-40"
            >
              Снять с рынка
            </button>
          ) : (
            <p>На лот уже есть ставки — снять его нельзя. Карточка уйдёт лидеру по окончании торгов.</p>
          )}
        </div>
      )}

      <section hidden={lot.kind === "fixed"}>
        <p className="mb-2 text-sm font-semibold text-ink-mist">История ставок</p>
        {!lot.bids?.length && <p className="text-xs text-ink-mist-dim">Ставок пока нет</p>}
        <div className="flex flex-col gap-1">
          {lot.bids?.map((b) => (
            <div key={b.id} className="flex items-center justify-between rounded-xl bg-white/5 px-3 py-2 text-xs">
              <span className={b.is_mine ? "font-semibold text-ink-chalk" : "text-ink-mist"}>
                {b.is_mine ? "Ты" : b.bidder_name}
                {b.kind === "buy_now" && " · купил сразу"}
              </span>
              <span className="flex items-center gap-2">
                <span className="text-ink-mist-dim">
                  {new Date(b.created_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                </span>
                <span className="font-mono font-semibold text-accent-lime">{b.amount.toLocaleString("ru-RU")}</span>
              </span>
            </div>
          ))}
        </div>
      </section>

      <ConfirmDialog
        open={pending !== null}
        title={
          pending?.kind === "bid" ? `Ставка ${pending.amount.toLocaleString("ru-RU")}?`
            : pending?.kind === "buy" ? `Купить за ${pending.amount.toLocaleString("ru-RU")}?`
            : "Снять лот с рынка?"
        }
        description={
          pending?.kind === "bid"
            ? "Монеты спишутся сразу и вернутся, только если ставку перебьют. Отменить ставку нельзя."
            : pending?.kind === "buy"
              ? "Монеты спишутся сразу, карточка перейдёт к тебе со всеми навыками и звёздами."
              : "Карточка вернётся в коллекцию."
        }
        confirmLabel={pending?.kind === "cancel" ? "Снять" : "Подтвердить"}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-2xl bg-bg-surface p-3">
      <p className="text-caption text-ink-mist-dim">{label}</p>
      <p className="mt-0.5 flex items-center gap-1 font-mono text-lg font-bold text-accent-lime">
        {value != null ? value.toLocaleString("ru-RU") : "—"}
        {value != null && <IconCoin size={13} />}
      </p>
    </div>
  );
}
