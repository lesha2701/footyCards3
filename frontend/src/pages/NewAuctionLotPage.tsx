import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import ConfirmDialog from "@/components/common/ConfirmDialog";
import NumberInput from "@/components/common/NumberInput";
import CardSkillBadge from "@/components/cards/CardSkillBadge";
import PlayerCard from "@/components/cards/PlayerCard";
import { AgentIcon } from "@/components/market/AgentBadge";
import { createAuctionLot, fetchAuctionInfo, fetchAuctionPriceFloor } from "@/api/auction";
import { fetchCollection } from "@/api/collection";
import { ApiRequestError } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import type { UserCard } from "@/types";

/** Same availability rule as the backend (create_lot): not admin-locked, not
 * in a trade or another lot, not in a lineup/Tactico squad, and no plain
 * diamonds — «Академия» cards are the one diamond kind that can be sold. */
function isListable(c: UserCard): boolean {
  return (
    !c.is_locked_by_admin && !c.is_locked_in_trade && !c.is_in_lineup && !c.is_in_tactico_squad &&
    (c.player.rarity !== "diamond" || !!c.player.path_talent_code)
  );
}

export default function NewAuctionLotPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [card, setCard] = useState<UserCard | null>(null);
  const [startPrice, setStartPrice] = useState(0);
  const [mode, setMode] = useState<"fixed" | "auction">("fixed");
  const fixed = mode === "fixed";
  const [withBuyNow, setWithBuyNow] = useState(false);
  const [buyNow, setBuyNow] = useState(0);
  const [hours, setHours] = useState<number | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [lastCopy, setLastCopy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: info } = useQuery({ queryKey: ["auction", "info"], queryFn: fetchAuctionInfo });
  const { data: collection } = useQuery({
    queryKey: ["collection-for-auction", search],
    queryFn: () => fetchCollection({ page_size: 100, search: search || undefined, sort_by: "rating", sort_dir: "desc" }),
  });
  const { data: floor } = useQuery({
    queryKey: ["auction", "floor", card?.id],
    queryFn: () => fetchAuctionPriceFloor(card!.id),
    enabled: !!card,
  });

  const duration = hours ?? info?.durations_hours?.[1] ?? info?.durations_hours?.[0] ?? null;
  const minPrice = floor?.min_price ?? 1;

  useEffect(() => {
    if (floor) {
      setStartPrice(floor.min_price);
      setBuyNow(floor.min_price * 2);
    }
  }, [floor]);

  const createMutation = useMutation({
    mutationFn: (confirmLastCopy: boolean) =>
      createAuctionLot({
        user_card_id: card!.id,
        kind: mode,
        start_price: startPrice,
        buy_now_price: !fixed && withBuyNow ? buyNow : null,
        duration_hours: fixed ? 0 : duration!,
        confirm_last_copy: confirmLastCopy,
      }),
    onSuccess: (lot) => {
      queryClient.invalidateQueries({ queryKey: ["auction"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      navigate(`/market/${lot.id}`, { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiRequestError && err.details?.requires_confirmation) {
        setLastCopy(true);
        setConfirmOpen(true);
        return;
      }
      setError(formatGameError(err, "Не удалось выставить лот"));
    },
  });

  const blocked = floor?.block_reason ?? null;
  const valid =
    !!card && (fixed || !!duration) && !blocked && startPrice >= minPrice && (fixed || !withBuyNow || buyNow > startPrice);
  const fee = info ? Math.floor(((!fixed && withBuyNow ? buyNow : startPrice) * info.fee_pct) / 100) : 0;

  if (info && (!info.enabled || info.restriction)) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Выставить на рынок</h1>
        <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-300">{info.restriction ?? "Рынок сейчас закрыт"}</p>
      </div>
    );
  }

  if (info && !info.license.active) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Выставить на рынок</h1>
        <div className="flex flex-col items-center gap-3 rounded-2xl bg-bg-surface p-5 text-center">
          <AgentIcon size={56} />
          <p className="text-sm text-ink-mist">
            Выставлять на рынок могут только агенты — купи «Агентскую лицензию» за {info.license.stars} ⭐ на{" "}
            {info.license.days} дн. Ставить и покупать можно и без неё.
          </p>
          <button
            onClick={() => navigate("/market/license")}
            className="w-full rounded-2xl bg-floodlight py-3 font-display text-sm font-bold text-bg-base active:scale-95"
          >
            Об агентской лицензии
          </button>
        </div>
      </div>
    );
  }

  const listable = collection?.items.filter(isListable) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Выставить на рынок</h1>
      {info && (
        <p className="text-caption text-ink-mist-dim">
          Активных лотов: {info.my_active_lots} из {info.max_active_lots}. Пока карточка на рынке, её нельзя ставить в составы,
          обменивать, продавать и улучшать.
        </p>
      )}

      {!card ? (
        <section>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по имени..."
            className="mb-2 w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
          />
          <div className="grid grid-cols-3 gap-2">
            {listable.map((c) => (
              <PlayerCard
                key={c.id}
                player={c.player}
                stars={c.stars}
                pathStage={c.path_stage}
                prestige={c.prestige}
                talentOverride={c.talent_override}
                size="sm"
                badge={<CardSkillBadge code={c.skill_code} level={c.skill_level} />}
                onClick={() => { setCard(c); setError(null); }}
              />
            ))}
            {collection && !listable.length && (
              <p className="col-span-3 text-xs text-ink-mist-dim">
                {search ? "Ничего не найдено" : "Нет карточек, которые можно выставить (убери их из составов)"}
              </p>
            )}
          </div>
        </section>
      ) : (
        <>
          <div className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
            <div className="w-20 shrink-0">
              <PlayerCard player={card.player} stars={card.stars} pathStage={card.path_stage} prestige={card.prestige} talentOverride={card.talent_override} size="sm" badge={<CardSkillBadge code={card.skill_code} level={card.skill_level} />} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-ink-chalk">{card.player.display_name}</p>
              <p className="text-caption text-ink-mist">Копия #{card.serial_number} · рейтинг {card.player.rating}</p>
              <button onClick={() => setCard(null)} className="mt-1 text-xs text-accent-lime">Выбрать другую</button>
            </div>
          </div>

          {blocked && <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-300">{blocked}</p>}
          {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

          <div className="grid grid-cols-2 gap-1 rounded-xl bg-white/5 p-1">
            {(["fixed", "auction"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-lg py-2 text-xs font-semibold ${mode === m ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
              >
                {m === "fixed" ? "Купить сразу" : "Аукцион"}
              </button>
            ))}
          </div>
          <p className="-mt-2 text-caption text-ink-mist-dim">
            {fixed
              ? `Фиксированная цена: первый, кто нажмёт «Купить», забирает карточку. Лот висит ${info?.fixed_duration_hours ?? 72} ч.`
              : "Торги: игроки делают ставки, карточка уходит лучшей ставке по окончании срока."}
          </p>

          <div>
            <label className="mb-1 block text-sm font-semibold text-ink-mist">{fixed ? "Цена" : "Стартовая цена"}</label>
            <NumberInput
              min={minPrice}
              value={startPrice}
              onChange={setStartPrice}
              className="w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk outline-none"
            />
            <p className="mt-1 text-caption text-ink-mist-dim">
              Не ниже {minPrice.toLocaleString("ru-RU")} — это ценность карточки
              {floor?.valuable ? " (легендарки, «Академия» и лимитки стоят дороже)" : ""}
            </p>
          </div>

          {!fixed && <div>
            <label className="flex items-center gap-2 text-sm font-semibold text-ink-mist">
              <input type="checkbox" checked={withBuyNow} onChange={(e) => setWithBuyNow(e.target.checked)} />
              Цена «Купить сейчас»
            </label>
            {withBuyNow && (
              <>
                <NumberInput
                  min={startPrice + 1}
                  value={buyNow}
                  onChange={setBuyNow}
                  className="mt-1 w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk outline-none"
                />
                {buyNow <= startPrice && <p className="mt-1 text-caption text-red-300">Должна быть выше стартовой цены</p>}
              </>
            )}
          </div>}

          {!fixed && <div>
            <p className="mb-1 text-sm font-semibold text-ink-mist">Срок</p>
            <div className="flex gap-2">
              {info?.durations_hours.map((h) => (
                <button
                  key={h}
                  onClick={() => setHours(h)}
                  className={`flex-1 rounded-xl py-2 text-xs font-semibold ${duration === h ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
                >
                  {h} ч
                </button>
              ))}
            </div>
          </div>}

          {info && (
            <p className="rounded-xl bg-white/5 px-3 py-2 text-caption text-ink-mist">
              Комиссия рынка {info.fee_pct}% сгорает при продаже. Снять лот можно, только пока на него нет ставок. Навыки, звёзды и
              прогресс карточки переходят покупателю.
            </p>
          )}

          <button
            disabled={!valid || createMutation.isPending}
            onClick={() => { setLastCopy(false); setConfirmOpen(true); }}
            className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            {createMutation.isPending ? "Выставляем..." : "Выставить"}
          </button>
        </>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title={lastCopy ? "Это последняя копия игрока" : "Выставить лот?"}
        description={
          lastCopy
            ? "Если лот продадут, этого игрока в коллекции не останется. Всё равно выставить?"
            : fixed
              ? `${card?.player.display_name ?? ""}: купить сразу за ${startPrice.toLocaleString("ru-RU")}, ${info?.fixed_duration_hours ?? 72} ч. При продаже комиссия ${fee.toLocaleString("ru-RU")} сгорит.`
              : `${card?.player.display_name ?? ""}: старт ${startPrice.toLocaleString("ru-RU")}${withBuyNow ? `, купить сейчас ${buyNow.toLocaleString("ru-RU")}` : ""}, ${duration ?? ""} ч. При продаже комиссия около ${fee.toLocaleString("ru-RU")} сгорит.`
        }
        confirmLabel="Выставить"
        onConfirm={() => { setConfirmOpen(false); createMutation.mutate(lastCopy); }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
