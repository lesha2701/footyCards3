import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchDailyOffer } from "@/api/packs";
import { IconClock, IconCoin } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

function useCountdown(endsAt: string | undefined): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);
  if (!endsAt) return "";
  const left = Math.max(0, new Date(endsAt).getTime() - now);
  const h = Math.floor(left / 3_600_000);
  const m = Math.floor((left % 3_600_000) / 60_000);
  return h > 0 ? `${h} ч ${m} мин` : `${m} мин`;
}

/** "Предложение дня": one coin pack at a discount, once a day. The price
 * shown here is only informative — the server decides and charges it. */
export default function DailyOfferCard() {
  const navigate = useNavigate();
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const { data: offer } = useQuery({ queryKey: ["packs", "daily-offer"], queryFn: fetchDailyOffer });
  const countdown = useCountdown(offer?.ends_at);
  if (!offer) return null;

  const canAfford = balance >= offer.price;
  return (
    <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-accent-lime/20 via-bg-surface to-bg-surface p-4 ring-1 ring-accent-lime/30">
      <div className="flex items-center justify-between">
        <span className="rounded-full bg-accent-lime px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-bg-base">
          Предложение дня · −{offer.discount_pct}%
        </span>
        <span className="flex items-center gap-1 font-mono text-[11px] text-ink-mist">
          <IconClock size={12} />
          {countdown}
        </span>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <img
          src={staticUrl(offer.pack.image_path ?? undefined)}
          alt={offer.pack.name}
          className="h-16 w-16 shrink-0 rounded-2xl object-cover"
        />
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-base font-bold text-ink-chalk">{offer.pack.name}</p>
          <p className="flex items-center gap-1.5 font-mono text-sm">
            <span className="text-ink-mist-dim line-through">{offer.pack.price}</span>
            <span className="flex items-center gap-1 font-bold text-accent-lime">
              <IconCoin size={13} />
              {offer.price}
            </span>
          </p>
        </div>
        <button
          onClick={() => navigate(`/packs/${offer.pack.id}/open`, { state: { dailyOffer: true } })}
          disabled={offer.claimed_today || !canAfford}
          className="shrink-0 rounded-full bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {offer.claimed_today ? "Куплено" : canAfford ? "Купить" : "Мало монет"}
        </button>
      </div>
      {offer.claimed_today && <p className="mt-2 text-[11px] text-ink-mist">Новое предложение — через {countdown}</p>}
    </section>
  );
}
