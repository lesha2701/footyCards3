import { useQuery } from "@tanstack/react-query";

import { fetchGiftShelf } from "@/api/gifts";
import { IconGift } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { SPECIAL_LABELS, type SpecialSerial } from "@/lib/giftSerial";

/** «Полка подарков» on a profile: pinned copies, then the rarest serials. */
export default function GiftShelf({ userId }: { userId: number }) {
  const { data } = useQuery({ queryKey: ["gift-shelf", userId], queryFn: () => fetchGiftShelf(userId) });
  if (!data || data.copies === 0) return null;
  return (
    <section className="rounded-2xl border border-rarity-epic/20 bg-gradient-to-b from-rarity-epic/10 to-transparent p-3" data-testid="gift-shelf">
      <div className="mb-2 flex items-baseline justify-between">
        <p className="text-micro font-bold uppercase tracking-[0.2em] text-rarity-epic">🎁 Полка подарков</p>
        <p className="text-micro text-ink-mist">
          Разных: {data.sets} · {data.copies} шт.{data.special > 0 && <span className="text-amber-200"> · ✨{data.special}</span>}
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {data.items.map((item) => (
          <div key={item.id} className="flex flex-col items-center gap-1 rounded-xl bg-black/20 p-2">
            <span
              className={`relative flex h-14 w-14 items-center justify-center overflow-hidden rounded-xl bg-rarity-epic/10 ${
                item.special ? "ring-2 ring-amber-300/60" : ""
              }`}
            >
              {item.gift_set.image_path ? (
                <img decoding="async" loading="lazy" src={staticUrl(item.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
              ) : (
                <IconGift size={22} className="text-rarity-epic" />
              )}
              {item.is_pinned && (
                <span className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-accent-lime text-micro font-bold text-bg-base">★</span>
              )}
            </span>
            <span className="w-full truncate text-center text-micro font-semibold text-ink-chalk">{item.gift_set.name}</span>
            {item.serial_number != null && (
              <span className={`font-mono text-micro ${item.special ? "text-amber-200" : "text-ink-mist-dim"}`}>
                №{item.serial_number}
              </span>
            )}
            {item.special && (
              <span className="text-[9px] font-bold uppercase text-amber-200/80">{SPECIAL_LABELS[item.special as SpecialSerial] ?? ""}</span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
