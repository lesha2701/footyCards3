import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { buyLifestyleWithCoins, claimLifestyleIncome, fetchLifestyle, type LifestyleCategory, type LifestyleItem } from "@/api/lifestyle";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCoin } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const CATEGORY_ICONS: Record<LifestyleCategory, string> = { car: "🚗", estate: "🏠", stocks: "📈", other: "✨" };

export function LifestyleIcon({ item, className = "h-14 w-14 text-4xl" }: { item: LifestyleItem; className?: string }) {
  return item.image_path ? (
    <img decoding="async" loading="lazy" src={staticUrl(item.image_path) ?? undefined} alt={item.name} className={`${className} rounded-xl object-cover`} />
  ) : (
    <span className={`${className} flex items-center justify-center rounded-xl bg-bg-surface leading-none`}>{item.emoji}</span>
  );
}

/** «Имущество»: the player's status collection (garage, real estate,
 * investments, other) and the shop. Items are bought for coins or Stars,
 * one of each; limited editions are numbered. Items may help the player:
 * faster freshness recovery, an XP bonus or a weekly income collected here. */
export default function LifestyleTab() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data, isLoading } = useQuery({ queryKey: ["lifestyle"], queryFn: fetchLifestyle });
  const [category, setCategory] = useState<LifestyleCategory | "owned">("owned");
  const [error, setError] = useState<string | null>(null);
  const [starsBusy, setStarsBusy] = useState<number | null>(null);

  const buyCoins = useMutation({
    mutationFn: buyLifestyleWithCoins,
    onSuccess: (next) => {
      hapticNotify("success");
      setError(null);
      queryClient.setQueryData(["lifestyle"], next);
      updateBalance(next.balance);
    },
    onError: (err) => setError(formatGameError(err, "Не получилось купить")),
  });
  const claim = useMutation({
    mutationFn: claimLifestyleIncome,
    onSuccess: (next) => {
      hapticNotify("success");
      setError(null);
      queryClient.setQueryData(["lifestyle"], next);
      updateBalance(next.balance);
      void queryClient.invalidateQueries({ queryKey: ["my-player"], exact: true });
    },
    onError: (err) => setError(formatGameError(err, "Не получилось забрать доход")),
  });
  const buyStars = async (item: LifestyleItem) => {
    setError(null);
    setStarsBusy(item.id);
    try {
      if ((await payMyPlayerWithStars({ purchase: "item", itemId: item.id })) === "paid") {
        hapticNotify("success");
        await queryClient.invalidateQueries({ queryKey: ["lifestyle"] });
      }
    } catch (err) {
      setError(formatGameError(err, "Не получилось оплатить"));
    } finally {
      setStarsBusy(null);
    }
  };

  if (isLoading || !data) return <ListSkeleton />;
  const owned = data.items.filter((i) => i.owned);
  const shown = category === "owned" ? owned : data.items.filter((i) => i.category === category);

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl bg-gradient-to-br from-amber-400/20 to-bg-surface p-4">
        <p className="text-xs text-ink-mist">Статус</p>
        <p className="font-display text-3xl font-black text-ink-chalk">
          {data.prestige} <span className="text-base font-bold text-amber-300">престижа</span>
        </p>
        <p className="mt-1 text-caption text-ink-mist">
          {owned.length ? `${owned.length} в имуществе · видно в твоём профиле` : "Собери гараж, недвижимость и инвестиции — каждый предмет добавляет престиж"}
        </p>
        {owned.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1 text-xl">{owned.slice(0, 12).map((i) => <span key={i.id}>{i.emoji}</span>)}</div>
        )}
        {data.effects.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {data.effects.map((e) => (
              <span key={e.effect} className="rounded-full bg-accent-lime/15 px-2 py-0.5 text-micro font-semibold text-accent-lime">{e.label}</span>
            ))}
          </div>
        )}
      </section>

      {data.income_ready > 0 && (
        <button
          disabled={claim.isPending}
          onClick={() => claim.mutate()}
          className="flex items-center justify-between rounded-2xl bg-gradient-to-r from-accent-lime/25 to-bg-surface p-4 text-left active:scale-[0.99] disabled:opacity-50"
        >
          <span>
            <span className="block font-display text-base font-bold text-ink-chalk">Доход от имущества</span>
            <span className="block text-caption text-ink-mist">Накопилось за прошедшие недели</span>
          </span>
          <span className="flex items-center gap-1 rounded-xl bg-floodlight px-3 py-2 text-sm font-bold text-bg-base">
            <IconCoin size={14} /> +{data.income_ready}
          </span>
        </button>
      )}

      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {[{ code: "owned" as const, label: "Моё" }, ...data.categories].map((c) => (
          <button
            key={c.code}
            onClick={() => setCategory(c.code)}
            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${category === c.code ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
          >
            {c.code !== "owned" && `${CATEGORY_ICONS[c.code]} `}{c.label}
          </button>
        ))}
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      {shown.length === 0 ? (
        <p className="rounded-2xl bg-bg-surface p-6 text-center text-sm text-ink-mist">
          {category === "owned" ? "Пока пусто — загляни в категории выше" : "Здесь пока ничего нет"}
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {shown.map((item) => (
            <div key={item.id} className={`flex items-center gap-3 rounded-2xl bg-bg-raised p-3 ${item.owned ? "ring-1 ring-amber-300/50" : ""}`}>
              <LifestyleIcon item={item} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-bold text-ink-chalk">{item.name}</span>
                <span className="block truncate text-caption text-ink-mist">{item.description}</span>
                {item.effect_label && (
                  <span className="mt-0.5 block text-caption font-semibold text-accent-lime">{item.effect_label}</span>
                )}
                <span className="mt-0.5 block text-caption text-amber-300">
                  +{item.prestige} престижа
                  {item.max_supply != null &&
                    (item.owned && item.serial_number
                      ? ` · №${item.serial_number} из ${item.max_supply}`
                      : ` · осталось ${Math.max(0, item.max_supply - item.sold_count)} из ${item.max_supply}`)}
                </span>
              </span>
              <span className="flex shrink-0 flex-col gap-1">
                {item.owned ? (
                  <span className="rounded-lg bg-amber-300/15 px-3 py-1.5 text-xs font-bold text-amber-300">Твоё</span>
                ) : item.sold_out ? (
                  <span className="rounded-lg bg-bg-surface px-3 py-1.5 text-xs text-ink-mist">Распродано</span>
                ) : (
                  <>
                    {item.coins_price > 0 && (
                      <button
                        disabled={buyCoins.isPending || data.balance < item.coins_price}
                        onClick={() => buyCoins.mutate(item.id)}
                        className="flex items-center justify-center gap-1 rounded-lg bg-floodlight px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
                      >
                        <IconCoin size={12} /> {item.coins_price}
                      </button>
                    )}
                    {item.stars_price > 0 && (
                      <button
                        disabled={starsBusy !== null}
                        onClick={() => buyStars(item)}
                        className="rounded-lg bg-amber-400 px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
                      >
                        ⭐ {item.stars_price}
                      </button>
                    )}
                  </>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
