import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { losesProgress } from "@/lib/cardStars";
import { useState } from "react";

import CardUpgradeModal from "@/components/cards/CardUpgradeModal";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import CardDetailModal from "@/components/collection/CardDetailModal";
import CardFilterBar from "@/components/collection/CardFilterBar";
import { cardLockProps } from "@/lib/cardLocks";
import { activeCount, matchesPlayer, useCardFilter } from "@/lib/cardFilter";
import CardSkillBadge from "@/components/cards/CardSkillBadge";
import PlayerCard from "@/components/cards/PlayerCard";
import { bestSkilledCopy, useSkillUpgradeCheck } from "@/lib/cardSkills";
import { useCardActions } from "@/components/collection/useCardActions";
import { IconChevronLeft, IconChevronRight, IconCoin, IconCollection, IconParty, IconSearch } from "@/components/icons";
import { fetchAlbumCollectionDetail, fetchAlbumOverview } from "@/api/album";
import { addTradeWish, fetchTradeWishes, removeTradeWish } from "@/api/trades";
import { ApiRequestError, staticUrl } from "@/lib/api";
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
          <p className="font-mono text-micro uppercase tracking-wider text-ink-mist">Собрано карточек</p>
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

      {!search && <NextGoal collections={data?.collections} onOpen={onOpen} />}

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

/** The incomplete collection with a reward that is closest to done — a
 * concrete "почти собрал" target instead of a flat list of progress bars. */
