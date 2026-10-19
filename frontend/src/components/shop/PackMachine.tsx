import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { IconChevronLeft, IconChevronRight, IconCoin } from "@/components/icons";
import { OddsBar } from "@/components/shop/PackOdds";
import StarsBuyButton from "@/components/shop/StarsBuyButton";
import TopUpButton from "@/components/shop/TopUpButton";
import { staticUrl } from "@/lib/api";
import { packBlocked, packEndsIn, packRemaining, packsWord, packTotal, pct, rarityLabel, topChance } from "@/lib/packOdds";
import { hapticSelection } from "@/lib/telegram";
import type { Pack, PackOpenResult } from "@/types";

const BULK = 10;
/** Auto-advance every few seconds; any touch or hover holds it for a while. */
const AUTO_MS = 4000;
const HOLD_MS = 12000;

/** «Автомат паков»: one big pack at a time, flipped with arrows or a swipe,
 * with «×1» and «×10» right under it. Coin packs open straight away (×1) or
 * through the quantity sheet (×10); Stars packs go through the invoice. */
export default function PackMachine({
  packs,
  index,
  onIndexChange,
  balance,
  onOpen,
  onOpenMany,
  onNeedCoins,
  topUpStars,
  onStarsPurchased,
}: {
  packs: Pack[];
  index: number;
  onIndexChange: (index: number) => void;
  balance: number;
  onOpen: (pack: Pack) => void;
  onOpenMany: (pack: Pack, quantity: number) => void;
  onNeedCoins: () => void;
  topUpStars: (need: number) => number | null;
  onStarsPurchased: (pack: Pack, result: PackOpenResult) => void;
}) {
  const [direction, setDirection] = useState(1);
  const [holdUntil, setHoldUntil] = useState(0);
  const [hovered, setHovered] = useState(false);
  const touch = useRef<{ x: number; y: number } | null>(null);
  const count = packs.length;

  useEffect(() => {
    if (count < 2 || hovered) return;
    const wait = Math.max(AUTO_MS, holdUntil - Date.now());
    const t = setTimeout(() => {
      if (document.hidden) return setHoldUntil(Date.now() + AUTO_MS);
      setDirection(1);
      onIndexChange((index + 1) % count);
    }, wait);
    return () => clearTimeout(t);
  }, [index, count, hovered, holdUntil, onIndexChange]);

  const pack = packs[index];
  if (!pack) return null;

  const hold = () => setHoldUntil(Date.now() + HOLD_MS);
  const go = (step: number) => {
    if (count < 2) return;
    hold();
    hapticSelection();
    setDirection(step);
    onIndexChange((index + step + count) % count);
  };

  const top = topChance(pack);
  const endsIn = packEndsIn(pack);
  const isStars = pack.stars_price != null;

  return (
    <section
      className="relative overflow-hidden rounded-3xl bg-gradient-to-b from-bg-raised to-bg-surface p-4 ring-1 ring-white/5"
      data-no-swipe
      onPointerEnter={(e) => e.pointerType === "mouse" && setHovered(true)}
      onPointerLeave={(e) => e.pointerType === "mouse" && setHovered(false)}
      onPointerDown={hold}
      onTouchStart={(e) => (touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY })}
      onTouchEnd={(e) => {
        const s = touch.current;
        touch.current = null;
        if (!s) return;
        const dx = e.changedTouches[0].clientX - s.x;
        const dy = e.changedTouches[0].clientY - s.y;
        if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) go(dx < 0 ? 1 : -1);
      }}
    >
      <div className="pointer-events-none absolute -top-16 left-1/2 h-48 w-48 -translate-x-1/2 rounded-full bg-accent-lime/15 blur-3xl" />

      <div className="relative flex items-center justify-between gap-2">
        <button
          onClick={() => go(-1)}
          disabled={packs.length < 2}
          aria-label="Предыдущий пак"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/5 text-ink-mist active:scale-90 disabled:opacity-0"
        >
          <IconChevronLeft size={18} />
        </button>
        <div className="relative h-52 w-40">
          <AnimatePresence initial={false} custom={direction} mode="popLayout">
            <motion.div
              key={pack.id}
              custom={direction}
              initial={{ x: direction * 120, opacity: 0, rotate: direction * 6 }}
              animate={{ x: 0, opacity: 1, rotate: 0 }}
              exit={{ x: direction * -120, opacity: 0, rotate: direction * -6 }}
              transition={{ type: "spring", stiffness: 320, damping: 30 }}
              className="card-shine absolute inset-0 overflow-hidden rounded-2xl shadow-xl shadow-black/40"
            >
              <img decoding="async" src={staticUrl(pack.image_path ?? undefined)} alt={pack.name} className="h-full w-full object-cover" />
            </motion.div>
          </AnimatePresence>
        </div>
        <button
          onClick={() => go(1)}
          disabled={packs.length < 2}
          aria-label="Следующий пак"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/5 text-ink-mist active:scale-90 disabled:opacity-0"
        >
          <IconChevronRight size={18} />
        </button>
      </div>

      {packs.length > 1 && (
        <div className="relative mt-3 flex justify-center gap-1.5" aria-hidden>
          {packs.map((p, i) => (
            <span key={p.id} className={`h-1.5 rounded-full transition-all ${i === index ? "w-4 bg-accent-lime" : "w-1.5 bg-white/20"}`} />
          ))}
        </div>
      )}

      <div className="relative mt-3 text-center">
        <p className="font-display text-lg font-bold text-ink-chalk">{pack.name}</p>
        {endsIn && <p className="text-xs font-bold text-red-400">⏳ Только {endsIn}</p>}
        {pack.pity_left != null && (
          <p className="mt-0.5 text-xs font-semibold text-amber-300">
            🎯 Легендарка гарантирована через {pack.pity_left} {packsWord(pack.pity_left)}
          </p>
        )}
        <p className="text-xs text-ink-mist">
          {pack.card_count} карт.
          {top && ` · ${rarityLabel(pack, top.rarity)} ${pct(top.probability)}`}
          {pack.expected_value != null && pack.expected_value > 0 && ` · ценность ~${Math.round(pack.expected_value)}`}
        </p>
        <OddsBar pack={pack} className="mx-auto mt-2 h-2 max-w-[220px]" />
        {pack.unavailable_reason && (
          <p className="mt-2 rounded-lg bg-amber-400/10 px-2 py-1 text-caption font-semibold text-amber-300">{pack.unavailable_reason}</p>
        )}
      </div>

      <div className="relative mt-4 flex min-h-[64px] flex-col justify-center">
        {isStars ? (
          <StarsBuyButton key={pack.id} pack={pack} onPurchased={(r) => onStarsPurchased(pack, r)} />
        ) : (
          <CoinButtons pack={pack} balance={balance} onOpen={onOpen} onOpenMany={onOpenMany} onNeedCoins={onNeedCoins} topUpStars={topUpStars} />
        )}
      </div>
    </section>
  );
}

