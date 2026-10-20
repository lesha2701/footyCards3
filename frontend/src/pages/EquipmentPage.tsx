import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchEquipmentInventory, unequipItem } from "@/api/equipment";
import EmptyState from "@/components/common/EmptyState";
import EquipmentTile from "@/components/equipment/EquipmentTile";
import EquipmentShop from "@/components/shop/EquipmentShop";
import { formatGameError } from "@/lib/errors";
import { haptic } from "@/lib/telegram";

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
      {tab === "inventory" ? <Inventory onShop={() => setTab("shop")} /> : <EquipmentShop showInventoryLink={false} />}
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
      {data.items.map(({ copy_id, item, card_name, serial_number }) => (
        <div key={copy_id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
          <EquipmentTile item={item} size="sm" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink-chalk">{item.name}</p>
            <p className="text-xs text-accent-lime">{item.effect_label}</p>
            <p className="truncate text-micro text-ink-mist">
              {item.slot_label}
              {serial_number && item.max_supply ? ` · №${serial_number} из ${item.max_supply}` : ""}
              {" · "}{card_name ? `надета: ${card_name}` : "свободна"}
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
