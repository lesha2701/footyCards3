import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { losesProgress } from "@/lib/cardStars";
import { useEffect, useMemo, useState } from "react";
import { motion, type PanInfo } from "framer-motion";

import CardUpgradeModal from "@/components/cards/CardUpgradeModal";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import CardDetailModal from "@/components/collection/CardDetailModal";
import CardFilterBar from "@/components/collection/CardFilterBar";
import { AlbumCover, AlbumPage, CompleteStamp, SlotNumber, Sticker } from "@/components/collection/AlbumBook";
import { freshOnPage, markPageSeen } from "@/lib/albumSeen";
import { haptic } from "@/lib/telegram";
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
import { POSITION_LABELS, RARITY_GRADIENTS, RARITY_ORDER } from "@/lib/rarity";
import type { AlbumCollectionSummary, AlbumPlayer, AlbumStaff } from "@/types";

/** The sticker album; `ownerId` = another player's, read-only (no rewards,
 * no «Ищу», no card actions, no «NEW» bookkeeping). */
export default function AlbumTab({ ownerId }: { ownerId?: number } = {}) {
  const [openCollectionId, setOpenCollectionId] = useState<number | null>(null);
  // The pages in album order, for flipping between them with a swipe.
  const { data: overview } = useQuery({
    queryKey: ["album-overview", "", ownerId ?? "me"], queryFn: () => fetchAlbumOverview(undefined, ownerId),
  });
  const pages = (overview?.collections ?? []).filter((c) => !c.available_from).map((c) => c.id);

  return openCollectionId === null ? (
    <AlbumOverview onOpen={setOpenCollectionId} ownerId={ownerId} />
  ) : (
    <AlbumDetail
      key={openCollectionId}
      collectionId={openCollectionId}
      pages={pages}
      ownerId={ownerId}
      onGo={setOpenCollectionId}
      onBack={() => setOpenCollectionId(null)}
    />
  );
}

