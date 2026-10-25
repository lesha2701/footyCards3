import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { createCardOfferInvoice, fetchCardOffers } from "@/api/cardOffers";
import PlayerCard from "@/components/cards/PlayerCard";
import { formatGameError } from "@/lib/errors";
import { formatCountdown } from "@/lib/rewards";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import type { CardOffer } from "@/types";

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

/** «Карты»: footballer cards on sale for Telegram Stars (the admin puts them
 * here — often retired cards back for a short time). */
export default function CardOfferShop() {
  const { data: offers } = useQuery({ queryKey: ["card-offers"], queryFn: fetchCardOffers });
  const now = useNow();
  if (!offers) return null;
  if (!offers.length) {
    return <p className="py-8 text-center text-sm text-ink-mist">Сейчас карточек за звёзды нет — загляни позже</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-caption text-ink-mist">
        Особые карточки за Telegram Stars. Лимитки — карты, которые больше не выпадают из паков: купить их можно только здесь и только пока идёт предложение.
      </p>
      <div className="grid grid-cols-2 gap-3">
        {offers.map((o) => <OfferTile key={o.id} offer={o} now={now} />)}
      </div>
    </div>
  );
}

/** «2 д 4 ч» for long windows, the clock for the last day. */
function timeLeft(ms: number): string {
  const days = Math.floor(ms / 86_400_000);
  return days >= 1 ? `${days} д ${Math.floor((ms % 86_400_000) / 3_600_000)} ч` : formatCountdown(ms);
}

function OfferTile({ offer, now }: { offer: CardOffer; now: number }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [got, setGot] = useState(false);
  const buy = useMutation({
    mutationFn: () => payShopWithStars(() => createCardOfferInvoice(offer.id)),
    onSuccess: (status) => {
      if (status === "paid") {
        hapticNotify("success");
        setGot(true);
      }
      setError(null);
      for (const key of [["card-offers"], ["collection"], ["profile", "me"]]) queryClient.invalidateQueries({ queryKey: key });
    },
    onError: (err) => setError(formatGameError(err, "Оплата не прошла")),
  });
  const left = offer.ends_at ? new Date(offer.ends_at).getTime() - now : null;
  const soldOut = offer.left === 0;
  const limitReached = offer.per_user_limit > 0 && offer.bought >= offer.per_user_limit;

  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-2.5">
      {(offer.retired || offer.title) && (
        <div className="flex min-w-0 flex-wrap items-center gap-1">
          {offer.retired && (
            <span className="rounded-full bg-amber-400 px-2 py-0.5 text-micro font-black uppercase text-bg-base">Лимитка</span>
          )}
          {offer.title && <span className="min-w-0 truncate text-micro font-semibold text-amber-200">{offer.title}</span>}
        </div>
      )}
      <PlayerCard player={offer.player} size="sm" dimmed={soldOut} />
      <div className="flex flex-wrap items-center justify-between gap-1 text-micro">
        {left != null && left > 0 && <span className="font-mono text-amber-300">⏳ {timeLeft(left)}</span>}
        {offer.left != null && offer.stock != null && (
          <span className={soldOut ? "text-red-400" : "text-ink-mist"}>Осталось {offer.left}/{offer.stock}</span>
        )}
      </div>
      {got ? (
        <p className="rounded-xl bg-accent-lime/15 py-2 text-center text-xs font-bold text-accent-lime">Карточка в коллекции ✓</p>
      ) : (
        <button
          onClick={() => buy.mutate()}
          disabled={buy.isPending || !offer.can_buy}
          className="w-full rounded-xl bg-amber-400 py-2 text-sm font-bold text-bg-base active:scale-95 disabled:bg-bg-raised disabled:text-ink-mist"
        >
          {soldOut ? "Раскупили" : limitReached ? "Уже куплено" : buy.isPending ? "Оплата..." : `${offer.stars_price} ⭐`}
        </button>
      )}
      {error && <p className="text-center text-micro text-red-400">{error}</p>}
    </div>
  );
}
