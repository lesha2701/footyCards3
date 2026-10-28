import type { ReactNode } from "react";

import RewardModal, { RewardCard, RewardCoins, RewardPack } from "@/components/common/RewardModal";
import { UserBadge } from "@/components/common/UserBadge";
import { IconCoin, IconCollection, IconPack, IconStar } from "@/components/icons";
import { RARITY_LABELS, RARITY_TEXT } from "@/lib/rarity";
import type { GrantedRewards, Rarity, RewardBundle } from "@/types";

const RARITY_RANK: Record<Rarity, number> = { common: 0, rare: 1, epic: 2, legendary: 3, diamond: 4 };

/** "What's inside" of one reward slot, as small chips — shown before
 * claiming or paying, so a purchase never hides its contents. */
export function RewardBundleChips({ bundle, compact = false }: { bundle: RewardBundle; compact?: boolean }) {
  const chip = "flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-caption text-ink-chalk";
  return (
    <div className={`flex flex-wrap items-center ${compact ? "justify-center gap-1" : "gap-1.5"}`}>
      {bundle.coins > 0 && (
        <span className={chip}>
          <IconCoin size={12} className="text-accent-lime" />
          <span className="font-mono">{bundle.coins}</span>
        </span>
      )}
      {bundle.pack_name && (
        <span className={chip}>
          <IconPack size={12} className="text-accent-cyan" />
          {!compact && <span>Пак «{bundle.pack_name}»</span>}
        </span>
      )}
      {bundle.card_rarity && (
        <span className={chip}>
          <IconCollection size={12} className={RARITY_TEXT[bundle.card_rarity]} />
          {!compact && <span>Карточка: {RARITY_LABELS[bundle.card_rarity].toLowerCase()}</span>}
        </span>
      )}
      {bundle.badge && (
        <span className={chip}>
          <UserBadge badge={bundle.badge} className="h-3 w-3" />
          {!compact && <span>{bundle.badge.name}</span>}
        </span>
      )}
      {bundle.cosmetic && (
        <span className={chip}>
          <IconStar size={12} className="text-amber-300" />
          {!compact && <span>{bundle.cosmetic.name}</span>}
        </span>
      )}
    </div>
  );
}

function grantedItems(granted: GrantedRewards, keyPrefix: string): JSX.Element[] {
  return [
    granted.coins > 0 && <RewardCoins key={`${keyPrefix}-coins`} amount={granted.coins} />,
    granted.pack_name && <RewardPack key={`${keyPrefix}-pack`} name={granted.pack_name} />,
    ...granted.cards.map((card) => <RewardCard key={`${keyPrefix}-card-${card.id}`} card={card} />),
    granted.badge && (
      <p key={`${keyPrefix}-badge`} className="flex items-center gap-1.5 text-sm font-semibold text-ink-chalk">
        <UserBadge badge={granted.badge} /> Значок «{granted.badge.name}»
      </p>
    ),
    granted.cosmetic && (
      <p key={`${keyPrefix}-cosmetic`} className="flex items-center gap-1.5 text-sm font-semibold text-amber-300">
        <IconStar size={14} /> «{granted.cosmetic.name}» — надень в «Стиле»
      </p>
    ),
  ].filter(Boolean) as JSX.Element[];
}

/** The shared "you got it" modal for every reward of these features. */
export function GrantedRewardModal({
  title, subtitle, granted, bonus, hero, onClose,
}: {
  title: string;
  subtitle?: string;
  granted: GrantedRewards;
  /** A bigger picture in place of the confetti icon (e.g. the opened chest). */
  hero?: ReactNode;
  /** Optional second reward (e.g. the month-completion bonus). */
  bonus?: GrantedRewards | null;
  onClose: () => void;
}) {
  const items = grantedItems(granted, "main");
  if (bonus) {
    items.push(<p key="bonus-title" className="mt-2 font-display text-sm font-bold text-amber-300">Бонус за весь месяц!</p>);
    items.push(...grantedItems(bonus, "bonus"));
  }
  const cards = [...granted.cards, ...(bonus?.cards ?? [])];
  const best = cards.reduce<Rarity | null>(
    (acc, c) => (acc === null || RARITY_RANK[c.player.rarity] > RARITY_RANK[acc] ? c.player.rarity : acc), null,
  );
  return <RewardModal title={title} subtitle={subtitle} hero={hero} rarity={best} items={items} onClose={onClose} />;
}
