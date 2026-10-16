import { useEffect, useRef, useState } from "react";

import { STAGES, STAGE_DURATION_MS } from "@/components/cards/revealStages";
import { RevealStage } from "@/components/cards/CardRevealStage";
import { UserBadge } from "@/components/common/UserBadge";
import { IconTag } from "@/components/icons";
import RewardModal from "@/components/common/RewardModal";
import { haptic } from "@/lib/telegram";
import { prizeLabel } from "@/lib/wheel";
import type { CollectionRewardGrant, WheelSpinResult } from "@/types";

function CollectionGrants({ grants }: { grants: CollectionRewardGrant[] }) {
  if (!grants.length) return null;
  return (
    <div className="flex flex-col gap-1.5">
      {grants.map((grant) => (
        <p key={grant.collection_id} className="flex items-center justify-center gap-1 text-xs font-semibold text-accent-lime">
          <IconTag size={12} />
          Коллекция «{grant.collection_name}» собрана! +{grant.reward_coins}
          {grant.granted_pack ? ` + пак «${grant.granted_pack.pack.name}»` : ""}
        </p>
      ))}
    </div>
  );
}

/** What a wheel spin won: a staged card reveal for a card prize, otherwise a
 * modal (coins, badge). Pack prizes are handled by the caller (they navigate
 * to the pack-opening flow instead). */
export function WheelPrizeResult({ result, onClose }: { result: WheelSpinResult; onClose: () => void }) {
  const [cardStageIndex, setCardStageIndex] = useState(0);
  const cardTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-advances the card-reveal stages, mirroring PackOpenPage's own timer
  // effect — a wheel-won single card gets the same staged reveal a pack's
  // cards get, just without the "next card" progression (there's only one).
  useEffect(() => {
    if (!result.card_result || cardStageIndex >= STAGES.length - 1) return;
    cardTimerRef.current = setTimeout(() => setCardStageIndex((i) => i + 1), STAGE_DURATION_MS);
    return () => {
      if (cardTimerRef.current) clearTimeout(cardTimerRef.current);
    };
  }, [result, cardStageIndex]);

  if (result.card_result) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col bg-bg-base">
        <button
          onClick={() => setCardStageIndex(STAGES.length - 1)}
          className="safe-top absolute right-4 top-4 z-10 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold text-ink-chalk"
        >
          Пропустить
        </button>
        <RevealStage
          opened={result.card_result}
          stage={STAGES[cardStageIndex]}
          index={0}
          total={1}
          onTap={() => {
            haptic("light");
            if (cardTimerRef.current) clearTimeout(cardTimerRef.current);
            if (cardStageIndex < STAGES.length - 1) setCardStageIndex((i) => i + 1);
          }}
        />
        {cardStageIndex === STAGES.length - 1 && (
          <div className="safe-bottom flex flex-col gap-3 px-6 pb-6 pt-2">
            <CollectionGrants grants={result.collection_rewards} />
            <button
              onClick={onClose}
              className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
            >
              Готово
            </button>
          </div>
        )}
      </div>
    );
  }

  const items = [
    result.badge_result ? (
      <div key="badge" className="flex flex-col items-center gap-2">
        <UserBadge badge={result.badge_result} className="h-10 w-10 text-3xl" />
        <p className="text-sm font-semibold text-ink-chalk">{result.badge_result.name}</p>
      </div>
    ) : (
      <p key="prize" className="text-sm font-semibold text-ink-chalk">{prizeLabel(result.prize)}</p>
    ),
    result.collection_rewards.length > 0 && <CollectionGrants key="grants" grants={result.collection_rewards} />,
  ].filter(Boolean) as JSX.Element[];
  return (
    <RewardModal
      title={result.duplicate_badge_coins ? `+${result.duplicate_badge_coins} монет` : "Приз получен!"}
      subtitle={result.duplicate_badge_coins ? "Такой значок у тебя уже был" : undefined}
      items={items}
      onClose={onClose}
    />
  );
}
