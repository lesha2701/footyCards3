import { useMarkSeen } from "@/lib/seenSections";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { buyCosmeticWithCoins, createCosmeticStarsInvoice, equipCosmetic, fetchCosmetics } from "@/api/monetization";
import { IconCoin } from "@/components/icons";
import CosmeticPreview from "@/components/shop/CosmeticPreview";
import InfoTile from "@/components/shop/InfoTile";
import { KIND_LABELS, backgroundClass } from "@/lib/cosmetics";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useOpenTile } from "@/lib/useOpenTile";
import { useSeenItems } from "@/lib/useSeenItems";
import { useAuthStore } from "@/store/authStore";
import type { CosmeticCatalog, CosmeticCatalogItem, CosmeticKind } from "@/types";

const KIND_GROUPS: { title: string; kinds: CosmeticKind[] }[] = [
  { title: "Профиль", kinds: ["profile_frame", "profile_background", "card_skin"] },
  { title: "Мордобой", kinds: ["brutality", "ring_gloves", "ring_shorts", "ring_entrance", "helmet"] },
];

const SHORT_LABELS: Record<CosmeticKind, string> = {
  profile_frame: "Рамки",
  profile_background: "Фоны",
  card_skin: "Скины карт",
  brutality: "Бруталити",
  ring_gloves: "Перчатки",
  ring_shorts: "Трусы",
  ring_entrance: "Выход",
  helmet: "Каска",
};

/** Owned first-to-buy order: what you can buy now, then the rest, then
 * what you already have. */
function shopOrder(a: CosmeticCatalogItem, b: CosmeticCatalogItem) {
  const rank = (i: CosmeticCatalogItem) => (i.owned ? 2 : i.coins_price || i.stars_price ? 0 : 1);
  return rank(a) - rank(b) || a.sort_order - b.sort_order;
}

/** «Стиль» catalog: profile frames, profile backgrounds and card skins —
 * visual only, bought for coins or ⭐ or earned in the calendar, club pass,
 * season pass and starter offer. The same square tiles and details sheet
 * as the rest of the shop; used by the «Стиль» page and the shop tab. */
