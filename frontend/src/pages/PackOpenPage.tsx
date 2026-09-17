import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { RevealStage, STAGES, STAGE_DURATION_MS } from "@/components/cards/CardRevealStage";
import { CoachRevealStage, COACH_STAGES, COACH_STAGE_DURATION_MS } from "@/components/cards/CoachRevealStage";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { UserBadge } from "@/components/common/UserBadge";
import { IconCoin, IconHandshake, IconTag } from "@/components/icons";
import { openPack, openPackBulk } from "@/api/packs";
import { useStarsPackPurchase } from "@/hooks/useStarsPackPurchase";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_LABELS } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { OpenedCard, OpenedCoachCard, PackBulkOpenResult, PackOpenResult } from "@/types";

// Bulk reveal walks player cards and coach cards as one combined sequence
// (backend keeps them as two separate arrays, same shape as a single pack's
// result) — players first, then coaches, matching the order they already
// appear in in BulkSummary's grid below.
type BulkRevealItem = { kind: "player"; item: OpenedCard } | { kind: "coach"; item: OpenedCoachCard };

function bulkStagesFor(entry: BulkRevealItem) {
  return entry.kind === "coach"
    ? { stages: COACH_STAGES as readonly string[], duration: COACH_STAGE_DURATION_MS }
    : { stages: STAGES as readonly string[], duration: STAGE_DURATION_MS };
}

export default function PackOpenPage() {
  const location = useLocation();
  // A quantity > 1 comes only from PacksPage's quantity sheet (never from
  // the Stars-purchase flow, which stays single-pack-only) — routed to its
  // own view entirely so the delicate staged single-card reveal animation
  // below is never touched by the bulk path.
  const quantity = (location.state as { quantity?: number } | null)?.quantity ?? 1;
  if (quantity > 1) return <BulkPackOpenView quantity={quantity} />;
  return <SinglePackOpenView />;
}

