import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchUpgradeableCards, fetchUpgradeRules } from "@/api/collection";
import CardUpgradeModal from "@/components/cards/CardUpgradeModal";
import PlayerCard from "@/components/cards/PlayerCard";
import EmptyState from "@/components/common/EmptyState";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import { IconChevronRight, IconCoin, IconUpgrade } from "@/components/icons";
import { effectiveUpgradeChance } from "@/lib/cardUpgrade";
import { RARITY_GRADIENTS, RARITY_LABELS } from "@/lib/rarity";
import type { Rarity, UserCard } from "@/types";

const RARITY_SEQUENCE: Rarity[] = ["common", "rare", "epic", "legendary"];

// Mirrors the backend's MAX_STAKED_CARDS (schemas/card_upgrade.py) — purely
// a client-side UX cap, the server is the actual source of truth.
const MAX_STAKED_CARDS = 10;

export default function UpgradePage() {
  const { data: rules, isLoading: rulesLoading } = useQuery({ queryKey: ["upgrade-rules"], queryFn: fetchUpgradeRules });
  const upgradeableRarities = RARITY_SEQUENCE.filter((r) => rules?.some((rule) => rule.from_rarity === r && rule.is_active));

  const [rarity, setRarity] = useState<Rarity | null>(null);
  const [selected, setSelected] = useState<UserCard[]>([]);
  const [upgrading, setUpgrading] = useState(false);
  const effectiveRarity = rarity ?? upgradeableRarities[0] ?? null;
  const currentRule = rules?.find((r) => r.from_rarity === effectiveRarity && r.is_active);

  const selectRarity = (r: Rarity) => {
    setRarity(r);
    setSelected([]);
  };

  const toggleCard = (card: UserCard) => {
    setSelected((prev) => {
      if (prev.some((c) => c.id === card.id)) return prev.filter((c) => c.id !== card.id);
      if (prev.length >= MAX_STAKED_CARDS) return prev;
      return [...prev, card];
    });
  };

  // Every individual unlocked card of this rarity — not deduplicated by
  // player (unlike the general collection browse endpoint), so duplicates
  // of the same player each show as their own selectable tile, and locked
  // cards (in a lineup, a Tactico squad, a pending trade, or frozen by an
  // admin) never appear as an option in the first place.
  const { data: cards, isLoading } = useQuery({
    queryKey: ["upgrade-cards", effectiveRarity],
    queryFn: () => fetchUpgradeableCards(effectiveRarity!),
    enabled: !!effectiveRarity,
  });

  const previewChance = currentRule && selected.length > 0 ? effectiveUpgradeChance(currentRule, selected.length) : null;
  const previewCost = currentRule ? currentRule.coin_cost * Math.max(1, selected.length) : null;

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
          <div className="relative mt-4 flex flex-wrap items-center gap-3 rounded-2xl bg-black/20 px-3 py-2.5">
            <span className="font-mono text-xs text-ink-mist">
              Шанс успеха{" "}
              <span className="font-bold text-accent-cyan">
                {Math.round((previewChance ?? currentRule.success_chance) * 100)}%
              </span>
            </span>
            <span className="h-3 w-px bg-white/10" />
            <span className="flex items-center gap-1 font-mono text-xs text-amber-300">
              <IconCoin size={12} />
              {previewCost ?? currentRule.coin_cost}
            </span>
            {currentRule.extra_card_bonus > 0 && (
              <span className="w-full text-[10px] text-ink-mist-dim">
                Ставь несколько карт этой редкости разом — шанс растёт (максимум {Math.round(currentRule.max_success_chance * 100)}%)
              </span>
            )}
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
                onClick={() => selectRarity(r)}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${
                  effectiveRarity === r ? "bg-amber-400 text-bg-base" : "bg-white/5 text-ink-mist"
                }`}
              >
                {RARITY_LABELS[r]}
              </button>
            ))}
          </div>

          {isLoading && <CardGridSkeleton count={9} />}
          {!isLoading && !cards?.length && (
            <EmptyState
              icon={IconUpgrade}
              title="Нечего улучшать"
              description={`Нет доступных карточек редкости «${RARITY_LABELS[effectiveRarity!]}» — открой паки, или освободи карточки из состава/обмена`}
            />
          )}

          <div className="grid grid-cols-3 gap-2 pb-20">
            {cards?.map((card) => (
              <PlayerCard
                key={card.id}
                player={card.player}
                selected={selected.some((c) => c.id === card.id)}
                onClick={() => toggleCard(card)}
              />
            ))}
          </div>
        </>
      )}

      {selected.length > 0 && (
        <div className="safe-bottom fixed inset-x-0 bottom-16 z-20 flex justify-center px-4">
          <div className="flex w-full max-w-md items-center gap-3 rounded-2xl border border-amber-400/20 bg-bg-surface p-3 shadow-lg">
            <button
              onClick={() => setSelected([])}
              className="rounded-xl bg-white/5 px-3 py-2 text-xs font-semibold text-ink-mist active:scale-95"
            >
              Сбросить
            </button>
            <div className="flex-1 text-xs text-ink-mist">
              Выбрано: <b className="text-ink-chalk">{selected.length}</b>
              {previewChance !== null && (
                <>
                  {" "}
                  · шанс <b className="text-accent-cyan">{Math.round(previewChance * 100)}%</b>
                </>
              )}
            </div>
            <button
              onClick={() => setUpgrading(true)}
              className="rounded-xl bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95"
            >
              Апгрейд
            </button>
          </div>
        </div>
      )}

      {upgrading && selected.length > 0 && (
        <CardUpgradeModal
          cards={selected}
          onClose={() => {
            setUpgrading(false);
            setSelected([]);
          }}
        />
      )}
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
