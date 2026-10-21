import { IconCoin } from "@/components/icons";
import InfoTile from "@/components/shop/InfoTile";
import { OddsBar, OddsList } from "@/components/shop/PackOdds";
import StarsBuyButton from "@/components/shop/StarsBuyButton";
import TopUpButton from "@/components/shop/TopUpButton";
import { staticUrl } from "@/lib/api";
import { packBlocked, packEndsIn, packRemaining, packsWord, packTotal } from "@/lib/packOdds";
import type { Pack, PackOpenResult } from "@/types";

const QUANTITIES = [1, 10];

/** A pack in the «Все паки» grid: the cover with a price chip; a tap opens
 * the sheet with every chance, the average value and ×1 / ×10 / any number. */
export default function PackTile({
  pack, open, onToggle, isNew, balance, onOpen, onCustom, onNeedCoins, topUpStars, onStarsPurchased,
}: {
  pack: Pack;
  isNew?: boolean;
  open: boolean;
  onToggle: () => void;
  balance: number;
  onOpen: (pack: Pack, quantity: number) => void;
  /** «Своё…»: the quantity sheet for any number. */
  onCustom?: (pack: Pack) => void;
  onNeedCoins: () => void;
  topUpStars: (need: number) => number | null;
  onStarsPurchased: (pack: Pack, result: PackOpenResult) => void;
}) {
  const isStars = pack.stars_price != null;
  const blocked = packBlocked(pack);
  const short = !isStars && balance < pack.price;
  const remaining = packRemaining(pack);
  const endsIn = packEndsIn(pack);

  return (
    <InfoTile
      open={open}
      onToggle={onToggle}
      isNew={isNew}
      badge={
        endsIn ? (
          <span className="rounded-full bg-red-500 px-1.5 py-0.5 text-micro font-bold text-white">⏳ {endsIn}</span>
        ) : undefined
      }
      accent={isStars ? "stars" : undefined}
      dimmed={blocked}
      name={pack.name}
      visual={<img decoding="async" loading="lazy" src={staticUrl(pack.image_path ?? undefined)} alt="" className="h-full w-full object-cover" />}
      price={
        isStars ? (
          <span className="text-amber-300">{pack.stars_price} ⭐</span>
        ) : (
          <span className={`flex items-center gap-1 ${short ? "text-ink-mist" : "text-accent-lime"}`}>
            <IconCoin size={11} /> {pack.price.toLocaleString("ru-RU")}
          </span>
        )
      }
      details={
        <>
          <span className="text-caption text-ink-mist">
            {pack.card_count} карт.
            {pack.expected_value != null && pack.expected_value > 0 && ` · ценность ~${Math.round(pack.expected_value)}`}
          </span>
          {pack.description && <span className="text-xs text-ink-mist">{pack.description}</span>}
          <OddsBar pack={pack} className="h-2" />
          <OddsList pack={pack} />
          {pack.unavailable_reason && <span className="text-caption font-semibold text-amber-300">{pack.unavailable_reason}</span>}
          {pack.pity_left != null && (
            <span className="text-xs font-semibold text-amber-300">🎯 Легендарка гарантирована через {pack.pity_left} {packsWord(pack.pity_left)}</span>
          )}
          {endsIn && <span className="text-xs font-semibold text-red-400">⏳ Уйдёт из магазина через {endsIn}</span>}
          {remaining !== null && <span className="text-caption text-amber-300">Можно купить ещё: {remaining}</span>}
        </>
      }
      action={
        isStars ? (
          <StarsBuyButton compact pack={pack} onPurchased={(r) => onStarsPurchased(pack, r)} />
        ) : blocked ? (
          <span className="rounded-full bg-white/5 py-3 text-center text-sm font-semibold text-ink-mist">Сейчас недоступен</span>
        ) : short ? (
          <TopUpButton need={pack.price - balance} stars={topUpStars(pack.price - balance)} onClick={onNeedCoins} className="rounded-full py-3 text-sm" />
        ) : (
          <div className="grid grid-cols-3 gap-2">
            {QUANTITIES.map((q) => {
              const total = packTotal(pack, q);
              const allowed = (remaining === null || q <= remaining) && total <= balance;
              return (
                <button
                  key={q}
                  onClick={() => onOpen(pack, q)}
                  disabled={!allowed}
                  className={`flex flex-col items-center rounded-2xl active:scale-95 disabled:opacity-35 ${
                    q === 1 ? "bg-white/5 text-ink-chalk ring-1 ring-white/10" : "bg-floodlight text-bg-base"
                  }`}
                >
                  <span className="font-display text-base font-bold leading-none">×{q}</span>
                  <span className="mt-1 flex items-center gap-0.5 font-mono text-micro font-semibold">
                    <IconCoin size={10} /> {total.toLocaleString("ru-RU")}
                  </span>
                  {total < pack.price * q && <span className="text-micro font-bold">−{pack.bulk10_discount_pct}%</span>}
                </button>
              );
            })}
            {onCustom && (
              <button
                onClick={() => onCustom(pack)}
                className="flex flex-col items-center justify-center rounded-2xl bg-white/5 text-ink-chalk ring-1 ring-white/10 active:scale-95"
              >
                <span className="font-display text-base font-bold leading-none">×?</span>
                <span className="mt-1 text-micro font-semibold text-ink-mist">своё</span>
              </button>
            )}
          </div>
        )
      }
    />
  );
}
