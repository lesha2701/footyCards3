import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { adminBroadcastGift, adminSendGift, fetchAdminTrophies, grantTrophy } from "@/admin/api";
import {
  buyCollectibleWithCoins,
  claimGift,
  createGiftInvoice,
  createGiftTransferInvoice,
  fetchGiftHistory,
  fetchGiftInvoiceStatus,
  fetchGiftLeaderboard,
  fetchGiftTransferPrice,
  markGiftTransfersSeen,
  fetchGiftSets,
  fetchMyGifts,
  pinGift,
} from "@/api/gifts";
import { fetchShopInvoiceStatus } from "@/api/monetization";
import { searchUsers } from "@/api/profile";
import PlayerCard from "@/components/cards/PlayerCard";
import SkillTokenTile from "@/components/cards/SkillTokenTile";
import EmptyState from "@/components/common/EmptyState";
import { UserBadge } from "@/components/common/UserBadge";
import InfoTile from "@/components/shop/InfoTile";
import { IconCoin, IconGift, IconInboxEmpty, IconSearch, IconTrophy } from "@/components/icons";
import RewardModal, { RewardCoins } from "@/components/common/RewardModal";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { SPECIAL_LABELS, specialSerial } from "@/lib/giftSerial";
import { filterBySerial, giftsWord, sortCopies, stackGifts, type CopySort, type GiftStack } from "@/lib/giftStacks";
import { RARITY_LABELS } from "@/lib/rarity";
import { hapticNotify, openTelegramInvoice, showConfirm } from "@/lib/telegram";
import { useOpenTile } from "@/lib/useOpenTile";
import { useAuthStore } from "@/store/authStore";
import type { Gift, GiftClaimResult, GiftLeaderRow, GiftSet, TrophyDefinition, UserPublic } from "@/types";

/** «Подарить» on someone's profile opens this page with that player
 * already picked as the recipient (router state `giftTo`). */
function usePresetRecipient(): UserPublic | null {
  const state = useLocation().state as { giftTo?: UserPublic } | null;
  return state?.giftTo ?? null;
}

