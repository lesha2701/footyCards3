import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  buyEquipment, createEquipmentStarsInvoice, fetchEquipmentInventory, fetchEquipmentShop, unequipItem,
  type EquipmentItem,
} from "@/api/equipment";
import EmptyState from "@/components/common/EmptyState";
import EquipmentTile from "@/components/equipment/EquipmentTile";
import { IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { RARITY_LABELS } from "@/lib/rarity";
import { payShopWithStars } from "@/lib/shopStars";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

type Tab = "inventory" | "shop";

/** «Экипировка»: the «Инвентарь» of owned things (and where each is worn)
 * and the shop, grouped by collection. Things are put on in the card sheet. */
export default function EquipmentPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "shop" ? "shop" : "inventory";
  const setTab = (next: Tab) => setParams(next === "shop" ? { tab: "shop" } : {}, { replace: true });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Экипировка</h1>
      <p className="-mt-2 text-xs text-ink-mist">
        Бутсы, форма, гетры, перчатки, аксессуар и артефакт дают карточке небольшой бонус. Надеть вещь — в карточке игрока, вкладка «Вещи».
      </p>
      <div className="grid grid-cols-2 gap-1 rounded-2xl bg-bg-surface p-1">
        {([["inventory", "Инвентарь"], ["shop", "Магазин"]] as [Tab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`min-h-[40px] rounded-xl text-xs font-semibold ${tab === id ? "bg-accent-lime text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "inventory" ? <Inventory onShop={() => setTab("shop")} /> : <Shop />}
    </div>
  );
}

function Inventory({ onShop }: { onShop: () => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["equipment-inventory"], queryFn: fetchEquipmentInventory });
  const unequip = useMutation({
    mutationFn: (copyId: number) => unequipItem(copyId),
    onSuccess: (inv) => {
      haptic("light");
      queryClient.setQueryData(["equipment-inventory"], inv);
      queryClient.invalidateQueries({ queryKey: ["card-equipment"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      setError(null);
    },
    onError: (err) => setError(formatGameError(err, "Не удалось снять")),
  });
  if (!data) return null;
  if (!data.items.length) {
    return (
      <div className="flex flex-col items-center gap-3">
        <EmptyState title="Инвентарь пуст" description="Купи первую вещь в магазине экипировки" />
        <button onClick={onShop} className="rounded-xl bg-accent-lime px-4 py-2 text-xs font-semibold text-bg-base">В магазин</button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {data.items.map(({ copy_id, item, card_name }) => (
        <div key={copy_id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
          <EquipmentTile item={item} size="sm" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink-chalk">{item.name}</p>
            <p className="text-xs text-accent-lime">{item.effect_label}</p>
            <p className="truncate text-micro text-ink-mist">
              {item.slot_label} · {card_name ? `надета: ${card_name}` : "свободна"}
            </p>
          </div>
          {card_name && (
            <button
              onClick={() => unequip.mutate(copy_id)}
              disabled={unequip.isPending}
              className="min-h-[36px] rounded-xl bg-white/5 px-3 text-xs font-semibold text-ink-mist disabled:opacity-40"
            >
              Снять
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function Shop() {
  const queryClient = useQueryClient();
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["equipment-shop"], queryFn: fetchEquipmentShop });
  const done = (name: string) => {
    hapticNotify("success");
    setError(null);
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
  const row = (item: EquipmentItem) => (
    <div key={item.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
      <EquipmentTile item={item} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-ink-chalk">{item.name}</p>
        <p className="text-xs text-accent-lime">{item.effect_label}</p>
        <p className="truncate text-micro text-ink-mist">
          {item.slot_label} · {RARITY_LABELS[item.rarity]}
          {item.cond_club ? ` · только для «${item.cond_club}»` : ""}
          {item.cond_country ? ` · только для страны ${item.cond_country}` : ""}
          {item.owned ? ` · у тебя ${item.owned}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 flex-col gap-1">
        {item.coins_price > 0 && (
          <button
            onClick={() => buyCoins.mutate(item)}
            disabled={busy || balance < item.coins_price}
            className="flex min-h-[32px] items-center justify-center gap-1 rounded-xl bg-accent-lime/15 px-2.5 text-xs font-semibold text-accent-lime disabled:opacity-40"
          >
            <IconCoin size={12} /> {item.coins_price}
          </button>
        )}
        {item.stars_price > 0 && (
          <button
            onClick={() => buyStars.mutate(item)}
            disabled={busy}
            className="min-h-[32px] rounded-xl bg-amber-300/15 px-2.5 text-xs font-semibold text-amber-300 disabled:opacity-40"
          >
            {item.stars_price} ⭐
          </button>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      {notice && <p className="rounded-xl bg-accent-lime/10 px-3 py-2 text-xs text-accent-lime" role="status">{notice}</p>}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {data.collections.filter((c) => c.items.length).map((c) => (
        <section key={c.id} className="flex flex-col gap-2">
          <div>
            <p className="font-display text-base font-bold text-ink-chalk">Коллекция «{c.name}»</p>
            <p className="text-xs text-ink-mist">
              {c.description ? `${c.description} ` : ""}
              {c.set_bonus_rating > 0 && `Комплект из ${c.set_size} вещей на одной карточке: +${c.set_bonus_rating} к рейтингу.`}
            </p>
          </div>
          {c.items.map(row)}
        </section>
      ))}
      {data.singles.length > 0 && (
        <section className="flex flex-col gap-2">
          <p className="font-display text-base font-bold text-ink-chalk">Отдельные вещи</p>
          {data.singles.map(row)}
        </section>
      )}
      <p className="text-micro text-ink-mist-dim">
        На одной карточке вещи дают не больше +{data.caps.rating} к рейтингу, +{data.caps.pp}% к удару или обыгрышу и +{data.caps.chemistry} к химии.
        Точность удара и обыгрыш действуют в турнирах игроков и карьере.
      </p>
    </div>
  );
}
