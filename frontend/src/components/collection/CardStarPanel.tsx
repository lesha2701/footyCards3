import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { claimCardStar, feedCardStars, fetchCardStars } from "@/api/collection";
import { IconCoin } from "@/components/icons";
import { invalidateAfterSkillChange } from "@/lib/cardSkills";
import { previewStarFeed, starString } from "@/lib/cardStars";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

/** «Звёзды» block of the card detail modal: duplicates of the same player
 * banked into THIS copy («копилка»), stars claimed for coins. Every number
 * comes from the server (GET .../stars); the confirmation only previews
 * what the server will do with them. */
export default function CardStarPanel({ cardId, isDiamond }: { cardId: number; isDiamond: boolean }) {
  const queryClient = useQueryClient();
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: state } = useQuery({
    queryKey: ["card-stars", cardId],
    queryFn: () => fetchCardStars(cardId),
    enabled: !isDiamond,
  });

  const onDone = (newBalance: number) => {
    hapticNotify("success");
    updateBalance(newBalance);
    setConfirming(false);
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["card-stars"] });
    invalidateAfterSkillChange(queryClient);
  };
  const onFail = (err: unknown) => {
    hapticNotify("error");
    setConfirming(false);
    setError(formatGameError(err, "Не удалось обновить звёзды"));
    queryClient.invalidateQueries({ queryKey: ["card-stars", cardId] });
  };
  const feedMutation = useMutation({
    mutationFn: () => feedCardStars(cardId, { all_free: true, idempotency_key: crypto.randomUUID() }),
    onSuccess: (data) => onDone(data.new_balance),
    onError: onFail,
  });
  const claimMutation = useMutation({
    mutationFn: () => claimCardStar(cardId, crypto.randomUUID()),
    onSuccess: (data) => onDone(data.new_balance),
    onError: onFail,
  });

  if (isDiamond || !state || state.max_stars === 0) return null;
  // Off and never used on this copy: nothing to show.
  if (!state.enabled && state.stars === 0 && state.progress === 0) return null;

  const atMax = state.stars >= state.max_stars;
  const freePlain = state.free_duplicates.filter((d) => !d.skill_code).length;
  const freeSkilled = state.free_duplicates.length - freePlain;
  const preview = previewStarFeed(state, freePlain, balance);
  const busy = feedMutation.isPending || claimMutation.isPending;

  return (
    <section className="mt-3 rounded-2xl bg-black/20 p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-ink-chalk">Звёзды</p>
        <span className="font-mono text-sm tracking-wider text-amber-300" aria-label={`Звёзд: ${state.stars} из ${state.max_stars}`}>
          {starString(state.stars, state.max_stars)}
        </span>
      </div>

      {atMax ? (
        <p className="mt-1 text-[11px] text-ink-mist">Максимум звёзд: +{state.rating_bonus} к рейтингу</p>
      ) : (
        <>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-amber-300"
              style={{ width: `${Math.min(100, (100 * state.progress) / (state.next_threshold ?? 1))}%` }}
            />
          </div>
          <p className="mt-1.5 text-[11px] text-ink-mist">
            Копилка: <b className="font-mono text-ink-chalk">{state.progress}/{state.next_threshold}</b> дублей до ★{state.stars + 1}
            {state.rating_after_next_star != null && (
              <> · рейтинг <b className="font-mono text-accent-cyan">{state.rating_now} → {state.rating_after_next_star}</b></>
            )}
          </p>
          <p className="mt-0.5 flex items-center gap-1 text-[11px] text-ink-mist">
            Звезда стоит <IconCoin size={11} /> {state.next_coin_cost}
            {freeSkilled > 0 && <span className="text-ink-mist-dim"> · копии с навыком не вкладываются</span>}
          </p>
        </>
      )}

      {state.block_reason && !atMax && <p className="mt-1.5 text-[11px] text-amber-300/90">{state.block_reason}</p>}
      {error && <p className="mt-1.5 rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">{error}</p>}

      {!state.block_reason && state.claimable && (
        <button
          onClick={() => claimMutation.mutate()}
          disabled={busy || balance < (state.next_coin_cost ?? 0)}
          className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl bg-amber-300/15 py-2 text-xs font-semibold text-amber-300 disabled:opacity-40"
        >
          Забрать ★{state.stars + 1} за <IconCoin size={12} /> {state.next_coin_cost}
        </button>
      )}

      {!state.block_reason && preview.consumed > 0 && !confirming && (
        <button
          onClick={() => setConfirming(true)}
          disabled={busy}
          className="mt-2 w-full rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-chalk disabled:opacity-40"
        >
          Вложить все дубли ({preview.consumed})
        </button>
      )}
      {!state.block_reason && freePlain === 0 && !state.claimable && !atMax && (
        <p className="mt-1.5 text-[11px] text-ink-mist-dim">Свободных дублей этого игрока пока нет</p>
      )}

      {confirming && (
        <div className="mt-2 rounded-xl bg-white/5 p-2.5 text-[11px] text-ink-mist">
          <p>
            −{preview.consumed} дубл{preview.consumed === 1 ? "ь" : "ей"}
            {preview.starsGained > 0 && <>, <b className="text-amber-300">+{preview.starsGained} ★</b></>}
            {preview.coinsSpent > 0 && <>, −{preview.coinsSpent} монет</>}
          </p>
          <p className="mt-0.5">
            {preview.stars >= state.max_stars
              ? "Будет максимум звёзд"
              : `Потом в копилке ${preview.progress}/${state.thresholds[preview.stars]} до ★${preview.stars + 1}`}
            {preview.waitingForCoins && " — звезду заберёшь, когда хватит монет"}
          </p>
          <p className="mt-0.5 text-ink-mist-dim">Вложенные дубли исчезнут, вернуть их нельзя.</p>
          <div className="mt-2 flex gap-2">
            <button onClick={() => setConfirming(false)} className="flex-1 rounded-lg bg-white/5 py-1.5 font-semibold text-ink-mist">
              Отмена
            </button>
            <button
              onClick={() => feedMutation.mutate()}
              disabled={busy}
              className="flex-1 rounded-lg bg-amber-300 py-1.5 font-semibold text-bg-base disabled:opacity-50"
            >
              {feedMutation.isPending ? "Вкладываем..." : "Вложить"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