function AlbumOverview({ onOpen, ownerId }: { onOpen: (id: number) => void; ownerId?: number }) {
  const [search, setSearch] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["album-overview", search, ownerId ?? "me"],
    queryFn: () => fetchAlbumOverview(search || undefined, ownerId),
  });

  return (
    <div className="flex flex-col gap-4">
      {data && (
        <AlbumCover
          owned={data.overall_owned}
          total={data.overall_total}
          completed={data.collections.filter((c) => c.id > 0 && c.is_complete).length}
        />
      )}

      {!search && !ownerId && <NextGoal collections={data?.collections} onOpen={onOpen} />}

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
        {data?.collections.map((c, i) => (
          <CollectionSpread key={c.id} page={i + 1} collection={c} onClick={() => onOpen(c.id)} />
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
    .filter((c) => c.id > 0 && !c.available_from && !c.is_complete && c.owned_count > 0 && (c.reward_coins > 0 || c.reward_pack_name))
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

/** «21 ноября» — the day an announced collection opens (Moscow time, like the event). */
function availableFromLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long", timeZone: "Europe/Moscow" });
}

function CollectionSpread({ collection, page, onClick }: { collection: AlbumCollectionSummary; page: number; onClick: () => void }) {
  const pct = collection.total_count > 0 ? Math.round((collection.owned_count / collection.total_count) * 100) : 0;
  return (
    <button
      onClick={onClick}
      className={`relative flex items-center gap-3 overflow-hidden rounded-2xl bg-bg-surface p-2.5 text-left active:scale-[0.98] ${
        collection.is_complete ? "ring-1 ring-amber-300/40" : ""
      }`}
    >
      <span className="absolute right-2 top-1 font-mono text-[9px] font-bold uppercase tracking-wider text-ink-mist-dim">Стр. {page}</span>
      {collection.is_complete && <CompleteStamp size={46} className="absolute right-7 top-1/2 -translate-y-1/2 opacity-80" />}
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
        {collection.available_from ? (
          <p className="mt-1 text-micro font-bold text-amber-300">🔒 Доступна с {availableFromLabel(collection.available_from)}</p>
        ) : collection.is_complete ? (
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

function AlbumDetail({
  collectionId, pages, ownerId, onGo, onBack,
}: {
  collectionId: number;
  pages: number[];
  ownerId?: number;
  onGo: (id: number) => void;
  onBack: () => void;
}) {
  const [search, setSearch] = useState("");
  // Same saved default filter as «Мои карты» (rarity/country/club/position).
  const { filter, setFilter, defaultFilter } = useCardFilter();
  const { data, isLoading } = useQuery({
    queryKey: ["album-detail", collectionId, search, ownerId ?? "me"],
    queryFn: () => fetchAlbumCollectionDetail(collectionId, search || undefined, ownerId),
  });
  // «Золотая страница»: every footballer of a finished page in a rare print.
  const golden = !!data && data.is_complete && data.total_count > 0 && (data.finished_count ?? 0) >= data.total_count;

  const {
    detailCard, setDetailCard, confirmSell, setConfirmSell,
    upgradeCard, setUpgradeCard, sellMutation, hideMutation,
  } = useCardActions([["album-detail"], ["album-overview"], ["collection"], ["collection-stats"]]);
  const visible = (data?.players ?? []).filter((slot) => matchesPlayer(filter, slot.player));
  const want = useWantToggle();

  // Page flipping: arrows and a sideways swipe go to the neighbour page.
  const at = pages.indexOf(collectionId);
  const prev = at > 0 ? pages[at - 1] : null;
  const next = at >= 0 && at < pages.length - 1 ? pages[at + 1] : null;
  const flip = (id: number | null) => {
    if (id === null) return;
    haptic("light");
    onGo(id);
  };
  const onSwipe = (_: unknown, info: PanInfo) => {
    if (Math.abs(info.offset.x) < 70 || Math.abs(info.offset.y) > Math.abs(info.offset.x)) return;
    flip(info.offset.x < 0 ? next : prev);
  };

  // Stickers got since the last visit of this page are pressed in.
  const ownedIds = useMemo(
    () => (data?.players ?? []).filter((p) => p.owned).map((p) => p.player.id),
    [data?.players],
  );
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const ownedKey = ownedIds.join(",");
  const loaded = !!data;
  useEffect(() => {
    if (!loaded || search || ownerId) return;
    setFresh(freshOnPage(collectionId, ownedIds));
    markPageSeen(collectionId, ownedIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectionId, ownedKey, loaded, search]);
  const numberOf = new Map((data?.players ?? []).map((p, i) => [p.player.id, i + 1]));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={onBack} aria-label="К альбому" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-bg-surface active:scale-95">
          <IconChevronLeft size={16} />
        </button>
        <p className="min-w-0 flex-1 truncate font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-amber-200/70">
          Альбом{at >= 0 ? ` · стр. ${at + 1} из ${pages.length}` : ""}
        </p>
        <button
          onClick={() => flip(prev)}
          disabled={prev === null}
          aria-label="Предыдущая страница"
          className="flex h-9 w-9 items-center justify-center rounded-xl bg-bg-surface active:scale-95 disabled:opacity-30"
        >
          <IconChevronLeft size={16} />
        </button>
        <button
          onClick={() => flip(next)}
          disabled={next === null}
          aria-label="Следующая страница"
          className="flex h-9 w-9 items-center justify-center rounded-xl bg-bg-surface active:scale-95 disabled:opacity-30"
        >
          <IconChevronRight size={16} />
        </button>
      </div>

      <div className="relative">
        <div className="flex items-start gap-3 pl-1">
          {data?.image_path && (
            <img src={staticUrl(data.image_path) ?? undefined} alt="" className="h-12 w-12 shrink-0 rounded-xl object-cover ring-1 ring-amber-200/20" />
          )}
          <div className="min-w-0 flex-1 pr-16">
            <p className="font-display text-lg font-black uppercase leading-tight tracking-wide text-ink-chalk">{data?.name ?? "…"}</p>
            {data && (
              <>
                <p className="mt-0.5 font-mono text-xs text-ink-mist">
                  {data.owned_count} / {data.total_count} наклеено
                </p>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-black/40">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${data.total_count ? Math.round((data.owned_count / data.total_count) * 100) : 0}%`,
                      background: data.is_complete ? "linear-gradient(90deg,#a07a2c,#f5d77a)" : "linear-gradient(90deg,#22d3ee,#bef264)",
                    }}
                  />
                </div>
              </>
            )}
          </div>
        </div>
        {data?.is_complete && <CompleteStamp size={66} golden={golden} className="absolute -right-1 -top-2" />}
      </div>

      {data?.available_from && (
        <div className="rounded-xl border border-amber-300/30 bg-amber-300/10 px-3 py-2.5 text-center text-xs font-semibold text-amber-200">
          🔒 Коллекция откроется {availableFromLabel(data.available_from)} — карточки будут только в юбилейном паке
        </div>
      )}
      {data && !ownerId && !data.is_complete && data.reward_coins > 0 && (
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
      {data?.is_complete && !ownerId && (
        <div className="rounded-xl bg-accent-lime/10 px-3 py-2.5 text-center text-xs font-semibold text-accent-lime">
          <IconParty size={14} className="mr-1 inline align-[-2px]" />Коллекция собрана{data.reward_coins > 0 ? ` — получено ${data.reward_coins} монет` : ""}!
        </div>
      )}
      {data?.is_complete && !search && (
        <div
          className={`rounded-xl px-3 py-2.5 text-center text-xs font-semibold ${
            golden ? "bg-gradient-to-r from-amber-300/25 via-yellow-200/20 to-amber-300/25 text-amber-200" : "bg-white/5 text-ink-mist"
          }`}
          data-testid="golden-page"
        >
          {golden
            ? "✨ Золотая страница — все футболисты в редких версиях!"
            : <>✨ Золотая страница: <b className="text-amber-200">{data.finished_count ?? 0}</b> / {data.total_count} в редких версиях</>}
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
      {!isLoading && !visible.length && !(data?.staff?.length && !search && !activeCount(filter)) && (
        <EmptyState
          icon={IconCollection}
          title="Никого не найдено"
          description={activeCount(filter) ? "Под этот фильтр никто не подходит — смени или очисти его" : "Попробуй другой запрос"}
        />
      )}

      {visible.length > 0 && (
        <motion.div
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.25 }}
          drag="x"
          dragConstraints={{ left: 0, right: 0 }}
          dragElastic={0.25}
          dragDirectionLock
          onDragEnd={onSwipe}
          className="touch-pan-y"
        >
          <AlbumPage>
            <div className="grid grid-cols-3 gap-x-2.5 gap-y-3 pl-1.5 pt-1">
              {visible.map((slot, i) => {
                const n = numberOf.get(slot.player.id) ?? i + 1;
                return (
                  <div key={slot.player.id} className="relative">
                    <SlotNumber n={n} />
                    {slot.owned && slot.card ? (
                      <Sticker seed={slot.player.id} fresh={fresh.has(slot.player.id)} delay={0.1 + Math.min(i, 8) * 0.06}>
                        <AlbumSlot slot={slot} number={n} onOpen={() => !ownerId && slot.card && setDetailCard(slot.card)} wanted={false} onToggleWant={() => {}} />
                      </Sticker>
                    ) : (
                      <AlbumSlot
                        slot={slot}
                        number={n}
                        onOpen={() => {}}
                        wanted={want.wanted.has(slot.player.id)}
                        onToggleWant={() => want.toggle(slot.player.id)}
                        canWant={!ownerId}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </AlbumPage>
        </motion.div>
      )}

      {!!data?.staff?.length && (
        <section className="flex flex-col gap-2">
          <p className="text-micro font-bold uppercase tracking-[0.12em] text-accent-cyan">Тренеры, стадионы и музы коллекции</p>
          <div className="grid grid-cols-3 gap-2">
            {data.staff.map((s) => <StaffSlot key={`${s.kind}-${s.id}`} staff={s} />)}
          </div>
        </section>
      )}

      {detailCard && (
        <CardDetailModal
          key={detailCard.id}
          onOpenCopy={setDetailCard}
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
  number,
  onOpen,
  wanted,
  onToggleWant,
  canWant = true,
}: {
  slot: AlbumPlayer;
  number: number;
  onOpen: () => void;
  wanted: boolean;
  onToggleWant: () => void;
  canWant?: boolean;
}) {
  const canUpgrade = useSkillUpgradeCheck();
  if (!slot.owned || !slot.card) {
    // Diamonds never trade (except «Академия»), so they can't be in «Ищу».
    const wantable = canWant && (slot.player.rarity !== "diamond" || !!slot.player.path_talent_code);
    return (
      <div className="relative flex aspect-[3/4] flex-col items-center justify-center gap-1 overflow-hidden rounded-xl border border-dashed border-amber-100/15 bg-black/25 p-2 text-center shadow-[inset_0_2px_10px_rgba(0,0,0,0.5)]">
        <span aria-hidden="true" className="pointer-events-none absolute inset-0 flex items-center justify-center font-display text-5xl font-black text-white/[0.04]">
          {number}
        </span>
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
      serial={slot.card.serial_number}
      finish={slot.card.finish}
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


/** A coach or stadium of the collection: art in its rarity frame, its
 * effects, greyed out until owned. */
function StaffSlot({ staff }: { staff: AlbumStaff }) {
  return (
    <div className={`rounded-xl bg-gradient-to-b p-[1.5px] ${RARITY_GRADIENTS[staff.rarity]} ${staff.owned ? "" : "opacity-45 grayscale"}`}>
      <div className="flex flex-col gap-0.5 rounded-[10px] bg-bg-surface p-1">
        <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-black/40">
          {staff.image_path ? (
            <img decoding="async" loading="lazy" src={staticUrl(staff.image_path) ?? undefined} alt="" className="h-full w-full object-cover" />
          ) : (
            <span className="flex h-full w-full items-center justify-center text-3xl">{staff.kind === "stadium" ? "🏟️" : staff.kind === "muse" ? staff.icon || "💃" : "🧥"}</span>
          )}
          <span className="absolute left-0.5 top-0.5 rounded bg-black/75 px-1 text-micro font-bold text-ink-chalk">
            {STAFF_LABELS[staff.kind]}
          </span>
        </div>
        <p className="truncate text-center text-micro font-bold text-ink-chalk">{staff.name}</p>
        {staff.effects.slice(0, 2).map((e) => (
          <p key={e} className={`truncate text-center text-[10px] font-semibold leading-tight ${e.startsWith("−") ? "text-red-300" : "text-accent-lime"}`}>{e}</p>
        ))}
      </div>
    </div>
  );
}

const STAFF_LABELS: Record<AlbumStaff["kind"], string> = { coach: "Тренер", stadium: "Стадион", muse: "Муза" };
