import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  blackjackHit, blackjackStand, createBlackjackStarsInvoice, fetchBlackjackStarsInvoiceStatus, fetchBlackjackStatus,
  startBlackjack,
} from "@/api/blackjack";
import { IconCoin } from "@/components/icons";
import { WheelPrizeResult } from "@/components/wheel/WheelPrizeResult";
import { PrizeOddsList, WheelReel } from "@/components/wheel/WheelReel";
import { formatGameError } from "@/lib/errors";
import { haptic, openTelegramInvoice } from "@/lib/telegram";
import { WHEEL_SPIN_MS, prizeLabel, shuffle, type WheelTheme } from "@/lib/wheel";
import { useAuthStore } from "@/store/authStore";
import type { BlackjackAction, BlackjackCard, BlackjackMatch, WheelPrize, WheelSpinResult } from "@/types";

const SUIT: Record<NonNullable<BlackjackCard["suit"]>, { label: string; icon: string }> = {
  gk: { label: "ВРТ", icon: "🧤" },
  df: { label: "ЗАЩ", icon: "🛡️" },
  mf: { label: "ПЗ", icon: "🎯" },
  fw: { label: "НАП", icon: "⚽" },
};

const FACE: Record<string, { title: string; short: string; icon: string }> = {
  playmaker: { title: "Плеймейкер", short: "10", icon: "🪄" },
  striker: { title: "Бомбардир", short: "10", icon: "🔥" },
  captain: { title: "Капитан", short: "10", icon: "©️" },
  legend: { title: "Легенда", short: "1/11", icon: "👑" },
};

const OUTCOME_TEXT: Record<string, { title: string; tone: string }> = {
  hat_trick: { title: "Хет-трик!", tone: "text-fuchsia-300" },
  win: { title: "Победа!", tone: "text-accent-lime" },
  push: { title: "Ничья", tone: "text-ink-chalk" },
  loss: { title: "Поражение", tone: "text-red-400" },
};

const REASON_TEXT: Record<string, string> = {
  natural: "21 с двух карт — Тренер соперника не ответил.",
  both_natural: "У обоих 21 с двух карт.",
  dealer_natural: "У Тренера соперника 21 с двух карт.",
  offside: "Офсайд! Перебор — больше 21.",
  dealer_offside: "Тренер соперника ушёл в офсайд.",
  higher: "У тебя больше очков.",
  lower: "У Тренера соперника больше очков.",
  equal: "Очков поровну.",
};

const POOL_TITLE: Record<WheelTheme, string> = {
  regular: "Колесо фортуны",
  golden: "Золотое колесо",
  jackpot: "Джекпот-колесо",
};

async function pollEntryInvoice(payloadToken: string): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt++) {
    const status = await fetchBlackjackStarsInvoiceStatus(payloadToken);
    if (status.status === "completed") return;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Оплата ещё обрабатывается — загляни через минуту");
}

function FootyCard({ card, index }: { card: BlackjackCard; index: number }) {
  const face = card.rank ? FACE[card.rank] : undefined;
  const suit = card.suit ? SUIT[card.suit] : undefined;
  return (
    <motion.div
      initial={{ opacity: 0, y: -40, rotate: -8, scale: 0.8 }}
      animate={{ opacity: 1, y: 0, rotate: 0, scale: 1 }}
      transition={{ delay: index * 0.15, type: "spring", stiffness: 260, damping: 22 }}
      className="relative h-[104px] w-[72px] shrink-0"
    >
      {card.hidden ? (
        <div className="flex h-full w-full items-center justify-center rounded-xl border border-white/10 bg-gradient-to-br from-white/10 to-bg-surface shadow-lg">
          <img decoding="async" src="/brand/victor-fc-crest.jpg" alt="" className="h-10 w-10 rounded-full opacity-80 ring-1 ring-white/10" />
        </div>
      ) : (
        <div
          className={`flex h-full w-full flex-col justify-between rounded-xl border p-1.5 shadow-lg ${
            card.rank === "legend"
              ? "border-amber-300/60 bg-gradient-to-br from-amber-400/30 to-amber-700/20"
              : face
                ? "border-purple-300/40 bg-gradient-to-br from-purple-500/25 to-blue-600/15"
                : "border-white/15 bg-gradient-to-br from-white/10 to-white/[0.03]"
          }`}
        >
          <div className="flex items-start justify-between">
            <span className="font-display text-lg font-bold leading-none text-ink-chalk">{face ? face.short : card.rank}</span>
            <span className="text-[9px] font-semibold text-ink-mist">{suit?.label}</span>
          </div>
          <div className="text-center text-2xl leading-none">{face ? face.icon : suit?.icon}</div>
          <p className="truncate text-center text-[9px] font-semibold text-ink-mist">
            {face ? face.title : "Игрок"}
          </p>
        </div>
      )}
    </motion.div>
  );
}

