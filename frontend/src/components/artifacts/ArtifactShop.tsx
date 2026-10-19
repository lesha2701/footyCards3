import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { buyArtifactWithCoins, createArtifactStarsInvoice, fetchArtifacts } from "@/api/monetization";
import EmptyState from "@/components/common/EmptyState";
import InfoTile from "@/components/shop/InfoTile";
import { IconCoin } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { RARITY_GRADIENTS } from "@/lib/rarity";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useOpenTile } from "@/lib/useOpenTile";
import { useSeenItems } from "@/lib/useSeenItems";
import { useAuthStore } from "@/store/authStore";
import type { ArtifactCatalog } from "@/types";

/** «Артефакты» in the shop: what each one does and for whom, before buying. */
export default function ArtifactShop() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: catalog } = useQuery({ queryKey: ["artifacts"], queryFn: fetchArtifacts });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const tiles = useOpenTile<number>();
  const seen = useSeenItems("artifacts", catalog?.shop.map((a) => a.id));

  const done = (data: ArtifactCatalog, name: string) => {
    queryClient.setQueryData(["artifacts"], data);
    updateBalance(data.balance);
    hapticNotify("success");
    setError(null);
    setNotice(`«${name}» теперь у тебя — смотри на полке`);
  };
  const buyCoins = useMutation({
    mutationFn: ({ id }: { id: number; name: string }) => buyArtifactWithCoins(id),
    onSuccess: (data, vars) => done(data, vars.name),
    onError: (err) => setError(formatGameError(err, "Не получилось купить")),
  });
  const buyStars = useMutation({
    mutationFn: ({ id }: { id: number; name: string }) => payShopWithStars(() => createArtifactStarsInvoice(id)),
    onSuccess: (status, vars) => {
      queryClient.invalidateQueries({ queryKey: ["artifacts"] });
      if (status === "paid") {
        hapticNotify("success");
        setNotice(`«${vars.name}» теперь у тебя — смотри на полке`);
      }
    },
    onError: (err) => setError(formatGameError(err, "Оплата не прошла")),
  });

  if (!catalog) return null;
  if (!catalog.enabled || !catalog.shop.length) {
    return <EmptyState title="Артефактов пока нет" description="Загляни позже" />;
  }
  const busy = buyCoins.isPending || buyStars.isPending;
  // What pays off for this player first (their stadium / coach / player
  // makes it stronger), sold-out and already-owned ones last.
  const rank = (a: (typeof catalog.shop)[number]) =>
    (a.left === 0 ? 4 : 0) + (a.owned_count > 0 ? 2 : 0) + (a.link_owned ? 0 : 1);
  const shop = [...catalog.shop].sort((x, y) => rank(x) - rank(y));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between rounded-2xl bg-bg-surface p-3">
        <p className="text-xs text-ink-mist">
          Работают {catalog.slots} активных артефакта, остальные стоят на полке. Копии одного артефакта не суммируются.
        </p>
        <button onClick={() => navigate("/artifacts")} className="shrink-0 text-xs font-semibold text-accent-lime">
          Моя полка →
        </button>
      </div>
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {notice && <p className="rounded-xl bg-accent-lime/10 px-3 py-2 text-xs text-accent-lime">{notice}</p>}
      <div className="grid grid-cols-2 gap-2.5">
        {shop.map((a) => (
          <InfoTile
            key={a.id}
            open={tiles.openKey === a.id}
            onToggle={() => {
              seen.markSeen(a.id);
              tiles.toggle(a.id);
            }}
            isNew={seen.isNew(a.id)}
            accent={a.stars_price > 0 && !a.coins_price ? "stars" : undefined}
            dimmed={a.left === 0}
            name={a.name}
            price={
              a.coins_price > 0 ? (
                <span className={`flex items-center gap-1 ${catalog.balance < a.coins_price ? "text-ink-mist" : "text-accent-lime"}`}>
                  <IconCoin size={11} /> {a.coins_price.toLocaleString("ru-RU")}
                </span>
              ) : (
                <span className="text-amber-300">{a.stars_price} ⭐</span>
              )
            }
            badge={
              a.owned_count > 0 ? (
                <span className="rounded-full bg-accent-lime px-1.5 py-0.5 text-micro font-bold text-bg-base">✓ есть</span>
              ) : a.link_owned && a.link_label ? (
                <span className="rounded-full bg-accent-lime px-1.5 py-0.5 text-micro font-bold text-bg-base">Твой бонус</span>
              ) : a.left !== null ? (
                <span className="rounded-full bg-black/75 px-1.5 py-0.5 font-mono text-micro text-amber-300">ост. {a.left}</span>
              ) : undefined
            }
            shape="square"
            visual={
              <span className={`block h-full w-full bg-gradient-to-b p-[3px] ${RARITY_GRADIENTS[a.rarity]}`}>
                <span className="flex h-full w-full items-center justify-center overflow-hidden rounded-[13px] bg-bg-base">
                  {a.image_path ? (
                    <img src={staticUrl(a.image_path)} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
                  ) : (
                    <span className="text-5xl">{a.icon}</span>
                  )}
                </span>
              </span>
            }
            details={
              <>
                <span className="flex flex-wrap items-center gap-x-2 font-mono text-xs font-bold">
                  {a.coins_price > 0 && (
                    <span className="flex items-center gap-1 text-accent-lime">
                      <IconCoin size={12} /> {a.coins_price.toLocaleString("ru-RU")}
                    </span>
                  )}
                  {a.coins_price > 0 && a.stars_price > 0 && <span className="font-sans font-normal text-ink-mist-dim">или</span>}
                  {a.stars_price > 0 && <span className="text-amber-300">{a.stars_price} ⭐</span>}
                </span>
                <span
                  className={`self-start rounded-full px-2 py-0.5 text-micro font-semibold ${
                    a.target === "club" ? "bg-sky-400/15 text-sky-300" : "bg-purple-400/15 text-purple-300"
                  }`}
                >
                  {a.target_label}
                </span>
                {a.effect_label && <span className="text-xs text-accent-lime">{a.effect_label}</span>}
                {a.link_name && a.link_label && (
                  <span className="text-caption text-ink-mist">
                    Если есть {a.link_kind} «{a.link_name}»: {a.link_label}
                    {a.link_owned ? " ✓ у тебя есть" : ""}
                  </span>
                )}
                {a.card_label && <span className="text-xs text-accent-lime">{a.card_label}</span>}
                {a.status > 0 && <span className="text-caption font-semibold text-amber-300">+{a.status} статуса Моему игроку</span>}
                {a.description && <span className="text-caption text-ink-mist-dim">{a.description}</span>}
                {a.left !== null && <span className="text-caption text-amber-300">Осталось: {a.left} из {a.max_supply}</span>}
                {a.owned_count > 0 && <span className="text-caption text-ink-mist">У тебя: {a.owned_count}</span>}
              </>
            }
            action={
              <div className="flex gap-1.5">
                {a.coins_price > 0 && (
                  <button
                    onClick={() => buyCoins.mutate({ id: a.id, name: a.name })}
                    disabled={busy || a.left === 0 || catalog.balance < a.coins_price}
                    className="flex flex-1 items-center justify-center gap-1 rounded-full bg-floodlight py-1.5 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
                  >
                    {a.coins_price.toLocaleString("ru-RU")} <IconCoin size={12} />
                  </button>
                )}
                {a.stars_price > 0 && (
                  <button
                    onClick={() => buyStars.mutate({ id: a.id, name: a.name })}
                    disabled={busy || a.left === 0}
                    className="flex-1 rounded-full bg-amber-400 py-1.5 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
                  >
                    {a.stars_price} ⭐
                  </button>
                )}
              </div>
            }
          />
        ))}
      </div>
    </div>
  );
}
