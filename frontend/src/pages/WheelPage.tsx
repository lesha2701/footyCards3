import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { createWheelStarsInvoice, fetchWheelStarsInvoiceStatus, fetchWheelStatus, spinFree } from "@/api/wheel";
import EmptyState from "@/components/common/EmptyState";
import { IconInboxEmpty, IconTarget } from "@/components/icons";
import { WheelPrizeResult } from "@/components/wheel/WheelPrizeResult";
import { PrizeOddsList, WheelReel } from "@/components/wheel/WheelReel";
import { WHEEL_SPIN_MS, shuffle } from "@/lib/wheel";
import { ApiRequestError } from "@/lib/api";
import { openTelegramInvoice } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { WheelSpinResult } from "@/types";

async function pollWheelStarsInvoice(payloadToken: string): Promise<WheelSpinResult> {
  const maxAttempts = 20;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const status = await fetchWheelStarsInvoiceStatus(payloadToken);
    if (status.status === "completed" && status.wheel_result) return status.wheel_result;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Приз ещё не пришёл — попробуй обновить страницу через минуту");
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
      await new Promise((resolve) => setTimeout(resolve, WHEEL_SPIN_MS));
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
      // transition duration is 0 (spinning === false): the reel's strip
      // repeats every prizes.length chips, so this shows the identical glyph
      // at the identical screen position while keeping the next spin's
      // "land a few loops further" math starting from a small base instead
      // of growing unboundedly past the end of the (fixed-length) strip.
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

  if (isLoading || !status) return null;

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
          <WheelReel prizes={shuffledPrizes} centerIndex={centerIndex} spinning={spinning} />

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

          <PrizeOddsList prizes={status.prizes} title="Шансы призов" />
        </>
      )}

      {result && <WheelPrizeResult result={result} onClose={() => setResult(null)} />}
    </div>
  );
}