export default function GiftsPage() {
  const presetTo = usePresetRecipient();
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"mine" | "shop" | "top">(presetTo ? "shop" : "mine");
  const [claimResult, setClaimResult] = useState<GiftClaimResult | null>(null);
  const [detailGift, setDetailGift] = useState<Gift | null>(null);
  const [openStackId, setOpenStackId] = useState<number | null>(null);

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

  if (!user) return null;

  // Both gift kinds now share the same pending -> claim -> reveal lifecycle:
  // a collectible with no configured prize just claims with nothing granted,
  // one with coins/pack configured grants it exactly like a bundle does.
  const collectibles = (myGifts ?? []).filter((g) => g.gift_set.kind === "collectible" && !!g.claimed_at);
  const pendingGifts = (myGifts ?? []).filter((g) => !g.claimed_at);
  const claimedBundles = (myGifts ?? []).filter((g) => g.gift_set.kind === "bundle" && g.claimed_at);
  const stacks = stackGifts(collectibles);
  const unseen = collectibles.filter((g) => g.transfer_unseen);
  const markSeen = () => {
    queryClient.setQueryData<Gift[]>(["gifts", "mine"], (old) => old?.map((g) => ({ ...g, transfer_unseen: false })));
    markGiftTransfersSeen().catch(() => undefined);
  };
  const openStack = stacks.find((s) => s.setId === openStackId) ?? null;
  const isEmpty = collectibles.length === 0 && pendingGifts.length === 0 && claimedBundles.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconGift size={20} className="text-rarity-epic" />
        Подарки
      </h1>

      {user.is_admin && <AdminGiftControls />}

      {presetTo && (
        <p className="rounded-2xl bg-rarity-epic/15 px-4 py-3 text-sm text-fuchsia-100" data-testid="gift-preset">
          🎁 Подарок для <b>{presetTo.first_name ?? presetTo.username ?? "игрока"}</b>: выбери новый в магазине или передай свой из «Мои».
        </p>
      )}

      <div className="grid grid-cols-3 gap-1 rounded-2xl bg-bg-surface p-1">
        {([
          ["mine", `Мои${pendingGifts.length > 0 ? ` (${pendingGifts.length})` : ""}`],
          ["shop", "Магазин"],
          ["top", "Коллекционеры"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`truncate rounded-xl px-1 py-2 text-xs font-semibold transition ${
              tab === key ? "bg-floodlight text-bg-base" : "text-ink-mist"
            }`}
          >
            {label}
          </button>
        ))}
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
            {stacks.length > 0 && (
              <div className="grid grid-cols-3 gap-2">
                {stacks.map((s) => (
                  <GiftStackTile
                    key={s.setId}
                    stack={s}
                    onClick={() => (s.copies.length === 1 ? setDetailGift(s.copies[0]) : setOpenStackId(s.setId))}
                  />
                ))}
              </div>
            )}

            {pendingGifts.length > 0 && (
              <div className="flex flex-col gap-2">
                {pendingGifts.map((g) => (
                  <div key={g.id} className="flex items-center justify-between rounded-2xl bg-bg-surface p-3">
                    <div className="flex items-center gap-3">
                      {g.gift_set.image_path ? (
                        <img decoding="async" loading="lazy" src={staticUrl(g.gift_set.image_path) ?? undefined} className="h-12 w-12 rounded-xl object-cover" />
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
      ) : tab === "shop" ? (
        <GiftShop />
      ) : (
        <GiftCollectors />
      )}

      {unseen.length > 0 && !claimResult && <ReceivedGiftsModal gifts={unseen} onClose={markSeen} />}
      {claimResult && <GiftClaimResultModal result={claimResult} onClose={() => setClaimResult(null)} />}
      {openStack && !detailGift && (
        <GiftStackSheet stack={openStack} onPick={setDetailGift} onClose={() => setOpenStackId(null)} />
      )}
      {detailGift && <GiftDetailSheet gift={detailGift} onClose={() => setDetailGift(null)} />}
    </div>
  );
}

function GiftClaimResultModal({ result, onClose }: { result: GiftClaimResult; onClose: () => void }) {
  const isCollectible = result.gift.gift_set.kind === "collectible";
  const packCards = result.pack_result?.cards ?? [];
  const topRarity = packCards.some((c) => c.card.player.rarity === "diamond")
    ? "diamond"
    : packCards.some((c) => c.card.player.rarity === "legendary") ? "legendary" : null;
  const items = [
    result.coins_credited > 0 && <RewardCoins key="coins" amount={result.coins_credited} />,
    result.pack_result && (
      result.pack_result.cards.length > 0 || result.pack_result.coach_cards.length > 0
      || result.pack_result.stadium_cards.length > 0 || (result.pack_result.skill_tokens ?? []).length > 0
    ) && (
      <div key="pack" className="w-full">
        <div className="grid grid-cols-3 gap-2">
          {result.pack_result.cards.map((c) => (
            <PlayerCard key={c.card.id} player={c.card.player} size="sm" />
          ))}
          {result.pack_result.coach_cards.map((c) => (
            <div key={`coach-${c.card.id}`} className="flex flex-col items-center gap-1.5 overflow-hidden rounded-2xl bg-rarity-epic/10 p-2">
              <span className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-xl bg-black/20">
                <img decoding="async" loading="lazy"
                  src={staticUrl(c.card.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                  alt={c.card.coach.display_name}
                  className="h-full w-full object-cover"
                />
              </span>
              <p className="w-full truncate text-center text-caption font-semibold text-ink-chalk">{c.card.coach.display_name}</p>
              <p className="text-micro text-ink-mist">Тренер · {RARITY_LABELS[c.card.coach.rarity]}</p>
            </div>
          ))}
          {(result.pack_result.skill_tokens ?? []).map((token, i) => (
            <SkillTokenTile key={`token-${i}`} skillCode={token.skill_code} quantity={token.quantity} />
          ))}
          {result.pack_result.stadium_cards.map((c) => (
            <div key={`stadium-${c.card.id}`} className="flex flex-col items-center gap-1.5 overflow-hidden rounded-2xl bg-rarity-epic/10 p-2">
              <span className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-xl bg-black/20">
                <img decoding="async" loading="lazy"
                  src={staticUrl(c.card.stadium.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                  alt={c.card.stadium.display_name}
                  className="h-full w-full object-cover"
                />
              </span>
              <p className="w-full truncate text-center text-caption font-semibold text-ink-chalk">{c.card.stadium.display_name}</p>
              <p className="text-micro text-ink-mist">Стадион · +{Math.round(c.card.stadium.boost_pct * 100)}%</p>
            </div>
          ))}
        </div>
      </div>
    ),
  ].filter(Boolean) as JSX.Element[];
  return (
    <RewardModal
      title={isCollectible ? result.gift.gift_set.name : "Подарок открыт!"}
      subtitle={
        isCollectible && result.gift.serial_number != null
          ? `№${result.gift.serial_number}${result.gift.gift_set.max_supply ? ` из ${result.gift.gift_set.max_supply}` : ""}`
          : undefined
      }
      icon={<IconGift size={30} />}
      hero={
        isCollectible ? (
          <span className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-2xl bg-rarity-epic/10">
            {result.gift.gift_set.image_path ? (
              <img decoding="async" src={staticUrl(result.gift.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
            ) : (
              <IconGift size={32} className="text-rarity-epic" />
            )}
          </span>
        ) : undefined
      }
      rarity={topRarity}
      items={items}
      onClose={onClose}
    />
  );
}

function GiftImage({ gift, size }: { gift: Gift; size: string }) {
  return (
    <span className={`flex ${size} shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-rarity-epic/10`}>
      {gift.gift_set.image_path ? (
        <img decoding="async" loading="lazy" src={staticUrl(gift.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
      ) : (
        <IconGift size={32} className="text-rarity-epic" />
      )}
    </span>
  );
}

/** «Особый номер»: a gold chip with its name. */
function SpecialChip({ serial }: { serial: number | null }) {
  const code = specialSerial(serial);
  if (!code) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-300/20 px-2 py-0.5 text-micro font-bold text-amber-200">
      ✨ {SPECIAL_LABELS[code]} номер
    </span>
  );
}

function editionLine(gift: Gift): string {
  const issued = Math.max(0, gift.gift_set.next_serial_number - 1);
  return gift.gift_set.max_supply ? `Выпущено ${issued} из ${gift.gift_set.max_supply}` : `Выпущено ${issued}`;
}

function personName(u: UserPublic | null | undefined): string {
  if (!u) return "администрация";
  return u.username ?? u.first_name ?? `игрок #${u.id}`;
}

function GiftDetailSheet({ gift, onClose }: { gift: Gift; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const { data: history } = useQuery({
    queryKey: ["gifts", "history", gift.id],
    queryFn: () => fetchGiftHistory(gift.id),
    enabled: showHistory,
  });

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
      <div className="max-h-[90vh] w-full max-w-sm overflow-y-auto rounded-2xl bg-bg-surface p-5 text-center" onClick={(e) => e.stopPropagation()}>
        <div className={`mx-auto w-fit rounded-2xl ${specialSerial(gift.serial_number) ? "ring-2 ring-amber-300/70 shadow-[0_0_24px_rgba(252,211,77,0.35)]" : ""}`}>
          <GiftImage gift={gift} size="h-24 w-24" />
        </div>
        <p className="mt-3 font-display text-base font-bold text-ink-chalk">{gift.gift_set.name}</p>
        {gift.serial_number != null && (
          <p className="mt-1 font-mono text-xs text-accent-lime">
            №{gift.serial_number}
            {gift.gift_set.max_supply ? ` из ${gift.gift_set.max_supply}` : ""}
          </p>
        )}
        <div className="mt-1"><SpecialChip serial={gift.serial_number} /></div>
        <p className="mt-1 text-micro text-ink-mist-dim">{editionLine(gift)}</p>
        <p className="mt-1 text-xs text-ink-mist">
          {gift.sender ? `От ${personName(gift.sender)}` : "От администрации"}
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
        <GiftTransfer gifts={[gift]} onDone={onClose} />

        <button
          onClick={() => setShowHistory((v) => !v)}
          className="mt-2 w-full rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-chalk active:scale-95"
          data-testid="gift-history-toggle"
        >
          📜 История копии
        </button>
        {showHistory && (
          <ol className="mt-2 flex flex-col gap-1.5 text-left" data-testid="gift-history">
            {(history?.entries ?? []).map((e, idx) => (
              <li key={idx} className="flex gap-2 rounded-xl bg-black/20 px-3 py-2 text-xs">
                <span className="mt-0.5">{e.kind === "issued" ? "🏷" : "🎁"}</span>
                <span className="min-w-0 flex-1">
                  <span className="text-ink-chalk">
                    {e.kind === "issued"
                      ? `Выпущен · ${e.from_user ? `подарок от ${personName(e.from_user)}` : "от администрации"} → ${personName(e.to_user)}`
                      : `${personName(e.from_user)} → ${personName(e.to_user)}`}
                  </span>
                  {e.message && <span className="block italic text-ink-mist-dim">«{e.message}»</span>}
                  <span className="block text-micro text-ink-mist-dim">{new Date(e.at).toLocaleDateString("ru-RU")}</span>
                </span>
              </li>
            ))}
            {!history && <li className="text-xs text-ink-mist">Загрузка…</li>}
          </ol>
        )}
        <button onClick={onClose} className="mt-2 w-full rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
          Закрыть
        </button>
      </div>
    </div>
  );
}

function GiftStackTile({ stack, onClick }: { stack: GiftStack; onClick: () => void }) {
  const first = stack.copies[0];
  const count = stack.copies.length;
  return (
    <button
      onClick={onClick}
      className="relative flex flex-col items-center gap-1.5 rounded-2xl bg-bg-surface p-2.5 active:scale-[0.98]"
      data-testid="gift-stack"
    >
      {count > 1 && (
        <>
          <span aria-hidden className="absolute inset-x-3 -top-1 h-2 rounded-t-xl bg-bg-surface/60" />
          <span aria-hidden className="absolute inset-x-5 -top-2 h-2 rounded-t-xl bg-bg-surface/30" />
        </>
      )}
      <span
        className={`relative flex h-16 w-16 items-center justify-center overflow-hidden rounded-xl bg-rarity-epic/10 ${
          stack.special > 0 ? "ring-2 ring-amber-300/60" : ""
        }`}
      >
        {first.gift_set.image_path ? (
          <img decoding="async" loading="lazy" src={staticUrl(first.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
        ) : (
          <IconGift size={26} className="text-rarity-epic" />
        )}
        {stack.pinned && (
          <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-accent-lime text-micro font-bold text-bg-base">
            ★
          </span>
        )}
      </span>
      {count > 1 && (
        <span className="absolute left-1.5 top-1.5 rounded-full bg-floodlight px-1.5 py-0.5 font-mono text-micro font-bold text-bg-base">
          ×{count}
        </span>
      )}
      <span className="w-full truncate text-center text-caption font-semibold text-ink-chalk">{first.gift_set.name}</span>
      {count === 1 && first.serial_number != null ? (
        <span className={`font-mono text-micro ${specialSerial(first.serial_number) ? "text-amber-200" : "text-ink-mist-dim"}`}>
          №{first.serial_number}
        </span>
      ) : count > 1 ? (
        <span className="text-micro text-ink-mist-dim">
          {count} шт.{stack.special > 0 && <span className="text-amber-200"> · ✨{stack.special}</span>}
        </span>
      ) : null}
    </button>
  );
}

/** The numbered copies of one stack: find a serial, sort the rarest first,
 * pick one copy — or several to pass on at once. */
function GiftStackSheet({ stack, onPick, onClose }: { stack: GiftStack; onPick: (g: Gift) => void; onClose: () => void }) {
  const first = stack.copies[0];
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<CopySort>("serial");
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<number[]>([]);
  const [sending, setSending] = useState(false);
  const shown = filterBySerial(sortCopies(stack.copies, sort), query);
  const pickedGifts = stack.copies.filter((g) => picked.includes(g.id));
  const toggle = (g: Gift) =>
    setPicked((ids) => (ids.includes(g.id) ? ids.filter((i) => i !== g.id) : ids.length >= 50 ? ids : [...ids, g.id]));

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 sm:items-center" onClick={onClose}>
      <div
        className="flex max-h-[85vh] w-full max-w-sm flex-col rounded-t-3xl bg-bg-surface p-5 sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="gift-stack-sheet"
      >
        <div className="flex items-center gap-3">
          <GiftImage gift={first} size="h-14 w-14" />
          <div className="min-w-0">
            <p className="truncate font-display text-base font-bold text-ink-chalk">{first.gift_set.name}</p>
            <p className="text-xs text-ink-mist">
              У тебя {stack.copies.length} шт.{stack.special > 0 ? ` · ✨ особых: ${stack.special}` : ""}
            </p>
            <p className="text-micro text-ink-mist-dim">{editionLine(first)}</p>
          </div>
        </div>

        {sending ? (
          <div className="mt-3 overflow-y-auto">
            <GiftTransfer gifts={pickedGifts} startOpen onDone={onClose} />
            <button onClick={() => setSending(false)} className="mt-2 w-full text-xs text-ink-mist">← Назад к выбору</button>
          </div>
        ) : (
          <>
            <div className="mt-3 flex gap-2">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                inputMode="numeric"
                placeholder="Найти №…"
                className="min-w-0 flex-1 rounded-xl bg-black/25 px-3 py-2 text-sm text-ink-chalk outline-none placeholder:text-ink-mist-dim"
                data-testid="gift-serial-search"
              />
              <button
                onClick={() => setSort(sort === "serial" ? "special" : "serial")}
                className={`shrink-0 rounded-xl px-3 py-2 text-xs font-bold ${sort === "special" ? "bg-amber-300/20 text-amber-200" : "bg-black/25 text-ink-mist"}`}
                data-testid="gift-sort-special"
              >
                {sort === "special" ? "✨ Особые" : "По номеру"}
              </button>
            </div>
            <button
              onClick={() => { setSelecting(!selecting); setPicked([]); }}
              className={`mt-2 rounded-xl py-2 text-xs font-semibold ${selecting ? "bg-floodlight/20 text-accent-lime" : "bg-black/20 text-ink-mist"}`}
              data-testid="gift-select-many"
            >
              {selecting ? "Отменить выбор" : "☑ Выбрать несколько, чтобы подарить"}
            </button>
            <div className="mt-3 grid grid-cols-4 gap-2 overflow-y-auto pb-1">
              {shown.map((g) => {
                const special = specialSerial(g.serial_number);
                const on = picked.includes(g.id);
                return (
                  <button
                    key={g.id}
                    onClick={() => (selecting ? toggle(g) : onPick(g))}
                    title={special ? SPECIAL_LABELS[special] : undefined}
                    className={`relative rounded-xl px-1 py-2.5 font-mono text-xs font-bold active:scale-95 ${
                      on
                        ? "bg-floodlight text-bg-base"
                        : special
                          ? "bg-amber-300/20 text-amber-200 ring-1 ring-amber-300/50"
                          : g.is_pinned
                            ? "bg-accent-lime/20 text-accent-lime"
                            : "bg-black/25 text-ink-chalk"
                    }`}
                  >
                    №{g.serial_number ?? "—"}
                    {g.is_pinned && <span className="absolute right-1 top-0.5 text-micro">★</span>}
                    {special && !on && <span className="absolute left-1 top-0.5 text-micro">✨</span>}
                  </button>
                );
              })}
              {shown.length === 0 && <p className="col-span-4 py-4 text-center text-xs text-ink-mist">Такого номера нет</p>}
            </div>
            {selecting && (
              <button
                onClick={() => setSending(true)}
                disabled={picked.length === 0}
                className="mt-3 w-full rounded-2xl bg-amber-300/20 py-2.5 text-sm font-bold text-amber-200 active:scale-95 disabled:opacity-40"
                data-testid="gift-send-picked"
              >
                🎁 Подарить выбранные ({picked.length})
              </button>
            )}
          </>
        )}
        <button onClick={onClose} className="mt-3 w-full rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
          Закрыть
        </button>
      </div>
    </div>
  );
}

/** «Подарить другу»: these exact numbered copies go to another player with an
 * optional note — Stars only, the price per copy. */
function GiftTransfer({ gifts, onDone, startOpen = false }: { gifts: Gift[]; onDone: () => void; startOpen?: boolean }) {
  const queryClient = useQueryClient();
  const { data: price } = useQuery({ queryKey: ["gifts", "transfer-price"], queryFn: fetchGiftTransferPrice });
  const [open, setOpen] = useState(startOpen);
  const [target, setTarget] = useState<UserPublic | null>(usePresetRecipient());
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const total = price ? price.stars * gifts.length : null;
  const serials = gifts.map((g) => `№${g.serial_number}`).join(", ");

  const send = async () => {
    if (!target || gifts.length === 0) return;
    setError(null);
    setBusy(true);
    try {
      const invoice = await createGiftTransferInvoice(gifts.map((g) => g.id), target.id, message.trim() || undefined);
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link, invoice.payload_token);
      if (paymentStatus === "cancelled") return;
      if (paymentStatus === "failed") {
        setError("Платёж не прошёл");
        return;
      }
      for (let attempt = 0; attempt < 20; attempt++) {
        const status = await fetchShopInvoiceStatus(invoice.payload_token);
        if (status.status === "completed") {
          hapticNotify("success");
          setSentTo(personName(target));
          queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Подарок ещё не передан — проверь через минуту");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : err instanceof Error ? err.message : "Не удалось передать подарок");
    } finally {
      setBusy(false);
    }
  };

  if (sentTo) {
    return (
      <div className="mt-3 rounded-2xl bg-accent-lime/10 p-3 text-sm text-accent-lime">
        {gifts.length === 1 ? `Подарок №${gifts[0].serial_number} передан` : `${giftsWord(gifts.length)} — переданы`}: {sentTo}
        <button onClick={onDone} className="mt-2 block w-full rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-mist">
          Готово
        </button>
      </div>
    );
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-2 w-full rounded-2xl bg-amber-300/15 py-2.5 text-sm font-bold text-amber-200 active:scale-95"
        data-testid="gift-transfer-open"
      >
        🎁 Подарить другу{price ? ` · ${price.stars} ⭐` : ""}
      </button>
    );
  }

  return (
    <div className="mt-3 flex flex-col gap-2 rounded-2xl bg-black/20 p-3 text-left" data-testid="gift-transfer">
      <p className="text-xs text-ink-mist">
        {gifts.length === 1 ? `Копия ${serials}` : `${giftsWord(gifts.length)} (${serials})`} {gifts.length === 1 ? "перейдёт" : "перейдут"} к выбранному игроку.
        Передача — только за звёзды{price ? `, ${price.stars} ⭐ за копию` : ""}.
      </p>
      <RecipientPicker target={target} onSelect={setTarget} />
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value.slice(0, 200))}
        rows={2}
        placeholder="Открытка к подарку (необязательно)"
        className="resize-none rounded-xl bg-black/20 px-3 py-2 text-sm text-ink-chalk outline-none placeholder:text-ink-mist-dim"
        data-testid="gift-transfer-note"
      />
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      <button
        onClick={send}
        disabled={!target || busy || total == null || gifts.length === 0}
        className="w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {busy ? "Передаём…" : `Передать за ${total ?? "…"} ⭐`}
      </button>
    </div>
  );
}

/** Copies another player passed on, shown once with an unwrapping. */
function ReceivedGiftsModal({ gifts, onClose }: { gifts: Gift[]; onClose: () => void }) {
  const first = gifts[0];
  const notes = [...new Set(gifts.map((g) => g.message).filter(Boolean))] as string[];
  return (
    <RewardModal
      title={gifts.length === 1 ? "Тебе передали подарок!" : `Тебе передали ${giftsWord(gifts.length)}!`}
      subtitle={`от ${personName(first.sender)}`}
      hero={<GiftImage gift={first} size="h-20 w-20" />}
      rarity={gifts.some((g) => specialSerial(g.serial_number)) ? "legendary" : null}
      items={[
        <div key="list" className="flex w-full flex-col gap-2" data-testid="received-gifts">
          <div className="flex flex-wrap justify-center gap-1.5">
            {gifts.slice(0, 12).map((g) => (
              <span
                key={g.id}
                className={`rounded-full px-2 py-1 font-mono text-xs font-bold ${
                  specialSerial(g.serial_number) ? "bg-amber-300/20 text-amber-200" : "bg-white/10 text-ink-chalk"
                }`}
              >
                {g.gift_set.name} №{g.serial_number}
              </span>
            ))}
            {gifts.length > 12 && <span className="text-xs text-ink-mist">и ещё {gifts.length - 12}</span>}
          </div>
          {notes.map((n) => (
            <p key={n} className="rounded-xl bg-white/5 px-3 py-2 text-center text-sm italic text-ink-chalk">✉️ «{n}»</p>
          ))}
        </div>,
      ]}
      buttonLabel="В коллекцию!"
      onClose={onClose}
    />
  );
}

/** «Коллекционеры»: who has the most different gifts and special serials. */
function GiftCollectors() {
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["gifts", "leaderboard"], queryFn: fetchGiftLeaderboard });
  if (!data) return <p className="py-6 text-center text-sm text-ink-mist">Загрузка…</p>;
  if (data.rows.length === 0) return <EmptyState icon={IconTrophy} title="Пока никто не собирает подарки" />;
  const row = (r: GiftLeaderRow, mine: boolean) => (
    <button
      key={`${mine ? "me" : "row"}-${r.user.id}`}
      onClick={() => navigate(`/users/${r.user.id}`)}
      className={`flex items-center gap-3 rounded-2xl px-3 py-2.5 text-left active:scale-[0.99] ${mine ? "bg-floodlight/15" : "bg-bg-surface"}`}
    >
      <span className={`w-7 text-center font-mono text-sm font-bold ${r.place <= 3 ? "text-amber-200" : "text-ink-mist"}`}>
        {r.place <= 3 ? ["🥇", "🥈", "🥉"][r.place - 1] : r.place}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1 truncate text-sm font-semibold text-ink-chalk">
          {personName(r.user)}
          <UserBadge badge={r.user.active_badge} />
        </span>
        <span className="text-micro text-ink-mist">
          {r.copies} шт.{r.special > 0 && <span className="text-amber-200"> · ✨ особых {r.special}</span>}
        </span>
      </span>
      <span className="text-right">
        <span className="block font-mono text-base font-bold text-ink-chalk">{r.sets}</span>
        <span className="text-micro text-ink-mist-dim">разных</span>
      </span>
    </button>
  );
  const meShown = data.me && data.rows.some((r) => r.user.id === data.me!.user.id);
  return (
    <div className="flex flex-col gap-2" data-testid="gift-collectors">
      <p className="text-xs text-ink-mist">
        Место — по числу разных коллекционных подарков, при равенстве — по числу копий. ✨ Особые номера: №1, 7/77/777,
        10/100/1000, одинаковые цифры, круглые сотни и зеркальные.
      </p>
      {data.rows.map((r) => row(r, r.user.id === data.me?.user.id))}
      {data.me && !meShown && (
        <>
          <p className="text-center text-micro text-ink-mist-dim">···</p>
          {row(data.me, true)}
        </>
      )}
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

/** Gift shop (bundles + collectibles) — also embedded as the "Подарки" tab of
 * the main shop (PacksPage). */
export function GiftShop() {
  const { data: giftSets } = useQuery({ queryKey: ["gift-sets"], queryFn: fetchGiftSets });
  const [selectedSet, setSelectedSet] = useState<GiftSet | null>(null);
  const tiles = useOpenTile<number>();

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
          <div className="grid grid-cols-2 gap-2.5">
            {collectibleSets.map((g) => (
              <GiftSetTile
                key={g.id}
                g={g}
                open={tiles.openKey === g.id}
                onToggle={() => tiles.toggle(g.id)}
                actionLabel="Купить"
                onAction={() => setSelectedSet(g)}
              />
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
  const preset = usePresetRecipient();
  const [recipientMode, setRecipientMode] = useState<"self" | "friend">(preset ? "friend" : "self");
  const [target, setTarget] = useState<UserPublic | null>(preset);
  const [message, setMessage] = useState("");
  const [currency, setCurrency] = useState<"stars" | "coins">(giftSet.coins_price > 0 ? "coins" : "stars");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [revealResult, setRevealResult] = useState<GiftClaimResult | null>(null);

  const recipientId = recipientMode === "self" ? user?.id : target?.id;

  // Self-purchases feel instant: claim (and thus grant any configured
  // prize) immediately after the purchase call succeeds, then show the same
  // reveal modal a "received" gift shows after tapping "Открыть" — no
  // separate trip to the pending list. Friend purchases keep the plain
  // "sent" confirmation; the prize belongs to the recipient, who gets their
  // own reveal when they claim it later.
  const revealIfSelf = async (giftId: number) => {
    const claimResult = await claimGift(giftId);
    updateBalance(claimResult.new_balance);
    hapticNotify("success");
    queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
    setRevealResult(claimResult);
  };

  const handleBuyWithCoins = async () => {
    if (!recipientId) return;
    setError(null);
    setBusy(true);
    try {
      const result = await buyCollectibleWithCoins(giftSet.id, recipientId, message || undefined);
      updateBalance(result.new_balance);
      queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
      if (recipientMode === "self") {
        try {
          await revealIfSelf(result.gift.id);
        } catch {
          hapticNotify("success");
          setSuccess(true);
        }
      } else {
        hapticNotify("success");
        setSuccess(true);
      }
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
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link, invoice.payload_token);
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
          queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
          if (recipientMode === "self" && status.gift_result) {
            try {
              await revealIfSelf(status.gift_result.id);
            } catch {
              hapticNotify("success");
              setSuccess(true);
            }
          } else {
            hapticNotify("success");
            setSuccess(true);
          }
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

  if (revealResult) {
    return <GiftClaimResultModal result={revealResult} onClose={onDone} />;
  }

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
  const tiles = useOpenTile<number>();
  const [target, setTarget] = useState<UserPublic | null>(usePresetRecipient());
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
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link, invoice.payload_token);
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
      <div className="grid grid-cols-2 gap-2.5">
        {giftSets.map((g) => (
          <GiftSetTile
            key={g.id}
            g={g}
            open={tiles.openKey === g.id}
            onToggle={() => tiles.toggle(g.id)}
            actionLabel="Подарить другу"
            onAction={() => setSelectedSet(g)}
          />
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

/** A gift set in the shop grid (2 per row): just the picture; a tap opens
 * the sheet with the price, what's inside, how many are left and the action. */
function GiftSetTile({
  g, open, onToggle, actionLabel, onAction,
}: {
  g: GiftSet;
  open: boolean;
  onToggle: () => void;
  actionLabel: string;
  onAction: () => void;
}) {
  const left = g.max_supply != null ? Math.max(0, g.max_supply - (g.next_serial_number - 1)) : null;
  return (
    <InfoTile
      open={open}
      onToggle={onToggle}
      accent={g.stars_price && !g.coins_price ? "stars" : undefined}
      dimmed={left === 0}
      shape="square"
      name={g.name}
      price={
        g.coins_price ? (
          <span className="flex items-center gap-1 text-accent-lime">
            <IconCoin size={11} /> {g.coins_price.toLocaleString("ru-RU")}
          </span>
        ) : (
          <span className="text-amber-300">{g.stars_price} ⭐</span>
        )
      }
      badge={
        left !== null ? (
          <span className="rounded-full bg-black/75 px-1.5 py-0.5 font-mono text-micro text-amber-300">ост. {left}</span>
        ) : undefined
      }
      visual={
        g.image_path ? (
          <img decoding="async" loading="lazy" src={staticUrl(g.image_path) ?? undefined} alt="" className="h-full w-full object-cover" />
        ) : (
          <IconGift size={48} className="text-rarity-epic" />
        )
      }
      details={
        <>
          <span className="flex flex-wrap items-center gap-x-2 font-mono text-xs font-bold">
            {!!g.coins_price && (
              <span className="flex items-center gap-1 text-accent-lime">
                <IconCoin size={12} /> {g.coins_price.toLocaleString("ru-RU")}
              </span>
            )}
            {!!g.coins_price && !!g.stars_price && <span className="font-sans font-normal text-ink-mist-dim">или</span>}
            {!!g.stars_price && <span className="text-amber-300">{g.stars_price} ⭐</span>}
          </span>
          {g.description && <span className="text-caption text-ink-mist">{g.description}</span>}
          {(g.coins_amount > 0 || g.pack_id) && (
            <span className="text-caption text-accent-lime">
              Внутри: {[g.coins_amount > 0 ? `${g.coins_amount.toLocaleString("ru-RU")} монет` : null, g.pack_id ? "пак" : null]
                .filter(Boolean)
                .join(" + ")}
            </span>
          )}
          {g.kind === "collectible" && <span className="text-caption text-ink-mist">Коллекционный: у каждого свой номер</span>}
          {left !== null && <span className="text-caption text-amber-300">Осталось: {left} из {g.max_supply}</span>}
        </>
      }
      action={
        <button
          onClick={onAction}
          disabled={left === 0}
          className="rounded-full bg-floodlight py-1.5 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {left === 0 ? "Распродано" : actionLabel}
        </button>
      }
    />
  );
}
