import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { exchangeClubCards, fetchClubSurplus, sellClubCards } from "@/api/clubFeatures";
import PlayerCard from "@/components/cards/PlayerCard";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCheck, IconChevronLeft, IconCoin, IconCollection, IconGift } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { RARITY_ORDER } from "@/lib/rarity";
import { hapticNotify } from "@/lib/telegram";
import type { ClubPackOpenResult } from "@/types";

type Mode = "sell" | "burn";

/** «Лишние карты» клуба: продать в казну или слить N карт за клубный пак.
 * Карты из любого шаблона состава защищены (club_market_service). */
export default function ClubSurplusPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["clubs", "surplus"], queryFn: fetchClubSurplus });
  const [mode, setMode] = useState<Mode>("sell");
  const [selected, setSelected] = useState<number[]>([]);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sold, setSold] = useState<string | null>(null);
  const [opened, setOpened] = useState<ClubPackOpenResult | null>(null);

  const refresh = () => {
    setSelected([]);
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["clubs"] });
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не удалось выполнить действие"));
  const sell = useMutation({
    mutationFn: () => sellClubCards(selected),
    onSuccess: (r) => { hapticNotify("success"); refresh(); setSold(`Продано карт: ${r.sold}. В казну +${r.coins} монет`); },
    onError,
  });
  const burn = useMutation({
    mutationFn: () => exchangeClubCards(selected),
    onSuccess: (r) => { hapticNotify("success"); refresh(); setOpened(r); },
    onError,
  });

  const free = useMemo(() => (data?.cards ?? []).filter((c) => !c.protected), [data]);
  const squadCount = (data?.cards ?? []).length - free.length;
  const total = free.filter((c) => selected.includes(c.card.id)).reduce((sum, c) => sum + c.sell_value, 0);

  if (isLoading || !data) return <ListSkeleton />;
  const need = data.exchange_count;
  const pack = data.exchange_pack;

  const toggle = (id: number) => {
    setSold(null);
    setOpened(null);
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : mode === "burn" && s.length >= need ? s : [...s, id]));
  };
  const switchMode = (next: Mode) => { setMode(next); setSelected([]); setSold(null); setOpened(null); };
  const canAct = data.enabled && data.can_manage;
  const sorted = [...free].sort(
    (a, b) => mode === "burn"
      ? RARITY_ORDER[a.card.player.rarity] - RARITY_ORDER[b.card.player.rarity] || a.sell_value - b.sell_value
      : RARITY_ORDER[b.card.player.rarity] - RARITY_ORDER[a.card.player.rarity] || b.sell_value - a.sell_value,
  );

  return (
    <div className="flex flex-col gap-4 pb-28">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Лишние карты</h1>
        <span className="ml-auto flex items-center gap-1 font-mono text-sm font-bold text-accent-lime">
          <IconCoin size={14} /> {data.budget}
        </span>
      </div>

      <p className="rounded-xl bg-white/5 px-3 py-2 text-xs leading-snug text-ink-mist">
        Карты вне состава можно продать в казну клуба или слить {need} любых карт за клубный пак.
        Карты из составов защищены. Помни: в турнире запасные выходят вместо дисквалифицированных — оставь пару игроков на скамейке.
      </p>
      {!data.can_manage && <p className="text-xs text-ink-mist-dim">Продавать и сливать карты могут капитан, вице-капитан, казначей и ассистенты.</p>}
      {!data.enabled && <p className="text-xs text-ink-mist-dim">Продажа и обмен временно недоступны.</p>}

      <div className="flex gap-1 rounded-xl bg-bg-surface p-1">
        {([["sell", "Продать в казну"], ["burn", `${need} карт → пак`]] as [Mode, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => switchMode(id)}
            className={`flex-1 rounded-lg py-2 text-xs font-semibold ${mode === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "burn" && (
        <div className="flex items-center gap-3 rounded-2xl bg-gradient-to-r from-accent-lime/15 to-bg-surface p-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-lime/15 text-accent-lime">
            <IconGift size={20} />
          </span>
          {pack ? (
            <div className="min-w-0 flex-1">
              <p className="font-display text-sm font-bold text-ink-chalk">{pack.name}</p>
              <p className="text-caption text-ink-mist">
                {pack.card_count} карт клубу · бесплатно, за {need} лишних карт (обычно стоит {pack.price} монет)
              </p>
            </div>
          ) : (
            <p className="text-xs text-ink-mist">Сейчас нет клубного пака для обмена.</p>
          )}
        </div>
      )}

      {sold && (
        <p className="flex items-center gap-1.5 rounded-xl bg-accent-green/10 px-3 py-2 text-sm font-semibold text-accent-green">
          <IconCheck size={14} /> {sold}
        </p>
      )}
      {opened && (
        <div className="flex flex-col gap-2 rounded-2xl bg-accent-green/10 p-3">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-accent-green">
            <IconCheck size={14} /> Пак «{opened.pack.name}» открыт — новые карты уже в клубе
          </p>
          <div className="grid grid-cols-3 gap-2">
            {opened.cards.map((item, i) =>
              item.card ? (
                <PlayerCard key={i} player={item.card.player} size="sm" animated />
              ) : (
                <div key={i} className="flex items-center justify-center rounded-xl bg-black/20 p-2 text-center text-caption text-ink-mist">
                  {item.coach_card ? `Тренер: ${item.coach_card.coach.display_name}` : item.stadium_card ? `Стадион: ${item.stadium_card.stadium.display_name}` : ""}
                </div>
              ),
            )}
          </div>
        </div>
      )}
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {sorted.length === 0 ? (
        <EmptyState
          icon={IconCollection}
          title="Лишних карт нет"
          description="Все карты клуба стоят в составах — открой клубный пак, чтобы пополнить скамейку"
        />
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {sorted.map((c) => (
            <PlayerCard
              key={c.card.id}
              player={c.card.player}
              size="sm"
              selected={selected.includes(c.card.id)}
              onClick={canAct ? () => toggle(c.card.id) : undefined}
              footer={
                mode === "sell" ? (
                  <span className="flex items-center justify-center gap-0.5 text-micro font-bold text-accent-lime">
                    +{c.sell_value} <IconCoin size={10} />
                  </span>
                ) : undefined
              }
            />
          ))}
        </div>
      )}

      {squadCount > 0 && <p className="text-center text-caption text-ink-mist-dim">В составах: {squadCount} карт — они защищены</p>}

      {canAct && sorted.length > 0 && (
        <div className="safe-bottom fixed inset-x-0 bottom-16 z-30 mx-auto flex max-w-md gap-2 px-4 py-2">
          {mode === "sell" ? (
            <>
              <button
                onClick={() => setSelected(selected.length === sorted.length ? [] : sorted.map((c) => c.card.id))}
                className="rounded-2xl bg-bg-surface px-4 py-3 text-xs font-semibold text-ink-mist shadow-xl"
              >
                {selected.length === sorted.length ? "Снять" : "Все"}
              </button>
              <button
                onClick={() => setConfirm(true)}
                disabled={!selected.length || sell.isPending}
                className="flex flex-1 items-center justify-center gap-1 rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base shadow-xl active:scale-95 disabled:opacity-60"
              >
                Продать {selected.length || ""} {selected.length ? <>за {total} <IconCoin size={14} /></> : "— выбери карты"}
              </button>
            </>
          ) : (
            <button
              onClick={() => setConfirm(true)}
              disabled={selected.length !== need || burn.isPending || !pack}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base shadow-xl active:scale-95 disabled:opacity-60"
            >
              <IconGift size={15} /> Слить {selected.length}/{need} за пак
            </button>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirm}
        title={mode === "sell" ? `Продать ${selected.length} карт за ${total} монет?` : `Слить ${need} карт за пак?`}
        description={
          mode === "sell"
            ? "Карты исчезнут из клуба, монеты придут в казну. Отменить нельзя."
            : `Отдаёшь ${need} карт — клуб сразу открывает «${pack?.name ?? ""}». Отменить нельзя.`
        }
        danger
        confirmLabel={mode === "sell" ? "Продать" : "Слить и открыть"}
        onConfirm={() => { setConfirm(false); if (mode === "sell") sell.mutate(); else burn.mutate(); }}
        onCancel={() => setConfirm(false)}
      />
    </div>
  );
}
