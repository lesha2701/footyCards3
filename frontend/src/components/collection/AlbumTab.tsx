import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import CardUpgradeModal from "@/components/cards/CardUpgradeModal";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import CardDetailModal from "@/components/collection/CardDetailModal";
import { useCardActions } from "@/components/collection/useCardActions";
import { IconChevronLeft, IconChevronRight, IconCoin, IconCollection, IconSearch } from "@/components/icons";
import { fetchAlbumCollectionDetail, fetchAlbumOverview } from "@/api/album";
import { staticUrl } from "@/lib/api";
import { POSITION_LABELS, RARITY_ORDER } from "@/lib/rarity";
import type { AlbumCollectionSummary, AlbumPlayer } from "@/types";

export default function AlbumTab() {
  const [openCollectionId, setOpenCollectionId] = useState<number | null>(null);

  return openCollectionId === null ? (
    <AlbumOverview onOpen={setOpenCollectionId} />
  ) : (
    <AlbumDetail collectionId={openCollectionId} onBack={() => setOpenCollectionId(null)} />
  );
}

function AlbumOverview({ onOpen }: { onOpen: (id: number) => void }) {
  const [search, setSearch] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["album-overview", search],
    queryFn: () => fetchAlbumOverview(search || undefined),
  });

  const pct = data && data.overall_total > 0 ? Math.round((data.overall_owned / data.overall_total) * 100) : 0;

  return (
    <div className="flex flex-col gap-4">
      {data && (
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-b from-emerald-950/60 to-bg-surface p-4">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-mist">Собрано карточек</p>
          <div className="mt-1 flex items-end justify-between">
            <p className="font-display text-3xl font-bold text-ink-chalk">
              {data.overall_owned}
              <span className="ml-1 text-lg font-semibold text-ink-mist">/ {data.overall_total}</span>
            </p>
            <span className="rounded-full bg-black/30 px-2.5 py-1 font-mono text-sm font-bold text-accent-lime">{pct}%</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg-raised">
            <div className="h-full rounded-full bg-gradient-to-r from-accent-cyan to-accent-lime" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 rounded-xl bg-bg-surface px-3 py-2.5">
        <IconSearch size={15} className="shrink-0 text-ink-mist-dim" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Найти игрока…"
          className="w-full bg-transparent text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
        />
      </div>

      {isLoading && <CardGridSkeleton count={4} />}
      {!isLoading && !data?.collections.length && (
        <EmptyState icon={IconCollection} title="Ничего не найдено" description="Попробуй другой запрос" />
      )}

      <div className="flex flex-col gap-2.5">
        {data?.collections.map((c) => (
          <CollectionSpread key={c.id} collection={c} onClick={() => onOpen(c.id)} />
        ))}
      </div>
    </div>
  );
}

function CollectionSpread({ collection, onClick }: { collection: AlbumCollectionSummary; onClick: () => void }) {
  const pct = collection.total_count > 0 ? Math.round((collection.owned_count / collection.total_count) * 100) : 0;
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 rounded-2xl bg-bg-surface p-2.5 text-left active:scale-[0.98] ${
        collection.is_complete ? "ring-1 ring-accent-lime/40" : ""
      }`}
    >
      <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-bg-raised">
        {collection.image_path ? (
          <img src={staticUrl(collection.image_path) ?? undefined} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-emerald-800 to-bg-raised font-display text-lg font-bold text-white/70">
            {collection.name.slice(0, 2).toUpperCase()}
          </div>
        )}
        {collection.is_complete && (
          <span className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-accent-lime text-[10px] font-bold text-bg-base">
            ✓
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <p className="truncate font-display text-sm font-bold text-ink-chalk">{collection.name}</p>
          <span className="shrink-0 font-mono text-xs text-ink-mist">
            <b className="text-ink-chalk">{collection.owned_count}</b>/{collection.total_count}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-bg-raised">
          <div
            className={`h-full rounded-full ${collection.is_complete ? "bg-accent-lime" : "bg-gradient-to-r from-accent-cyan to-accent-lime"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        {collection.is_complete ? (
          <p className="mt-1 text-[10px] font-bold uppercase tracking-wide text-accent-lime">Собрана</p>
        ) : collection.reward_coins > 0 ? (
          <p className="mt-1 flex items-center gap-1 text-[10px] text-ink-mist">
            Награда: {collection.reward_coins}
            <IconCoin size={9} className="text-accent-lime" />
            {collection.reward_pack_name && ` + пак «${collection.reward_pack_name}»`}
          </p>
        ) : null}
      </div>
      <IconChevronRight size={16} className="shrink-0 text-ink-mist-dim" />
    </button>
  );
}

function AlbumDetail({ collectionId, onBack }: { collectionId: number; onBack: () => void }) {
  const [search, setSearch] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["album-detail", collectionId, search],
    queryFn: () => fetchAlbumCollectionDetail(collectionId, search || undefined),
  });

  const {
    detailCard, setDetailCard, confirmSell, setConfirmSell,
    upgradeCard, setUpgradeCard, sellMutation, hideMutation,
  } = useCardActions([["album-detail"], ["album-overview"], ["collection"], ["collection-stats"]]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={onBack} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-bg-surface active:scale-95">
          <IconChevronLeft size={16} />
        </button>
        <div className="min-w-0">
          <p className="truncate font-display text-base font-bold text-ink-chalk">{data?.name ?? "…"}</p>
          {data && (
            <p className="font-mono text-xs text-ink-mist">
              {data.owned_count} / {data.total_count} собрано
              {data.total_count > 0 && ` · ${Math.round((data.owned_count / data.total_count) * 100)}%`}
            </p>
          )}
        </div>
      </div>

      {data && !data.is_complete && data.reward_coins > 0 && (
        <div className="flex flex-col gap-1 rounded-xl bg-bg-surface px-3 py-2.5 text-xs text-ink-mist">
          <p>
            Не хватает <b className="text-ink-chalk">{data.total_count - data.owned_count}</b> футболистов
          </p>
          <p className="flex flex-wrap items-center gap-1">
            Награда:
            <b className="flex items-center gap-1 text-accent-lime">
              {data.reward_coins} <IconCoin size={10} />
            </b>
            {data.reward_pack_name && <span>+ пак «{data.reward_pack_name}»</span>}
          </p>
        </div>
      )}
      {data?.is_complete && (
        <div className="rounded-xl bg-accent-lime/10 px-3 py-2.5 text-center text-xs font-semibold text-accent-lime">
          🎉 Коллекция собрана{data.reward_coins > 0 ? ` — получено ${data.reward_coins} монет` : ""}!
        </div>
      )}

      <div className="flex items-center gap-2 rounded-xl bg-bg-surface px-3 py-2.5">
        <IconSearch size={15} className="shrink-0 text-ink-mist-dim" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Найти в этой коллекции…"
          className="w-full bg-transparent text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
        />
      </div>

      {isLoading && <CardGridSkeleton count={9} />}
      {!isLoading && !data?.players.length && (
        <EmptyState icon={IconCollection} title="Никого не найдено" description="Попробуй другой запрос" />
      )}

      <div className="grid grid-cols-3 gap-2">
        {data?.players.map((slot) => (
          <AlbumSlot key={slot.player.id} slot={slot} onOpen={() => slot.card && setDetailCard(slot.card)} />
        ))}
      </div>

      {detailCard && (
        <CardDetailModal
          card={detailCard}
          onClose={() => setDetailCard(null)}
          onSell={() => setConfirmSell({ ids: [detailCard.id], lastCopy: false })}
          onToggleHidden={(hidden) => hideMutation.mutate({ id: detailCard.id, hidden })}
          hiddenPending={hideMutation.isPending}
          onUpgrade={
            RARITY_ORDER[detailCard.player.rarity] < RARITY_ORDER.legendary
              ? () => { setUpgradeCard(detailCard); setDetailCard(null); }
              : undefined
          }
        />
      )}

      {upgradeCard && <CardUpgradeModal card={upgradeCard} onClose={() => setUpgradeCard(null)} />}

      <ConfirmDialog
        open={!!confirmSell}
        title={confirmSell?.lastCopy ? "Это последний экземпляр!" : "Продать карточку?"}
        description={
          confirmSell?.lastCopy
            ? "Ты продашь единственный экземпляр этого футболиста — он снова станет пустым слотом в альбоме. Это действие нельзя отменить."
            : "Монеты будут зачислены на баланс. Действие нельзя отменить."
        }
        danger
        confirmLabel="Продать"
        onConfirm={() => confirmSell && sellMutation.mutate({ ids: confirmSell.ids, confirmLastCopy: confirmSell.lastCopy })}
        onCancel={() => setConfirmSell(null)}
      />
    </div>
  );
}

