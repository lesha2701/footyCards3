import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  buyEquipment, createEquipmentStarsInvoice, fetchEquipmentShop, type EquipmentItem,
} from "@/api/equipment";
import EmptyState from "@/components/common/EmptyState";
import { IconCoin } from "@/components/icons";
import InfoTile from "@/components/shop/InfoTile";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { RARITY_GRADIENTS, RARITY_LABELS } from "@/lib/rarity";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useOpenTile } from "@/lib/useOpenTile";
import { useSeenItems } from "@/lib/useSeenItems";
import { useAuthStore } from "@/store/authStore";

/** «Экипировка» catalog in the shop look: collections (with their set
 * bonus) and single things as square tiles with a price chip; a tap opens
 * the sheet with the effect, conditions and the buy buttons. Things are put
 * on in the card sheet («Вещи»). Used by the shop tab and /equipment. */
export default function EquipmentShop() {
  const queryClient = useQueryClient();
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tiles = useOpenTile<number>();
  const { data } = useQuery({ queryKey: ["equipment-shop"], queryFn: fetchEquipmentShop });
  const allIds = data ? [...data.collections.flatMap((c) => c.items), ...data.singles].map((i) => i.id) : undefined;
  const seen = useSeenItems("equipment", allIds);

  const done = (name: string) => {
    hapticNotify("success");
    setError(null);
    tiles.close();
    setNotice(`«${name}» в инвентаре — надень её в карточке игрока, вкладка «Вещи»`);
    queryClient.invalidateQueries({ queryKey: ["equipment-shop"] });
    queryClient.invalidateQueries({ queryKey: ["equipment-inventory"] });
    queryClient.invalidateQueries({ queryKey: ["card-equipment"] });
  };
  const buyCoins = useMutation({
    mutationFn: (item: EquipmentItem) => buyEquipment(item.id, crypto.randomUUID()),
    onSuccess: (res, item) => {
      updateBalance(res.new_balance);
      done(item.name);
    },
    onError: (err) => setError(formatGameError(err, "Не получилось купить")),
  });
  const buyStars = useMutation({
    mutationFn: (item: EquipmentItem) => payShopWithStars(() => createEquipmentStarsInvoice(item.id)),
    onSuccess: (status, item) => status === "paid" && done(item.name),
    onError: (err) => setError(formatGameError(err, "Оплата не прошла")),
  });

  if (!data) return null;
  if (!data.enabled) return <EmptyState title="Экипировка скоро появится" description="Загляни позже" />;
  const busy = buyCoins.isPending || buyStars.isPending;

  const tile = (item: EquipmentItem, setNote?: string) => (
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
      accent={item.stars_price > 0 && !item.coins_price ? "stars" : undefined}
      badge={
        item.owned ? (
          <span className="rounded-full bg-accent-lime px-1.5 py-0.5 text-micro font-bold text-bg-base">✓ {item.owned}</span>
        ) : (
          <span className="rounded-full bg-black/75 px-1.5 py-0.5 text-micro font-semibold text-ink-chalk">{item.slot_label}</span>
        )
      }
      visual={
        <span className={`block h-full w-full bg-gradient-to-b p-[3px] ${RARITY_GRADIENTS[item.rarity]}`}>
          <span className="flex h-full w-full items-center justify-center overflow-hidden rounded-[13px] bg-bg-base">
            {item.image_path ? (
              <img src={staticUrl(item.image_path)} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
            ) : (
              <span className="text-5xl" aria-hidden>{item.icon}</span>
            )}
          </span>
        </span>
      }
      price={
        item.coins_price > 0 ? (
          <span className={`flex items-center gap-1 ${balance < item.coins_price ? "text-ink-mist" : "text-accent-lime"}`}>
            <IconCoin size={11} /> {item.coins_price.toLocaleString("ru-RU")}
          </span>
        ) : (
          <span className="text-amber-300">{item.stars_price} ⭐</span>
        )
      }
      details={
        <>
          <span className="flex flex-wrap items-center gap-x-2 font-mono text-xs font-bold">
            {item.coins_price > 0 && (
              <span className="flex items-center gap-1 text-accent-lime">
                <IconCoin size={12} /> {item.coins_price.toLocaleString("ru-RU")}
              </span>
            )}
            {item.coins_price > 0 && item.stars_price > 0 && <span className="font-sans font-normal text-ink-mist-dim">или</span>}
            {item.stars_price > 0 && <span className="text-amber-300">{item.stars_price} ⭐</span>}
          </span>
          <span className="text-caption text-ink-mist">
            {item.slot_label} · {RARITY_LABELS[item.rarity]}
          </span>
          <span className="text-sm font-semibold text-accent-lime">{item.effect_label}</span>
          {item.cond_club && <span className="text-xs text-amber-300">Действует только для игроков «{item.cond_club}»</span>}
          {item.cond_country && <span className="text-xs text-amber-300">Действует только для игроков страны {item.cond_country}</span>}
          {setNote && <span className="text-xs text-path">{setNote}</span>}
          {item.description && <span className="text-xs text-ink-mist">{item.description}</span>}
          {!!item.owned && <span className="text-caption text-ink-mist">У тебя: {item.owned}</span>}
          <span className="text-caption text-ink-mist-dim">Надеть — в карточке игрока, вкладка «Вещи».</span>
        </>
      }
      action={
        <div className="flex gap-2">
          {item.coins_price > 0 && (
            <button
              onClick={() => buyCoins.mutate(item)}
              disabled={busy || balance < item.coins_price}
              className="flex flex-1 items-center justify-center gap-1 rounded-full bg-floodlight font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              {item.coins_price.toLocaleString("ru-RU")} <IconCoin size={13} />
            </button>
          )}
          {item.stars_price > 0 && (
            <button
              onClick={() => buyStars.mutate(item)}
              disabled={busy}
              className="flex-1 rounded-full bg-amber-400 font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              {item.stars_price} ⭐
            </button>
          )}
        </div>
      }
    />
  );

  return (
    <div className="flex flex-col gap-4">
      {notice && <p className="rounded-xl bg-accent-lime/10 px-3 py-2 text-xs text-accent-lime" role="status">{notice}</p>}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {data.collections.filter((c) => c.items.length).map((c) => {
        const setNote =
          c.set_bonus_rating > 0
            ? `Полный комплект «${c.name}» (${c.set_size} шт.) на одной карточке — ещё +${c.set_bonus_rating} к рейтингу`
            : undefined;
        return (
          <section key={c.id} className="flex flex-col gap-2">
            <div className="flex items-end justify-between gap-2">
              <div className="min-w-0">
                <p className="font-display text-base font-bold text-ink-chalk">«{c.name}»</p>
                {c.description && <p className="text-xs text-ink-mist">{c.description}</p>}
              </div>
              {c.set_bonus_rating > 0 && (
                <span className="shrink-0 rounded-full bg-path/15 px-2 py-1 text-micro font-bold text-path">
                  Комплект {c.set_size}: +{c.set_bonus_rating}
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2.5">{c.items.map((i) => tile(i, setNote))}</div>
          </section>
        );
      })}
      {data.singles.length > 0 && (
        <section className="flex flex-col gap-2">
          <p className="font-display text-base font-bold text-ink-chalk">Отдельные вещи</p>
          <div className="grid grid-cols-2 gap-2.5">{data.singles.map((i) => tile(i))}</div>
        </section>
      )}
      <p className="text-micro text-ink-mist-dim">
        На одной карточке вещи дают не больше +{data.caps.rating} к рейтингу, +{data.caps.pp}% к удару или обыгрышу и +
        {data.caps.chemistry} к химии. Точность удара и обыгрыш действуют в Card Arena, турнирах игроков и карьере (в Арене обыгрыш — в выходах один на один и проходах по флангу).
      </p>
    </div>
  );
}
