import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  buyMuseGift, claimMuseDaily, createMuseGiftStarsInvoice, fetchMuses, sellSpareMuse, setActiveMuse,
  type Muse, type MuseAccessory, type MuseAlbum,
} from "@/api/muses";
import EmptyState from "@/components/common/EmptyState";
import { IconCoin } from "@/components/icons";
import MuseArt from "@/components/muses/MuseArt";
import MuseDateButton, { MuseMoodLine } from "@/components/muses/MuseDateButton";
import { formatGameError } from "@/lib/errors";
import { RARITY_LABELS } from "@/lib/rarity";
import { payShopWithStars } from "@/lib/shopStars";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

/** «Музы»: the album of Muses (owned and still to find), the active Muse
 * that inspires «Мой футболист», her daily coins and gifts that raise her
 * bonus. Muses drop from the «Музы» pack. */
export default function MusesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  // /muses?open=<id> (home «Профиль музы») opens her card right away.
  const [params] = useSearchParams();
  const [openId, setOpenId] = useState<number | null>(() => Number(params.get("open")) || null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["muses"], queryFn: fetchMuses });

  const apply = (album: MuseAlbum, message?: string) => {
    queryClient.setQueryData(["muses"], album);
    queryClient.invalidateQueries({ queryKey: ["my-player"] });
    if (album.new_balance != null) updateBalance(album.new_balance);
    setError(null);
    setNotice(message ?? null);
  };
  const fail = (fallback: string) => (err: unknown) => setError(formatGameError(err, fallback));

  const claim = useMutation({
    mutationFn: claimMuseDaily,
    onSuccess: (album) => {
      hapticNotify("success");
      apply(album, `+${album.claimed} монет от музы`);
    },
    onError: fail("Не получилось забрать монеты"),
  });

  if (!data) return null;
  if (!data.enabled) return <EmptyState title="Музы скоро появятся" description="Загляни позже" />;
  const all = data.collections.flatMap((c) => c.muses);
  const open = all.find((m) => m.id === openId) ?? null;
  const active = data.active;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Музы</h1>
        <p className="mt-0.5 text-xs text-ink-mist">
          Муза вдохновляет «Моего футболиста»: бонус даёт одна активная муза. Подарки усиливают её бонус, а раз в день
          её ждёт свидание — случайная мини-игра на отдельной попытке.
        </p>
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {notice && <p className="rounded-xl bg-accent-lime/10 px-3 py-2 text-xs text-accent-lime" role="status">{notice}</p>}

      {active ? (
        <section className="flex gap-3 rounded-2xl bg-gradient-to-br from-pink-500/15 to-bg-surface p-3">
          <button onClick={() => setOpenId(active.id)} className="w-28 shrink-0 active:scale-95">
            <MuseArt muse={active} className="aspect-[3/4] w-full rounded-2xl" iconClass="text-6xl" />
          </button>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="text-micro font-bold uppercase tracking-wide text-pink-300">Активная муза</p>
            <p className="truncate font-display text-lg font-bold text-ink-chalk">{active.name}</p>
            {active.title && <p className="truncate text-caption text-ink-mist">{active.title}</p>}
            <p className="text-sm font-semibold text-accent-lime">{active.effect_label}</p>
            {active.boost_pct > 0 && <p className="text-caption text-pink-300">Подарки: +{active.boost_pct}%</p>}
            <MuseMoodLine album={data} />
            <div className="mt-auto flex flex-col gap-1.5">
              <MuseDateButton album={data} />
              {data.daily.coins > 0 && (
                <button
                  onClick={() => claim.mutate()}
                  disabled={claim.isPending || data.daily.claimed_today}
                  className="flex w-full items-center justify-center gap-1 rounded-full bg-floodlight py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
                >
                  {data.daily.claimed_today ? (
                    <>Сегодня получено: {data.daily.claimed_coins} <IconCoin size={12} /></>
                  ) : (
                    <>Забрать {data.daily.coins} <IconCoin size={12} /></>
                  )}
                </button>
              )}
            </div>
          </div>
        </section>
      ) : (
        <section className="flex flex-col items-center gap-2 rounded-2xl bg-bg-surface p-4 text-center">
          <span className="text-4xl" aria-hidden>💖</span>
          <p className="text-sm text-ink-mist">
            {data.owned_count ? "Выбери активную музу в альбоме ниже." : "Музы выпадают из пака «Музы» — 10% шанс в каждой карточке."}
          </p>
          {!data.owned_count && (
            <button onClick={() => navigate("/packs")} className="rounded-full bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95">
              К пакам
            </button>
          )}
        </section>
      )}

      <p className="px-1 text-caption text-ink-mist">
        В альбоме: <span className="font-bold text-ink-chalk">{data.owned_count}</span> из {data.total_count}
      </p>

      {data.collections.map((collection) => {
        const owned = collection.muses.filter((m) => m.owned).length;
        return (
          <section key={collection.id ?? "loose"} className="flex flex-col gap-2.5 rounded-2xl bg-bg-surface p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-display text-sm font-bold text-ink-chalk">«{collection.name}»</p>
                {collection.description && <p className="mt-0.5 line-clamp-2 text-caption text-ink-mist">{collection.description}</p>}
              </div>
              <span className="shrink-0 rounded-full bg-pink-500/15 px-2 py-0.5 font-mono text-micro font-bold text-pink-300">
                {owned}/{collection.muses.length}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {collection.muses.map((muse) => (
                <button
                  key={muse.id}
                  onClick={() => {
                    haptic("light");
                    setOpenId(muse.id);
                  }}
                  className="relative flex flex-col text-left active:scale-95"
                >
                  <MuseArt muse={muse} locked={!muse.owned} className="aspect-[3/4] w-full rounded-2xl" />
                  <span className={`mt-1 truncate text-caption font-semibold ${muse.owned ? "text-ink-chalk" : "text-ink-mist-dim"}`}>
                    {muse.name}
                  </span>
                  <span className="truncate text-micro text-ink-mist">{muse.owned ? muse.effect_label : RARITY_LABELS[muse.rarity]}</span>
                  {muse.is_active && (
                    <span className="absolute left-1 top-1 rounded-full bg-pink-500 px-1.5 py-0.5 text-micro font-bold text-white">♥</span>
                  )}
                  {muse.copies > 1 && (
                    <span className="absolute right-1 top-1 rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-micro font-bold text-ink-chalk">
                      ×{muse.copies}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </section>
        );
      })}

      <MuseSheet
        muse={open}
        accessories={data.accessories}
        onClose={() => setOpenId(null)}
        onApplied={(album, message) => apply(album, message)}
        onError={(message) => setError(message)}
      />
    </div>
  );
}

function MuseSheet({
  muse,
  accessories,
  onClose,
  onApplied,
  onError,
}: {
  muse: Muse | null;
  accessories: MuseAccessory[];
  onClose: () => void;
  onApplied: (album: MuseAlbum, message?: string) => void;
  onError: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const activate = useMutation({
    mutationFn: (id: number | null) => setActiveMuse(id),
    onSuccess: (album, id) => {
      hapticNotify("success");
      onApplied(album, id ? "Муза теперь вдохновляет «Моего футболиста»" : undefined);
    },
    onError: (err) => onError(formatGameError(err, "Не получилось")),
  });
  const sell = useMutation({
    mutationFn: (id: number) => sellSpareMuse(id, 1),
    onSuccess: (album) => onApplied(album, `Лишняя копия продана: +${album.sold_coins} монет`),
    onError: (err) => onError(formatGameError(err, "Не получилось продать")),
  });
  const giftCoins = useMutation({
    mutationFn: ({ museId, gift }: { museId: number; gift: MuseAccessory }) => buyMuseGift(museId, gift.id, crypto.randomUUID()),
    onSuccess: (album, { gift }) => {
      hapticNotify("success");
      onApplied(album, `«${gift.name}» подарен — бонус музы вырос`);
    },
    onError: (err) => onError(formatGameError(err, "Не получилось купить подарок")),
  });
  const giftStars = useMutation({
    mutationFn: ({ museId, gift }: { museId: number; gift: MuseAccessory }) =>
      payShopWithStars(() => createMuseGiftStarsInvoice(museId, gift.id)),
    onSuccess: async (status, { gift }) => {
      if (status !== "paid") return;
      hapticNotify("success");
      const album = await queryClient.fetchQuery({ queryKey: ["muses"], queryFn: fetchMuses });
      onApplied(album, `«${gift.name}» подарен — бонус музы вырос`);
    },
    onError: (err) => onError(formatGameError(err, "Оплата не прошла")),
  });
  const busy = activate.isPending || sell.isPending || giftCoins.isPending || giftStars.isPending;

  return (
    <AnimatePresence>
      {muse && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="safe-bottom flex max-h-[88vh] w-full max-w-md flex-col gap-3 overflow-y-auto rounded-t-3xl border border-white/10 bg-bg-surface p-4"
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex gap-3">
              <MuseArt muse={muse} locked={!muse.owned} className="aspect-[3/4] w-32 shrink-0 rounded-2xl" iconClass="text-6xl" />
              <div className="flex min-w-0 flex-col gap-1">
                <p className="font-display text-lg font-bold text-ink-chalk">{muse.name}</p>
                <p className="text-caption text-ink-mist">
                  {muse.title ? `${muse.title} · ` : ""}{RARITY_LABELS[muse.rarity]}
                </p>
                <p className="text-sm font-semibold text-accent-lime">{muse.effect_label}</p>
                {muse.owned && muse.boost_pct > 0 && (
                  <p className="text-caption text-pink-300">Без подарков: {muse.base_effect_label} · подарки +{muse.boost_pct}%</p>
                )}
                {muse.description && <p className="text-xs text-ink-mist">{muse.description}</p>}
                {!muse.owned && <p className="text-xs text-ink-mist-dim">Ещё не в альбоме — ищи в паке «Музы».</p>}
              </div>
            </div>

            {muse.owned && (
              <div className="flex gap-2">
                <button
                  onClick={() => activate.mutate(muse.is_active ? null : muse.id)}
                  disabled={busy}
                  className={`flex-1 rounded-full py-2.5 text-xs font-bold active:scale-95 disabled:opacity-40 ${muse.is_active ? "bg-white/10 text-ink-mist" : "bg-pink-500 text-white"}`}
                >
                  {muse.is_active ? "Активна · снять" : "Сделать активной"}
                </button>
                {muse.copies > 1 && (
                  <button
                    onClick={() => sell.mutate(muse.id)}
                    disabled={busy}
                    className="flex items-center gap-1 rounded-full bg-white/5 px-3 py-2.5 text-xs font-semibold text-ink-chalk active:scale-95 disabled:opacity-40"
                  >
                    Продать лишнюю +{muse.spare_coins} <IconCoin size={11} />
                  </button>
                )}
              </div>
            )}

            {muse.owned && accessories.length > 0 && (
              <div className="flex flex-col gap-2">
                <p className="text-xs font-bold text-ink-chalk">Подарки</p>
                <div className="grid grid-cols-2 gap-2">
                  {accessories.map((gift) => {
                    const has = muse.accessory_ids.includes(gift.id);
                    return (
                      <div key={gift.id} className={`flex flex-col gap-1 rounded-2xl p-2 ${has ? "bg-pink-500/10" : "bg-white/5"}`}>
                        <div className="flex items-center gap-2">
                          <span className="text-2xl leading-none" aria-hidden>{gift.icon}</span>
                          <div className="min-w-0">
                            <p className="truncate text-caption font-semibold text-ink-chalk">{gift.name}</p>
                            <p className="text-micro text-pink-300">+{gift.boost_pct}% к бонусу</p>
                          </div>
                        </div>
                        {has ? (
                          <p className="text-center text-micro font-bold text-accent-lime">✓ подарено</p>
                        ) : (
                          <div className="flex gap-1">
                            {gift.coins_price > 0 && (
                              <button
                                onClick={() => giftCoins.mutate({ museId: muse.id, gift })}
                                disabled={busy || balance < gift.coins_price}
                                className="flex flex-1 items-center justify-center gap-0.5 rounded-full bg-floodlight py-1 text-micro font-bold text-bg-base active:scale-95 disabled:opacity-40"
                              >
                                {gift.coins_price.toLocaleString("ru-RU")} <IconCoin size={10} />
                              </button>
                            )}
                            {gift.stars_price > 0 && (
                              <button
                                onClick={() => giftStars.mutate({ museId: muse.id, gift })}
                                disabled={busy}
                                className="flex-1 rounded-full bg-amber-400 py-1 text-micro font-bold text-bg-base active:scale-95 disabled:opacity-40"
                              >
                                {gift.stars_price} ⭐
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            <button onClick={onClose} className="rounded-full bg-white/5 py-2.5 text-xs font-semibold text-ink-mist active:scale-95">
              Закрыть
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
