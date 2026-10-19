import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { equipItem, fetchCardEquipment, unequipItem, type CardEquipmentSlot } from "@/api/equipment";
import EquipmentTile from "@/components/equipment/EquipmentTile";
import { formatGameError } from "@/lib/errors";
import { haptic } from "@/lib/telegram";

/** «Экипировка» tab of the card sheet: the card's slots (things + one
 * artifact), what they add, and picking a thing from the inventory. */
export default function CardEquipmentPanel({ cardId }: { cardId: number }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["card-equipment", cardId], queryFn: () => fetchCardEquipment(cardId) });

  const refresh = () => {
    // card-stars: the sheet header reads the rating from it.
    for (const key of [["card-equipment"], ["card-stars"], ["equipment-inventory"], ["equipment-shop"], ["collection"], ["album-detail"], ["lineup-templates"]]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };
  const equip = useMutation({
    mutationFn: (copyId: number) => equipItem(copyId, cardId),
    onSuccess: (state) => {
      haptic("light");
      queryClient.setQueryData(["card-equipment", cardId], state);
      setOpen(null);
      setError(null);
      refresh();
    },
    onError: (err) => setError(formatGameError(err, "Не удалось надеть")),
  });
  const unequip = useMutation({
    mutationFn: (copyId: number) => unequipItem(copyId),
    onSuccess: () => {
      haptic("light");
      setError(null);
      refresh();
    },
    onError: (err) => setError(formatGameError(err, "Не удалось снять")),
  });

  if (!data) return null;
  if (!data.enabled) {
    return <p className="mt-3 rounded-xl bg-black/20 px-3 py-2 text-xs text-ink-mist">Экипировка пока недоступна</p>;
  }
  const busy = equip.isPending || unequip.isPending;
  const bonusParts = [
    data.rating_bonus ? `+${data.rating_bonus} к рейтингу` : null,
    data.chemistry ? `+${data.chemistry} к химии` : null,
    data.boosts.shot_pp ? `+${data.boosts.shot_pp}% к удару` : null,
    data.boosts.dribble_pp ? `+${data.boosts.dribble_pp}% к обыгрышу` : null,
  ].filter(Boolean);

  return (
    <div className="mt-3 flex flex-col gap-2">
      <p className="rounded-xl bg-black/20 px-3 py-2 text-xs text-ink-mist">
        {bonusParts.length ? <>Даёт: <b className="text-accent-lime">{bonusParts.join(" · ")}</b></> : "Пока ничего не надето"}
      </p>
      {error && <p className="rounded-lg bg-red-500/10 px-2 py-1 text-xs text-red-400">{error}</p>}
      <div className="grid grid-cols-3 gap-2">
        {data.slots.map((slot) => (
          <SlotButton key={slot.code} slot={slot} active={open === slot.code} onClick={() => setOpen(open === slot.code ? null : slot.code)} />
        ))}
      </div>
      {open && (() => {
        const slot = data.slots.find((s) => s.code === open)!;
        return (
          <section className="rounded-2xl bg-black/20 p-3">
            <p className="text-xs font-semibold text-ink-chalk">{slot.label}</p>
            {!slot.available && <p className="mt-1 text-xs text-ink-mist">Этот слот только для вратаря</p>}
            {slot.worn && (
              <div className="mt-2 flex items-center gap-2">
                <EquipmentTile item={slot.worn.item} size="sm" dimmed={!slot.worn.applies} />
                <span className="min-w-0 flex-1 text-xs">
                  <b className="block truncate text-ink-chalk">{slot.worn.item.name}</b>
                  <span className={slot.worn.applies ? "text-accent-lime" : "text-ink-mist-dim"}>
                    {slot.worn.applies ? slot.worn.item.effect_label : "Не действует на этого игрока"}
                  </span>
                </span>
                <button
                  onClick={() => unequip.mutate(slot.worn!.copy_id)}
                  disabled={busy}
                  className="min-h-[36px] rounded-xl bg-white/5 px-3 text-xs font-semibold text-ink-mist disabled:opacity-40"
                >
                  Снять
                </button>
              </div>
            )}
            {slot.available && slot.options.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1.5">
                {slot.options.map((o) => (
                  <li key={o.copy_id} className="flex items-center gap-2">
                    <EquipmentTile item={o.item} size="sm" dimmed={!o.applies} />
                    <span className="min-w-0 flex-1 text-xs">
                      <b className="block truncate text-ink-chalk">{o.item.name}</b>
                      <span className={o.applies ? "text-ink-mist" : "text-ink-mist-dim"}>
                        {o.applies ? o.item.effect_label : `Не подойдёт: ${o.item.cond_club ?? o.item.cond_country ?? "условие"}`}
                      </span>
                    </span>
                    <button
                      onClick={() => equip.mutate(o.copy_id)}
                      disabled={busy}
                      className="min-h-[36px] rounded-xl bg-accent-lime/15 px-3 text-xs font-semibold text-accent-lime disabled:opacity-40"
                    >
                      Надеть
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {slot.available && slot.options.length === 0 && (
              <p className="mt-2 text-xs text-ink-mist">
                В инвентаре нет свободных вещей для этого слота.{" "}
                <button onClick={() => navigate("/equipment?tab=shop")} className="font-semibold text-accent-lime">
                  В магазин
                </button>
              </p>
            )}
          </section>
        );
      })()}
      <button onClick={() => navigate("/equipment")} className="min-h-[40px] rounded-xl bg-white/5 text-xs font-semibold text-ink-mist">
        Инвентарь и магазин экипировки
      </button>
    </div>
  );
}

function SlotButton({ slot, active, onClick }: { slot: CardEquipmentSlot; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`flex min-h-[88px] flex-col items-center justify-center gap-1 rounded-2xl p-2 ${
        active ? "bg-bg-raised ring-2 ring-accent-lime/60" : "bg-black/20"
      } ${slot.available ? "" : "opacity-40"} ${slot.code === "artifact" ? "border border-amber-300/30" : ""}`}
    >
      {slot.worn ? (
        <EquipmentTile item={slot.worn.item} size="sm" dimmed={!slot.worn.applies} />
      ) : (
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-dashed border-white/15 text-lg text-ink-mist-dim">+</span>
      )}
      <span className="text-micro text-ink-mist">{slot.label}</span>
    </button>
  );
}
