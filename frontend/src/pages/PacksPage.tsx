import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import EmptyState from "@/components/common/EmptyState";
import { IconChevronUp, IconPack } from "@/components/icons";
import { CardGridSkeleton, ListSkeleton } from "@/components/common/Skeleton";
import { BuyCoinsModal, CoinPackagesPanel } from "@/components/shop/CoinPackages";
import DailyOfferCard from "@/components/shop/DailyOfferCard";
import EquipmentShop from "@/components/shop/EquipmentShop";
import PackMachine from "@/components/shop/PackMachine";
import PackTile from "@/components/shop/PackTile";
import QuantitySheet from "@/components/shop/QuantitySheet";
import StyleShop from "@/components/shop/StyleShop";
import { fetchDailyOffer, fetchPacks } from "@/api/packs";
import { PACK_PURCHASE_TERMS_URL } from "@/lib/legalLinks";
import { packBlocked, packEndsIn, packRemaining, packTotal } from "@/lib/packOdds";
import { useOpenTile } from "@/lib/useOpenTile";
import { useSeenItems } from "@/lib/useSeenItems";
import { useTopUpStars } from "@/lib/useTopUp";
import { openLink } from "@/lib/telegram";
import { sortPacksByPrice, sortPacksByStarsPrice } from "@/lib/packs";
import { useAuthStore } from "@/store/authStore";
import { usePacksUiStore } from "@/store/packsUiStore";
import MonetizationEntries from "@/components/shop/MonetizationEntries";
import ArtifactShop from "@/components/artifacts/ArtifactShop";
import { fetchEquipmentShop } from "@/api/equipment";
import { fetchArtifacts } from "@/api/monetization";
import { StarterOfferBanner } from "@/components/shop/StarterOffer";
import type { Pack, PackOpenResult } from "@/types";

// Matches backend's pack_service.MAX_BULK_PACK_QUANTITY — enforced there
// regardless, but clamping here too avoids the user typing something the
// server will just reject.
const MAX_BULK_PACK_QUANTITY = 100;
const BULK_QUANTITY_PRESETS = [10];

// The gift shop lives in GiftsPage (inventory + shop); loaded only when the
// "Подарки" tab is opened.
const GiftShop = lazy(() => import("@/pages/GiftsPage").then((m) => ({ default: m.GiftShop })));

type ShopTab = "coins" | "buy-coins" | "equipment" | "style" | "gifts" | "artifacts";
const SHOP_TABS: { id: ShopTab; label: string }[] = [
  { id: "coins", label: "Паки" },
  { id: "buy-coins", label: "Монеты" },
  { id: "equipment", label: "Экипировка" },
  { id: "artifacts", label: "Артефакты" },
  { id: "style", label: "Стиль" },
  { id: "gifts", label: "Подарки" },
];

