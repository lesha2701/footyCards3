import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { buyKontraChest, createKontraChestInvoice, equipKontraGear, fetchKontraGear, fetchKontraSquad } from "@/api/kontra";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { KontraGear, KontraGearList } from "@/types";

const SLOT_ICON: Record<string, string> = { boots: "👟", shinguards: "🦵", armband: "🎽", gloves: "🧤" };
const RARITY_TEXT: Record<string, string> = {
  common: "text-slate-300", rare: "text-blue-300", epic: "text-purple-300", legendary: "text-amber-300",
};
const STAT_LABEL: Record<string, string> = { spd: "скорости", def: "защиты", atk: "атаки", max_hp: "HP" };

/** «Тактические комплекты»: pieces from boss/arena drops and chests; worn by
 *  squad cards, two or four of one set add a set bonus. */
export default function KontraGearPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [picking, setPicking] = useState<KontraGear | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: gear } = useQuery({ queryKey: ["kontra-gear"], queryFn: fetchKontraGear });
  const { data: squad } = useQuery({ queryKey: ["kontra-squad"], queryFn: fetchKontraSquad });

  const apply = (g: KontraGearList) => {
    queryClient.setQueryData(["kontra-gear"], g);
    queryClient.invalidateQueries({ queryKey: ["kontra-squad"] });
    updateBalance(g.balance);
    setError(null);
  };
  const chest = useMutation({ mutationFn: buyKontraChest, onSuccess: (g) => { hapticNotify("success"); apply(g); }, onError: (e) => setError(formatGameError(e, "Не получилось")) });
  const stars = useMutation({
    mutationFn: () => payShopWithStars(createKontraChestInvoice),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["kontra-gear"] }),
    onError: (e) => setError(formatGameError(e, "Оплата не прошла")),
  });
  const equip = useMutation({
    mutationFn: ({ gearId, cardId }: { gearId: number; cardId: number | null }) => equipKontraGear(gearId, cardId),
    onSuccess: (g) => { apply(g); setPicking(null); },
    onError: (e) => setError(formatGameError(e, "Не получилось")),
  });

  const names = new Map(squad?.fighters.map((f) => [f.card.card_id, f.card.display_name]) ?? []);

  return (
    <div className="flex flex-col gap-3">
      <button onClick={() => navigate("/play/kontra")} className="flex items-center gap-1 self-start text-xs text-ink-mist">
        <IconChevronLeft size={16} /> Контратака
      </button>
      <h1 className="font-display text-xl font-bold text-ink-chalk">Тактические комплекты</h1>
      <p className="text-caption text-ink-mist">Выпадают за босса и победы на арене. Каждая вещь — небольшой бонус, 2 и 4 вещи одного комплекта дают бонус комплекта.</p>

      {gear && (
        <section className="rounded-2xl bg-gradient-to-br from-amber-400/15 to-bg-surface p-3">
          <p className="text-sm font-bold text-ink-chalk">🎁 Сундук комплекта — случайная вещь</p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {gear.chest_coins > 0 && (
              <button onClick={() => chest.mutate()} disabled={chest.isPending || gear.balance < gear.chest_coins} className="flex items-center justify-center gap-1 rounded-xl bg-floodlight py-2 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40">
                {gear.chest_coins.toLocaleString("ru-RU")} <IconCoin size={13} />
              </button>
            )}
            {gear.chest_stars > 0 && (
              <button onClick={() => stars.mutate()} disabled={stars.isPending} className="rounded-xl bg-amber-400 py-2 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40">
                {gear.chest_stars} ⭐
              </button>
            )}
          </div>
        </section>
      )}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <section className="grid grid-cols-2 gap-2">
        {gear?.sets.map((s) => (
          <div key={s.code} className="rounded-xl bg-bg-surface p-2">
            <p className="text-xs font-bold text-ink-chalk">{s.name}</p>
            <p className="text-micro text-ink-mist">{s.description}</p>
          </div>
        ))}
      </section>

      <div className="flex flex-col gap-1.5">
        {gear?.items.map((g) => (
          <button key={g.id} onClick={() => setPicking(g)} className="flex items-center gap-3 rounded-xl bg-bg-surface px-3 py-2 text-left active:scale-[0.99]">
            <span className="text-2xl">{SLOT_ICON[g.slot]}</span>
            <span className="min-w-0 flex-1">
              <span className={`block text-sm font-bold ${RARITY_TEXT[g.rarity]}`}>{g.slot_label} «{g.set_name}»</span>
              <span className="block text-micro text-ink-mist">{g.rarity_label} · +{g.pct}% {STAT_LABEL[g.stat] ?? g.stat}</span>
            </span>
            <span className="max-w-[40%] truncate text-micro text-ink-mist-dim">{g.card_id ? names.get(g.card_id) ?? "надето" : "не надето"}</span>
          </button>
        ))}
        {gear && !gear.items.length && <p className="py-6 text-center text-sm text-ink-mist">Пока пусто — бей босса или открой сундук</p>}
      </div>

      {picking && squad && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={() => setPicking(null)}>
          <div className="safe-bottom flex w-full flex-col gap-2 rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="font-display text-base font-bold text-ink-chalk">Надеть: {picking.slot_label} «{picking.set_name}»</p>
            {squad.fighters.map((f) => (
              <button key={f.card.card_id} onClick={() => equip.mutate({ gearId: picking.id, cardId: f.card.card_id })}
                className={`rounded-xl px-3 py-2 text-left text-sm active:scale-[0.98] ${picking.card_id === f.card.card_id ? "bg-amber-400/20 text-amber-200" : "bg-white/5 text-ink-chalk"}`}>
                {f.card.display_name} <span className="text-micro text-ink-mist">· {f.role_label}</span>
              </button>
            ))}
            {picking.card_id && (
              <button onClick={() => equip.mutate({ gearId: picking.id, cardId: null })} className="text-xs text-ink-mist underline">Снять</button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
