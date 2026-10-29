import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import {
  claimFreeKickReward,
  createFreeKickRefillInvoice,
  fetchFreeKickRefill,
  refillFreeKickWithCoins,
  shootFreeKick3D,
  startFreeKick3D,
} from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import ErrorBoundary from "@/components/common/ErrorBoundary";
import GameHero from "@/components/common/GameHero";
import { IconCoin } from "@/components/icons";
import FreeKickScene3D, { type LiveShot } from "@/components/freeKick3d/FreeKickScene3D";
import SceneCrash from "@/components/freeKick3d/SceneCrash";
import { formatGameError } from "@/lib/errors";
import { useCrashLog } from "@/lib/freeKick3d/crashLog";
import { crowdChant, crowdHush, crowdTension, playFreeKickSfx, startCrowd } from "@/lib/freeKick3d/sfx";
import { swipeFromPoints, type SwipePoint } from "@/lib/freeKick3d/swipe";
import {
  GOAL_HALF_WIDTH,
  GOAL_HEIGHT,
  createSetup,
  quantizeSwipe,
  simulateShot,
  swipeToKick,
  type QuantizedSwipe,
  type ShotOutcome,
} from "@/lib/freeKick3d/trajectory";
import { payShopWithStars } from "@/lib/shopStars";
import { audio } from "@/lib/sound";
import { haptic, hapticNotify, showConfirm } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { FreeKick3DKick, FreeKick3DShotResult, FreeKick3DStartResult, UserCard } from "@/types";

const OUTCOME: Record<ShotOutcome, { label: string; className: string }> = {
  goal: { label: "ГОЛ!", className: "text-accent-lime" },
  save: { label: "Сейв", className: "text-accent-cyan" },
  miss: { label: "Мимо", className: "text-ink-mist" },
  wall: { label: "В стенку", className: "text-ink-mist" },
};

const BONUS: Record<FreeKick3DShotResult["bonuses"][number], string> = {
  corner: "в угол",
  curl: "с закруткой",
};

type Series = FreeKick3DStartResult & { card: UserCard };

/** «Штрафной удар» in 3D: pick a card, then a series of free kicks from
 * server-chosen positions. Each swipe is simulated here for the show and
 * replayed on the server (same engine, same integers), which alone decides
 * the outcome and the coins. */
export default function FreeKick3DPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [series, setSeries] = useState<Series | null>(null);
  const [kick, setKick] = useState<FreeKick3DKick | null>(null);
  const [results, setResults] = useState<FreeKick3DShotResult[]>([]);
  const [finished, setFinished] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [cardSearch, setCardSearch] = useState("");

  const { data: collection } = useQuery({
    queryKey: ["collection", "free-kick", cardSearch],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: cardSearch || undefined }),
    enabled: series === null,
  });

  const start = useMutation({
    mutationFn: (card: UserCard) => startFreeKick3D(card.id).then((data) => ({ ...data, card })),
    onSuccess: (data) => {
      setSeries(data);
      setKick(data.kick);
      setResults([]);
      setFinished(false);
      setErrorMsg(null);
      void queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      void queryClient.invalidateQueries({ queryKey: ["free-kick-refill"] });
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать серию")),
  });

  const claim = useMutation({
    mutationFn: () => claimFreeKickReward(series!.session_id),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
    },
  });

  // On cooldown the card picker waits: the screen offers a refill instead.
  const { data: refill, isPending: refillLoading } = useQuery({
    queryKey: ["free-kick-refill"],
    queryFn: fetchFreeKickRefill,
    enabled: !series || finished,
    refetchInterval: 30_000,
  });

  if (!series || !kick) {
    return (
      <div className="flex flex-col gap-5">
        <GameHero game="free-kick" title="Штрафной удар" />
        <p className="text-sm text-ink-mist">
          Серия штрафных с разных позиций. Свайпни от мяча к воротам: быстрее — сильнее, длиннее — выше, дугой —
          закрутка. Чем выше рейтинг игрока, тем чуть сильнее удар и закрутка.
        </p>
        {errorMsg && !refill?.on_cooldown && (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>
        )}
        {refill?.on_cooldown && (
          <>
            <NextSeries onPlay={() => setErrorMsg(null)} />
            <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
              К играм
            </button>
          </>
        )}
        <CardPickerModal
          open={!start.isPending && !refillLoading && !refill?.on_cooldown}
          title="Кто бьёт?"
          cards={collection?.items ?? []}
          onSelect={(card) => start.mutate(card)}
          onClose={() => navigate("/play")}
          searchValue={cardSearch}
          onSearchChange={setCardSearch}
        />
      </div>
    );
  }

  const total = results.length ? results[results.length - 1].total_coins : 0;

  if (finished) {
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        <p className="font-display text-2xl font-bold text-ink-chalk">Серия завершена</p>
        <div className="flex flex-wrap justify-center gap-2">
          {results.map((r, i) => (
            <span key={i} className={`rounded-lg bg-bg-surface px-2 py-1 text-xs font-semibold ${OUTCOME[r.outcome].className}`}>
              {OUTCOME[r.outcome].label}
            </span>
          ))}
        </div>
        <p className="text-sm text-ink-mist">
          Голов: {results.filter((r) => r.outcome === "goal").length} из {results.length} · Итог:{" "}
          <span className="inline-flex items-center gap-1 font-mono font-bold text-accent-lime">
            {total}
            <IconCoin size={14} />
          </span>
        </p>
        {claim.isPending ? (
          <p className="text-sm text-ink-mist">Начисление награды...</p>
        ) : claim.data ? (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              Ты получил +{claim.data.reward_coins}
              <IconCoin size={16} />
            </p>
            {claim.data.reward_coins === 0 && total > 0 && (
              <p className="mt-1 text-xs text-ink-mist">Лимит наградных серий на сегодня исчерпан</p>
            )}
          </div>
        ) : claim.isError ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(claim.error, "Не удалось начислить награду")}
          </p>
        ) : null}
        <NextSeries onPlay={() => start.mutate(series.card)} starting={start.isPending} />
        {start.isError && (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(start.error, "Не удалось начать серию")}
          </p>
        )}
        <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
          Вернуться к играм
        </button>
      </div>
    );
  }

  return (
    <SeriesKick
      series={series}
      kick={kick}
      total={total}
      streak={results.length ? results[results.length - 1].streak : series.streak}
      onBack={async () => {
        if (await showConfirm("Серия не закончена — оставшиеся удары сгорят. Выйти?")) navigate("/play");
      }}
      onResult={(r) => setResults((prev) => [...prev, r])}
      onNext={(r) => {
        if (r.next_kick) setKick(r.next_kick);
        else {
          setFinished(true);
          claim.mutate();
        }
      }}
    />
  );
}

