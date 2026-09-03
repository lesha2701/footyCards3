import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { createWheelStarsInvoice, fetchWheelStarsInvoiceStatus, fetchWheelStatus, spinFree } from "@/api/wheel";
import { RevealStage, STAGES, STAGE_DURATION_MS } from "@/components/cards/CardRevealStage";
import EmptyState from "@/components/common/EmptyState";
import { UserBadge } from "@/components/common/UserBadge";
import { IconCard, IconCoin, IconInboxEmpty, IconPack, IconTag, IconTarget } from "@/components/icons";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { openTelegramInvoice, haptic } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Rarity, WheelPrize, WheelSpinResult } from "@/types";

async function pollWheelStarsInvoice(payloadToken: string): Promise<WheelSpinResult> {
  const maxAttempts = 20;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const status = await fetchWheelStarsInvoiceStatus(payloadToken);
    if (status.status === "completed" && status.wheel_result) return status.wheel_result;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Приз ещё не пришёл — попробуй обновить страницу через минуту");
}

// Fisher-Yates — computed once per distinct prize set (see the useMemo below),
// not on every render, so the reel's visual order stays stable across spins
// within a session instead of reshuffling mid-flow.
function shuffle<T>(items: T[]): T[] {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function prizeLabel(prize: WheelPrize): string {
  if (prize.prize_type === "coins") return `+${prize.coins_amount} монет`;
  if (prize.prize_type === "pack") return prize.pack?.name ?? "Пак";
  if (prize.prize_type === "card_rarity") {
    const labels: Record<string, string> = { common: "Обычная карта", rare: "Редкая карта", epic: "Эпическая карта", legendary: "Легендарная карта" };
    return labels[prize.card_rarity ?? "rare"];
  }
  return prize.badge?.name ?? "Значок";
}

function PrizeGlyph({ prize }: { prize: WheelPrize }) {
  if (prize.prize_type === "coins") return <IconCoin size={26} />;
  if (prize.prize_type === "pack") return <IconPack size={26} />;
  if (prize.prize_type === "card_rarity") return <IconCard size={26} />;
  if (prize.badge?.image_path) return <img src={staticUrl(prize.badge.image_path) ?? undefined} className="h-6 w-6 rounded-full object-cover" />;
  return <span className="text-lg leading-none">{prize.badge?.icon ?? "🏅"}</span>;
}

const GLYPH_BG: Record<Exclude<WheelPrize["prize_type"], "card_rarity">, string> = {
  coins: "bg-accent-lime/12 text-accent-lime",
  pack: "bg-accent/12 text-accent",
  badge: "bg-amber-400/12 text-amber-300",
};

// Matches this rarity's actual color language (see lib/rarity.ts's
// RARITY_TEXT/RARITY_GRADIENTS) instead of a fixed color for every
// card_rarity prize regardless of which rarity it actually rolls.
const RARITY_GLYPH_BG: Record<Rarity, string> = {
  common: "bg-slate-400/12 text-slate-300",
  rare: "bg-blue-500/12 text-blue-400",
  epic: "bg-purple-500/12 text-purple-400",
  legendary: "bg-amber-400/12 text-amber-400",
  diamond: "bg-cyan-400/12 text-cyan-300",
};

function glyphBgClass(prize: WheelPrize): string {
  if (prize.prize_type === "card_rarity") return RARITY_GLYPH_BG[prize.card_rarity ?? "common"];
  return GLYPH_BG[prize.prize_type];
}

export default function WheelPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: status, isLoading } = useQuery({ queryKey: ["wheel-status"], queryFn: fetchWheelStatus });
  const [centerIndex, setCenterIndex] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [result, setResult] = useState<WheelSpinResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cardStageIndex, setCardStageIndex] = useState(0);
  const cardTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Stable per prize-set (keyed on the sorted id list, not the array
  // reference) so a background refetch after a spin doesn't reshuffle the
  // reel out from under an in-flight spin's centerIndex/wonIndex math —
  // only an actual admin change to the prize pool reshuffles it.
  const prizesKey = status?.prizes.map((p) => p.id).join(",") ?? "";
  const shuffledPrizes = useMemo(() => (status ? shuffle(status.prizes) : []), [prizesKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const runSpin = async (mutationFn: () => Promise<WheelSpinResult>) => {
    if (!shuffledPrizes.length) return;
    setError(null);
    setSpinning(true);
    try {
      const spinResult = await mutationFn();
      const wonIndex = shuffledPrizes.findIndex((p) => p.id === spinResult.prize.id);
      // Land a few full loops further than the actual index so the strip
      // visibly spins past several prizes before settling, then holds on
      // the true winner — same "roll fast, ease into the result" idea used
      // by the pack-opening reveal, adapted to a horizontal strip.
      setCenterIndex((prev) => prev - (prev % shuffledPrizes.length) + shuffledPrizes.length * 3 + (wonIndex >= 0 ? wonIndex : 0));
      await new Promise((resolve) => setTimeout(resolve, 2600));
      updateBalance(spinResult.new_balance);
      queryClient.invalidateQueries({ queryKey: ["wheel-status"] });

      if (spinResult.badge_result) {
        // updateBalance only patches the balance field — a freshly-won and
        // auto-equipped badge otherwise never reaches the nickname display
        // (ProfilePage etc., all of which read user.active_badge) until the
        // next full session reload, since nothing else refetches the user.
        const current = useAuthStore.getState().user;
        if (current) useAuthStore.getState().setUser({ ...current, active_badge: spinResult.badge_result });
      }

      if (spinResult.pack_result) {
        // Reuse the exact same staged-reveal flow the shop uses (PackOpenPage
        // already supports a prefetched result via location.state — the same
        // escape hatch StarsPackCard uses for a Stars-purchased pack), rather
        // than a flat "you won a pack" text label.
        navigate(`/packs/${spinResult.pack_result.pack.id}/open`, { state: { result: spinResult.pack_result } });
        return;
      }

      if (spinResult.card_result) setCardStageIndex(0);
      setResult(spinResult);
    } catch (err) {
      // A player who simply closed the Telegram payment sheet deliberately
      // backed out — mirrors PacksPage.tsx's Stars-purchase flow, which
      // treats "cancelled" as a silent return to idle with no error banner.
      if (err instanceof Error && err.message === "__cancelled__") return;
      setError(err instanceof ApiRequestError ? err.message : err instanceof Error ? err.message : "Не удалось прокрутить колесо");
    } finally {
      setSpinning(false);
      // Snap centerIndex back down modulo prizes.length now that the
      // transition duration is 0 (spinning === false): prizeStrip repeats
      // every prizes.length chips, so this shows the identical glyph at the
      // identical screen position while keeping the next spin's "land a few
      // loops further" math starting from a small base instead of growing
      // unboundedly past the end of the (fixed-length) prizeStrip array.
      setCenterIndex((prev) => prev % shuffledPrizes.length);
    }
  };

  const freeMutation = useMutation({ mutationFn: spinFree });
  const starsMutation = useMutation({
    mutationFn: async () => {
      const invoice = await createWheelStarsInvoice();
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") throw new Error("__cancelled__");
      if (paymentStatus === "failed") throw new Error("Платёж не прошёл");
      return pollWheelStarsInvoice(invoice.payload_token);
    },
  });

  // Auto-advances the card-reveal stages, mirroring PackOpenPage's own timer
  // effect — a wheel-won single card gets the same staged reveal a pack's
  // cards get, just without the "next card" progression (there's only one).
  useEffect(() => {
    if (!result?.card_result || cardStageIndex >= STAGES.length - 1) return;
    cardTimerRef.current = setTimeout(() => setCardStageIndex((i) => i + 1), STAGE_DURATION_MS);
    return () => {
      if (cardTimerRef.current) clearTimeout(cardTimerRef.current);
    };
  }, [result, cardStageIndex]);

  if (isLoading || !status) return null;

  const prizeStrip = Array.from({ length: shuffledPrizes.length * 6 }, (_, i) => shuffledPrizes[i % shuffledPrizes.length]);
  const CHIP_WIDTH = 88;

  return (
    <div className="flex flex-col gap-5">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconTarget size={20} className="text-accent-lime" />
        Колесо фортуны
      </h1>

      {!shuffledPrizes.length ? (
        <EmptyState icon={IconInboxEmpty} title="Колесо пока не настроено" description="Загляни позже" />
      ) : (
        <>
          <div className="relative overflow-hidden rounded-3xl bg-bg-surface pb-8 pt-12">
            <div className="pointer-events-none absolute left-1/2 top-1 z-10 -translate-x-1/2 text-accent">▼</div>
            <motion.div
              className="flex"
              animate={{ x: -centerIndex * CHIP_WIDTH }}
              transition={{ duration: spinning ? 2.4 : 0, ease: [0.12, 0.8, 0.2, 1] }}
              style={{ paddingLeft: "calc(50% - 44px)" }}
            >
              {prizeStrip.map((prize, i) => {
                const isCenter = i === centerIndex && !spinning;
                return (
                  <div key={i} className="flex shrink-0 flex-col items-center gap-2" style={{ width: CHIP_WIDTH }}>
                    <div
                      className={`flex h-16 w-16 items-center justify-center rounded-2xl transition-all ${glyphBgClass(prize)} ${
                        isCenter ? "scale-125 outline outline-2 outline-accent" : "scale-90 opacity-50"
                      }`}
                    >
                      <PrizeGlyph prize={prize} />
                    </div>
                  </div>
                );
              })}
            </motion.div>
          </div>

          {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

          <div className="flex flex-col gap-2">
            <button
              onClick={() => runSpin(() => freeMutation.mutateAsync())}
              disabled={spinning || status.free_spins_remaining === 0}
              className="w-full rounded-xl bg-accent py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              Крутить бесплатно ({status.free_spins_remaining}/{status.free_spins_total})
            </button>

            <button
              onClick={() => runSpin(() => starsMutation.mutateAsync())}
              disabled={spinning}
              className="w-full rounded-xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
            >
              Крутить за ⭐ {status.spin_cost_stars}
            </button>
          </div>
        </>
      )}

      {result?.card_result && (
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
              {result.collection_rewards.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  {result.collection_rewards.map((grant) => (
                    <p key={grant.collection_id} className="flex items-center justify-center gap-1 text-xs font-semibold text-accent-lime">
                      <IconTag size={12} />
                      Коллекция «{grant.collection_name}» собрана! +{grant.reward_coins}
                      {grant.granted_pack ? ` + пак «${grant.granted_pack.pack.name}»` : ""}
                    </p>
                  ))}
                </div>
              )}
              <button
                onClick={() => setResult(null)}
                className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
              >
                Готово
              </button>
            </div>
          )}
        </div>
      )}

      {result && !result.card_result && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-6" onClick={() => setResult(null)}>
          <div
            className="max-h-[85vh] w-full max-w-xs overflow-y-auto rounded-2xl border border-white/10 bg-bg-surface p-6 text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="font-display text-lg font-bold text-ink-chalk">
              {result.duplicate_badge_coins ? `+${result.duplicate_badge_coins} монет (значок уже был)` : `Приз получен!`}
            </p>

            {result.badge_result ? (
              <div className="mt-3 flex flex-col items-center gap-2">
                <UserBadge badge={result.badge_result} className="h-10 w-10 text-3xl" />
                <p className="text-sm font-semibold text-ink-chalk">{result.badge_result.name}</p>
              </div>
            ) : (
              <p className="mt-2 text-sm text-ink-mist">{prizeLabel(result.prize)}</p>
            )}

            {result.collection_rewards.length > 0 && (
              <div className="mt-3 flex flex-col gap-1.5">
                {result.collection_rewards.map((grant) => (
                  <p key={grant.collection_id} className="flex items-center justify-center gap-1 text-xs font-semibold text-accent-lime">
                    <IconTag size={12} />
                    Коллекция «{grant.collection_name}» собрана! +{grant.reward_coins}
                    {grant.granted_pack ? ` + пак «${grant.granted_pack.pack.name}»` : ""}
                  </p>
                ))}
              </div>
            )}

            <button onClick={() => setResult(null)} className="mt-5 w-full rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base active:scale-95">
              Ок
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
