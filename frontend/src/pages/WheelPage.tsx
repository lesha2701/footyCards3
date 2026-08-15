import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";

import { createWheelStarsInvoice, fetchWheelStarsInvoiceStatus, fetchWheelStatus, spinFree, spinPaidCoins } from "@/api/wheel";
import EmptyState from "@/components/common/EmptyState";
import { UserBadge } from "@/components/common/UserBadge";
import { IconCard, IconCoin, IconInboxEmpty, IconPack, IconTag, IconTarget } from "@/components/icons";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS, RARITY_LABELS } from "@/lib/rarity";
import { openTelegramInvoice } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { WheelPrize, WheelSpinResult } from "@/types";

async function pollWheelStarsInvoice(payloadToken: string): Promise<WheelSpinResult> {
  const maxAttempts = 20;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const status = await fetchWheelStarsInvoiceStatus(payloadToken);
    if (status.status === "completed" && status.wheel_result) return status.wheel_result;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Приз ещё не пришёл — попробуй обновить страницу через минуту");
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

const GLYPH_BG: Record<WheelPrize["prize_type"], string> = {
  coins: "bg-accent-lime/12 text-accent-lime",
  pack: "bg-accent/12 text-accent",
  card_rarity: "bg-[#a855f7]/12 text-[#a855f7]",
  badge: "bg-amber-400/12 text-amber-300",
};

export default function WheelPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: status, isLoading } = useQuery({ queryKey: ["wheel-status"], queryFn: fetchWheelStatus });
  const [centerIndex, setCenterIndex] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [result, setResult] = useState<WheelSpinResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [payChoice, setPayChoice] = useState<"coins" | "stars" | null>(null);

  const runSpin = async (mutationFn: () => Promise<WheelSpinResult>) => {
    if (!status?.prizes.length) return;
    setError(null);
    setSpinning(true);
    try {
      const spinResult = await mutationFn();
      const wonIndex = status.prizes.findIndex((p) => p.id === spinResult.prize.id);
      // Land a few full loops further than the actual index so the strip
      // visibly spins past several prizes before settling, then holds on
      // the true winner — same "roll fast, ease into the result" idea used
      // by the pack-opening reveal, adapted to a horizontal strip.
      setCenterIndex((prev) => prev - (prev % status.prizes.length) + status.prizes.length * 3 + (wonIndex >= 0 ? wonIndex : 0));
      await new Promise((resolve) => setTimeout(resolve, 2600));
      setResult(spinResult);
      updateBalance(spinResult.new_balance);
      queryClient.invalidateQueries({ queryKey: ["wheel-status"] });
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
      setCenterIndex((prev) => prev % status.prizes.length);
    }
  };

  const freeMutation = useMutation({ mutationFn: spinFree });
  const coinsMutation = useMutation({ mutationFn: spinPaidCoins });
  const starsMutation = useMutation({
    mutationFn: async () => {
      const invoice = await createWheelStarsInvoice();
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") throw new Error("__cancelled__");
      if (paymentStatus === "failed") throw new Error("Платёж не прошёл");
      return pollWheelStarsInvoice(invoice.payload_token);
    },
  });

  if (isLoading || !status) return null;

  const prizeStrip = Array.from({ length: status.prizes.length * 6 }, (_, i) => status.prizes[i % status.prizes.length]);
  const CHIP_WIDTH = 88;

  return (
    <div className="flex flex-col gap-5">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconTarget size={20} className="text-accent-lime" />
        Колесо фортуны
      </h1>

      {!status.prizes.length ? (
        <EmptyState icon={IconInboxEmpty} title="Колесо пока не настроено" description="Загляни позже" />
      ) : (
        <>
          <div className="relative overflow-hidden rounded-3xl bg-bg-surface py-8">
            <div className="pointer-events-none absolute left-1/2 top-2 -translate-x-1/2 text-accent">▼</div>
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
                      className={`flex h-16 w-16 items-center justify-center rounded-2xl transition-all ${GLYPH_BG[prize.prize_type]} ${
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

            {payChoice === null ? (
              <button
                onClick={() => setPayChoice("coins")}
                disabled={spinning}
                className="w-full rounded-xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
              >
                Крутить платно
              </button>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => { setPayChoice(null); runSpin(() => coinsMutation.mutateAsync()); }}
                  disabled={spinning}
                  className="flex items-center justify-center gap-1 rounded-xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
                >
                  <IconCoin size={14} />{status.spin_cost_coins}
                </button>
                <button
                  onClick={() => { setPayChoice(null); runSpin(() => starsMutation.mutateAsync()); }}
                  disabled={spinning}
                  className="rounded-xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
                >
                  ⭐ {status.spin_cost_stars}
                </button>
              </div>
            )}
          </div>
        </>
      )}

      {result && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-6" onClick={() => setResult(null)}>
          <div
            className="max-h-[85vh] w-full max-w-xs overflow-y-auto rounded-2xl border border-white/10 bg-bg-surface p-6 text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="font-display text-lg font-bold text-ink-chalk">
              {result.duplicate_badge_coins ? `+${result.duplicate_badge_coins} монет (значок уже был)` : `Приз получен!`}
            </p>

            {result.pack_result ? (
              <div className="mt-3 flex flex-col gap-3">
                <p className="text-sm text-ink-mist">{result.pack_result.pack.name}</p>
                <div className="grid grid-cols-2 gap-2">
                  {result.pack_result.cards.map((opened) => (
                    <div
                      key={opened.card.id}
                      className={`overflow-hidden rounded-xl bg-gradient-to-b ${RARITY_GRADIENTS[opened.card.player.rarity]} p-[2px]`}
                    >
                      <div className="flex flex-col rounded-[10px] bg-bg-surface">
                        <img
                          src={staticUrl(opened.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                          alt={opened.card.player.display_name}
                          className="aspect-square w-full object-cover"
                        />
                        <div className="p-1.5">
                          <p className="truncate text-[11px] font-bold text-ink-chalk">{opened.card.player.display_name}</p>
                          <p className="text-[9px] text-ink-mist">{RARITY_LABELS[opened.card.player.rarity]}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : result.card_result ? (
              <div className="mt-3 flex flex-col items-center gap-2">
                <div className={`w-24 overflow-hidden rounded-xl bg-gradient-to-b ${RARITY_GRADIENTS[result.card_result.card.player.rarity]} p-[2px]`}>
                  <img
                    src={staticUrl(result.card_result.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                    alt={result.card_result.card.player.display_name}
                    className="aspect-square w-full rounded-[10px] object-cover"
                  />
                </div>
                <p className="text-sm font-semibold text-ink-chalk">{result.card_result.card.player.display_name}</p>
                <p className="text-xs text-ink-mist">{RARITY_LABELS[result.card_result.card.player.rarity]}</p>
              </div>
            ) : result.badge_result ? (
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
