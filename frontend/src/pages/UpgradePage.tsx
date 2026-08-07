import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchCollection, fetchUpgradeRules, type CollectionFilters } from "@/api/collection";
import CardUpgradeModal from "@/components/cards/CardUpgradeModal";
import PlayerCard from "@/components/cards/PlayerCard";
import EmptyState from "@/components/common/EmptyState";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import { IconChevronRight, IconCoin, IconUpgrade } from "@/components/icons";
import { RARITY_GRADIENTS, RARITY_LABELS } from "@/lib/rarity";
import type { Rarity, UserCard } from "@/types";

const RARITY_SEQUENCE: Rarity[] = ["common", "rare", "epic", "legendary"];

export default function UpgradePage() {
  const { data: rules, isLoading: rulesLoading } = useQuery({ queryKey: ["upgrade-rules"], queryFn: fetchUpgradeRules });
  const upgradeableRarities = RARITY_SEQUENCE.filter((r) => rules?.some((rule) => rule.from_rarity === r && rule.is_active));

  const [rarity, setRarity] = useState<Rarity | null>(null);
  const [upgradeCard, setUpgradeCard] = useState<UserCard | null>(null);
  const effectiveRarity = rarity ?? upgradeableRarities[0] ?? null;
  const currentRule = rules?.find((r) => r.from_rarity === effectiveRarity && r.is_active);

  const filters: CollectionFilters = {
    rarity: effectiveRarity ?? undefined,
    sort_by: "rating",
    sort_dir: "desc",
    page_size: 60,
  };
  const { data: page, isLoading } = useQuery({
    queryKey: ["collection", "upgrade", effectiveRarity],
    queryFn: () => fetchCollection(filters),
    enabled: !!effectiveRarity,
  });

  return (
    <div className="flex flex-col gap-5">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-amber-500/25 via-orange-600/10 to-bg-surface p-5">
        <ForgeSparks />
        <div className="relative flex items-center gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-amber-400/20 text-amber-300">
            <IconUpgrade size={24} />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold text-ink-chalk">Кузница апгрейдов</h1>
            <p className="text-xs text-ink-mist">Рискни карточкой и монетами — получи более редкую взамен</p>
          </div>
        </div>

        {!!RARITY_SEQUENCE.length && (
          <div className="relative mt-4 flex items-center gap-1.5 overflow-x-auto pb-1">
            {RARITY_SEQUENCE.map((r, i) => (
              <div key={r} className="flex shrink-0 items-center gap-1.5">
                <span
                  className={`rounded-full bg-gradient-to-b ${RARITY_GRADIENTS[r]} px-2.5 py-1 font-mono text-[10px] font-bold text-white ${
                    effectiveRarity === r ? "ring-2 ring-amber-300" : ""
                  }`}
                >
                  {RARITY_LABELS[r]}
                </span>
                {i < RARITY_SEQUENCE.length - 1 && <IconChevronRight size={12} className="text-ink-mist-dim" />}
              </div>
            ))}
          </div>
        )}

        {currentRule && (
          <div className="relative mt-4 flex items-center gap-3 rounded-2xl bg-black/20 px-3 py-2.5">
            <span className="font-mono text-xs text-ink-mist">
              Шанс успеха <span className="font-bold text-accent-cyan">{Math.round(currentRule.success_chance * 100)}%</span>
            </span>
            <span className="h-3 w-px bg-white/10" />
            <span className="flex items-center gap-1 font-mono text-xs text-amber-300">
              <IconCoin size={12} />
              {currentRule.coin_cost}
            </span>
          </div>
        )}
      </section>

      {!rulesLoading && upgradeableRarities.length === 0 && (
        <EmptyState icon={IconUpgrade} title="Апгрейд пока недоступен" description="Загляни позже — правила ещё не настроены" />
      )}

      {upgradeableRarities.length > 0 && (
        <>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {upgradeableRarities.map((r) => (
              <button
                key={r}
                onClick={() => setRarity(r)}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${
                  effectiveRarity === r ? "bg-amber-400 text-bg-base" : "bg-white/5 text-ink-mist"
                }`}
              >
                {RARITY_LABELS[r]}
              </button>
            ))}
          </div>

          {isLoading && <CardGridSkeleton count={9} />}
          {!isLoading && !page?.items.length && (
            <EmptyState
              icon={IconUpgrade}
              title="Нечего улучшать"
              description={`Нет карточек редкости «${RARITY_LABELS[effectiveRarity!]}» — открой паки, чтобы получить их`}
            />
          )}

          <div className="grid grid-cols-3 gap-2">
            {page?.items.map((card) => (
              <PlayerCard key={card.id} player={card.player} onClick={() => setUpgradeCard(card)} />
            ))}
          </div>
        </>
      )}

      {upgradeCard && <CardUpgradeModal card={upgradeCard} onClose={() => setUpgradeCard(null)} />}
    </div>
  );
}

function ForgeSparks() {
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.12]" viewBox="0 0 320 160" fill="none">
      <circle cx="280" cy="26" r="2" fill="currentColor" className="text-amber-300" />
      <circle cx="292" cy="44" r="1.5" fill="currentColor" className="text-amber-300" />
      <circle cx="264" cy="52" r="1.5" fill="currentColor" className="text-amber-300" />
      <path d="M240 10 Q260 40 230 70" stroke="currentColor" strokeWidth="1" className="text-amber-300" fill="none" />
      <circle cx="30" cy="120" r="2" fill="currentColor" className="text-orange-400" />
      <circle cx="48" cy="100" r="1.5" fill="currentColor" className="text-orange-400" />
    </svg>
  );
}