function AlbumSlot({ slot, onOpen }: { slot: AlbumPlayer; onOpen: () => void }) {
  if (!slot.owned || !slot.card) {
    return (
      <div className="flex aspect-[3/4] flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-white/15 bg-black/10 p-2 text-center">
        <svg viewBox="0 0 24 24" fill="none" className="w-7 opacity-30">
          <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.6" />
          <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" stroke="currentColor" strokeWidth="1.6" />
        </svg>
        <p className="line-clamp-2 text-[10px] font-semibold leading-tight text-ink-mist">{slot.player.display_name}</p>
        <p className="text-[9px] uppercase tracking-wide text-ink-mist-dim">{POSITION_LABELS[slot.player.position]}</p>
      </div>
    );
  }

  return (
    <button
      onClick={onOpen}
      className="relative flex aspect-[3/4] flex-col overflow-hidden rounded-xl bg-bg-surface active:scale-95"
    >
      <img
        src={staticUrl(slot.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
        alt=""
        className="h-full w-full object-cover"
        loading="lazy"
      />
      <span className="absolute left-1 top-1 rounded bg-black/60 px-1 py-0.5 font-mono text-[9px] font-bold text-white">
        {slot.player.position}
      </span>
      <span className="absolute right-1 top-1 rounded bg-black/60 px-1 py-0.5 font-mono text-[9px] font-bold text-accent-lime">
        {slot.player.rating}
      </span>
      {slot.duplicate_count > 1 && (
        <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 py-0.5 font-mono text-[9px] font-bold text-ink-chalk">
          ×{slot.duplicate_count}
        </span>
      )}
    </button>
  );
}