function CoinButtons({
  pack, balance, onOpen, onOpenMany, onNeedCoins, topUpStars,
}: {
  pack: Pack;
  balance: number;
  onOpen: (pack: Pack) => void;
  onOpenMany: (pack: Pack, quantity: number) => void;
  onNeedCoins: () => void;
  topUpStars: (need: number) => number | null;
}) {
  if (packBlocked(pack)) {
    return <p className="rounded-2xl bg-white/5 py-3 text-center text-sm font-semibold text-ink-mist">Сейчас недоступен</p>;
  }
  if (balance < pack.price) {
    const need = pack.price - balance;
    return <TopUpButton need={need} stars={topUpStars(need)} onClick={onNeedCoins} className="rounded-2xl py-3 font-display text-sm" />;
  }
  const remaining = packRemaining(pack);
  // As many as the balance and the purchase limit allow, up to ten.
  // ×10 may be cheaper than 10 × price (admin's bulk discount).
  const fitsTen = packTotal(pack, BULK) <= balance && (remaining ?? BULK) >= BULK;
  const many = fitsTen ? BULK : Math.min(BULK - 1, remaining ?? BULK, Math.floor(balance / pack.price));
  const shownMany = many >= 2 ? many : BULK;
  const total = packTotal(pack, shownMany);
  const gross = pack.price * shownMany;
  return (
    <div className="grid grid-cols-2 gap-2">
      <button
        onClick={() => onOpen(pack)}
        className="flex flex-col items-center rounded-2xl bg-white/5 py-2.5 ring-1 ring-white/10 active:scale-95"
      >
        <span className="font-display text-base font-bold text-ink-chalk">×1</span>
        <span className="flex items-center gap-1 font-mono text-xs text-accent-lime">
          <IconCoin size={11} /> {pack.price.toLocaleString("ru-RU")}
        </span>
      </button>
      <button
        onClick={() => onOpenMany(pack, many)}
        disabled={many < 2}
        className="flex flex-col items-center rounded-2xl bg-floodlight py-2.5 text-bg-base active:scale-95 disabled:opacity-40"
      >
        <span className="font-display text-base font-bold">
          ×{shownMany}
          {total < gross && <span className="ml-1 rounded-full bg-bg-base/20 px-1.5 text-micro">−{pack.bulk10_discount_pct}%</span>}
        </span>
        <span className="flex items-center gap-1 font-mono text-xs font-semibold">
          {total < gross && <s className="opacity-60">{gross.toLocaleString("ru-RU")}</s>}
          <IconCoin size={11} /> {total.toLocaleString("ru-RU")}
        </span>
      </button>
    </div>
  );
}
