import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { IconCoin, IconCollection } from "@/components/icons";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import CardUpgradeModal from "@/components/cards/CardUpgradeModal";
import PlayerCard from "@/components/cards/PlayerCard";
import CardDetailModal from "@/components/collection/CardDetailModal";
import { useCardActions } from "@/components/collection/useCardActions";
import { fetchCollection, fetchCollectionStats, type CollectionFilters } from "@/api/collection";
import { fetchCollections } from "@/api/collections";
import { RARITY_LABELS, RARITY_ORDER } from "@/lib/rarity";
import type { Rarity } from "@/types";

const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary", "diamond"];

const PAGE_SIZE = 60;

export default function MyCardsTab() {
  const [rarity, setRarity] = useState<Rarity | null>(null);
  const [collectionId, setCollectionId] = useState<number | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<CollectionFilters["sort_by"]>("acquired_at");
  const [pageNum, setPageNum] = useState(1);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);

  const {
    detailCard, setDetailCard, confirmSell, setConfirmSell,
    upgradeCard, setUpgradeCard, sellMutation, hideMutation,
  } = useCardActions([["collection"], ["collection-stats"]]);

  // Resetting to page 1 whenever a filter changes (rather than on every
  // render) keeps a stale page number from silently returning an empty
  // "Карточек не найдено" result after narrowing the filters.
  useEffect(() => {
    setPageNum(1);
  }, [rarity, collectionId, search, sortBy]);

  const filters: CollectionFilters = {
    rarity: rarity ?? undefined,
    collection_id: collectionId,
    search: search || undefined,
    sort_by: sortBy,
    sort_dir: "desc",
    page: pageNum,
    page_size: PAGE_SIZE,
  };

  const { data: page, isLoading } = useQuery({ queryKey: ["collection", filters], queryFn: () => fetchCollection(filters) });
  const { data: stats } = useQuery({ queryKey: ["collection-stats"], queryFn: fetchCollectionStats });
  const { data: collections } = useQuery({ queryKey: ["collections"], queryFn: fetchCollections });

  useEffect(() => {
    if (sellMutation.isSuccess) {
      setSelected([]);
      setSelectMode(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sellMutation.isSuccess]);

  const toggleSelect = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const totalSellValue = (page?.items ?? [])
    .filter((c) => selected.includes(c.id))
    .reduce((sum, c) => sum + c.player.quick_sell_price, 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
        <button
          onClick={() => { setSelectMode((v) => !v); setSelected([]); }}
          className="rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-ink-mist"
        >
          {selectMode ? "Отмена" : "Выбрать"}
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-x-3 rounded-2xl bg-bg-surface p-4">
          <div>
            <p className="font-display text-2xl font-bold text-ink-chalk">{stats.unique_players}</p>
            <p className="mt-0.5 text-[11px] text-ink-mist">Уникальных</p>
          </div>
          <div>
            <p className="font-display text-2xl font-bold text-ink-chalk">{stats.total_cards}</p>
            <p className="mt-0.5 text-[11px] text-ink-mist">Всего карточек</p>
          </div>
        </div>
      )}

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Поиск по имени..."
        className="rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
      />

      <div className="flex gap-2 overflow-x-auto pb-1">
        <FilterChip active={rarity === null} label="Все" onClick={() => setRarity(null)} />
        {RARITIES.map((r) => (
          <FilterChip key={r} active={rarity === r} label={RARITY_LABELS[r]} onClick={() => setRarity(r)} />
        ))}
      </div>

      <select
        value={sortBy}
        onChange={(e) => setSortBy(e.target.value as CollectionFilters["sort_by"])}
        className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
      >
        <option value="acquired_at">По дате получения</option>
        <option value="rating">По рейтингу</option>
        <option value="rarity">По редкости</option>
      </select>

      {!!collections?.length && (
        <select
          value={collectionId ?? ""}
          onChange={(e) => setCollectionId(e.target.value ? Number(e.target.value) : undefined)}
          className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
        >
          <option value="">Все коллекции</option>
          {collections.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      )}

      {isLoading && <CardGridSkeleton count={9} />}
      {!isLoading && !page?.items.length && <EmptyState icon={IconCollection} title="Карточек не найдено" description="Открой паки, чтобы собрать коллекцию" />}

      <div className="grid grid-cols-3 gap-2">
        {page?.items.map((card) => (
          <PlayerCard
            key={card.id}
            player={card.player}
            badge={
              card.duplicate_count && card.duplicate_count > 1 ? (
                <span className="rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-[9px] font-bold text-ink-chalk">×{card.duplicate_count}</span>
              ) : undefined
            }
            selected={selectMode && selected.includes(card.id)}
            onClick={() => (selectMode ? toggleSelect(card.id) : setDetailCard(card))}
          />
        ))}
      </div>

      {page && page.pages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => setPageNum((p) => Math.max(1, p - 1))}
            disabled={pageNum <= 1}
            className="rounded-full bg-white/5 px-4 py-2 text-xs font-semibold text-ink-chalk disabled:opacity-30"
          >
            Назад
          </button>
          <span className="font-mono text-xs text-ink-mist">
            {pageNum} / {page.pages} · {page.total} карт
          </span>
          <button
            onClick={() => setPageNum((p) => Math.min(page.pages, p + 1))}
            disabled={pageNum >= page.pages}
            className="rounded-full bg-white/5 px-4 py-2 text-xs font-semibold text-ink-chalk disabled:opacity-30"
          >
            Вперёд
          </button>
        </div>
      )}

      {selectMode && selected.length > 0 && (
        <div className="safe-bottom fixed inset-x-0 bottom-16 z-30 mx-auto flex max-w-lg items-center justify-between rounded-2xl border border-white/10 bg-bg-surface px-4 py-3 shadow-xl">
          <span className="flex items-center gap-1.5 text-sm text-ink-mist">
            Выбрано: {selected.length} ·
            <IconCoin size={13} className="text-accent-lime" />
            <span className="font-mono text-accent-lime">{totalSellValue}</span>
          </span>
          <button
            onClick={() => setConfirmSell({ ids: selected, lastCopy: false })}
            className="rounded-full bg-red-500 px-4 py-2 text-xs font-bold text-white active:scale-95"
          >
            Продать
          </button>
        </div>
      )}

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

      {upgradeCard && <CardUpgradeModal cards={[upgradeCard]} onClose={() => setUpgradeCard(null)} />}

      <ConfirmDialog
        open={!!confirmSell}
        title={confirmSell?.lastCopy ? "Это последний экземпляр!" : "Продать карточки?"}
        description={
          confirmSell?.lastCopy
            ? "Ты продашь единственный экземпляр этого футболиста. Это действие нельзя отменить."
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

function FilterChip({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${active ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
    >
      {label}
    </button>
  );
}
