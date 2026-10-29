import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchCardStars, setCardsLocked } from "@/api/collection";
import { fetchActiveLineup, setActiveLineup } from "@/api/lineups";
import { fetchPathState } from "@/api/path";
import DiamondFeedModal from "@/components/cards/DiamondFeedModal";
import { IconCoin, IconLock, IconLockOpen, IconPlay, IconStar, IconTag, IconUpgrade } from "@/components/icons";
import CardSkillPanel from "@/components/collection/CardSkillPanel";
import CardStarPanel from "@/components/collection/CardStarPanel";
import CardEquipmentPanel from "@/components/equipment/CardEquipmentPanel";
import ShareButton from "@/components/common/ShareButton";
import PathPanel from "@/components/path/PathPanel";
import { staticUrl } from "@/lib/api";
import { squadLabel } from "@/lib/cardLocks";
import { formatGameError } from "@/lib/errors";
import { planArenaPlacement } from "@/lib/lineupPlacement";
import { useSwipeDownToClose } from "@/lib/useSwipe";
import { haptic } from "@/lib/telegram";
import { pathFrameClass } from "@/lib/pathCards";
import { prestigeMarks, prestigeStyle } from "@/lib/prestige";
import { POSITION_LABELS, RARITY_GLOW_STATIC, RARITY_GRADIENTS, RARITY_LABELS } from "@/lib/rarity";
import type { UserCard } from "@/types";

type Tab = "overview" | "path" | "skill" | "stars" | "equipment";

/** Card detail sheet: a compact header (image, name, rating), tabs instead of
 * one long scroll (Обзор / Путь / Навык / Звёзды — only the ones that apply
 * to this copy) and a sticky action bar, so «Продать» and «Закрыть» are
 * always reachable without scrolling. */