/** What's next after a series (and on the start screen while on cooldown):
 * play again when a series is available, otherwise buy one now — the day's
 * first for coins, the rest for Telegram Stars, up to the daily cap. */
function NextSeries({ onPlay, starting = false }: { onPlay: () => void; starting?: boolean }) {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [error, setError] = useState<string | null>(null);
  const { data: refill } = useQuery({ queryKey: ["free-kick-refill"], queryFn: fetchFreeKickRefill, refetchInterval: 30_000 });
  const refreshed = async () => {
    hapticNotify("success");
    setError(null);
    await queryClient.invalidateQueries({ queryKey: ["free-kick-refill"] });
    void queryClient.invalidateQueries({ queryKey: ["game-limits"] });
    onPlay();
  };
  const coins = useMutation({
    mutationFn: refillFreeKickWithCoins,
    onSuccess: async (data) => {
      if (data.new_balance != null) updateBalance(data.new_balance);
      await refreshed();
    },
    onError: (err) => setError(formatGameError(err, "Не получилось обновить серию")),
  });
  const stars = useMutation({
    mutationFn: () => payShopWithStars(createFreeKickRefillInvoice),
    onSuccess: async (result) => {
      if (result === "paid") await refreshed();
    },
    onError: (err) => setError(formatGameError(err, "Оплата не прошла")),
  });

  if (!refill) return null;
  if (!refill.on_cooldown) {
    return (
      <button
        onClick={onPlay}
        disabled={starting}
        className="rounded-2xl bg-accent px-6 py-3 font-semibold text-black disabled:opacity-50"
      >
        {starting ? "Начинаем…" : "Сыграть ещё серию"}
      </button>
    );
  }
  const minutes = Math.max(1, Math.ceil(refill.retry_after_seconds / 60));
  const left = refill.daily_limit - refill.refills_today;
  const busy = coins.isPending || stars.isPending;
  return (
    <div className="flex w-full max-w-xs flex-col items-center gap-2 rounded-2xl bg-bg-surface p-4">
      <p className="text-sm text-ink-mist">Следующая серия через {minutes} мин</p>
      {refill.can_refill ? (
        <>
          <button
            onClick={() => (refill.price_coins != null ? coins.mutate() : stars.mutate())}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-2xl bg-accent px-5 py-3 font-semibold text-black disabled:opacity-50"
          >
            {busy ? (
              "Обновляем…"
            ) : refill.price_coins != null ? (
              <>
                Ещё серия сразу — {refill.price_coins}
                <IconCoin size={15} />
              </>
            ) : (
              <>Ещё серия сразу — ⭐ {refill.price_stars}</>
            )}
          </button>
          <p className="text-caption text-ink-mist">
            Обновлений сегодня: осталось {left} из {refill.daily_limit}
          </p>
        </>
      ) : (
        <p className="text-caption text-ink-mist">Обновления серии на сегодня закончились</p>
      )}
      {error && <p className="text-caption text-red-400">{error}</p>}
    </div>
  );
}