function NextGoal({
  collections,
  onOpen,
}: {
  collections: AlbumCollectionSummary[] | undefined;
  onOpen: (id: number) => void;
}) {
  const goal = (collections ?? [])
    .filter((c) => c.id > 0 && !c.is_complete && c.owned_count > 0 && (c.reward_coins > 0 || c.reward_pack_name))
    .sort((a, b) => (a.total_count - a.owned_count) - (b.total_count - b.owned_count))[0];
  if (!goal) return null;
  const left = goal.total_count - goal.owned_count;
  return (
    <button
      onClick={() => onOpen(goal.id)}
      className="flex items-center gap-3 rounded-2xl border border-accent-lime/25 bg-accent-lime/5 p-3 text-left active:scale-[0.98]"
    >
      <IconCollection size={20} className="shrink-0 text-accent-lime" />
      <span className="min-w-0 flex-1">
        <span className="block text-micro font-semibold uppercase tracking-wider text-accent-lime">Почти собрано</span>
        <span className="block truncate text-sm font-semibold text-ink-chalk">
          «{goal.name}»: осталось {left} {left === 1 ? "карточка" : left < 5 ? "карточки" : "карточек"}
        </span>
        <span className="flex items-center gap-1 text-caption text-ink-mist">
          Награда: {goal.reward_coins > 0 && <>{goal.reward_coins} <IconCoin size={10} className="text-accent-lime" /></>}
          {goal.reward_pack_name && ` пак «${goal.reward_pack_name}»`}
        </span>
      </span>
      <IconChevronRight size={16} className="shrink-0 text-ink-mist-dim" />
    </button>
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
          <img decoding="async" loading="lazy" src={staticUrl(collection.image_path) ?? undefined} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-emerald-800 to-bg-raised font-display text-lg font-bold text-white/70">
            {collection.name.slice(0, 2).toUpperCase()}
          </div>
        )}
        {collection.is_complete && (
          <span className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-accent-lime text-micro font-bold text-bg-base">
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
          <p className="mt-1 text-micro font-bold uppercase tracking-wide text-accent-lime">Собрана</p>
        ) : collection.reward_coins > 0 ? (
          <p className="mt-1 flex items-center gap-1 text-micro text-ink-mist">
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
  // Same saved default filter as «Мои карты» (rarity/country/club/position).
  const { filter, setFilter, defaultFilter } = useCardFilter();
  const { data, isLoading } = useQuery({
    queryKey: ["album-detail", collectionId, search],
    queryFn: () => fetchAlbumCollectionDetail(collectionId, search || undefined),
  });

  const {
    detailCard, setDetailCard, confirmSell, setConfirmSell,
    upgradeCard, setUpgradeCard, sellMutation, hideMutation,
  } = useCardActions([["album-detail"], ["album-overview"], ["collection"], ["collection-stats"]]);
  const visible = (data?.players ?? []).filter((slot) => matchesPlayer(filter, slot.player));
  const want = useWantToggle();

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
          <IconParty size={14} className="mr-1 inline align-[-2px]" />Коллекция собрана{data.reward_coins > 0 ? ` — получено ${data.reward_coins} монет` : ""}!
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

      <CardFilterBar filter={filter} onChange={setFilter} defaultFilter={defaultFilter} showSort={false} showSkill={false} />

      {want.error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{want.error}</p>}
      {isLoading && <CardGridSkeleton count={9} />}
      {!isLoading && !visible.length && (
        <EmptyState
          icon={IconCollection}
          title="Никого не найдено"
          description={activeCount(filter) ? "Под этот фильтр никто не подходит — смени или очисти его" : "Попробуй другой запрос"}
        />
      )}

      <div className="grid grid-cols-3 gap-2">
        {visible.map((slot, i) => (
          <div key={slot.player.id} className="animate-card-in" style={{ animationDelay: `${Math.min(i, 14) * 22}ms` }}>
            <AlbumSlot
              slot={slot}
              onOpen={() => slot.card && setDetailCard(slot.card)}
              wanted={want.wanted.has(slot.player.id)}
              onToggleWant={() => want.toggle(slot.player.id)}
            />
          </div>
        ))}
      </div>

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
        open={!!confirmSell}
        title={confirmSell?.lastCopy ? "Это последний экземпляр!" : "Продать карточку?"}
        description={
          (confirmSell?.lastCopy
            ? "Ты продашь единственный экземпляр этого футболиста — он снова станет пустым слотом в альбоме. Это действие нельзя отменить."
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

/** «Ищу» of «Поиск обменов», toggled from missing album slots. */
function useWantToggle() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data: wishes } = useQuery({ queryKey: ["trade-wishes"], queryFn: fetchTradeWishes });
  const wanted = new Set((wishes?.wants ?? []).map((p) => p.id));
  const mutation = useMutation({
    mutationFn: (playerId: number) => (wanted.has(playerId) ? removeTradeWish("want", playerId) : addTradeWish("want", playerId)),
    onSuccess: (data) => {
      queryClient.setQueryData(["trade-wishes"], data);
      queryClient.invalidateQueries({ queryKey: ["trade-matches"] });
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось обновить «Ищу»"),
  });
  return { wanted, toggle: (playerId: number) => mutation.mutate(playerId), error };
}

function AlbumSlot({
  slot,
  onOpen,
  wanted,
  onToggleWant,
}: {
  slot: AlbumPlayer;
  onOpen: () => void;
  wanted: boolean;
  onToggleWant: () => void;
}) {
  const canUpgrade = useSkillUpgradeCheck();
  if (!slot.owned || !slot.card) {
    // Diamonds never trade (except «Академия»), so they can't be in «Ищу».
    const wantable = slot.player.rarity !== "diamond" || !!slot.player.path_talent_code;
    return (
      <div className="relative flex aspect-[3/4] flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-white/15 bg-black/10 p-2 text-center">
        {wantable && (
          <button
            onClick={onToggleWant}
            className={`absolute inset-x-1.5 bottom-1.5 rounded-lg py-1 text-micro font-bold active:scale-95 ${
              wanted ? "bg-accent-lime/20 text-accent-lime" : "bg-white/10 text-ink-mist"
            }`}
          >
            {wanted ? "✓ Ищу" : "+ Ищу"}
          </button>
        )}
        <svg viewBox="0 0 24 24" fill="none" className="w-7 opacity-30">
          <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.6" />
          <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" stroke="currentColor" strokeWidth="1.6" />
        </svg>
        <p className="line-clamp-2 text-micro font-semibold leading-tight text-ink-mist">{slot.player.display_name}</p>
        <p className="text-micro uppercase tracking-wide text-ink-mist-dim">{POSITION_LABELS[slot.player.position]}</p>
      </div>
    );
  }

  const best = bestSkilledCopy(slot.card.skilled_copies);
  // The shared card face (rarity frame, rating top-left, position top-right,
  // skill bottom-left, «Академия» bottom-right); copies count under the name.
  return (
    <PlayerCard
      player={slot.player}
      size="sm"
      onClick={onOpen}
      stars={slot.card.stars}
      pathStage={slot.card.path_stage}
      prestige={slot.card.prestige}
      talentOverride={slot.card.talent_override}
      {...cardLockProps(slot.card)}
      badge={
        best ? (
          <CardSkillBadge
            code={best.skill_code}
            level={best.skill_level}
            extraCount={(slot.card.skilled_copies?.length ?? 1) - 1}
            upgradable={(slot.card.skilled_copies ?? []).some((c) => canUpgrade(c.skill_code, c.skill_level))}
          />
        ) : undefined
      }
      footer={
        slot.duplicate_count > 1 ? (
          <p className="pb-1 text-center font-mono text-micro font-bold leading-none text-ink-mist">×{slot.duplicate_count}</p>
        ) : undefined
      }
    />
  );
}
