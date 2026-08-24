import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { adminBroadcastGift, adminSendGift, fetchAdminTrophies, grantTrophy } from "@/admin/api";
import {
  buyCollectibleWithCoins,
  claimGift,
  createGiftInvoice,
  fetchGiftInvoiceStatus,
  fetchGiftSets,
  fetchMyGifts,
  pinGift,
} from "@/api/gifts";
import { searchUsers } from "@/api/profile";
import PlayerCard from "@/components/cards/PlayerCard";
import EmptyState from "@/components/common/EmptyState";
import { UserBadge } from "@/components/common/UserBadge";
import { IconCoin, IconGift, IconInboxEmpty, IconSearch, IconTrophy } from "@/components/icons";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { hapticNotify, openTelegramInvoice, showConfirm } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Gift, GiftClaimResult, GiftSet, TrophyDefinition, UserPublic } from "@/types";

export default function GiftsPage() {
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"mine" | "shop">("mine");
  const [claimResult, setClaimResult] = useState<GiftClaimResult | null>(null);
  const [detailGift, setDetailGift] = useState<Gift | null>(null);

  const { data: myGifts } = useQuery({ queryKey: ["gifts", "mine"], queryFn: fetchMyGifts });

  const claimMutation = useMutation({
    mutationFn: claimGift,
    onSuccess: (data) => {
      hapticNotify("success");
      updateBalance(data.new_balance);
      setClaimResult(data);
      queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
    },
  });

  // Collectible gifts have no "open" ceremony — a random pack roll needs an
  // explicit claim tap, but a cosmetic collectible's reward *is* the row
  // existing, so silently mark any unclaimed one claimed the moment it shows
  // up, instead of making the player hunt for a button that isn't there.
  useEffect(() => {
    const pendingCollectibles = (myGifts ?? []).filter((g) => g.gift_set.kind === "collectible" && !g.claimed_at);
    if (pendingCollectibles.length === 0) return;
    Promise.allSettled(pendingCollectibles.map((g) => claimGift(g.id))).then(() => {
      queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
    });
  }, [myGifts, queryClient]);

  if (!user) return null;

  const collectibles = (myGifts ?? []).filter((g) => g.gift_set.kind === "collectible");
  const pendingBundles = (myGifts ?? []).filter((g) => g.gift_set.kind === "bundle" && !g.claimed_at);
  const claimedBundles = (myGifts ?? []).filter((g) => g.gift_set.kind === "bundle" && g.claimed_at);
  const isEmpty = collectibles.length === 0 && pendingBundles.length === 0 && claimedBundles.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconGift size={20} className="text-rarity-epic" />
        Подарки
      </h1>

      {user.is_admin && <AdminGiftControls />}

      <div className="flex gap-2 rounded-2xl bg-bg-surface p-1">
        <button
          onClick={() => setTab("mine")}
          className={`flex-1 rounded-xl py-2 text-sm font-semibold transition ${
            tab === "mine" ? "bg-floodlight text-bg-base" : "text-ink-mist"
          }`}
        >
          Мои подарки{pendingBundles.length > 0 ? ` (${pendingBundles.length})` : ""}
        </button>
        <button
          onClick={() => setTab("shop")}
          className={`flex-1 rounded-xl py-2 text-sm font-semibold transition ${
            tab === "shop" ? "bg-floodlight text-bg-base" : "text-ink-mist"
          }`}
        >
          Магазин подарков
        </button>
      </div>

      {tab === "mine" ? (
        isEmpty ? (
          <div className="flex flex-col gap-3">
            <button
              onClick={() => setTab("shop")}
              className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95"
            >
              Магазин подарков
            </button>
            <EmptyState icon={IconInboxEmpty} title="Подарков пока нет" description="Купи подарок себе или другу в магазине." />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {collectibles.length > 0 && (
              <div className="grid grid-cols-3 gap-2">
                {collectibles.map((g) => (
                  <button
                    key={g.id}
                    onClick={() => setDetailGift(g)}
                    className="flex flex-col items-center gap-1.5 rounded-2xl bg-bg-surface p-2.5 active:scale-[0.98]"
                  >
                    <span className="relative flex h-16 w-16 items-center justify-center overflow-hidden rounded-xl bg-rarity-epic/10">
                      {g.gift_set.image_path ? (
                        <img src={staticUrl(g.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
                      ) : (
                        <IconGift size={26} className="text-rarity-epic" />
                      )}
                      {g.is_pinned && (
                        <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-accent-lime text-[9px] font-bold text-bg-base">
                          ★
                        </span>
                      )}
                    </span>
                    <span className="w-full truncate text-center text-[11px] font-semibold text-ink-chalk">{g.gift_set.name}</span>
                  </button>
                ))}
              </div>
            )}

            {pendingBundles.length > 0 && (
              <div className="flex flex-col gap-2">
                {pendingBundles.map((g) => (
                  <div key={g.id} className="flex items-center justify-between rounded-2xl bg-bg-surface p-3">
                    <div className="flex items-center gap-3">
                      {g.gift_set.image_path ? (
                        <img src={staticUrl(g.gift_set.image_path) ?? undefined} className="h-12 w-12 rounded-xl object-cover" />
                      ) : (
                        <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-rarity-epic/10">
                          <IconGift size={22} className="text-rarity-epic" />
                        </span>
                      )}
                      <div>
                        <p className="text-sm font-semibold text-ink-chalk">{g.gift_set.name}</p>
                        <p className="text-xs text-ink-mist">
                          {g.sender ? `От ${g.sender.username ?? g.sender.first_name ?? "игрока"}` : "От администрации"}
                        </p>
                        {g.message && <p className="mt-0.5 text-xs italic text-ink-mist-dim">«{g.message}»</p>}
                      </div>
                    </div>
                    <button
                      onClick={() => claimMutation.mutate(g.id)}
                      disabled={claimMutation.isPending}
                      className="shrink-0 rounded-xl bg-floodlight px-3 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
                    >
                      Открыть
                    </button>
                  </div>
                ))}
              </div>
            )}

            {claimedBundles.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold text-ink-mist-dim">История</p>
                <div className="flex flex-col gap-1.5">
                  {claimedBundles.map((g) => (
                    <div key={g.id} className="flex items-center justify-between rounded-xl bg-bg-surface/60 px-3 py-2 text-xs">
                      <span className="text-ink-mist">{g.gift_set.name}</span>
                      <span className="text-ink-mist-dim">{new Date(g.claimed_at!).toLocaleDateString("ru-RU")}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      ) : (
        <ShopTab />
      )}

      {claimResult && <GiftClaimResultModal result={claimResult} onClose={() => setClaimResult(null)} />}
      {detailGift && <GiftDetailSheet gift={detailGift} onClose={() => setDetailGift(null)} />}
    </div>
  );
}

function GiftClaimResultModal({ result, onClose }: { result: GiftClaimResult; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" onClick={onClose}>
      <div className="w-full max-w-sm rounded-2xl bg-bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <p className="flex items-center justify-center gap-1.5 text-center font-display text-base font-bold text-ink-chalk">
          <IconGift size={18} className="text-rarity-epic" />
          Подарок открыт!
        </p>

        {result.coins_credited > 0 && (
          <div className="mt-3 flex items-center justify-center gap-1.5 rounded-xl bg-accent-green/10 py-2 font-mono text-sm font-bold text-accent-green">
            +{result.coins_credited} <IconCoin size={14} />
          </div>
        )}

        {result.pack_result && result.pack_result.cards.length > 0 && (
          <div className="mt-3 grid grid-cols-3 gap-2">
            {result.pack_result.cards.map((c) => (
              <PlayerCard key={c.card.id} player={c.card.player} size="sm" />
            ))}
          </div>
        )}

        <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
          Отлично!
        </button>
      </div>
    </div>
  );
}

function GiftDetailSheet({ gift, onClose }: { gift: Gift; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const pinMutation = useMutation({
    mutationFn: (pinned: boolean) => pinGift(gift.id, pinned),
    onSuccess: () => {
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось изменить закрепление"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" onClick={onClose}>
      <div className="w-full max-w-sm rounded-2xl bg-bg-surface p-5 text-center" onClick={(e) => e.stopPropagation()}>
        <span className="mx-auto flex h-24 w-24 items-center justify-center overflow-hidden rounded-2xl bg-rarity-epic/10">
          {gift.gift_set.image_path ? (
            <img src={staticUrl(gift.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
          ) : (
            <IconGift size={40} className="text-rarity-epic" />
          )}
        </span>
        <p className="mt-3 font-display text-base font-bold text-ink-chalk">{gift.gift_set.name}</p>
        <p className="mt-1 text-xs text-ink-mist">
          {gift.sender ? `От ${gift.sender.username ?? gift.sender.first_name ?? "игрока"}` : "От администрации"}
        </p>
        {gift.message && <p className="mt-1 text-xs italic text-ink-mist-dim">«{gift.message}»</p>}

        {error && <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

        <button
          onClick={() => pinMutation.mutate(!gift.is_pinned)}
          disabled={pinMutation.isPending}
          className="mt-4 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {gift.is_pinned ? "Открепить" : "Закрепить в профиле"}
        </button>
        <button onClick={onClose} className="mt-2 w-full rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
          Закрыть
        </button>
      </div>
    </div>
  );
}

function RecipientPicker({ target, onSelect }: { target: UserPublic | null; onSelect: (u: UserPublic | null) => void }) {
  const [query, setQuery] = useState("");
  const { data: results } = useQuery({
    queryKey: ["user-search", query],
    queryFn: () => searchUsers(query),
    enabled: query.length >= 2 && !target,
  });

  if (target) {
    return (
      <div className="flex items-center justify-between rounded-xl bg-black/20 px-3 py-2.5">
        <span className="flex items-center gap-1 text-sm text-ink-chalk">
          {target.username ?? target.first_name ?? `Игрок #${target.id}`}
          <UserBadge badge={target.active_badge} />
        </span>
        <button onClick={() => onSelect(null)} className="text-xs text-accent-lime">Сменить</button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Введи имя пользователя..."
        className="rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
      />
      {results && results.length > 0 && (
        <div className="flex flex-col gap-1">
          {results.map((u) => (
            <button
              key={u.id}
              onClick={() => onSelect(u)}
              className="flex items-center justify-between rounded-xl bg-black/20 px-3 py-2 text-left active:scale-[0.98]"
            >
              <span className="flex items-center gap-1 text-sm text-ink-chalk">
                {u.username ?? u.first_name ?? `Игрок #${u.id}`}
                <UserBadge badge={u.active_badge} />
              </span>
            </button>
          ))}
        </div>
      )}
      {query.length >= 2 && results?.length === 0 && (
        <EmptyState icon={IconSearch} title="Никого не найдено" />
      )}
    </div>
  );
}

function ShopTab() {
  const { data: giftSets } = useQuery({ queryKey: ["gift-sets"], queryFn: fetchGiftSets });
  const [selectedSet, setSelectedSet] = useState<GiftSet | null>(null);

  const bundleSets = (giftSets ?? []).filter((g) => g.kind === "bundle");
  const collectibleSets = (giftSets ?? []).filter((g) => g.kind === "collectible");

  if (selectedSet) {
    return <CollectiblePurchasePanel giftSet={selectedSet} onDone={() => setSelectedSet(null)} />;
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="mb-2 font-display text-sm font-bold text-ink-chalk">Наборы</p>
        {bundleSets.length > 0 ? (
          <BundleShop giftSets={bundleSets} />
        ) : (
          <EmptyState icon={IconGift} title="Наборов пока нет" description="Загляни позже — мы готовим подарки." />
        )}
      </div>
      <div>
        <p className="mb-2 font-display text-sm font-bold text-ink-chalk">Коллекционные</p>
        {collectibleSets.length > 0 ? (
          <div className="grid grid-cols-2 gap-2">
            {collectibleSets.map((g) => (
              <button
                key={g.id}
                onClick={() => setSelectedSet(g)}
                className="flex flex-col items-center gap-2 rounded-2xl bg-bg-surface p-3 text-center active:scale-[0.98]"
              >
                {g.image_path ? (
                  <img src={staticUrl(g.image_path) ?? undefined} className="h-16 w-16 rounded-xl object-cover" />
                ) : (
                  <span className="flex h-16 w-16 items-center justify-center rounded-xl bg-rarity-epic/10">
                    <IconGift size={28} className="text-rarity-epic" />
                  </span>
                )}
                <p className="text-sm font-semibold text-ink-chalk">{g.name}</p>
                <p className="flex items-center gap-2 font-mono text-xs font-bold text-accent-lime">
                  {!!g.coins_price && (
                    <span className="flex items-center gap-1">
                      <IconCoin size={11} />
                      {g.coins_price}
                    </span>
                  )}
                  {!!g.stars_price && <span>{g.stars_price} ⭐</span>}
                </p>
              </button>
            ))}
          </div>
        ) : (
          <EmptyState icon={IconGift} title="Коллекционных подарков пока нет" description="Загляни позже — мы готовим подарки." />
        )}
      </div>
    </div>
  );
}

function CollectiblePurchasePanel({ giftSet, onDone }: { giftSet: GiftSet; onDone: () => void }) {
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();
  const [recipientMode, setRecipientMode] = useState<"self" | "friend">("self");
  const [target, setTarget] = useState<UserPublic | null>(null);
  const [message, setMessage] = useState("");
  const [currency, setCurrency] = useState<"stars" | "coins">(giftSet.coins_price > 0 ? "coins" : "stars");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const recipientId = recipientMode === "self" ? user?.id : target?.id;

  const handleBuyWithCoins = async () => {
    if (!recipientId) return;
    setError(null);
    setBusy(true);
    try {
      const result = await buyCollectibleWithCoins(giftSet.id, recipientId, message || undefined);
      updateBalance(result.new_balance);
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Не удалось купить подарок");
    } finally {
      setBusy(false);
    }
  };

  const handleBuyWithStars = async () => {
    if (!recipientId) return;
    setError(null);
    setBusy(true);
    try {
      const invoice = await createGiftInvoice(giftSet.id, recipientId, message || undefined);
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") {
        setBusy(false);
        return;
      }
      if (paymentStatus === "failed") {
        setError("Платёж не прошёл");
        setBusy(false);
        return;
      }

      for (let attempt = 0; attempt < 20; attempt++) {
        const status = await fetchGiftInvoiceStatus(invoice.payload_token);
        if (status.status === "completed") {
          hapticNotify("success");
          queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
          setSuccess(true);
          setBusy(false);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Подарок ещё не отправлен — попробуй проверить через минуту");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : err instanceof Error ? err.message : "Не удалось отправить подарок");
      setBusy(false);
    }
  };

  const handleConfirm = () => (currency === "coins" ? handleBuyWithCoins() : handleBuyWithStars());

  if (success) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-bg-surface p-6 text-center">
        <IconGift size={32} className="text-rarity-epic" />
        <p className="font-display text-base font-bold text-ink-chalk">Подарок отправлен!</p>
        <button onClick={onDone} className="mt-2 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
          Готово
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink-chalk">{giftSet.name}</p>
        <button onClick={onDone} className="text-xs text-accent-lime">Назад</button>
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="flex gap-2 rounded-xl bg-black/20 p-1">
        <button
          onClick={() => { setRecipientMode("self"); setTarget(null); }}
          className={`flex-1 rounded-lg py-2 text-xs font-semibold ${recipientMode === "self" ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
        >
          Себе
        </button>
        <button
          onClick={() => setRecipientMode("friend")}
          className={`flex-1 rounded-lg py-2 text-xs font-semibold ${recipientMode === "friend" ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
        >
          Другу
        </button>
      </div>

      {recipientMode === "friend" && <RecipientPicker target={target} onSelect={setTarget} />}

      <input
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        maxLength={500}
        placeholder="Поздравительная надпись (необязательно)"
        className="rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
      />

      {giftSet.stars_price > 0 && giftSet.coins_price > 0 && (
        <div className="flex gap-2 rounded-xl bg-black/20 p-1">
          <button
            onClick={() => setCurrency("coins")}
            className={`flex flex-1 items-center justify-center gap-1 rounded-lg py-2 text-xs font-semibold ${currency === "coins" ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            <IconCoin size={12} />
            {giftSet.coins_price}
          </button>
          <button
            onClick={() => setCurrency("stars")}
            className={`flex-1 rounded-lg py-2 text-xs font-semibold ${currency === "stars" ? "bg-amber-400 text-bg-base" : "text-ink-mist"}`}
          >
            {giftSet.stars_price} ⭐
          </button>
        </div>
      )}

      <button
        onClick={handleConfirm}
        disabled={(recipientMode === "friend" && !target) || busy}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {busy ? "Отправка..." : `Отправить за ${currency === "coins" ? `${giftSet.coins_price} монет` : `${giftSet.stars_price} ⭐`}`}
      </button>
    </div>
  );
}

function BundleShop({ giftSets }: { giftSets: GiftSet[] }) {
  const [selectedSet, setSelectedSet] = useState<GiftSet | null>(null);
  const [target, setTarget] = useState<UserPublic | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSend = async () => {
    if (!selectedSet || !target) return;
    setError(null);
    setBusy(true);
    try {
      const invoice = await createGiftInvoice(selectedSet.id, target.id, message || undefined);
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") {
        setBusy(false);
        return;
      }
      if (paymentStatus === "failed") {
        setError("Платёж не прошёл");
        setBusy(false);
        return;
      }

      for (let attempt = 0; attempt < 20; attempt++) {
        const status = await fetchGiftInvoiceStatus(invoice.payload_token);
        if (status.status === "completed") {
          hapticNotify("success");
          setSuccess(true);
          setBusy(false);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Подарок ещё не отправлен — попробуй проверить через минуту");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : err instanceof Error ? err.message : "Не удалось отправить подарок");
      setBusy(false);
    }
  };

  if (success) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-bg-surface p-6 text-center">
        <IconGift size={32} className="text-rarity-epic" />
        <p className="font-display text-base font-bold text-ink-chalk">Подарок отправлен!</p>
        <p className="text-sm text-ink-mist">{target?.username ?? target?.first_name} сможет открыть его в своём профиле.</p>
        <button
          onClick={() => { setSuccess(false); setSelectedSet(null); setTarget(null); setMessage(""); }}
          className="mt-2 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95"
        >
          Отправить ещё один
        </button>
      </div>
    );
  }

  if (!selectedSet) {
    return (
      <div className="grid grid-cols-2 gap-2">
        {giftSets.map((g) => (
          <button
            key={g.id}
            onClick={() => setSelectedSet(g)}
            className="flex flex-col items-center gap-2 rounded-2xl bg-bg-surface p-3 text-center active:scale-[0.98]"
          >
            {g.image_path ? (
              <img src={staticUrl(g.image_path) ?? undefined} className="h-16 w-16 rounded-xl object-cover" />
            ) : (
              <span className="flex h-16 w-16 items-center justify-center rounded-xl bg-rarity-epic/10">
                <IconGift size={28} className="text-rarity-epic" />
              </span>
            )}
            <p className="text-sm font-semibold text-ink-chalk">{g.name}</p>
            <p className="font-mono text-xs font-bold text-accent-lime">{g.stars_price} ⭐</p>
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink-chalk">{selectedSet.name}</p>
        <button onClick={() => setSelectedSet(null)} className="text-xs text-accent-lime">Сменить набор</button>
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <RecipientPicker target={target} onSelect={setTarget} />

      <input
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        maxLength={500}
        placeholder="Поздравительная надпись (необязательно)"
        className="rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
      />

      <button
        onClick={handleSend}
        disabled={!target || busy}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {busy ? "Отправка..." : `Отправить за ${selectedSet.stars_price} ⭐`}
      </button>
    </div>
  );
}

function AdminGiftControls() {
  const queryClient = useQueryClient();
  const { data: giftSets } = useQuery({ queryKey: ["gift-sets"], queryFn: fetchGiftSets });
  const { data: trophies } = useQuery({ queryKey: ["admin-trophies"], queryFn: fetchAdminTrophies });
  const [action, setAction] = useState<"send" | "broadcast" | "trophy" | null>(null);
  const [giftSetId, setGiftSetId] = useState<number | "">("");
  const [trophyId, setTrophyId] = useState<number | "">("");
  const [target, setTarget] = useState<UserPublic | null>(null);
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => { setGiftSetId(""); setTrophyId(""); setTarget(null); setMessage(""); setError(null); };

  const sendMutation = useMutation({
    mutationFn: () => adminSendGift(Number(giftSetId), target!.id, message || undefined),
    onSuccess: () => { setNotice("Подарок отправлен игроку"); reset(); setAction(null); queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] }); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось отправить подарок"),
  });

  const broadcastMutation = useMutation({
    mutationFn: () => adminBroadcastGift(Number(giftSetId), message || undefined),
    onSuccess: (data) => { setNotice(`Подарок разослан ${data.recipients} игрокам`); reset(); setAction(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось разослать подарок"),
  });

  const trophyMutation = useMutation({
    mutationFn: () => grantTrophy(target!.id, Number(trophyId), message || undefined),
    onSuccess: () => { setNotice("Трофей вручён"); reset(); setAction(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось вручить трофей"),
  });

  return (
    <div className="rounded-2xl border border-rarity-epic/30 bg-rarity-epic/5 p-4">
      <p className="flex items-center gap-1.5 font-display text-sm font-bold text-ink-chalk">
        <IconTrophy size={15} className="text-rarity-epic" />
        Админ-инструменты
      </p>
      {notice && <p className="mt-2 rounded-xl bg-accent-green/10 px-3 py-2 text-xs text-accent-green">{notice}</p>}

      <div className="mt-3 flex flex-wrap gap-2">
        <button onClick={() => { setAction(action === "send" ? null : "send"); reset(); setNotice(null); }} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${action === "send" ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}>
          Отправить игроку
        </button>
        <button onClick={() => { setAction(action === "broadcast" ? null : "broadcast"); reset(); setNotice(null); }} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${action === "broadcast" ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}>
          Разослать всем
        </button>
        <button onClick={() => { setAction(action === "trophy" ? null : "trophy"); reset(); setNotice(null); }} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${action === "trophy" ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}>
          Подарить трофей
        </button>
      </div>

      {action && (
        <div className="mt-3 flex flex-col gap-2">
          {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

          {action !== "trophy" && (
            <select
              value={giftSetId}
              onChange={(e) => setGiftSetId(e.target.value ? Number(e.target.value) : "")}
              className="rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk outline-none"
            >
              <option value="">Выбери набор...</option>
              {giftSets?.map((g) => (
                <option key={g.id} value={g.id}>{g.name}{g.kind === "collectible" ? " (коллекционный)" : ""}</option>
              ))}
            </select>
          )}

          {action === "trophy" && (
            <select
              value={trophyId}
              onChange={(e) => setTrophyId(e.target.value ? Number(e.target.value) : "")}
              className="rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk outline-none"
            >
              <option value="">Выбери трофей...</option>
              {trophies?.map((t: TrophyDefinition) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          )}

          {action !== "broadcast" && <RecipientPicker target={target} onSelect={setTarget} />}

          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={500}
            rows={4}
            placeholder="Подпись (необязательно) — переносы строк и HTML-теги (например <blockquote>) сохраняются как есть"
            className="resize-y rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
          />

          {action === "send" && (
            <button
              onClick={() => sendMutation.mutate()}
              disabled={!giftSetId || !target || sendMutation.isPending}
              className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
            >
              Отправить бесплатно
            </button>
          )}
          {action === "broadcast" && (
            <button
              onClick={async () => {
                if (await showConfirm("Разослать этот набор бесплатно всем зарегистрированным игрокам?")) broadcastMutation.mutate();
              }}
              disabled={!giftSetId || broadcastMutation.isPending}
              className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
            >
              Разослать всем
            </button>
          )}
          {action === "trophy" && (
            <button
              onClick={() => trophyMutation.mutate()}
              disabled={!trophyId || !target || trophyMutation.isPending}
              className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
            >
              Вручить трофей
            </button>
          )}
        </div>
      )}
    </div>
  );
}
