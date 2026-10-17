import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import CardFilterBar from "@/components/collection/CardFilterBar";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { IconCoin, IconCollection, IconLock, IconLockOpen } from "@/components/icons";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import CardUpgradeModal from "@/components/cards/CardUpgradeModal";
import { losesProgress } from "@/lib/cardStars";
import PlayerCard from "@/components/cards/PlayerCard";
import CardDetailModal from "@/components/collection/CardDetailModal";
import { useCardActions } from "@/components/collection/useCardActions";
import {
  fetchCollection, fetchCollectionStats, sellDuplicates, setCardsLocked, type CollectionFilters, type SellDuplicatesResult,
} from "@/api/collection";
import { fetchCollections } from "@/api/collections";
import { cardLockProps, inSquad } from "@/lib/cardLocks";
import { useCardFilter } from "@/lib/cardFilter";
import { RARITY_ORDER } from "@/lib/rarity";
import CardSkillBadge from "@/components/cards/CardSkillBadge";
import { useSkillUpgradeCheck } from "@/lib/cardSkills";
import { formatGameError } from "@/lib/errors";
import { haptic } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { UserCard } from "@/types";

const PAGE_SIZE = 60;

export default function MyCardsTab() {
  // Starts from the player's saved default filter (CardFilterBar saves it).
  const { filter, setFilter, defaultFilter } = useCardFilter();
  const [collectionId, setCollectionId] = useState<number | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [dupPreview, setDupPreview] = useState<SellDuplicatesResult | null>(null);
  const [dupMessage, setDupMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
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
  }, [filter, collectionId, search]);

  const filters: CollectionFilters = {
    rarity: filter.rarity ?? undefined,
    country: filter.country ?? undefined,
    club: filter.club ?? undefined,
    position: filter.position ?? undefined,
    collection_id: collectionId,
    search: search || undefined,
    sort_by: filter.sort_by,
    sort_dir: "desc",
    has_skill: filter.has_skill || undefined,
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
  }, [sellMutation.isSuccess]);

  const duplicatesMutation = useMutation({
    mutationFn: sellDuplicates,
    onSuccess: (data) => {
      if (data.preview) {
        if (data.sold_count === 0) setDupMessage("Лишних дубликатов нет — продавать нечего");
        else { setDupMessage(null); setDupPreview(data); }
        return;
      }
      haptic("medium");
      setDupPreview(null);
      setDupMessage(`Продано ${data.sold_count} шт. · +${data.coins_earned} монет`);
      updateBalance(data.new_balance);
      for (const key of [["collection"], ["collection-stats"], ["card-skills"], ["album-overview"], ["album-detail"]]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
    onError: (err) => { setDupPreview(null); setDupMessage(formatGameError(err, "Не удалось продать дубликаты")); },
  });

  const toggleSelect = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const selectedCards = (page?.items ?? []).filter((c) => selected.includes(c.id));
  // Squad copies and the owner's locked ones are never sold.
  const sellable = selectedCards.filter(
    (c) => !inSquad(c) && !c.is_user_locked && !c.is_locked_by_admin && !c.is_locked_in_trade,
  );
  const totalSellValue = sellable.reduce((sum, c) => sum + c.player.quick_sell_price, 0);
  const allLocked = selectedCards.length > 0 && selectedCards.every((c) => c.is_user_locked);

  const lockMutation = useMutation({
    mutationFn: ({ ids, locked }: { ids: number[]; locked: boolean }) => setCardsLocked(ids, locked),
    onSuccess: (data) => {
      haptic("light");
      setDupMessage(
        data.locked
          ? `🔒 Замок на ${data.card_ids.length} шт. — их не продать и не сжечь`
          : `Замок снят с ${data.card_ids.length} шт.`,
      );
      setSelected([]);
      setSelectMode(false);
      for (const key of [["collection"], ["album-detail"], ["upgrade-cards"]]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
    onError: (err) => setDupMessage(formatGameError(err, "Не удалось поставить замок")),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end gap-2">
        <button
          onClick={() => duplicatesMutation.mutate(true)}
          disabled={duplicatesMutation.isPending}
          className="rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-ink-mist disabled:opacity-50"
        >
          Продать дубликаты
        </button>
        <button
          onClick={() => { setSelectMode((v) => !v); setSelected([]); }}
          className="rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-ink-mist"
        >
          {selectMode ? "Отмена" : "Выбрать"}
        </button>
      </div>

      {dupMessage && (
        <p className="rounded-xl bg-bg-surface px-3 py-2 text-xs text-ink-mist" role="status">{dupMessage}</p>
      )}

      {stats && (
        <div className="grid grid-cols-2 gap-x-3 rounded-2xl bg-bg-surface p-4">
          <div>
            <p className="font-display text-2xl font-bold text-ink-chalk">{stats.unique_players}</p>
            <p className="mt-0.5 text-caption text-ink-mist">Уникальных</p>
          </div>
          <div>
            <p className="font-display text-2xl font-bold text-ink-chalk">{stats.total_cards}</p>
            <p className="mt-0.5 text-caption text-ink-mist">Всего карточек</p>
          </div>
        </div>
      )}

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Поиск по имени..."
        className="rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
      />

      <CardFilterBar filter={filter} onChange={setFilter} defaultFilter={defaultFilter} />

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
            stars={card.stars}
            pathStage={card.path_stage} prestige={card.prestige} talentOverride={card.talent_override}
            badge={<CardTileBadges card={card} />}
            {...cardLockProps(card)}
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

      {selectMode && selected.length === 0 && (
        <p className="text-center text-xs text-ink-mist">Отметь карточки, чтобы продать их или поставить замок 🔒</p>
      )}

      {selectMode && selected.length > 0 && (
        <div className="safe-bottom fixed inset-x-0 bottom-16 z-30 mx-auto flex max-w-lg flex-col gap-2 rounded-2xl border border-white/10 bg-bg-surface px-4 py-3 shadow-xl">
          <span className="flex items-center gap-1.5 text-sm text-ink-mist">
            Выбрано: {selected.length}
            {sellable.length > 0 && (
              <>
                {" "}· <IconCoin size={13} className="text-accent-lime" />
                <span className="font-mono text-accent-lime">{totalSellValue}</span>
              </>
            )}
          </span>
          {sellable.length < selectedCards.length && (
            <span className="text-micro text-ink-mist-dim">
              {selectedCards.length - sellable.length} шт. в составе или под замком — не продаются
            </span>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => lockMutation.mutate({ ids: selected, locked: !allLocked })}
              disabled={lockMutation.isPending}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-full bg-amber-400 px-3 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-50"
            >
              {allLocked ? <IconLockOpen size={14} /> : <IconLock size={14} />}
              {allLocked ? "Снять замок" : "Поставить замок"}
            </button>
            <button
              onClick={() => setConfirmSell({
                ids: sellable.map((c) => c.id),
                lastCopy: false,
                skillLoss: sellable.some((c) => losesProgress(c)),
              })}
              disabled={sellable.length === 0}
              className="flex-1 rounded-full bg-red-500 px-3 py-2 text-xs font-bold text-white active:scale-95 disabled:opacity-40"
            >
              Продать{sellable.length > 0 && sellable.length < selectedCards.length ? ` ${sellable.length}` : ""}
            </button>
          </div>
        </div>
      )}

      {detailCard && (
        <CardDetailModal
          card={detailCard}
          onClose={() => setDetailCard(null)}
          onSell={() => setConfirmSell({ ids: [detailCard.id], lastCopy: false, skillLoss: losesProgress(detailCard) })}
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
        open={!!dupPreview}
        title={`Продать ${dupPreview?.sold_count ?? 0} дубликатов?`}
        description={
          `Получишь ${dupPreview?.coins_earned ?? 0} монет. По одной карточке каждого игрока остаётся; `
          + "карточки с навыком, в составах, в обменах, под замком и бриллиантовые не продаются."
        }
        confirmLabel="Продать"
        onConfirm={() => duplicatesMutation.mutate(false)}
        onCancel={() => setDupPreview(null)}
      />

      <ConfirmDialog
        open={!!confirmSell}
        title={confirmSell?.lastCopy ? "Это последний экземпляр!" : "Продать карточки?"}
        description={
          (confirmSell?.lastCopy
            ? "Ты продашь единственный экземпляр этого футболиста. Это действие нельзя отменить."
            : "Монеты будут зачислены на баланс. Действие нельзя отменить.")
          + (confirmSell?.skillLoss ? " У карточки есть навык или звёзды — они будут потеряны без возврата." : "")
        }
        danger
        confirmLabel="Продать"
        onConfirm={() => confirmSell && sellMutation.mutate({
          ids: confirmSell.ids, confirmLastCopy: confirmSell.lastCopy, confirmSkillLoss: !!confirmSell.skillLoss,
        })}
        onCancel={() => setConfirmSell(null)}
      />
    </div>
  );
}

/** A skilled copy is listed as its own tile (backend list_user_cards), so a
 * tile's skill badge is that exact copy's skill; ×N still counts every copy. */
function CardTileBadges({ card }: { card: UserCard }) {
  const canUpgrade = useSkillUpgradeCheck();
  const hasDuplicates = !!card.duplicate_count && card.duplicate_count > 1;
  if (!card.skill_code && !hasDuplicates) return null;
  return (
    <span className="flex items-center gap-1">
      {hasDuplicates && (
        <span className="rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-micro font-bold text-ink-chalk">×{card.duplicate_count}</span>
      )}
      <CardSkillBadge code={card.skill_code} level={card.skill_level} upgradable={canUpgrade(card.skill_code, card.skill_level)} />
    </span>
  );
}