/** The next goal-in-a-row count that pays the «Серия без промахов» bonus:
 * 3, 5, 10, then every 10th (as the server's free_kick_service.streak_bonus). */
function nextStreakMilestone(streak: number): number {
  if (streak < 3) return 3;
  if (streak < 5) return 5;
  return (Math.floor(streak / 10) + 1) * 10;
}

/** One kick of the series: the 3D scene, the swipe, the server's verdict. */
function SeriesKick({
  series,
  kick,
  total,
  streak,
  onBack,
  onResult,
  onNext,
}: {
  series: Series;
  kick: FreeKick3DKick;
  total: number;
  /** Goals in a row before this kick. */
  streak: number;
  onBack: () => void;
  onResult: (r: FreeKick3DShotResult) => void;
  onNext: (r: FreeKick3DShotResult) => void;
}) {
  const setup = useMemo(() => createSetup(kick.seed, series.rating), [kick.seed, series.rating]);
  const [shot, setShot] = useState<LiveShot | null>(null);
  const [shown, setShown] = useState(false);
  const [trail, setTrail] = useState<SwipePoint[]>([]);
  const [ready, setReady] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const onReady = useCallback(() => setReady(true), []);
  const points = useRef<SwipePoint[]>([]);
  const fpsRef = useRef<HTMLSpanElement | null>(null);
  const crashLog = useCrashLog();

  const shoot = useMutation({
    mutationFn: (q: QuantizedSwipe) => shootFreeKick3D(series.session_id, q),
    onSuccess: onResult,
    onError: (err) => {
      // The kick wasn't taken: let the player swipe it again.
      setErrorMsg(formatGameError(err, "Удар не засчитан — попробуй ещё раз"));
      setShot(null);
      setShown(false);
    },
  });
  const verdict = shoot.data;
  // The replay and the server agree (same engine); the server's word is final.
  const outcome: ShotOutcome | null = shown && verdict ? verdict.outcome : null;

  // The crowd: humming all series long, a chant at each new position.
  useEffect(() => startCrowd(), []);
  useEffect(() => {
    if (ready) crowdChant();
  }, [ready, kick.seed]);

  // The crowd reacts the instant the ball decides it — on the local replay,
  // which is the server's own computation; no waiting for its answer.
  const replayed: ShotOutcome | null = shown && shot ? shot.trajectory.outcome : null;
  const endBall = shot?.trajectory.end.position;
  const offWoodwork = !!shot?.trajectory.events.some((e) => e.type === "post");
  useEffect(() => {
    if (!replayed) return;
    crowdHush();
    crowdTension(false);
    hapticNotify(replayed === "goal" ? "success" : replayed === "save" ? "warning" : "error");
    // Into the stands: the crowd laughs rather than groans (but off the
    // woodwork it's a near thing, whatever the ball does afterwards).
    const wild =
      !offWoodwork && !!endBall && (Math.abs(endBall.x) > GOAL_HALF_WIDTH + 4 || endBall.y > GOAL_HEIGHT + 3);
    playFreeKickSfx(replayed === "goal" ? "roar" : wild ? "laugh" : "groan");
  }, [replayed, endBall, offWoodwork]);

  const onDecided = useCallback(() => setShown(true), []);
  const aiming = ready && shot === null;

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!aiming) return;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Not every WebView lets a pointer be captured; the swipe still works.
    }
    points.current = [{ x: e.clientX, y: e.clientY, t: e.timeStamp }];
    setTrail(points.current);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!aiming || points.current.length === 0) return;
    points.current = [...points.current, { x: e.clientX, y: e.clientY, t: e.timeStamp }];
    setTrail(points.current);
  };
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!aiming || points.current.length === 0) return;
    const pts = [...points.current, { x: e.clientX, y: e.clientY, t: e.timeStamp }];
    points.current = [];
    const swipe = swipeFromPoints(pts, window.innerHeight);
    const q = swipe ? quantizeSwipe(swipe) : null;
    setTrail([]);
    if (!q || q.dy >= 0) return;
    const k = swipeToKick(setup, q);
    haptic("medium");
    audio(); // resume the audio context inside the gesture (mobile autoplay rules)
    crowdTension(true);
    setErrorMsg(null);
    setShot({ id: kick.kick_index + 1, kick: k, trajectory: simulateShot(setup, k) });
    shoot.mutate(q);
  };

  const speedKmh = shot ? Math.round(Math.hypot(shot.kick.velocity.x, shot.kick.velocity.y, shot.kick.velocity.z) * 3.6) : 0;
  const distance = Math.round(Math.hypot(setup.ball.x, setup.ball.z));
  const isLast = kick.kick_index + 1 >= series.total_kicks;

  return (
    <div className="fixed inset-0 z-50 select-none overflow-hidden bg-bg-base text-ink-chalk">
      {/* A 3D failure (WebGL) restarts the scene, not the app. */}
      <ErrorBoundary fallback={(error, retry) => <SceneCrash error={error} retry={retry} log={crashLog.current} />}>
        <FreeKickScene3D
          setup={setup}
          shot={shot}
          onDecided={onDecided}
          onReady={onReady}
          fpsRef={fpsRef}
          kickerCelebration={series.celebration === "cel_silly" ? "silly_dance" : "celebrate"}
          gear={{ ball: series.ball, kickerBoots: series.boots }}
        />
      </ErrorBoundary>

      {/* Swipe surface over the canvas. */}
      <div
        className="absolute inset-0"
        style={{ touchAction: "none" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          points.current = [];
          setTrail([]);
        }}
      >
        {trail.length > 1 && (
          <svg className="pointer-events-none absolute inset-0 h-full w-full">
            <polyline
              points={trail.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke="rgba(198,230,58,0.85)"
              strokeWidth={6}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </div>

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-4">
        <button
          type="button"
          onClick={onBack}
          className="pointer-events-auto rounded-full bg-bg-surface/80 px-3 py-1.5 text-sm font-semibold"
        >
          ← Выйти
        </button>
        <div className="text-right">
          <div className="font-display text-sm">
            Удар {kick.kick_index + 1} / {series.total_kicks}
          </div>
          <div className="flex items-center justify-end gap-1 text-caption text-ink-mist">
            {series.card.player.display_name} · {series.rating} · {distance} м ·
            <span className="inline-flex items-center gap-0.5 font-mono text-accent-lime">
              {total}
              <IconCoin size={11} />
            </span>
          </div>
          {streak > 0 && (
            <div className="mt-1 inline-flex rounded-full bg-orange-500/20 px-2 py-0.5 text-caption font-semibold text-orange-300">
              🔥 {streak} подряд · бонус через {nextStreakMilestone(streak) - streak}
            </div>
          )}
          <span ref={fpsRef} className="hidden" />
        </div>
      </div>

      {(aiming || !ready) && (
        <div className="pointer-events-none absolute inset-x-0 top-20 px-6 text-center text-sm text-ink-chalk/90 drop-shadow">
          {ready ? "Свайпни от мяча к воротам. Быстрее — сильнее, длиннее — выше, дугой — закрутка." : "Загружаем…"}
          {errorMsg && <div className="mt-2 text-red-300">{errorMsg}</div>}
        </div>
      )}

      {shown && !verdict && shoot.isPending && (
        <div className="absolute inset-x-0 bottom-10 text-center text-sm text-ink-mist">Судья смотрит повтор…</div>
      )}

      {outcome && verdict && (
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-2 bg-gradient-to-t from-bg-base/90 to-transparent p-6 pb-10 pt-16">
          <div className={`font-display text-4xl drop-shadow ${OUTCOME[outcome].className}`}>{OUTCOME[outcome].label}</div>
          <div className="text-caption text-ink-chalk/80">
            {speedKmh} км/ч{verdict.bonuses.length > 0 && ` · ${verdict.bonuses.map((b) => BONUS[b]).join(", ")}`}
          </div>
          {verdict.streak_bonus > 0 && (
            <div className="rounded-full bg-orange-500/20 px-3 py-1 text-sm font-semibold text-orange-300">
              🔥 {verdict.streak} голов подряд! +{verdict.streak_bonus}
            </div>
          )}
          {verdict.coins_this_kick > 0 && (
            <div className="flex items-center gap-1 font-mono text-lg font-bold text-accent-lime">
              +{verdict.coins_this_kick}
              <IconCoin size={16} />
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              // Same scene, next position: no WebGL context churn between kicks.
              setShot(null);
              setShown(false);
              shoot.reset();
              onNext(verdict);
            }}
            className="mt-1 rounded-xl bg-accent px-6 py-3 font-semibold text-black">
            {isLast ? "Итоги серии" : "Следующий удар"}
          </button>
        </div>
      )}
    </div>
  );
}
