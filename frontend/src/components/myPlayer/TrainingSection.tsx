import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { buyExtraTraining, type MyPlayerView } from "@/api/myPlayer";
import { IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { hapticNotify } from "@/lib/telegram";

interface Props {
  view: MyPlayerView;
  onSaved: (view: MyPlayerView) => void;
  onStart: () => void;
}

/** «Тренировка дня»: the free daily run, then extra runs bought for coins or
 * Telegram Stars (up to the daily max set in the admin panel). */
export default function TrainingSection({ view, onSaved, onStart }: Props) {
  const t = view.training;
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [starsBusy, setStarsBusy] = useState(false);
  const maxXp = t.xp_base + t.xp_per_hit * t.max_hits;

  const buyCoins = useMutation({
    mutationFn: buyExtraTraining,
    onSuccess: (next) => { setError(null); hapticNotify("success"); onSaved(next); },
    onError: (err) => setError(formatGameError(err, "Не получилось купить тренировку")),
  });
  const buyStars = async () => {
    setError(null);
    setStarsBusy(true);
    try {
      if ((await payMyPlayerWithStars("training")) === "paid") {
        hapticNotify("success");
        await queryClient.invalidateQueries({ queryKey: ["my-player"] });
      }
    } catch (err) {
      setError(formatGameError(err, "Не получилось оплатить"));
    } finally {
      setStarsBusy(false);
    }
  };

  const status = !t.done_today
    ? `Бесплатная тренировка: до +${maxXp} опыта сверх дневного лимита`
    : t.extra_credits > 0
      ? `Дополнительных тренировок: ${t.extra_credits}`
      : "Бесплатная на сегодня пройдена";
  const canBuy = t.done_today && t.extra_credits === 0 && t.extra_left_today > 0;

  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <span>
          <span className="block font-display text-base font-bold text-ink-chalk">Тренировка дня</span>
          <span className="block text-[11px] text-ink-mist">{status}</span>
        </span>
        <button
          disabled={!t.can_train}
          onClick={onStart}
          className="shrink-0 rounded-xl bg-floodlight px-4 py-2 text-sm font-bold text-bg-base disabled:opacity-40 active:scale-95"
        >
          {t.can_train ? "Начать" : "✓"}
        </button>
      </div>

      {t.done_today && t.extra_max > 0 && (
        <div className="mt-3 rounded-xl bg-bg-raised p-3">
          <p className="text-xs text-ink-mist">
            Ещё тренировка (до +{maxXp} опыта) · сегодня можно купить {t.extra_left_today} из {t.extra_max}
          </p>
          {canBuy && (
            <div className="mt-2 grid grid-cols-2 gap-2">
              {t.extra_coins_price > 0 && (
                <button
                  disabled={buyCoins.isPending}
                  onClick={() => buyCoins.mutate()}
                  className="flex items-center justify-center gap-1 rounded-lg bg-floodlight py-2 text-xs font-bold text-bg-base disabled:opacity-40"
                >
                  <IconCoin size={12} /> {t.extra_coins_price}
                </button>
              )}
              {t.extra_stars_price > 0 && (
                <button
                  disabled={starsBusy}
                  onClick={buyStars}
                  className="rounded-lg bg-amber-400 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
                >
                  ⭐ {t.extra_stars_price}
                </button>
              )}
            </div>
          )}
        </div>
      )}
      {error && <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
    </section>
  );
}
