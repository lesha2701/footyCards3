import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";

import { catchUpDay, claimDailyReward, createCatchUpStarsInvoice, fetchDailyRewardCalendar } from "@/api/dailyRewards";
import { GrantedRewardModal, RewardBundleChips } from "@/components/rewards/RewardBundleView";
import { IconCheck, IconCoin, IconCollection, IconGift, IconPack, IconStar } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { isEmptyBundle } from "@/lib/rewards";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { CalendarClaimResult, CalendarDay, RewardBundle } from "@/types";

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

/** "2026-10-01" as a local date (new Date(iso) would be UTC midnight). */
function localDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function DayIcon({ reward }: { reward: RewardBundle }) {
  if (reward.cosmetic || reward.badge) return <IconStar size={13} />;
  if (reward.card_rarity) return <IconCollection size={13} />;
  if (reward.pack_name) return <IconPack size={13} />;
  return <IconCoin size={13} />;
}

const CELL: Record<CalendarDay["status"], string> = {
  claimed: "bg-accent-green/15 text-accent-green",
  today: "bg-accent-lime/20 text-accent-lime ring-2 ring-accent-lime",
  missed: "bg-white/[0.03] text-ink-mist-dim",
  future: "bg-white/5 text-ink-mist",
};

/** «Календарь наград»: one reward per day of the current month, claimed
 * once a day; missed days stay missed unless caught up for coins or ⭐.
 * Bigger rewards on the highlighted days and a bonus for the whole month. */
export default function LoginCalendar() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: calendar } = useQuery({ queryKey: ["daily-reward-calendar"], queryFn: fetchDailyRewardCalendar });
  const [selected, setSelected] = useState<CalendarDay | null>(null);
  const [result, setResult] = useState<CalendarClaimResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const done = (data: CalendarClaimResult) => {
    updateBalance(data.new_balance);
    hapticNotify("success");
    setSelected(null);
    setError(null);
    setResult(data);
    for (const key of [["daily-reward-calendar"], ["collection"], ["season-pass"], ["profile", "me"]]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не удалось получить награду"));

  const claim = useMutation({ mutationFn: claimDailyReward, onSuccess: done, onError });
  const catchUpCoins = useMutation({ mutationFn: (date: string) => catchUpDay(date), onSuccess: done, onError });
  const catchUpFree = useMutation({ mutationFn: (date: string) => catchUpDay(date, true), onSuccess: done, onError });
  const catchUpStars = useMutation({
    mutationFn: (date: string) => payShopWithStars(() => createCatchUpStarsInvoice(date)),
    onSuccess: (status) => {
      if (status === "paid") {
        hapticNotify("success");
        setSelected(null);
        queryClient.invalidateQueries({ queryKey: ["daily-reward-calendar"] });
        queryClient.invalidateQueries({ queryKey: ["profile", "me"] });
      }
    },
    onError,
  });

  if (!calendar) return null;

  const monthName = localDate(calendar.month).toLocaleDateString("ru-RU", { month: "long" });
  // Monday-first offset of the 1st, so the grid lines up with weekdays.
  const offset = (localDate(calendar.month).getDay() + 6) % 7;
  const busy = claim.isPending || catchUpCoins.isPending || catchUpStars.isPending || catchUpFree.isPending;

  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 whitespace-nowrap font-display text-base font-bold text-ink-chalk">
          <IconGift size={16} className="text-accent-lime" />
          Календарь наград
        </p>
        <span className="whitespace-nowrap font-mono text-xs text-ink-mist">
          <span className="capitalize">{monthName}</span> · {calendar.claimed_count}/{calendar.days_in_month}
        </span>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center">
        {WEEKDAYS.map((w) => (
          <span key={w} className="text-micro text-ink-mist-dim">{w}</span>
        ))}
        {Array.from({ length: offset }).map((_, i) => <span key={`pad-${i}`} />)}
        {calendar.days.map((d) => (
          <button
            key={d.day}
            onClick={() => setSelected(d)}
            aria-label={`${d.day} число`}
            className={`relative flex aspect-square flex-col items-center justify-center gap-0.5 rounded-lg text-micro active:scale-95 ${CELL[d.status]} ${
              d.is_big && d.status !== "claimed" ? "border border-amber-400/60" : ""
            }`}
          >
            <span className="font-mono leading-none">{d.day}</span>
            {d.status === "claimed" ? <IconCheck size={12} /> : <DayIcon reward={d.reward} />}
            {d.is_big && d.status !== "claimed" && (
              <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-amber-400" />
            )}
          </button>
        ))}
      </div>

      {!isEmptyBundle(calendar.month_bonus) && (
        <div className="mt-3 flex items-center justify-between gap-2 rounded-xl bg-amber-400/10 px-3 py-2">
          <span className="text-xs text-amber-300">
            {calendar.month_bonus_claimed ? "Бонус за месяц получен ✓" : "Все дни месяца — бонус:"}
          </span>
          {!calendar.month_bonus_claimed && <RewardBundleChips bundle={calendar.month_bonus} />}
        </div>
      )}

      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
      <button
        onClick={() => claim.mutate()}
        disabled={calendar.already_claimed_today || busy}
        className="mt-3 w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {calendar.already_claimed_today ? "Сегодня уже получено" : claim.isPending ? "Забираем..." : "Забрать награду"}
      </button>
      {calendar.catchups_left > 0 && calendar.days.some((d) => d.status === "missed") && (
        <p className="mt-2 text-center text-caption text-ink-mist-dim">
          Пропустил день? Нажми на него, чтобы догнать (осталось в этом месяце: {calendar.catchups_left})
        </p>
      )}

      {selected && (
        <DaySheet
          day={selected}
          catchupCoins={calendar.catchup_coins}
          catchupStars={calendar.catchup_stars}
          catchupsLeft={calendar.catchups_left}
          freeLeft={calendar.free_catchups_left}
          onCatchUpFree={() => catchUpFree.mutate(selected.date)}
          busy={busy}
          onClaim={() => claim.mutate()}
          onCatchUpCoins={() => catchUpCoins.mutate(selected.date)}
          onCatchUpStars={() => catchUpStars.mutate(selected.date)}
          onClose={() => setSelected(null)}
        />
      )}
      {result && (
        <GrantedRewardModal
          title="Награда получена!"
          subtitle={`${result.day} число`}
          granted={result.granted}
          bonus={result.month_bonus}
          onClose={() => setResult(null)}
        />
      )}
    </section>
  );
}

