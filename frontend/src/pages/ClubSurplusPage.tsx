import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { exchangeClubCards, fetchClubSurplus, sellClubCards } from "@/api/clubFeatures";
import PlayerCard from "@/components/cards/PlayerCard";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCheck, IconChevronLeft, IconCoin, IconCollection, IconSwap } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { RARITY_LABELS, RARITY_ORDER, RARITY_TEXT } from "@/lib/rarity";
import { hapticNotify } from "@/lib/telegram";
import type { ClubCard, Rarity } from "@/types";

type Mode = "sell" | "exchange";

/** «Лишние карты» клуба: продать в казну или обменять N → 1 следующей редкости.
 * Карты из любого шаблона состава защищены (club_market_service). */
export default function ClubSurplusPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["clubs", "surplus"], queryFn: fetchClubSurplus });
  const [mode, setMode] = useState<Mode>("sell");
  const [rarity, setRarity] = useState<Rarity>("common");
  const [selected, setSelected] = useState<number[]>([]);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ text: string; card?: ClubCard } | null>(null);

  const refresh = () => {
    setSelected([]);
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["clubs"] });
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не удалось выполнить действие"));
  const sell = useMutation({
    mutationFn: () => sellClubCards(selected),
    onSuccess: (r) => { hapticNotify("success"); refresh(); setResult({ text: `Продано карт: ${r.sold}. В казну +${r.coins} монет` }); },
    onError,
  });
  const exchange = useMutation({
    mutationFn: () => exchangeClubCards(selected),
    onSuccess: (r) => { hapticNotify("success"); refresh(); setResult({ text: "Обмен состоялся!", card: r.card }); },
    onError,
  });

  const free = useMemo(() => (data?.cards ?? []).filter((c) => !c.protected), [data]);
  const visible = mode === "sell" ? free : free.filter((c) => c.card.player.rarity === rarity);
  const squad = (data?.cards ?? []).filter((c) => c.protected);
  const total = free.filter((c) => selected.includes(c.card.id)).reduce((sum, c) => sum + c.sell_value, 0);

  if (isLoading || !data) return <ListSkeleton />;
  const need = data.exchange_count;
  const option = data.exchange_options.find((o) => o.rarity === rarity);

  const toggle = (id: number) => {
    setResult(null);
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : mode === "exchange" && s.length >= need ? s : [...s, id]));
  };
  const switchMode = (next: Mode) => { setMode(next); setSelected([]); setResult(null); };
  const canAct = data.enabled && data.can_manage;

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
        Карты вне состава можно продать в казну клуба или обменять {need} одинаковой редкости на 1 карту редкостью выше.
        Карты из составов защищены. Помни: в турнире запасные выходят вместо дисквалифицированных — оставь пару игроков на скамейке.
      </p>
      {!data.can_manage && <p className="text-xs text-ink-mist-dim">Продавать и обменивать могут капитан и ассистенты.</p>}
      {!data.enabled && <p className="text-xs text-ink-mist-dim">Продажа и обмен временно недоступны.</p>}

      <div className="flex gap-1 rounded-xl bg-bg-surface p-1">
        {([["sell", "Продать в казну"], ["exchange", `Обмен ${need} → 1`]] as [Mode, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => switchMode(id)}
            className={`flex-1 rounded-lg py-2 text-xs font-semibold ${mode === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "exchange" && (
        <div className="grid grid-cols-3 gap-2">
          {data.exchange_options.map((o) => (
            <button
              key={o.rarity}
              onClick={() => { setRarity(o.rarity); setSelected([]); setResult(null); }}
              className={`flex flex-col items-center rounded-xl p-2 text-caption ${rarity === o.rarity ? "bg-white/10 ring-2 ring-accent" : "bg-bg-surface"}`}
            >
              <span className={`font-bold ${RARITY_TEXT[o.rarity]}`}>{RARITY_LABELS[o.rarity]}</span>
              <span className="text-ink-mist-dim">→ {RARITY_LABELS[o.target_rarity].toLowerCase()}</span>
              <span className={o.available >= need ? "text-accent-lime" : "text-ink-mist-dim"}>{o.available} / {need}</span>
            </button>
          ))}
        </div>
      )}

      {result && (
        <div className="flex flex-col items-center gap-2 rounded-2xl bg-accent-green/10 p-3 text-center">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-accent-green"><IconCheck size={14} /> {result.text}</p>
          {result.card && (
            <div className="w-28">
              <PlayerCard player={result.card.player} size="sm" animated />
            </div>
          )}
        </div>
      )}
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {visible.length === 0 ? (
        <EmptyState
          icon={IconCollection}
          title={mode === "sell" ? "Лишних карт нет" : "Нет карт этой редкости вне состава"}
          description="Все карты клуба стоят в составах — открой клубный пак, чтобы пополнить скамейку"
        />
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {[...visible]
            .sort((a, b) => RARITY_ORDER[b.card.player.rarity] - RARITY_ORDER[a.card.player.rarity] || b.sell_value - a.sell_value)
            .map((c) => (
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

      {squad.length > 0 && (
        <p className="text-center text-caption text-ink-mist-dim">В составах: {squad.length} карт — они защищены</p>
      )}

      {canAct && visible.length > 0 && (
        <div className="safe-bottom fixed inset-x-0 bottom-16 z-30 mx-auto flex max-w-md gap-2 px-4 py-2">
          {mode === "sell" ? (
            <>
              <button
                onClick={() => setSelected(selected.length === visible.length ? [] : visible.map((c) => c.card.id))}
                className="rounded-2xl bg-bg-surface px-4 py-3 text-xs font-semibold text-ink-mist shadow-xl"
              >
                {selected.length === visible.length ? "Снять" : "Все"}
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
              disabled={selected.length !== need || exchange.isPending || !option}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base shadow-xl active:scale-95 disabled:opacity-60"
            >
              <IconSwap size={15} /> Обменять {selected.length}/{need} на {option ? RARITY_LABELS[option.target_rarity].toLowerCase() : ""}
            </button>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirm}
        title={mode === "sell" ? `Продать ${selected.length} карт за ${total} монет?` : `Обменять ${need} карт?`}
        description={
          mode === "sell"
            ? "Карты исчезнут из клуба, монеты придут в казну. Отменить нельзя."
            : `Отдаёшь ${need} карт и получаешь 1 случайную карту редкости «${option ? RARITY_LABELS[option.target_rarity] : ""}». Отменить нельзя.`
        }
        danger
        confirmLabel={mode === "sell" ? "Продать" : "Обменять"}
        onConfirm={() => { setConfirm(false); if (mode === "sell") sell.mutate(); else exchange.mutate(); }}
        onCancel={() => setConfirm(false)}
      />
    </div>
  );
}
