import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { createStarterOfferInvoice, fetchStarterOffer, markStarterOfferSeen } from "@/api/monetization";
import { IconClose, IconGift } from "@/components/icons";
import { RewardBundleChips } from "@/components/rewards/RewardBundleView";
import { formatGameError } from "@/lib/errors";
import { formatCountdown } from "@/lib/rewards";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import type { StarterOffer } from "@/types";

function useCountdown(iso: string | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return iso ? new Date(iso).getTime() - now : 0;
}

function useStarterOfferPurchase(onDone?: () => void) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const buy = useMutation({
    mutationFn: () => payShopWithStars(createStarterOfferInvoice),
    onSuccess: (status) => {
      if (status === "paid") {
        hapticNotify("success");
        onDone?.();
      }
      setError(null);
      for (const key of [["starter-offer"], ["profile", "me"], ["cosmetics"], ["collection"]]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
    onError: (err) => setError(formatGameError(err, "Оплата не прошла")),
  });
  return { buy, error };
}

function OfferBody({ offer, onBuy, busy, error }: { offer: StarterOffer; onBuy: () => void; busy: boolean; error: string | null }) {
  const left = useCountdown(offer.expires_at);
  return (
    <>
      <div className="mt-3">
        <RewardBundleChips bundle={offer.contents} />
      </div>
      <p className="mt-3 font-mono text-xs text-amber-300">Исчезнет через {formatCountdown(left)}</p>
      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
      <button
        onClick={onBuy}
        disabled={busy || left <= 0}
        className="mt-3 w-full rounded-2xl bg-amber-400 py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {busy ? "Оплата..." : `Забрать за ${offer.stars_price} ⭐`}
      </button>
      <p className="mt-2 text-center text-caption text-ink-mist-dim">Звёзды не выводятся.</p>
    </>
  );
}

/** Full-screen once (first time the offer is seen), then only the banner. */
export function StarterOfferModal() {
  const queryClient = useQueryClient();
  const { data: offer } = useQuery({ queryKey: ["starter-offer"], queryFn: fetchStarterOffer });
  const [open, setOpen] = useState(false);
  const { buy, error } = useStarterOfferPurchase(() => setOpen(false));

  useEffect(() => {
    if (offer?.available && !offer.seen) {
      setOpen(true);
      markStarterOfferSeen()
        .then((data) => queryClient.setQueryData(["starter-offer"], data))
        .catch(() => undefined);
    }
  }, [offer, queryClient]);

  if (!open || !offer?.available) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-6" role="dialog" aria-label="Стартовое предложение">
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="relative w-full max-w-xs rounded-3xl bg-gradient-to-b from-sky-500/40 via-bg-surface to-bg-surface p-5 text-center"
      >
        <button onClick={() => setOpen(false)} aria-label="Закрыть" className="absolute right-3 top-3 text-ink-mist">
          <IconClose size={18} />
        </button>
        <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-sky-400/20 text-sky-300">
          <IconGift size={30} />
        </span>
        <p className="mt-3 font-display text-lg font-bold text-ink-chalk">Стартовый набор</p>
        <p className="text-xs text-ink-mist">Ограниченное предложение — один раз на аккаунт</p>
        <OfferBody offer={offer} onBuy={() => buy.mutate()} busy={buy.isPending} error={error} />
      </motion.div>
    </div>,
    document.body,
  );
}

/** The banner (home + shop) with a countdown, while the offer lasts. */
export function StarterOfferBanner() {
  const { data: offer } = useQuery({ queryKey: ["starter-offer"], queryFn: fetchStarterOffer });
  const { buy, error } = useStarterOfferPurchase();
  if (!offer?.available) return null;
  return (
    <section className="rounded-2xl border border-sky-400/40 bg-gradient-to-br from-sky-500/20 to-bg-surface p-4">
      <p className="flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
        <IconGift size={16} className="text-sky-300" /> Стартовый набор
      </p>
      <OfferBody offer={offer} onBuy={() => buy.mutate()} busy={buy.isPending} error={error} />
    </section>
  );
}