function DaySheet({
  day, catchupCoins, catchupStars, catchupsLeft, freeLeft, busy, onClaim, onCatchUpCoins, onCatchUpStars, onCatchUpFree, onClose,
}: {
  freeLeft: number;
  onCatchUpFree: () => void;
  day: CalendarDay;
  catchupCoins: number;
  catchupStars: number;
  catchupsLeft: number;
  busy: boolean;
  onClaim: () => void;
  onCatchUpCoins: () => void;
  onCatchUpStars: () => void;
  onClose: () => void;
}) {
  const canCatchUp = day.status === "missed" && catchupsLeft > 0;
  const canFree = day.status === "missed" && freeLeft > 0;
  const date = localDate(day.date).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60" onClick={onClose}>
      <motion.div
        initial={{ y: 40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="w-full max-w-md rounded-t-3xl bg-bg-surface p-5 pb-8"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="font-display text-lg font-bold text-ink-chalk">{date}</p>
        <p className="mt-0.5 text-xs text-ink-mist">
          {day.status === "claimed" && (day.claim_method === "login" ? "Получено" : "Получено (догнал)")}
          {day.status === "today" && "Награда дня — забери сегодня"}
          {day.status === "missed" && "Пропущено"}
          {day.status === "future" && "Откроется в этот день"}
        </p>
        <div className="mt-3">
          <RewardBundleChips bundle={day.reward} />
        </div>
        {day.status === "today" && (
          <button
            onClick={onClaim}
            disabled={busy}
            className="mt-4 w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base disabled:opacity-40"
          >
            Забрать
          </button>
        )}
        {canFree && (
          <button
            onClick={onCatchUpFree}
            disabled={busy}
            className="mt-4 w-full rounded-2xl bg-emerald-400 py-3 text-sm font-bold text-bg-base disabled:opacity-40"
          >
            Догнать бесплатно · абонемент (осталось {freeLeft})
          </button>
        )}
        {canCatchUp && (
          <div className="mt-4 flex flex-col gap-2">
            {catchupCoins > 0 && (
              <button
                onClick={onCatchUpCoins}
                disabled={busy}
                className="flex items-center justify-center gap-1.5 rounded-2xl bg-white/10 py-3 text-sm font-bold text-ink-chalk disabled:opacity-40"
              >
                Догнать за {catchupCoins} <IconCoin size={14} className="text-accent-lime" />
              </button>
            )}
            {catchupStars > 0 && (
              <button
                onClick={onCatchUpStars}
                disabled={busy}
                className="rounded-2xl bg-amber-400 py-3 text-sm font-bold text-bg-base disabled:opacity-40"
              >
                Догнать за {catchupStars} ⭐
              </button>
            )}
            <p className="text-center text-caption text-ink-mist-dim">Догнать можно ещё {catchupsLeft} раз в этом месяце</p>
          </div>
        )}
        {day.status === "missed" && !canCatchUp && !canFree && (
          <p className="mt-3 text-xs text-ink-mist-dim">Лимит догонялок на этот месяц исчерпан.</p>
        )}
      </motion.div>
    </div>
  );
}