function Hand({ title, cards, total, hint }: { title: string; cards: BlackjackCard[]; total: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <p className="font-display text-sm font-bold text-ink-chalk">{title}</p>
        <p className="font-mono text-sm text-ink-chalk">
          {total}
          {hint && <span className="ml-1 text-xs text-ink-mist">{hint}</span>}
        </p>
      </div>
      <div className="flex min-h-[104px] flex-wrap gap-2">
        {cards.map((card, i) => (
          <FootyCard key={`${i}-${card.hidden ? "h" : `${card.suit}${card.rank}`}`} card={card} index={i} />
        ))}
      </div>
    </div>
  );
}

function prizesFor(pool: WheelTheme, golden: WheelPrize[], jackpot: WheelPrize[]): WheelPrize[] {
  return pool === "jackpot" ? jackpot : pool === "golden" ? golden : [];
}

export default function BlackjackPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: status, isLoading } = useQuery({ queryKey: ["blackjack-status"], queryFn: fetchBlackjackStatus });

  const [match, setMatch] = useState<BlackjackMatch | null>(null);
  const [pendingSpin, setPendingSpin] = useState<WheelSpinResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [wheelOpen, setWheelOpen] = useState(false);
  const [centerIndex, setCenterIndex] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [prizeResult, setPrizeResult] = useState<WheelSpinResult | null>(null);
  const wheelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (wheelOpen) wheelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [wheelOpen]);

  // Resume a hand left in progress (reload, app switch).
  useEffect(() => {
    if (!match && status?.active_match) setMatch(status.active_match);
  }, [status?.active_match]); // eslint-disable-line react-hooks/exhaustive-deps

  const pool: WheelTheme = (match?.reward_pool as WheelTheme | null) ?? "golden";
  const poolPrizes = status ? prizesFor(pool, status.golden_prizes, status.jackpot_prizes) : [];
  const prizesKey = poolPrizes.map((p) => p.id).join(",");
  const reel = useMemo(() => shuffle(poolPrizes), [prizesKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyAction = (action: BlackjackAction) => {
    setError(null);
    setMatch(action.match);
    // A won prize is already in new_balance — hold it back until the wheel
    // has landed so the header doesn't spoil the spin.
    if (action.spin_result) setPendingSpin(action.spin_result);
    else updateBalance(action.new_balance);
    if (action.match.status === "finished") {
      haptic(action.match.outcome === "loss" ? "heavy" : "medium");
      queryClient.invalidateQueries({ queryKey: ["blackjack-status"] });
    }
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Что-то пошло не так"));

  const startMutation = useMutation({
    mutationFn: startBlackjack,
    onSuccess: (action) => {
      setPendingSpin(null);
      setWheelOpen(false);
      applyAction(action);
      queryClient.invalidateQueries({ queryKey: ["blackjack-status"] });
    },
    onError,
  });
  const hitMutation = useMutation({ mutationFn: (id: number) => blackjackHit(id), onSuccess: applyAction, onError });
  const standMutation = useMutation({ mutationFn: (id: number) => blackjackStand(id), onSuccess: applyAction, onError });
  const buyMutation = useMutation({
    mutationFn: async () => {
      const invoice = await createBlackjackStarsInvoice();
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") return "cancelled" as const;
      if (paymentStatus === "failed") throw new Error("Платёж не прошёл");
      await pollEntryInvoice(invoice.payload_token);
      return "paid" as const;
    },
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["blackjack-status"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Не удалось оплатить"),
  });

  const spinWheel = async () => {
    if (!pendingSpin || !reel.length) return;
    setSpinning(true);
    const wonIndex = reel.findIndex((p) => p.id === pendingSpin.prize.id);
    setCenterIndex((prev) => prev - (prev % reel.length) + reel.length * 3 + (wonIndex >= 0 ? wonIndex : 0));
    await new Promise((resolve) => setTimeout(resolve, WHEEL_SPIN_MS));
    setSpinning(false);
    setCenterIndex((prev) => prev % reel.length);
    const won = pendingSpin;
    setPendingSpin(null);
    updateBalance(won.new_balance);
    if (won.badge_result) {
      const current = useAuthStore.getState().user;
      if (current) useAuthStore.getState().setUser({ ...current, active_badge: won.badge_result });
    }
    if (won.pack_result) {
      navigate(`/packs/${won.pack_result.pack.id}/open`, { state: { result: won.pack_result } });
      return;
    }
    setPrizeResult(won);
  };

  if (isLoading || !status) return null;

  const busy = startMutation.isPending || hitMutation.isPending || standMutation.isPending;
  const inProgress = match?.status === "in_progress";
  const finished = match?.status === "finished";
  const freeLike = status.free_remaining + status.replay_entries;
  const canStart = freeLike + status.paid_entries > 0;
  const paidOn = status.paid_daily_limit > 0;
  const paidLeftToday = Math.max(0, status.paid_daily_limit - status.paid_bought_today);
  const outcome = match?.outcome ? OUTCOME_TEXT[match.outcome] : null;

  const startLabel =
    status.free_remaining > 0
      ? "Играть бесплатно"
      : status.replay_entries > 0
        ? "Переигровка (бесплатно)"
        : `Играть (куплено попыток: ${status.paid_entries})`;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-xl font-bold text-ink-chalk">21: Добавленное время</h1>
        <p className="mt-1 text-sm text-ink-mist">
          Набери больше Тренера соперника, но не больше 21. Звёзды — 10, Легенда — 1 или 11. Тренер добирает до 17.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-xl bg-bg-surface px-2 py-2">
          <p className="font-mono text-base font-bold text-ink-chalk">{status.free_remaining}/{status.free_per_day}</p>
          <p className="text-[10px] text-ink-mist">бесплатно сегодня</p>
        </div>
        <div className="rounded-xl bg-bg-surface px-2 py-2">
          <p className="font-mono text-base font-bold text-ink-chalk">{status.replay_entries}</p>
          <p className="text-[10px] text-ink-mist">переигровки</p>
        </div>
        <div className="rounded-xl bg-bg-surface px-2 py-2">
          <p className="font-mono text-base font-bold text-ink-chalk">{status.paid_entries}</p>
          <p className="text-[10px] text-ink-mist">куплено</p>
        </div>
      </div>

      {!status.enabled && !inProgress && (
        <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-300">Игра временно недоступна.</p>
      )}

      {match && (
        <div className="flex flex-col gap-4 rounded-3xl bg-bg-surface p-4">
          <Hand
            title="Тренер соперника"
            cards={match.dealer_cards}
            total={inProgress ? `${match.dealer_total} + ?` : String(match.dealer_total)}
          />
          <div className="h-px bg-white/5" />
          <Hand
            title="Ты"
            cards={match.player_cards}
            total={String(match.player_total)}
            hint={match.player_soft && match.player_total < 21 ? "(Легенда = 11)" : undefined}
          />

          {inProgress && (
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => { haptic("light"); hitMutation.mutate(match.id); }}
                disabled={busy}
                className="rounded-xl bg-accent py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
              >
                Ещё карту
              </button>
              <button
                onClick={() => { haptic("light"); standMutation.mutate(match.id); }}
                disabled={busy}
                className="rounded-xl bg-white/10 py-3 text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
              >
                Хватит
              </button>
            </div>
          )}

          <AnimatePresence>
            {finished && outcome && (
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center gap-1 text-center"
              >
                <p className={`font-display text-2xl font-bold ${outcome.tone}`}>{outcome.title}</p>
                {match.outcome_reason && <p className="text-sm text-ink-mist">{REASON_TEXT[match.outcome_reason]}</p>}
                {match.outcome === "push" && <p className="text-xs text-ink-mist">Попытка не потрачена — переигровка уже ждёт.</p>}
                {match.outcome === "loss" && match.consolation_coins > 0 && (
                  <p className="flex items-center gap-1 text-sm font-semibold text-accent-lime">
                    Утешительный приз +{match.consolation_coins} <IconCoin size={14} />
                  </p>
                )}
                {match.prize && !pendingSpin && !wheelOpen && (
                  <p className="text-sm text-ink-chalk">Приз: {prizeLabel(match.prize)}</p>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {pendingSpin && !wheelOpen && (
        <button
          onClick={() => {
            setWheelOpen(true);
            // Let the reel mount at rest first so the spin visibly animates.
            setTimeout(spinWheel, 300);
          }}
          className={`w-full rounded-2xl py-3.5 font-display text-base font-bold text-bg-base active:scale-95 ${
            pool === "jackpot" ? "bg-gradient-to-r from-fuchsia-400 to-amber-300" : "bg-gradient-to-r from-amber-300 to-amber-500"
          }`}
        >
          Крутить {POOL_TITLE[pool]}
        </button>
      )}

      {wheelOpen && reel.length > 0 && (
        <div ref={wheelRef} className="flex flex-col gap-3">
          <p className="text-center font-display text-base font-bold text-ink-chalk">{POOL_TITLE[pool]}</p>
          <WheelReel prizes={reel} centerIndex={centerIndex} spinning={spinning} theme={pool} />
        </div>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      {!inProgress && !pendingSpin && !spinning && status.enabled && (
        <div className="flex flex-col gap-2">
          {canStart ? (
            <button
              onClick={() => startMutation.mutate()}
              disabled={busy}
              className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
            >
              {startMutation.isPending ? "Раздаём..." : match ? `Ещё партия — ${startLabel.toLowerCase()}` : startLabel}
            </button>
          ) : (
            <p className="text-center text-sm text-ink-mist">Бесплатная попытка вернётся завтра.</p>
          )}
          {paidOn && (
            <button
              onClick={() => buyMutation.mutate()}
              disabled={buyMutation.isPending || paidLeftToday === 0}
              className="w-full rounded-xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
            >
              {buyMutation.isPending
                ? "Ждём оплату..."
                : paidLeftToday === 0
                  ? "Лимит покупок на сегодня исчерпан"
                  : `Купить попытку за ⭐ ${status.stars_cost} (осталось ${paidLeftToday})`}
            </button>
          )}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <PrizeOddsList prizes={status.golden_prizes} title="Золотое колесо (победа) — шансы" />
        <PrizeOddsList prizes={status.jackpot_prizes} title="Джекпот-колесо (Хет-трик) — шансы" />
        <details className="rounded-2xl bg-bg-surface px-4 py-3 text-sm text-ink-mist">
          <summary className="cursor-pointer font-display font-bold text-ink-chalk">Правила</summary>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            <li>Карты 2–10 по номиналу, Звёзды (Плеймейкер, Бомбардир, Капитан) — 10, Легенда — 1 или 11.</li>
            <li>Одна карта Тренера соперника закрыта до конца партии. Он берёт карты, пока у него меньше 17, и останавливается на любых 17.</li>
            <li>«Ещё карту» или «Хватит». Больше 21 — офсайд, партия проиграна.</li>
            <li>Хет-трик (21 с двух карт) — спин Джекпот-колеса. Победа — спин Золотого колеса.</li>
            <li>Ничья — бесплатная переигровка, попытка не тратится.</li>
            <li>
              Поражение — утешительный приз
              {status.consolation_coins > 0 ? ` ${status.consolation_coins} монет` : " не начисляется"}.
            </li>
            <li>
              {status.free_per_day} бесплатн. попытка в день
              {paidOn ? `, дальше — за ⭐ ${status.stars_cost} (до ${status.paid_daily_limit} в день)` : ""}. Призы только
              внутриигровые.
            </li>
          </ul>
        </details>
      </div>

      {prizeResult && <WheelPrizeResult result={prizeResult} onClose={() => { setPrizeResult(null); setWheelOpen(false); }} />}
    </div>
  );
}