export default function CardDetailModal({
  card,
  onClose,
  onSell,
  onToggleHidden,
  hiddenPending,
  onUpgrade,
}: {
  card: UserCard;
  onClose: () => void;
  onSell: () => void;
  onToggleHidden: (hidden: boolean) => void;
  hiddenPending: boolean;
  onUpgrade?: () => void;
}) {
  const player = card.player;
  const isDiamond = player.rarity === "diamond";
  const isPath = !!player.path_talent_code;
  const queryClient = useQueryClient();
  // The `card` prop is a snapshot: these follow what's done from this sheet.
  const [userLocked, setUserLocked] = useState(!!card.is_user_locked);
  const [inArena, setInArena] = useState(card.is_in_lineup);
  const [notice, setNotice] = useState<string | null>(null);
  const [feeding, setFeeding] = useState(false);
  const frozen = card.is_locked_by_admin || card.is_locked_in_trade;
  const squad = squadLabel({ ...card, is_in_lineup: inArena });
  // Selling needs a free copy: not frozen, not in a squad, not under the lock.
  const locked = frozen || !!squad || userLocked;
  const [tab, setTab] = useState<Tab>(isPath ? "path" : "overview");
  // Pull the grab handle / header down to close the sheet.
  const swipeDown = useSwipeDownToClose(onClose);

  const refreshLists = () => {
    for (const key of [["collection"], ["album-detail"], ["upgrade-cards"], ["academy"], ["lineup"], ["lineup-templates"]]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };

  const lockMutation = useMutation({
    mutationFn: (next: boolean) => setCardsLocked([card.id], next),
    onSuccess: (data) => {
      haptic("light");
      setUserLocked(data.locked);
      setNotice(data.locked ? "🔒 Карточка под замком: её не продать и не сжечь" : "Замок снят");
      refreshLists();
    },
    onError: (err) => setNotice(formatGameError(err, "Не удалось поставить замок")),
  });

  // «В состав Card Arena» straight from the card: picks the slot itself.
  const arenaMutation = useMutation({
    mutationFn: async () => {
      const plan = planArenaPlacement(await fetchActiveLineup(), card);
      if (!plan.ok) throw new Error(plan.reason);
      await setActiveLineup(plan.slots);
      return plan;
    },
    onSuccess: (plan) => {
      haptic("medium");
      setInArena(true);
      setNotice(plan.ok && plan.replaced
        ? `В составе Card Arena вместо «${plan.replaced.player.display_name}»`
        : "Поставлена в состав Card Arena");
      refreshLists();
    },
    onError: (err) => setNotice(formatGameError(err, "Не удалось поставить в состав")),
  });
  // Same cache entry CardStarPanel reads, so feeding duplicates updates the
  // rating shown here right away (the `card` prop is a snapshot).
  const { data: starState } = useQuery({
    queryKey: ["card-stars", card.id],
    queryFn: () => fetchCardStars(card.id),
    enabled: !isDiamond,
  });
  // «Академия»: prestige raises the quick-sell price (server-computed).
  const { data: pathState } = useQuery({
    queryKey: ["path", card.id],
    queryFn: () => fetchPathState(card.id),
    enabled: isPath,
  });
  const sellPrice = pathState?.prestige?.sell_price ?? player.quick_sell_price;
  const rating = starState?.rating_now ?? player.rating;
  const starBonus = starState?.rating_bonus ?? card.star_rating_bonus ?? 0;
  const tabs: [Tab, string][] = [
    ["overview", "Обзор"],
    ...(isPath ? ([["path", "Путь"]] as [Tab, string][]) : []),
    ["skill", "Навык"],
    ...(!isDiamond ? ([["stars", "Звёзды"]] as [Tab, string][]) : []),
    ["equipment", "Вещи"],
  ];
  // The sheet keeps a static frame: a shine band would sweep over its text.
  const frame = isPath
    ? `bg-gradient-to-b ${pathFrameClass(card.path_stage, card.prestige).replace(" card-shine", "")} p-[3px]`
    : isDiamond
      ? `bg-gradient-to-b ${RARITY_GRADIENTS.diamond} p-[3px] ${RARITY_GLOW_STATIC.diamond}`
      : "border border-white/10 bg-bg-surface";

  return (
    // Bottom sheet on phones, centered card on wider screens.
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        className={`flex max-h-[92vh] w-full max-w-md flex-col overflow-hidden rounded-t-3xl sm:max-w-sm sm:rounded-3xl ${frame}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={player.display_name}
      >
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-t-[21px] bg-bg-surface sm:rounded-[21px]">
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pt-3">
            <div {...swipeDown}>
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/15 sm:hidden" aria-hidden />
            <div className="flex gap-3">
              <div className="relative w-28 shrink-0">
                <img loading="lazy"
                  src={staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                  alt={player.display_name}
                  className="aspect-[3/4] w-full rounded-2xl object-cover"
                  decoding="async"
                />
                <span className="absolute left-1.5 top-1.5 rounded-md bg-black/70 px-1.5 py-0.5 font-display text-base font-bold leading-none text-white">
                  {rating}
                </span>
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-display text-lg font-bold leading-tight text-ink-chalk">{player.display_name}</p>
                <p className="mt-0.5 text-sm text-ink-mist">{POSITION_LABELS[player.position]} · {player.club}</p>
                <p className="mt-1 text-xs text-ink-mist">
                  {isPath ? "🌱 Академия" : RARITY_LABELS[player.rarity]} · № {card.serial_number}
                </p>
                {(card.prestige ?? 0) > 0 && (
                  <p className={`mt-1 inline-block rounded-full px-2 py-0.5 text-caption font-bold ${prestigeStyle(card.prestige!).chip}`}>
                    {prestigeMarks(card.prestige!)} Престиж
                  </p>
                )}
                {card.prestige_icon_number != null && (
                  <p className="mt-1 text-xs font-bold text-prestige">Икона Академии №{card.prestige_icon_number}</p>
                )}
                <p className="mt-1 text-xs text-ink-mist">
                  АТК <b className="font-mono text-accent-cyan">{player.attack_rating}</b> · ЗЩТ{" "}
                  <b className="font-mono text-accent-cyan">{player.defense_rating}</b>
                </p>
                {starBonus > 0 && <p className="text-xs text-amber-300">+{starBonus} от звёзд</p>}
                {!!card.path_rating_bonus && <p className="text-xs text-path">+{card.path_rating_bonus} от пути 🌱</p>}
                {!!card.equipment_rating_bonus && <p className="text-xs text-accent-lime">+{card.equipment_rating_bonus} от экипировки</p>}
              </div>
            </div>
            </div>

            {tabs.length > 1 && (
              <div role="tablist" className="mt-4 flex gap-1 rounded-2xl bg-black/20 p-1">
                {tabs.map(([value, label]) => (
                  <button
                    key={value}
                    role="tab"
                    aria-selected={tab === value}
                    onClick={() => setTab(value)}
                    className={`min-h-[36px] flex-1 rounded-xl text-xs font-semibold ${
                      tab === value ? "bg-bg-raised text-ink-chalk" : "text-ink-mist"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}

            <div className="pb-3">
              {tab === "overview" && (
                <div className="mt-3 space-y-2">
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <span className="text-ink-mist">Редкость: <b className="text-ink-chalk">{RARITY_LABELS[player.rarity]}</b></span>
                    <span className="text-ink-mist">Страна: <b className="text-ink-chalk">{player.country}</b></span>
                  </div>
                  {player.collection_name && (
                    <p className="flex items-center gap-1 text-xs font-semibold text-accent-lime">
                      <IconTag size={12} />
                      Коллекция: {player.collection_name}
                    </p>
                  )}
                  {(frozen || squad) && (
                    <p className="flex items-center gap-1.5 text-xs text-ink-mist">
                      <IconLock size={13} />
                      {squad
                        ? `Играет — ${squad}. Качать можно, продать — нет`
                        : card.is_locked_in_trade ? "Заблокирована (в обмене)" : "Заблокирована администратором"}
                    </p>
                  )}

                  <section className="flex flex-col gap-2 rounded-2xl bg-black/20 p-2.5" aria-label="Прокачка">
                    <p className="px-0.5 text-micro font-semibold uppercase tracking-wider text-ink-mist-dim">Прокачка</p>
                    {!inArena && !frozen && (
                      <ActionButton onClick={() => arenaMutation.mutate()} disabled={arenaMutation.isPending} icon={<IconPlay size={15} />}>
                        В состав Card Arena
                      </ActionButton>
                    )}
                    {isDiamond && !isPath && (
                      <ActionButton onClick={() => setFeeding(true)} disabled={frozen} icon={<IconStar size={15} />}>
                        Поднять рейтинг бриллианта
                      </ActionButton>
                    )}
                    {onUpgrade && (
                      <ActionButton onClick={onUpgrade} disabled={frozen || userLocked} icon={<IconUpgrade size={15} />}>
                        {userLocked ? "Кузница: сначала сними замок" : "Апгрейд редкости в Кузнице"}
                      </ActionButton>
                    )}
                    <p className="px-0.5 text-micro text-ink-mist-dim">
                      {isPath
                        ? "Путь, попытки и престиж — во вкладке «Путь»; навык — во вкладке «Навык»."
                        : isDiamond
                          ? "Навык — во вкладке «Навык»."
                          : "Звёзды и навык — в своих вкладках выше."}
                    </p>
                  </section>

                  <label className="flex min-h-[44px] items-center justify-between gap-3 rounded-xl bg-black/20 px-3 py-2">
                    <span className="flex flex-col">
                      <span className="flex items-center gap-1.5 text-xs font-semibold text-ink-chalk">
                        {userLocked ? <IconLock size={13} className="text-amber-300" /> : <IconLockOpen size={13} />} Замок
                      </span>
                      <span className="text-micro text-ink-mist-dim">Защита от продажи и сжигания в прокачке</span>
                    </span>
                    <input
                      type="checkbox"
                      checked={userLocked}
                      disabled={lockMutation.isPending}
                      onChange={(e) => lockMutation.mutate(e.target.checked)}
                      className="h-5 w-5 shrink-0 accent-amber-400"
                      aria-label="Замок"
                    />
                  </label>
                  <label className="flex min-h-[44px] items-center justify-between gap-3 rounded-xl bg-black/20 px-3 py-2">
                    <span className="text-xs text-ink-mist">Скрыть от предложений обмена</span>
                    <input
                      type="checkbox"
                      checked={card.hidden_from_trade}
                      disabled={hiddenPending}
                      onChange={(e) => onToggleHidden(e.target.checked)}
                      className="h-5 w-5 shrink-0 accent-accent-lime"
                    />
                  </label>
                  {card.from_free_source && (player.rarity === "legendary" || player.rarity === "diamond" || !!player.path_talent_code) && (
                    <p className="rounded-xl bg-black/20 px-3 py-2 text-xs text-ink-mist">
                      🔒 Привязана к аккаунту: получена бесплатно (награда, бесплатный пак, колесо), поэтому её нельзя обменять.
                      Играть ею, улучшать и продавать системе можно.
                    </p>
                  )}
                  {(player.rarity === "legendary" || player.rarity === "diamond") && (
                    <ShareButton kind="card" id={card.id} label="Похвастаться в Telegram" />
                  )}
                </div>
              )}
              {tab === "path" && isPath && (
                <PathPanel key={`path-${card.id}`} cardId={card.id} player={player} card={card} inArena={inArena} />
              )}
              {tab === "skill" && <CardSkillPanel key={card.id} cardId={card.id} />}
              {tab === "stars" && <CardStarPanel key={`stars-${card.id}`} cardId={card.id} isDiamond={isDiamond} />}
              {tab === "equipment" && <CardEquipmentPanel key={`equipment-${card.id}`} cardId={card.id} />}
            </div>
          </div>

          {notice && (
            <p className="shrink-0 border-t border-white/10 bg-bg-surface px-4 pt-2 text-xs text-accent-lime" role="status">
              {notice}
            </p>
          )}
          <div className="flex shrink-0 gap-2 border-t border-white/10 bg-bg-surface px-4 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3">
            <button onClick={onClose} className="min-h-[44px] flex-1 rounded-2xl bg-white/5 text-sm font-semibold text-ink-mist">
              Закрыть
            </button>
            <button
              onClick={onSell}
              disabled={locked}
              className="flex min-h-[44px] flex-1 items-center justify-center gap-1.5 rounded-2xl bg-red-500 text-sm font-semibold text-white disabled:opacity-40"
            >
              {userLocked ? (
                <>
                  <IconLock size={13} /> Под замком
                </>
              ) : (
                <>
                  Продать за
                  <IconCoin size={13} />
                  {sellPrice}
                </>
              )}
            </button>
          </div>
        </div>
      </div>
      {feeding && <DiamondFeedModal card={card} onClose={() => { setFeeding(false); refreshLists(); }} />}
    </div>
  );
}

function ActionButton({
  onClick, disabled, icon, children,
}: {
  onClick: () => void;
  disabled?: boolean;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex min-h-[44px] w-full items-center justify-center gap-1.5 rounded-xl bg-bg-raised text-sm font-semibold text-accent-lime disabled:opacity-40"
    >
      {icon}
      {children}
    </button>
  );
}
