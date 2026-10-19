import { useStarsPackPurchase } from "@/hooks/useStarsPackPurchase";
import { packBlocked } from "@/lib/packOdds";
import type { Pack, PackOpenResult } from "@/types";

/** «Купить за ⭐» for a Stars pack: invoice → payment → delivery states. */
export default function StarsBuyButton({
  pack, onPurchased, compact,
}: {
  pack: Pack;
  onPurchased: (result: PackOpenResult) => void;
  compact?: boolean;
}) {
  const { phase, error, buy, busy } = useStarsPackPurchase(pack.id, onPurchased);
  const blocked = packBlocked(pack);
  const label = blocked
    ? "Сейчас недоступен"
    : phase === "invoicing"
      ? "Готовим счёт..."
      : phase === "waiting"
        ? "Ждём оплату..."
        : phase === "delivering"
          ? "Начисляем пак..."
          : `Купить за ${pack.stars_price} ⭐`;
  return (
    <>
      <button
        onClick={buy}
        disabled={blocked || busy}
        className={`w-full bg-amber-400 font-bold text-bg-base active:scale-95 disabled:opacity-40 ${
          compact ? "rounded-full py-1.5 text-xs" : "rounded-2xl py-3 font-display text-sm"
        }`}
      >
        {label}
      </button>
      {!!pack.bonus_coins && !compact && (
        <p className="mt-1.5 text-center text-caption text-accent-lime">+{pack.bonus_coins} монет в подарок</p>
      )}
      {error && <p className="mt-1.5 text-center text-caption text-red-400">{error}</p>}
    </>
  );
}
