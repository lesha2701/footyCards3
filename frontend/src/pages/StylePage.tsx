import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { buyCosmeticWithCoins, createCosmeticStarsInvoice, equipCosmetic, fetchCosmetics } from "@/api/monetization";
import { IconCoin, IconStar } from "@/components/icons";
import CosmeticPreview from "@/components/shop/CosmeticPreview";
import { KIND_LABELS, backgroundClass } from "@/lib/cosmetics";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { CosmeticCatalog, CosmeticKind } from "@/types";

const KINDS: CosmeticKind[] = ["profile_frame", "profile_background", "card_skin"];

/** «Стиль»: profile frames, profile backgrounds and card skins — visual
 * only, bought for coins or ⭐ or earned in the calendar, club pass, season
 * pass and starter offer. */
export default function StylePage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [kind, setKind] = useState<CosmeticKind>("profile_frame");
  const [error, setError] = useState<string | null>(null);
  const { data: catalog } = useQuery({ queryKey: ["cosmetics"], queryFn: fetchCosmetics });

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

  const items = catalog?.items.filter((i) => i.kind === kind) ?? [];
  const busy = buyCoins.isPending || buyStars.isPending || equip.isPending;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconStar size={20} className="text-amber-300" /> Стиль
      </h1>
      <p className="-mt-2 text-xs text-ink-mist">Только внешний вид — на рейтинг и матчи не влияет.</p>

      {catalog && (
        <section className={`flex items-center gap-4 rounded-3xl p-4 ${backgroundClass(catalog.equipped.background) ?? "bg-bg-surface"}`}>
          <CosmeticPreview item={{ kind: "profile_frame", style_key: catalog.equipped.frame ?? "" }} avatarUrl={user?.avatar_url ?? undefined} />
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-base font-bold text-ink-chalk">{user?.first_name}</p>
            <p className="text-caption text-ink-mist">Так тебя видят другие</p>
          </div>
          <CosmeticPreview item={{ kind: "card_skin", style_key: catalog.equipped.card_skin ?? "" }} />
        </section>
      )}

      <div className="flex gap-1.5 rounded-2xl bg-bg-surface p-1">
        {KINDS.map((k) => (
          <button
            key={k}
            onClick={() => setKind(k)}
            className={`flex-1 rounded-xl py-2 text-xs font-semibold ${kind === k ? "bg-accent-lime text-bg-base" : "text-ink-mist"}`}
          >
            {KIND_LABELS[k]}
          </button>
        ))}
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="grid grid-cols-2 gap-2">
        {items.map((item) => (
          <div key={item.id} className={`flex flex-col items-center gap-2 rounded-2xl bg-bg-surface p-3 text-center ${item.equipped ? "ring-2 ring-accent-lime" : ""}`}>
            <CosmeticPreview item={item} avatarUrl={user?.avatar_url ?? undefined} />
            <p className="font-display text-sm font-bold leading-tight text-ink-chalk">{item.name}</p>
            {item.description && <p className="text-micro leading-tight text-ink-mist-dim">{item.description}</p>}
            {item.status > 0 && <p className="text-micro font-semibold text-amber-300">+{item.status} статуса</p>}
            {item.owned ? (
              <button
                onClick={() => equip.mutate({ k: item.kind, id: item.equipped ? null : item.id })}
                disabled={busy}
                className={`w-full rounded-xl py-1.5 text-xs font-bold disabled:opacity-40 ${
                  item.equipped ? "bg-white/10 text-ink-mist" : "bg-accent-lime text-bg-base"
                }`}
              >
                {item.equipped ? "Снять" : "Надеть"}
              </button>
            ) : (
              <div className="flex w-full flex-col gap-1">
                {item.coins_price > 0 && (
                  <button
                    onClick={() => buyCoins.mutate(item.id)}
                    disabled={busy || (catalog?.balance ?? 0) < item.coins_price}
                    className="flex items-center justify-center gap-1 rounded-xl bg-white/10 py-1.5 text-xs font-bold text-ink-chalk disabled:opacity-40"
                  >
                    {item.coins_price} <IconCoin size={12} className="text-accent-lime" />
                  </button>
                )}
                {item.stars_price > 0 && (
                  <button
                    onClick={() => buyStars.mutate(item.id)}
                    disabled={busy}
                    className="rounded-xl bg-amber-400 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
                  >
                    {item.stars_price} ⭐
                  </button>
                )}
                {item.coins_price === 0 && item.stars_price === 0 && (
                  <span className="text-micro text-ink-mist-dim">Только в наградах</span>
                )}
              </div>
            )}
          </div>
        ))}
        {catalog && items.length === 0 && (
          <p className="col-span-2 py-6 text-center text-sm text-ink-mist">Здесь пока пусто</p>
        )}
      </div>
    </div>
  );
}