export default function StyleShop() {
  useMarkSeen("style");
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [kind, setKind] = useState<CosmeticKind>("profile_frame");
  const [error, setError] = useState<string | null>(null);
  const tiles = useOpenTile<number>();
  const { data: catalog } = useQuery({ queryKey: ["cosmetics"], queryFn: fetchCosmetics });
  const seen = useSeenItems("cosmetics", catalog?.items.map((i) => i.id));

  const apply = (data: CosmeticCatalog) => {
    queryClient.setQueryData(["cosmetics"], data);
    queryClient.invalidateQueries({ queryKey: ["profile", "me"] });
    updateBalance(data.balance);
    setError(null);
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));

  const buyCoins = useMutation({
    mutationFn: (id: number) => buyCosmeticWithCoins(id),
    onSuccess: (data) => {
      hapticNotify("success");
      apply(data);
    },
    onError,
  });
  const buyStars = useMutation({
    mutationFn: (id: number) => payShopWithStars(() => createCosmeticStarsInvoice(id)),
    onSuccess: (status) => {
      if (status === "paid") hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["cosmetics"] });
      queryClient.invalidateQueries({ queryKey: ["profile", "me"] });
    },
    onError,
  });
  const equip = useMutation({
    mutationFn: ({ k, id }: { k: CosmeticKind; id: number | null }) => equipCosmetic(k, id),
    onSuccess: apply,
    onError,
  });

  const items = (catalog?.items.filter((i) => i.kind === kind) ?? []).sort(shopOrder);
  const busy = buyCoins.isPending || buyStars.isPending || equip.isPending;
  const balance = catalog?.balance ?? 0;
  const avatar = user?.avatar_url ?? undefined;

  return (
    <div className="flex flex-col gap-3">
      {catalog && (
        <section
          className={`flex items-center gap-4 rounded-3xl p-4 ring-1 ring-white/5 ${backgroundClass(catalog.equipped.background) ?? "bg-bg-surface"}`}
        >
          <CosmeticPreview item={{ kind: "profile_frame", style_key: catalog.equipped.frame ?? "" }} avatarUrl={avatar} />
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-base font-bold text-ink-chalk">{user?.first_name}</p>
            <p className="text-caption text-ink-mist">Так тебя видят другие · на матчи не влияет</p>
          </div>
          <CosmeticPreview item={{ kind: "card_skin", style_key: catalog.equipped.card_skin ?? "" }} />
        </section>
      )}

      {/* Every section visible at once (no sideways scroller): two labelled groups. */}
      {KIND_GROUPS.map((group) => (
        <div key={group.title} className="flex flex-col gap-1.5">
          <span className="font-mono text-micro uppercase tracking-wider text-ink-mist-dim">{group.title}</span>
          <div className="grid grid-cols-3 gap-1.5">
            {group.kinds.map((k) => (
              <button
                key={k}
                onClick={() => setKind(k)}
                className={`min-w-0 truncate rounded-full px-2 py-2 text-xs font-semibold active:scale-95 ${
                  kind === k ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"
                }`}
              >
                {SHORT_LABELS[k]}
              </button>
            ))}
          </div>
        </div>
      ))}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="grid grid-cols-2 gap-2.5">
        {items.map((item) => {
          const rewardOnly = !item.coins_price && !item.stars_price;
          return (
            <InfoTile
              key={item.id}
              shape="square"
              open={tiles.openKey === item.id}
              onToggle={() => {
                seen.markSeen(item.id);
                tiles.toggle(item.id);
              }}
              isNew={seen.isNew(item.id)}
              name={item.name}
              accent={item.equipped ? "selected" : !item.coins_price && item.stars_price ? "stars" : undefined}
              visual={
                <span
                  className={`flex h-full w-full items-center justify-center ${
                    item.kind === "profile_background" ? "" : "bg-gradient-to-b from-white/[0.04] to-transparent"
                  }`}
                >
                  <CosmeticPreview item={item} avatarUrl={avatar} size="lg" />
                </span>
              }
              badge={
                item.equipped ? (
                  <span className="rounded-full bg-accent-lime px-1.5 py-0.5 text-micro font-bold text-bg-base">Надето</span>
                ) : item.owned ? (
                  <span className="rounded-full bg-white/15 px-1.5 py-0.5 text-micro font-bold text-ink-chalk">✓ есть</span>
                ) : undefined
              }
              price={
                item.owned ? undefined : rewardOnly ? (
                  <span className="font-sans text-ink-mist">награда</span>
                ) : item.coins_price ? (
                  <span className={`flex items-center gap-1 ${balance < item.coins_price ? "text-ink-mist" : "text-accent-lime"}`}>
                    <IconCoin size={11} /> {item.coins_price.toLocaleString("ru-RU")}
                  </span>
                ) : (
                  <span className="text-amber-300">{item.stars_price} ⭐</span>
                )
              }
              details={
                <>
                  <span className="text-caption text-ink-mist">
                    {item.kind === "brutality"
                      ? "Добивание после победы в «Мордобое» — шутка, на бой не влияет"
                      : item.kind === "helmet"
                        ? "Одноразовая: отразит чужое бруталити, потом можно купить снова"
                        : item.kind.startsWith("ring_")
                          ? `${KIND_LABELS[item.kind]} · вид твоего боксёра в «Мордобое»`
                          : `${KIND_LABELS[item.kind]} · только внешний вид`}
                  </span>
                  {!item.owned && !rewardOnly && (
                    <span className="flex flex-wrap items-center gap-x-2 font-mono text-xs font-bold">
                      {item.coins_price > 0 && (
                        <span className="flex items-center gap-1 text-accent-lime">
                          <IconCoin size={12} /> {item.coins_price.toLocaleString("ru-RU")}
                        </span>
                      )}
                      {item.coins_price > 0 && item.stars_price > 0 && <span className="font-sans font-normal text-ink-mist-dim">или</span>}
                      {item.stars_price > 0 && <span className="text-amber-300">{item.stars_price} ⭐</span>}
                    </span>
                  )}
                  {item.description && <span className="text-xs text-ink-mist">{item.description}</span>}
                  {item.status > 0 && <span className="text-xs font-semibold text-amber-300">+{item.status} статуса Моему игроку</span>}
                  {item.kind === "brutality" && (item.win_bonus_coins ?? 0) > 0 && (
                    <span className="flex items-center gap-1 text-xs font-semibold text-accent-lime">
                      +{item.win_bonus_coins} <IconCoin size={11} /> к выигрышу каждый раз, когда применяешь
                    </span>
                  )}
                  {item.is_exclusive && <span className="text-caption text-path">Эксклюзив</span>}
                  {rewardOnly && !item.owned && (
                    <span className="text-xs text-ink-mist">Не продаётся — выпадает в календаре, пропусках и стартовом наборе.</span>
                  )}
                </>
              }
              action={
                item.owned && item.kind === "brutality" ? (
                  <span className="text-center text-caption text-ink-mist">Есть — применяй на экране итога боя</span>
                ) : item.owned && item.kind === "helmet" ? (
                  <span className="text-center text-caption text-ink-mist">Надета — сработает сама 🪖</span>
                ) : item.owned ? (
                  <button
                    onClick={() => equip.mutate({ k: item.kind, id: item.equipped ? null : item.id })}
                    disabled={busy}
                    className={`rounded-full font-bold active:scale-95 disabled:opacity-40 ${
                      item.equipped ? "bg-white/10 text-ink-mist" : "bg-floodlight text-bg-base"
                    }`}
                  >
                    {item.equipped ? "Снять" : "Надеть"}
                  </button>
                ) : rewardOnly ? undefined : (
                  <div className="flex gap-2">
                    {item.coins_price > 0 && (
                      <button
                        onClick={() => buyCoins.mutate(item.id)}
                        disabled={busy || balance < item.coins_price}
                        className="flex flex-1 items-center justify-center gap-1 rounded-full bg-floodlight font-bold text-bg-base active:scale-95 disabled:opacity-40"
                      >
                        {item.coins_price.toLocaleString("ru-RU")} <IconCoin size={13} />
                      </button>
                    )}
                    {item.stars_price > 0 && (
                      <button
                        onClick={() => buyStars.mutate(item.id)}
                        disabled={busy}
                        className="flex-1 rounded-full bg-amber-400 font-bold text-bg-base active:scale-95 disabled:opacity-40"
                      >
                        {item.stars_price} ⭐
                      </button>
                    )}
                  </div>
                )
              }
            />
          );
        })}
        {catalog && items.length === 0 && <p className="col-span-2 py-6 text-center text-sm text-ink-mist">Здесь пока пусто</p>}
      </div>
    </div>
  );
}
