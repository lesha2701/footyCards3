import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { buyArtifactWithCoins, createArtifactStarsInvoice, fetchArtifacts } from "@/api/monetization";
import ArtifactTile from "@/components/artifacts/ArtifactTile";
import EmptyState from "@/components/common/EmptyState";
import { IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
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
      {catalog.shop.map((a) => (
        <div key={a.id} className="flex items-start gap-3 rounded-2xl bg-bg-surface p-3">
          <ArtifactTile artifact={a} />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="font-display text-sm font-bold text-ink-chalk">{a.name}</p>
            <span className={`self-start rounded-full px-2 py-0.5 text-micro font-semibold ${
              a.target === "club" ? "bg-sky-400/15 text-sky-300" : "bg-purple-400/15 text-purple-300"
            }`}>
              {a.target_label}
            </span>
            {a.effect_label && <p className="text-xs text-accent-lime">{a.effect_label}</p>}
            {a.stadium_name && a.stadium_label && (
              <p className="text-caption text-ink-mist">
                Со стадионом «{a.stadium_name}»: {a.stadium_label}{a.stadium_owned ? " ✓ у тебя есть" : ""}
              </p>
            )}
            {a.description && <p className="text-caption text-ink-mist-dim">{a.description}</p>}
            {a.left !== null && <p className="text-caption text-amber-300">Осталось: {a.left} из {a.max_supply}</p>}
            {a.owned_count > 0 && <p className="text-caption text-ink-mist">У тебя: {a.owned_count}</p>}
            <div className="mt-1 flex gap-1.5">
              {a.coins_price > 0 && (
                <button
                  onClick={() => buyCoins.mutate({ id: a.id, name: a.name })}
                  disabled={busy || a.left === 0 || catalog.balance < a.coins_price}
                  className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-white/10 py-1.5 text-xs font-bold text-ink-chalk disabled:opacity-40"
                >
                  {a.coins_price} <IconCoin size={12} className="text-accent-lime" />
                </button>
              )}
              {a.stars_price > 0 && (
                <button
                  onClick={() => buyStars.mutate({ id: a.id, name: a.name })}
                  disabled={busy || a.left === 0}
                  className="flex-1 rounded-xl bg-amber-400 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
                >
                  {a.stars_price} ⭐
                </button>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