export default function PacksPage() {
  const { data: packs, isLoading } = useQuery({ queryKey: ["packs"], queryFn: fetchPacks });
  const { data: dailyOffer } = useQuery({ queryKey: ["packs", "daily-offer"], queryFn: fetchDailyOffer });
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const navigate = useNavigate();
  const sortDirection = usePacksUiStore((s) => s.coinSortDirection);
  const setSortDirection = usePacksUiStore((s) => s.setCoinSortDirection);
  // One «Магазин» section; the tab is in the URL (?tab=) so links can open
  // it directly. Old «?tab=stars» links land on «Паки» (Stars packs live there now).
  const [params, setParams] = useSearchParams();
  // Old links: «?tab=stars» → «Паки», «?tab=passes» → «Стиль» (passes now sit in «Монеты»).
  const rawTab = params.get("tab") === "passes" ? "style" : params.get("tab");
  const tab: ShopTab = SHOP_TABS.some((t) => t.id === rawTab) ? (rawTab as ShopTab) : "coins";
  const setTab = (next: ShopTab) => setParams(next === "coins" ? {} : { tab: next }, { replace: true });
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [sheet, setSheet] = useState<{ pack: Pack; quantity: number } | null>(null);
  const tiles = useOpenTile<number>();
  const topUpStars = useTopUpStars();
  const seenPacks = useSeenItems("packs", packs?.map((p) => p.id));
  const [topUp, setTopUp] = useState(false);
  const [machinePick, setMachinePick] = useState<number | null>(null);

  // «Артефакты» / «Экипировка» tabs hide once the server says they are off (shown while loading, so the grid does not jump).
  const { data: artifacts } = useQuery({ queryKey: ["artifacts"], queryFn: fetchArtifacts });
  const { data: equipment } = useQuery({ queryKey: ["equipment-shop"], queryFn: fetchEquipmentShop });
  const shopTabs = SHOP_TABS.filter(
    (t) => (t.id !== "artifacts" || artifacts?.enabled !== false) && (t.id !== "equipment" || equipment?.enabled !== false),
  );

  // Coin packs then Stars packs, each by price; the grid follows the sort toggle.
  const allPacks = useMemo(() => {
    const coin = (packs ?? []).filter((p) => p.stars_price == null);
    const stars = (packs ?? []).filter((p) => p.stars_price != null);
    return [...sortPacksByPrice(coin, sortDirection), ...sortPacksByStarsPrice(stars, sortDirection)];
  }, [packs, sortDirection]);
  // The machine always runs cheap → expensive; it starts on today's offer,
  // else on the priciest coin pack the player can afford.
  const machinePacks = useMemo(() => {
    const coin = (packs ?? []).filter((p) => p.stars_price == null);
    const stars = (packs ?? []).filter((p) => p.stars_price != null);
    return [...sortPacksByPrice(coin, "asc"), ...sortPacksByStarsPrice(stars, "asc")];
  }, [packs]);
  const defaultIndex = (() => {
    const offerIdx = dailyOffer ? machinePacks.findIndex((p) => p.id === dailyOffer.pack.id) : -1;
    if (offerIdx >= 0) return offerIdx;
    // A pack about to leave the shop goes first.
    const limitedIdx = machinePacks.findIndex((p) => !packBlocked(p) && packEndsIn(p));
    if (limitedIdx >= 0) return limitedIdx;
    let best = 0;
    machinePacks.forEach((p, i) => {
      if (p.stars_price == null && !packBlocked(p) && p.price <= balance) best = i;
    });
    return best;
  })();
  const machineIndex = machinePick !== null && machinePick < machinePacks.length ? machinePick : defaultIndex;

  const openOne = (pack: Pack) => navigate(`/packs/${pack.id}/open`);
  const starsDone = (pack: Pack, result: PackOpenResult) => navigate(`/packs/${pack.id}/open`, { state: { result } });
  // Short on coins: top up right here instead of leaving for «Монеты».
  const needCoins = () => setTopUp(true);

  return (
    <div className="flex flex-col gap-4">
      {/* Every section visible at once: a 3-column grid, never a sideways scroller. */}
      <div className="grid grid-cols-3 gap-1.5" role="tablist" aria-label="Разделы магазина">
        {shopTabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`min-w-0 truncate rounded-full px-2 py-2 text-xs font-semibold transition active:scale-95 ${
              tab === t.id
                ? t.id === "buy-coins" ? "bg-amber-400 text-bg-base" : "bg-floodlight text-bg-base"
                : "bg-bg-surface text-ink-mist"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isLoading && tab === "coins" && <CardGridSkeleton count={3} />}

      {tab === "buy-coins" ? (
        <>
          <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
            <div>
              <p className="font-display text-base font-bold text-ink-chalk">Монеты за Telegram Stars</p>
              <p className="mt-1 text-xs text-ink-mist">Монеты сразу зачисляются на баланс и тратятся на паки, навыки и всё остальное.</p>
            </div>
            <CoinPackagesPanel onPurchased={updateBalance} />
          </section>
          {/* Club and season passes sit with the coins (same Stars buyers). */}
          <MonetizationEntries showStyle={false} showArtifacts={false} showEquipment={false} />
        </>
      ) : tab === "equipment" ? (
        <EquipmentShop />
      ) : tab === "artifacts" ? (
        <ArtifactShop />
      ) : tab === "gifts" ? (
        <Suspense fallback={<ListSkeleton count={3} />}>
          <button onClick={() => navigate("/gifts")} className="self-end text-xs font-semibold text-accent-lime">
            Мои подарки →
          </button>
          <GiftShop />
        </Suspense>
      ) : tab === "style" ? (
        <>
          <StyleShop />
          <p className="text-center text-caption text-ink-mist-dim">
            Покупки за Telegram Stars напрямую поддерживают разработку VICTOR FC — спасибо! ⭐
          </p>
        </>
      ) : (
        <>
          {/* First purchase is the big one: the starter offer leads the packs tab. */}
          <StarterOfferBanner />
          <DailyOfferCard />
          {!isLoading && !allPacks.length && <EmptyState icon={IconPack} title="Паков пока нет" description="Загляни позже" />}
          {!!machinePacks.length && (
            <PackMachine
              packs={machinePacks}
              index={machineIndex}
              onIndexChange={setMachinePick}
              balance={balance}
              onOpen={openOne}
              onOpenMany={(pack, quantity) => setSheet({ pack, quantity })}
              onNeedCoins={needCoins}
              topUpStars={topUpStars}
              onStarsPurchased={starsDone}
            />
          )}
          {!!allPacks.length && (
            <section>
              <div className="mb-2 flex items-center justify-between">
                <h2 className="font-display text-base font-bold text-ink-chalk">Все паки</h2>
                <button
                  onClick={() => setSortDirection(sortDirection === "asc" ? "desc" : "asc")}
                  className="flex items-center gap-1.5 rounded-full bg-bg-surface px-3 py-1.5 font-mono text-xs text-ink-mist active:scale-95"
                >
                  <IconChevronUp size={12} className={`transition-transform ${sortDirection === "asc" ? "" : "rotate-180"}`} />
                  {sortDirection === "asc" ? "Дешевле → дороже" : "Дороже → дешевле"}
                </button>
              </div>
              <p className="mb-2 text-caption text-ink-mist">Нажми на пак — покажем цену, шансы и ценность</p>
              <div className="grid grid-cols-2 gap-2.5">
                {allPacks.map((pack) => (
                  <PackTile
                    key={pack.id}
                    pack={pack}
                    open={tiles.openKey === pack.id}
                    onToggle={() => {
                      seenPacks.markSeen(pack.id);
                      tiles.toggle(pack.id);
                    }}
                    isNew={seenPacks.isNew(pack.id)}
                    balance={balance}
                    onOpen={(p, quantity) => navigate(`/packs/${p.id}/open`, quantity > 1 ? { state: { quantity } } : undefined)}
                    onNeedCoins={needCoins}
                    topUpStars={topUpStars}
                    onCustom={(p) => {
                      tiles.close();
                      setSheet({ pack: p, quantity: 1 });
                    }}
                    onStarsPurchased={starsDone}
                  />
                ))}
              </div>
            </section>
          )}
          <button
            onClick={() => openLink(PACK_PURCHASE_TERMS_URL)}
            className="text-center text-caption text-ink-mist-dim underline underline-offset-2"
          >
            Условия покупки цифровых паков
          </button>
        </>
      )}

      {topUp && <BuyCoinsModal onClose={() => setTopUp(false)} onPurchased={updateBalance} />}

      {sheet && (
        <QuantitySheet
          name={sheet.pack.name}
          unitPrice={sheet.pack.price}
          total={(q) => packTotal(sheet.pack, q)}
          maxQuantity={Math.min(MAX_BULK_PACK_QUANTITY, packRemaining(sheet.pack) ?? MAX_BULK_PACK_QUANTITY)}
          presets={BULK_QUANTITY_PRESETS}
          initialQuantity={sheet.quantity}
          balance={balance}
          onClose={() => setSheet(null)}
          onConfirm={(quantity) => {
            const pack = sheet.pack;
            setSheet(null);
            navigate(`/packs/${pack.id}/open`, quantity > 1 ? { state: { quantity } } : undefined);
          }}
        />
      )}
    </div>
  );
}
