import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import PlayerCard from "@/components/cards/PlayerCard";
import { bulkSellCards, fetchCollection, fetchCollectionStats, sellCard, type CollectionFilters } from "@/api/collection";
import { fetchCollections } from "@/api/collections";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { POSITION_LABELS, RARITY_LABELS } from "@/lib/rarity";
import { useAuthStore } from "@/store/authStore";
import type { Rarity, UserCard } from "@/types";

const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];

export default function CollectionPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [rarity, setRarity] = useState<Rarity | null>(null);
  const [collectionId, setCollectionId] = useState<number | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<CollectionFilters["sort_by"]>("acquired_at");
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [detailCard, setDetailCard] = useState<UserCard | null>(null);
  const [confirmSell, setConfirmSell] = useState<{ ids: number[]; lastCopy: boolean } | null>(null);

  const filters: CollectionFilters = {
    rarity: rarity ?? undefined,
    collection_id: collectionId,
    search: search || undefined,
    sort_by: sortBy,
    sort_dir: "desc",
    page_size: 60,
  };

  const { data: page, isLoading } = useQuery({ queryKey: ["collection", filters], queryFn: () => fetchCollection(filters) });
  const { data: stats } = useQuery({ queryKey: ["collection-stats"], queryFn: fetchCollectionStats });
  const { data: collections } = useQuery({ queryKey: ["collections"], queryFn: fetchCollections });

  const sellMutation = useMutation({
    mutationFn: ({ ids, confirmLastCopy }: { ids: number[]; confirmLastCopy: boolean }) =>
      ids.length === 1 ? sellCard(ids[0], confirmLastCopy) : bulkSellCards(ids, confirmLastCopy),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      queryClient.invalidateQueries({ queryKey: ["collection-stats"] });
      setSelected([]);
      setSelectMode(false);
      setDetailCard(null);
      setConfirmSell(null);
    },
    onError: (err: unknown) => {
      if (err instanceof ApiRequestError && err.details?.requires_confirmation) {
        setConfirmSell((prev) => (prev ? { ...prev, lastCopy: true } : null));
      }
    },
  });

  const toggleSelect = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const totalSellValue = (page?.items ?? [])
    .filter((c) => selected.includes(c.id))
    .reduce((sum, c) => sum + c.player.quick_sell_price, 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold text-slate-100">Коллекция</h1>
        <button
          onClick={() => { setSelectMode((v) => !v); setSelected([]); }}
          className="rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-slate-300"
        >
          {selectMode ? "Отмена" : "Выбрать"}
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-bg-surface px-3 py-2">
            <p className="text-[11px] text-slate-400">Уникальных</p>
            <p className="font-display text-lg font-bold text-slate-100">{stats.unique_players}</p>
          </div>
          <div className="rounded-xl bg-bg-surface px-3 py-2">
            <p className="text-[11px] text-slate-400">Всего карточек</p>
            <p className="font-display text-lg font-bold text-slate-100">{stats.total_cards}</p>
          </div>
        </div>
      )}

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Поиск по имени..."
        className="rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 outline-none"
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
        className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-slate-200 outline-none"
      >
        <option value="acquired_at">По дате получения</option>
        <option value="rating">По рейтингу</option>
        <option value="rarity">По редкости</option>
      </select>

      {!!collections?.length && (
        <select
          value={collectionId ?? ""}
          onChange={(e) => setCollectionId(e.target.value ? Number(e.target.value) : undefined)}
          className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-slate-200 outline-none"
        >
          <option value="">Все коллекции</option>
          {collections.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      )}

      {isLoading && <CardGridSkeleton count={9} />}
      {!isLoading && !page?.items.length && <EmptyState icon="🃏" title="Карточек не найдено" description="Открой паки, чтобы собрать коллекцию" />}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {page?.items.map((card) => (
          <PlayerCard
            key={card.id}
            player={card.player}
            badge={
              card.duplicate_count && card.duplicate_count > 1 ? (
                <span className="rounded-full bg-black/70 px-1.5 py-0.5 text-[9px] font-bold text-white">×{card.duplicate_count}</span>
              ) : undefined
            }
            selected={selectMode && selected.includes(card.id)}
            onClick={() => (selectMode ? toggleSelect(card.id) : setDetailCard(card))}
          />
        ))}
      </div>

      {selectMode && selected.length > 0 && (
        <div className="safe-bottom fixed inset-x-0 bottom-16 z-30 mx-auto flex max-w-lg items-center justify-between rounded-2xl border border-white/10 bg-bg-surface px-4 py-3 shadow-xl">
          <span className="text-sm text-slate-300">Выбрано: {selected.length} · 🪙 {totalSellValue}</span>
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
        />
      )}

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
      className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${active ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"}`}
    >
      {label}
    </button>
  );
}

function CardDetailModal({ card, onClose, onSell }: { card: UserCard; onClose: () => void; onSell: () => void }) {
  const player = card.player;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-xs rounded-3xl border border-white/10 bg-bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <img
          src={staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
          alt={player.display_name}
          className="aspect-square w-full rounded-2xl object-cover"
        />
        <p className="mt-3 font-display text-lg font-bold text-slate-100">{player.display_name}</p>
        <p className="text-sm text-slate-400">{POSITION_LABELS[player.position]} · {player.club}</p>
        {player.collection_name && (
          <p className="mt-1 text-xs font-semibold text-amber-400">🏷️ Коллекция: {player.collection_name}</p>
        )}
        <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
          <span className="text-slate-400">Рейтинг: <b className="text-amber-300">{player.rating}</b></span>
          <span className="text-slate-400">Редкость: <b>{RARITY_LABELS[player.rarity]}</b></span>
          <span className="text-slate-400">Страна: <b>{player.country}</b></span>
          <span className="text-slate-400">№ {card.serial_number}</span>
        </div>
        {(card.is_locked_by_admin || card.is_locked_in_trade || card.is_in_lineup) && (
          <p className="mt-2 text-xs text-amber-400">
            🔒 Заблокирована {card.is_in_lineup ? "(в составе)" : card.is_locked_in_trade ? "(в обмене)" : "(администратором)"}
          </p>
        )}
        <div className="mt-4 flex gap-2">
          <button onClick={onClose} className="flex-1 rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-slate-300">Закрыть</button>
          <button
            onClick={onSell}
            disabled={card.is_locked_by_admin || card.is_locked_in_trade || card.is_in_lineup}
            className="flex-1 rounded-2xl bg-red-500 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
          >
            Продать за 🪙{player.quick_sell_price}
          </button>
        </div>
      </div>
    </div>
  );
}