function SinglePackOpenView() {
  const { packId } = useParams<{ packId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  // Present when arriving with an already-claimed result (e.g. the free pack) so we skip re-opening it.
  const prefetchedResult = (location.state as { result?: PackOpenResult } | null)?.result ?? null;

  const [phase, setPhase] = useState<"packshot" | "revealing" | "summary">("packshot");
  const [cardIndex, setCardIndex] = useState(0);
  const [stageIndex, setStageIndex] = useState(0);
  // Set when a single-card, no-bonus pack finishes its reveal — that path
  // normally skips straight to "/packs" (see the comment in nextCard below),
  // so this flag stands in for the summary screen just to surface the
  // "open another" action without re-showing the card that was just revealed.
  const [singleCardDone, setSingleCardDone] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasStartedRef = useRef(false);
  // Lazily initialized once via the ref-during-render pattern, which (unlike
  // useMemo) is guaranteed stable across React 18 StrictMode's dev-only
  // double-render/double-effect replay — so a duplicate invocation reuses the
  // same idempotency key and the backend's dedup logic returns the original
  // result instead of charging the player twice.
  const idempotencyKeyRef = useRef<string | null>(null);
  if (idempotencyKeyRef.current === null) {
    idempotencyKeyRef.current = `pack-${packId}-${crypto.randomUUID()}`;
  }
  const idempotencyKey = idempotencyKeyRef.current;

  // A plain useState/useEffect (rather than TanStack Query's useMutation) for
  // this fire-once-on-mount request: useMutation's result is delivered via an
  // internal observer subscription that is itself wired up in a useEffect, and
  // that subscription can be torn down and rebuilt by React 18 StrictMode's
  // dev-only double-invoke of effects independently of the in-flight request —
  // so the resolved data can arrive after the *new* subscription replaces the
  // one the pending request's promise chain was going to notify, leaving the
  // UI stuck on the loading state even though the purchase completed. Local
  // state sidesteps that lifecycle entirely.
  const [requestState, setRequestState] = useState<
    { status: "pending" } | { status: "success"; data: PackOpenResult } | { status: "error"; message: string }
  >(prefetchedResult ? { status: "success", data: prefetchedResult } : { status: "pending" });

  useEffect(() => {
    if (prefetchedResult) return;
    // Guards against React 18 StrictMode's dev-only double-invoke of effects
    // (mount → cleanup → mount) firing this purchase twice; the ref persists
    // across that replay since it isn't reset by the cleanup function.
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;

    openPack(Number(packId), idempotencyKey)
      .then((data) => {
        updateBalance(data.new_balance);
        setRequestState({ status: "success", data });
      })
      .catch((err: unknown) => {
        setRequestState({
          status: "error",
          message: err instanceof ApiRequestError ? err.message : "Не удалось открыть пак",
        });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const result = requestState.status === "success" ? requestState.data : null;

  const advance = () => {
    if (!result) return;
    haptic("light");
    if (timerRef.current) clearTimeout(timerRef.current);

    if (stageIndex < STAGES.length - 1) {
      setStageIndex((i) => i + 1);
    }
  };

  const nextCard = () => {
    if (!result) return;
    haptic("light");
    if (timerRef.current) clearTimeout(timerRef.current);

    if (cardIndex < result.cards.length - 1) {
      setCardIndex((i) => i + 1);
      setStageIndex(0);
      return;
    }
    hapticNotify("success");
    // A single-card pack has already shown its one card in full during the
    // reveal stage above — if there's no reward banner to add, a follow-up
    // "Pack opened" screen re-displaying that same card is pure friction.
    // Instead of navigating straight away, just surface the done/open-another
    // actions in place so this path still offers "open another".
    if (
      result.cards.length === 1 &&
      result.coach_cards.length === 0 &&
      !result.referral_bonus_coins &&
      result.collection_rewards.length === 0 &&
      !result.pack.bonus_coins &&
      !result.pack.badge
    ) {
      setSingleCardDone(true);
      return;
    }
    setPhase("summary");
  };

  const isStarsPack = result ? result.pack.stars_price != null : false;
  const canAffordAgain = result ? (isStarsPack ? true : balance >= result.pack.price) : false;

  const resetForReopen = () => {
    setPhase("packshot");
    setCardIndex(0);
    setStageIndex(0);
    setSingleCardDone(false);
  };

  const reopenCoinPack = () => {
    if (!packId) return;
    idempotencyKeyRef.current = `pack-${packId}-${crypto.randomUUID()}`;
    resetForReopen();
    setRequestState({ status: "pending" });
    openPack(Number(packId), idempotencyKeyRef.current)
      .then((data) => {
        updateBalance(data.new_balance);
        setRequestState({ status: "success", data });
      })
      .catch((err: unknown) => {
        setRequestState({
          status: "error",
          message: err instanceof ApiRequestError ? err.message : "Не удалось открыть пак",
        });
      });
  };

  const {
    buy: buyStarsPackAgain,
    busy: buyingStarsPackAgain,
    error: buyStarsPackAgainError,
  } = useStarsPackPurchase(Number(packId), (data) => {
    updateBalance(data.new_balance);
    resetForReopen();
    setRequestState({ status: "success", data });
  });

  const handleOpenAnother = () => {
    haptic("light");
    if (isStarsPack) buyStarsPackAgain();
    else reopenCoinPack();
  };

  useEffect(() => {
    if (phase !== "revealing" || stageIndex >= STAGES.length - 1) return;
    timerRef.current = setTimeout(advance, STAGE_DURATION_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, cardIndex, stageIndex, result]);

  const skipAll = () => {
    if (!result) return;
    // Fast-forwards through the staged reveal animation only — always lands
    // on the last card fully revealed, same as advancing through it
    // naturally, so the player still sees what they got. It must never jump
    // straight past that to "summary"/navigate away, or a single-card pack
    // (the common case) would skip showing the card entirely.
    if (timerRef.current) clearTimeout(timerRef.current);
    haptic("light");
    // A pack whose every slot rolled a coach has no player cards at all, so
    // there is nothing for the staged reveal to fast-forward through —
    // entering "revealing" here would render RevealStage with
    // result.cards[-1] (undefined) and crash. Coach cards only ever appear
    // in the summary grid, so go straight there.
    if (result.cards.length === 0) {
      hapticNotify("success");
      setPhase("summary");
      return;
    }
    setPhase("revealing"); // in case skip is tapped from the packshot screen, before opening
    setCardIndex(result.cards.length - 1);
    setStageIndex(STAGES.length - 1);
  };

  if (requestState.status === "pending") return <LoadingScreen />;
  if (requestState.status === "error") {
    return <ErrorScreen message={requestState.message} onRetry={() => navigate("/packs")} />;
  }
  if (!result) return null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg-base">
      {phase !== "summary" && !singleCardDone && (
        <button
          onClick={skipAll}
          className="safe-top absolute right-4 top-4 z-10 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold text-ink-chalk"
        >
          Пропустить всё
        </button>
      )}

      {phase === "packshot" && (
        <PackShot
          pack={result.pack}
          onOpen={() => {
            haptic("medium");
            // Same zero-player-cards case as skipAll below — a coach-only
            // pack has nothing to show in the staged reveal, so skip it
            // entirely rather than rendering RevealStage with an undefined card.
            if (result.cards.length === 0) {
              hapticNotify("success");
              setPhase("summary");
              return;
            }
            setPhase("revealing");
          }}
        />
      )}

      {phase === "revealing" && (
        <div className="flex flex-1 flex-col">
          <RevealStage
            key={`${cardIndex}-${stageIndex}`}
            opened={result.cards[cardIndex]}
            stage={STAGES[stageIndex]}
            index={cardIndex}
            total={result.cards.length}
            onTap={advance}
          />
          {stageIndex === STAGES.length - 1 && (
            <div className="safe-bottom px-6 pb-6 pt-2">
              {singleCardDone ? (
                <ReopenActions
                  onDone={() => navigate("/packs")}
                  onOpenAnother={handleOpenAnother}
                  canOpenAnother={canAffordAgain}
                  busy={isStarsPack && buyingStarsPackAgain}
                  error={isStarsPack ? buyStarsPackAgainError : null}
                />
              ) : (
                <button
                  onClick={nextCard}
                  className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
                >
                  {cardIndex < result.cards.length - 1 ? "Следующая карта" : "Готово"}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {phase === "summary" && (
        <Summary
          result={result}
          onDone={() => navigate("/packs")}
          onOpenAnother={handleOpenAnother}
          canOpenAnother={canAffordAgain}
          busy={isStarsPack && buyingStarsPackAgain}
          error={isStarsPack ? buyStarsPackAgainError : null}
        />
      )}
    </div>
  );
}

/** Opening N packs at once stages through every card — player and coach
 * alike — one at a time, same reveal animations as a single pack, but
 * auto-advances card to card instead of waiting for a tap, since card_count
 * up to 12 and quantity up to 100 can mean hundreds of cards, too many to
 * click through individually. A visible "Пропустить" escape hatch jumps
 * straight to the summary grid at any point. */
function BulkPackOpenView({ quantity }: { quantity: number }) {
  const { packId } = useParams<{ packId: string }>();
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const balance = useAuthStore((s) => s.user?.balance ?? 0);

  const [phase, setPhase] = useState<"packshot" | "revealing" | "summary">("packshot");
  const [cardIndex, setCardIndex] = useState(0);
  const [stageIndex, setStageIndex] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasStartedRef = useRef(false);
  const idempotencyKeyRef = useRef<string | null>(null);
  if (idempotencyKeyRef.current === null) {
    idempotencyKeyRef.current = `pack-bulk-${packId}-${crypto.randomUUID()}`;
  }

  const [requestState, setRequestState] = useState<
    { status: "idle" } | { status: "pending" } | { status: "success"; data: PackBulkOpenResult } | { status: "error"; message: string }
  >({ status: "idle" });

  const runOpen = () => {
    if (!packId) return;
    setRequestState({ status: "pending" });
    openPackBulk(Number(packId), quantity, idempotencyKeyRef.current!)
      .then((data) => {
        updateBalance(data.new_balance);
        setRequestState({ status: "success", data });
      })
      .catch((err: unknown) => {
        setRequestState({
          status: "error",
          message: err instanceof ApiRequestError ? err.message : "Не удалось открыть паки",
        });
      });
  };

  useEffect(() => {
    // Guards React 18 StrictMode's dev-only double-invoke of effects, same
    // as the single-pack view above — the ref persists across that replay.
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;
    runOpen();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const result = requestState.status === "success" ? requestState.data : null;
  const revealItems: BulkRevealItem[] = result
    ? [
        ...result.cards.map((item): BulkRevealItem => ({ kind: "player", item })),
        ...result.coach_cards.map((item): BulkRevealItem => ({ kind: "coach", item })),
      ]
    : [];
  const currentItem = revealItems[cardIndex] ?? null;
  const currentStages = currentItem ? bulkStagesFor(currentItem) : null;

  useEffect(() => {
    if (phase !== "revealing" || !currentStages) return;
    timerRef.current = setTimeout(() => {
      if (stageIndex < currentStages.stages.length - 1) {
        setStageIndex((i) => i + 1);
        return;
      }
      if (cardIndex < revealItems.length - 1) {
        setCardIndex((i) => i + 1);
        setStageIndex(0);
        return;
      }
      hapticNotify("success");
      setPhase("summary");
    }, currentStages.duration);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, cardIndex, stageIndex, result]);

  // Tapping the card fast-forwards through its stages, then on to the next
  // card — same gesture as the single-pack view's tap-to-advance, just
  // continuing on to the next card instead of stopping at "reveal".
  const advanceOnTap = () => {
    if (!currentStages) return;
    haptic("light");
    if (timerRef.current) clearTimeout(timerRef.current);
    if (stageIndex < currentStages.stages.length - 1) {
      setStageIndex((i) => i + 1);
    } else if (cardIndex < revealItems.length - 1) {
      setCardIndex((i) => i + 1);
      setStageIndex(0);
    } else {
      hapticNotify("success");
      setPhase("summary");
    }
  };

  const resetForReopen = () => {
    setPhase("packshot");
    setCardIndex(0);
    setStageIndex(0);
  };

  const reopen = () => {
    haptic("light");
    idempotencyKeyRef.current = `pack-bulk-${packId}-${crypto.randomUUID()}`;
    resetForReopen();
    runOpen();
  };

  const skipToSummary = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    haptic("light");
    hapticNotify("success");
    setPhase("summary");
  };

  if (requestState.status === "pending" || requestState.status === "idle") return <LoadingScreen />;
  if (requestState.status === "error") {
    return <ErrorScreen message={requestState.message} onRetry={() => navigate("/packs")} />;
  }
  if (!result) return null;

  const canOpenAnother = balance >= result.pack.price * quantity;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg-base">
      {phase !== "summary" && (
        <button
          onClick={skipToSummary}
          className="safe-top absolute right-4 top-4 z-10 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold text-ink-chalk"
        >
          Пропустить
        </button>
      )}

      {phase === "packshot" && (
        <button
          onClick={() => {
            haptic("medium");
            // An empty batch (shouldn't normally happen) has nothing to
            // stage through — go straight to the grid.
            if (revealItems.length === 0) {
              hapticNotify("success");
              setPhase("summary");
              return;
            }
            setPhase("revealing");
          }}
          className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center"
        >
          <motion.img
            src={staticUrl(result.pack.image_path ?? undefined)}
            alt={result.pack.name}
            className="w-52 drop-shadow-2xl"
            animate={{ scale: [1, 1.04, 1], rotate: [0, -1.5, 1.5, 0] }}
            transition={{ repeat: Infinity, duration: 1.6 }}
          />
          <p className="font-display text-xl font-bold text-ink-chalk">{quantity}× {result.pack.name}</p>
          <p className="animate-pulse text-sm text-accent-lime">Нажми, чтобы открыть</p>
        </button>
      )}

      {phase === "revealing" && currentItem && currentStages && (
        currentItem.kind === "coach" ? (
          <CoachRevealStage
            key={`${cardIndex}-${stageIndex}`}
            opened={{ card: { coach: currentItem.item.card.coach }, is_new: currentItem.item.is_new }}
            stage={(COACH_STAGES[stageIndex] ?? COACH_STAGES[COACH_STAGES.length - 1])}
            index={cardIndex}
            total={revealItems.length}
            onTap={advanceOnTap}
          />
        ) : (
          <RevealStage
            key={`${cardIndex}-${stageIndex}`}
            opened={currentItem.item}
            stage={(STAGES[stageIndex] ?? STAGES[STAGES.length - 1])}
            index={cardIndex}
            total={revealItems.length}
            onTap={advanceOnTap}
          />
        )
      )}

      {phase === "summary" && (
        <BulkSummary
          result={result}
          onDone={() => navigate("/packs")}
          onOpenAnother={reopen}
          canOpenAnother={canOpenAnother}
        />
      )}
    </div>
  );
}

function BulkSummary({
  result,
  onDone,
  onOpenAnother,
  canOpenAnother,
}: {
  result: PackBulkOpenResult;
  onDone: () => void;
  onOpenAnother: () => void;
  canOpenAnother: boolean;
}) {
  const totalOpened = result.cards.length + result.coach_cards.length;
  return (
    <div className="safe-bottom flex flex-1 flex-col gap-4 overflow-y-auto px-5 pb-6 pt-16">
      <h2 className="text-center font-display text-2xl font-bold text-ink-chalk">
        Открыто {result.quantity} × «{result.pack.name}»!
      </h2>
      <p className="flex items-center justify-center gap-1.5 text-center text-sm text-ink-mist">
        Потрачено {result.total_price_paid} <IconCoin size={13} className="text-accent-lime" />
        <span className="text-ink-mist-dim">· получено карт: {totalOpened}</span>
      </p>
      {!!result.referral_bonus_coins && (
        <div className="flex items-center justify-center gap-2 rounded-2xl bg-accent-lime/10 px-4 py-3 text-center">
          <IconHandshake size={18} className="text-accent-lime" />
          <p className="text-sm font-semibold text-accent-lime">
            Бонус за приглашение: +{result.referral_bonus_coins}
          </p>
          <IconCoin size={14} className="text-accent-lime" />
        </div>
      )}
      {result.collection_rewards.map((grant) => (
        <div key={grant.collection_id} className="flex items-center justify-center gap-2 rounded-2xl bg-accent-lime/10 px-4 py-3 text-center">
          <IconTag size={18} className="text-accent-lime" />
          <p className="text-sm font-semibold text-accent-lime">
            Коллекция «{grant.collection_name}» собрана! +{grant.reward_coins}
            {grant.granted_pack ? ` + пак «${grant.granted_pack.pack.name}»` : ""}
          </p>
          <IconCoin size={14} className="text-accent-lime" />
        </div>
      ))}
      <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4">
        {result.cards.map((opened) => (
          <div
            key={opened.card.id}
            className={`relative overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[opened.card.player.rarity]} p-[2px] ${RARITY_GLOW[opened.card.player.rarity]}`}
          >
            <div className="flex flex-col rounded-[14px] bg-bg-surface">
              <img
                src={staticUrl(opened.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt={opened.card.player.display_name}
                className="aspect-square w-full object-cover"
              />
              <div className="p-1.5 text-center">
                <p className="truncate text-[11px] font-bold text-ink-chalk">{opened.card.player.display_name}</p>
                <p className="text-[9px] text-ink-mist">{RARITY_LABELS[opened.card.player.rarity]}</p>
              </div>
            </div>
            {opened.is_new && (
              <span className="absolute left-1 top-1 rounded-full bg-accent-green px-1.5 py-0.5 text-[9px] font-bold text-bg-base">NEW</span>
            )}
            {opened.duplicate_count > 1 && (
              <span className="absolute right-1 top-1 rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-[9px] font-bold text-ink-chalk">
                ×{opened.duplicate_count}
              </span>
            )}
          </div>
        ))}
        {result.coach_cards.map((opened) => (
          <div
            key={`coach-${opened.card.id}`}
            className={`relative overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[opened.card.coach.rarity]} p-[2px] ${RARITY_GLOW[opened.card.coach.rarity]}`}
          >
            <div className="flex flex-col rounded-[14px] bg-bg-surface">
              <img
                src={staticUrl(opened.card.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt={opened.card.coach.display_name}
                className="aspect-square w-full object-cover"
              />
              <div className="p-1.5 text-center">
                <p className="truncate text-[11px] font-bold text-ink-chalk">{opened.card.coach.display_name}</p>
                <p className="text-[9px] text-ink-mist">Тренер · {RARITY_LABELS[opened.card.coach.rarity]}</p>
              </div>
            </div>
            {opened.is_new && (
              <span className="absolute left-1 top-1 rounded-full bg-accent-green px-1.5 py-0.5 text-[9px] font-bold text-bg-base">NEW</span>
            )}
            {opened.duplicate_count > 1 && (
              <span className="absolute right-1 top-1 rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-[9px] font-bold text-ink-chalk">
                ×{opened.duplicate_count}
              </span>
            )}
          </div>
        ))}
      </div>
      <div className="mt-2">
        <ReopenActions onDone={onDone} onOpenAnother={onOpenAnother} canOpenAnother={canOpenAnother} busy={false} error={null} />
      </div>
    </div>
  );
}

function ReopenActions({
  onDone,
  onOpenAnother,
  canOpenAnother,
  busy,
  error,
}: {
  onDone: () => void;
  onOpenAnother: () => void;
  canOpenAnother: boolean;
  busy: boolean;
  error: string | null;
}) {
  return (
    <div className="flex flex-col gap-2">
      {error && <p className="text-center text-xs text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button
          onClick={onDone}
          className="flex-1 rounded-2xl bg-white/10 py-3.5 font-display text-base font-bold text-ink-chalk active:scale-95"
        >
          Готово
        </button>
        <button
          onClick={onOpenAnother}
          disabled={!canOpenAnother || busy}
          className="flex-1 rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {busy ? "Открываем..." : "Открыть ещё"}
        </button>
      </div>
    </div>
  );
}

function PackShot({ pack, onOpen }: { pack: PackOpenResult["pack"]; onOpen: () => void }) {
  return (
    <button onClick={onOpen} className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center">
      <motion.img
        src={staticUrl(pack.image_path ?? undefined)}
        alt={pack.name}
        className="w-52 drop-shadow-2xl"
        animate={{ scale: [1, 1.04, 1], rotate: [0, -1.5, 1.5, 0] }}
        transition={{ repeat: Infinity, duration: 1.6 }}
      />
      <p className="font-display text-xl font-bold text-ink-chalk">{pack.name}</p>
      <p className="animate-pulse text-sm text-accent-lime">Нажми, чтобы открыть</p>
    </button>
  );
}

function Summary({
  result,
  onDone,
  onOpenAnother,
  canOpenAnother,
  busy,
  error,
}: {
  result: PackOpenResult;
  onDone: () => void;
  onOpenAnother: () => void;
  canOpenAnother: boolean;
  busy: boolean;
  error: string | null;
}) {
  // A single-card pack's one card was already fully shown during the reveal
  // stage — re-displaying it here (and the generic "Pack opened" heading)
  // would be pure repetition, so this screen is only reached at all when
  // there's an actual reward banner below worth showing. Coach cards never
  // go through that staged reveal (they only ever appear in this grid), so
  // any coach card always earns the recap — otherwise an all-coach pack
  // (result.cards.length === 0) would never show its coach card anywhere.
  const showRecap = result.coach_cards.length > 0 || result.cards.length > 1;
  // grid-cols-2 leaves a lone card pinned to the left column instead of
  // centered — only matters when the recap shows exactly one card (e.g. a
  // pack that granted a single coach card and nothing else).
  const totalOpened = result.cards.length + result.coach_cards.length;
  const singleCardWidthClass = totalOpened === 1 ? "w-2/5" : "";
  return (
    <div className="safe-bottom flex flex-1 flex-col gap-4 overflow-y-auto px-5 pb-6 pt-16">
      {showRecap && <h2 className="text-center font-display text-2xl font-bold text-ink-chalk">Пак открыт!</h2>}
      {!!result.pack.bonus_coins && (
        <div className="flex items-center justify-center gap-2 rounded-2xl bg-amber-400/10 px-4 py-3 text-center">
          <IconCoin size={18} className="text-amber-300" />
          <p className="text-sm font-semibold text-amber-300">
            Бонус пака: +{result.pack.bonus_coins}
          </p>
        </div>
      )}
      {result.pack.badge && (
        <div className="flex items-center justify-center gap-2 rounded-2xl bg-amber-400/10 px-4 py-3 text-center">
          <UserBadge badge={result.pack.badge} className="h-5 w-5 text-lg" />
          <p className="text-sm font-semibold text-amber-300">
            Новый значок: {result.pack.badge.name}
          </p>
        </div>
      )}
      {!!result.referral_bonus_coins && (
        <div className="flex items-center justify-center gap-2 rounded-2xl bg-accent-lime/10 px-4 py-3 text-center">
          <IconHandshake size={18} className="text-accent-lime" />
          <p className="text-sm font-semibold text-accent-lime">
            Бонус за приглашение: +{result.referral_bonus_coins}
          </p>
          <IconCoin size={14} className="text-accent-lime" />
        </div>
      )}
      {result.collection_rewards.map((grant) => (
        <div key={grant.collection_id} className="flex items-center justify-center gap-2 rounded-2xl bg-accent-lime/10 px-4 py-3 text-center">
          <IconTag size={18} className="text-accent-lime" />
          <p className="text-sm font-semibold text-accent-lime">
            Коллекция «{grant.collection_name}» собрана! +{grant.reward_coins}
            {grant.granted_pack ? ` + пак «${grant.granted_pack.pack.name}»` : ""}
          </p>
          <IconCoin size={14} className="text-accent-lime" />
        </div>
      ))}
      {showRecap && (
        <div className={totalOpened === 1 ? "flex justify-center" : "grid grid-cols-2 gap-3 sm:grid-cols-3"}>
          {result.cards.map((opened) => (
            <div
              key={opened.card.id}
              className={`relative overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[opened.card.player.rarity]} p-[2px] ${RARITY_GLOW[opened.card.player.rarity]} ${singleCardWidthClass}`}
            >
              <div className="flex flex-col rounded-[14px] bg-bg-surface">
                <img
                  src={staticUrl(opened.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                  alt={opened.card.player.display_name}
                  className="aspect-square w-full object-cover"
                />
                <div className="p-2 text-center">
                  <p className="truncate text-xs font-bold text-ink-chalk">{opened.card.player.display_name}</p>
                  <p className="text-[10px] text-ink-mist">{RARITY_LABELS[opened.card.player.rarity]}</p>
                  {opened.card.player.collection_name && (
                    <p className="flex items-center justify-center gap-1 truncate text-[9px] font-semibold text-accent-lime">
                      <IconTag size={9} />
                      {opened.card.player.collection_name}
                    </p>
                  )}
                </div>
              </div>
              {opened.is_new && (
                <span className="absolute left-1 top-1 rounded-full bg-accent-green px-1.5 py-0.5 text-[9px] font-bold text-bg-base">NEW</span>
              )}
              {opened.duplicate_count > 1 && (
                <span className="absolute right-1 top-1 rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-[9px] font-bold text-ink-chalk">
                  ×{opened.duplicate_count}
                </span>
              )}
            </div>
          ))}
          {result.coach_cards.map((opened) => (
            <div
              key={`coach-${opened.card.id}`}
              className={`relative overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[opened.card.coach.rarity]} p-[2px] ${RARITY_GLOW[opened.card.coach.rarity]} ${singleCardWidthClass}`}
            >
              <div className="flex flex-col rounded-[14px] bg-bg-surface">
                <img
                  src={staticUrl(opened.card.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                  alt={opened.card.coach.display_name}
                  className="aspect-square w-full object-cover"
                />
                <div className="p-2 text-center">
                  <p className="truncate text-xs font-bold text-ink-chalk">{opened.card.coach.display_name}</p>
                  <p className="text-[10px] text-ink-mist">Тренер · {RARITY_LABELS[opened.card.coach.rarity]}</p>
                </div>
              </div>
              {opened.is_new && (
                <span className="absolute left-1 top-1 rounded-full bg-accent-green px-1.5 py-0.5 text-[9px] font-bold text-bg-base">NEW</span>
              )}
              {opened.duplicate_count > 1 && (
                <span className="absolute right-1 top-1 rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-[9px] font-bold text-ink-chalk">
                  ×{opened.duplicate_count}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="mt-2">
        <ReopenActions
          onDone={onDone}
          onOpenAnother={onOpenAnother}
          canOpenAnother={canOpenAnother}
          busy={busy}
          error={error}
        />
      </div>
    </div>
  );
}
