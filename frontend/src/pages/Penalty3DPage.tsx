import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import { claimPenaltyReward, forfeitPenalty, savePenalty3D, shootPenalty3D, startPenalty3D } from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import ErrorBoundary from "@/components/common/ErrorBoundary";
import GameHero from "@/components/common/GameHero";
import { IconCoin } from "@/components/icons";
import FreeKickScene3D, { type LiveShot } from "@/components/freeKick3d/FreeKickScene3D";
import PenaltyHowTo, { type HowToRole } from "@/components/freeKick3d/PenaltyHowTo";
import SceneCrash from "@/components/freeKick3d/SceneCrash";
import { formatGameError } from "@/lib/errors";
import { useCrashLog } from "@/lib/freeKick3d/crashLog";
import { isSeen, markSeen } from "@/lib/seenSections";
import { crowdChant, crowdHush, crowdTension, playFreeKickSfx, startCrowd } from "@/lib/freeKick3d/sfx";
import { swipeFromPoints, type SwipePoint } from "@/lib/freeKick3d/swipe";
import {
  GOAL_HALF_WIDTH,
  KEEPER_MAX_HAND_Y,
  createPenaltySetup,
  penaltyBotShot,
  playerKeeperSetup,
  quantizeSwipe,
  simulateShot,
  swipeToKick,
  type QuantizedDive,
  type QuantizedSwipe,
  type ShotSetup,
} from "@/lib/freeKick3d/trajectory";
import { audio } from "@/lib/sound";
import { haptic, hapticNotify, showConfirm } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Penalty3DKick, Penalty3DResult, Penalty3DStartResult, UserCard } from "@/types";

type Series = Penalty3DStartResult & { card: UserCard };

/** What the outcome means for the player, by who kicked. */
const VERDICT: Record<Penalty3DKick["kicker"], Record<Penalty3DResult["outcome"], { label: string; good: boolean }>> = {
  player: { goal: { label: "ГОЛ!", good: true }, save: { label: "Сейв", good: false }, miss: { label: "Мимо", good: false } },
  bot: { goal: { label: "Пропустил", good: false }, save: { label: "Отбил!", good: true }, miss: { label: "Мимо!", good: true } },
};

/** A swipe this long (px) is a dive; its direction is where the keeper goes. */
const DIVE_SWIPE_PX = 28;
/** Wait in goal before the bot runs up (ms). */
const BOT_RUNUP_DELAY_MS = 1300;

/** «Пенальти» against the bot, in 3D: five kicks each, then sudden death.
 * You shoot with a swipe (as in the free kick) and keep goal by swiping
 * where to dive at the moment of the strike. Every kick is the server's
 * seed and the server's own replay — the scene only shows it. */
export default function Penalty3DPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [series, setSeries] = useState<Series | null>(null);
  const [kick, setKick] = useState<Penalty3DKick | null>(null);
  const [results, setResults] = useState<Penalty3DResult[]>([]);
  const [finished, setFinished] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [cardSearch, setCardSearch] = useState("");

  const { data: collection } = useQuery({
    queryKey: ["collection", "penalty-3d", cardSearch],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: cardSearch || undefined }),
    enabled: series === null,
  });

  const start = useMutation({
    mutationFn: (card: UserCard) => startPenalty3D(card.id).then((data) => ({ ...data, card })),
    onSuccess: (data) => {
      setSeries(data);
      setKick(data.kick);
      setResults([]);
      setFinished(false);
      setErrorMsg(null);
      void queryClient.invalidateQueries({ queryKey: ["game-limits"] });
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать серию")),
  });

  const claim = useMutation({
    mutationFn: () => claimPenaltyReward(series!.session_id),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
    },
  });

  if (!series || !kick) {
    return (
      <div className="flex flex-col gap-5">
        <GameHero game="penalty" title="Пенальти" />
        <p className="text-sm text-ink-mist">
          Серия пенальти с ботом: по пять ударов, потом до первого промаха. Бьёшь свайпом от мяча к воротам, а на
          воротах свайпаешь, куда прыгать, в момент удара — раньше нельзя, бьющий увидит. Не трогаешь — вратарь стоит в
          центре.
        </p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <CardPickerModal
          open={!start.isPending}
          title="Кто бьёт?"
          cards={collection?.items ?? []}
          onSelect={(card) => start.mutate(card)}
          onClose={() => navigate("/play/penalty")}
          searchValue={cardSearch}
          onSearchChange={setCardSearch}
        />
      </div>
    );
  }

  const last = results[results.length - 1];

  if (finished && last) {
    const won = last.result === "win";
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        <p className={`font-display text-3xl font-bold ${won ? "text-accent-lime" : "text-ink-chalk"}`}>
          {won ? "Победа!" : "Поражение"}
        </p>
        <p className="font-mono text-2xl text-ink-chalk">
          {last.player_score} : {last.bot_score}
        </p>
        <Scoreboard results={results} />
        {last.rating_delta != null && (
          <p className="text-sm text-ink-mist">
            Рейтинг пенальти: {last.rating_delta > 0 ? `+${last.rating_delta}` : last.rating_delta}
          </p>
        )}
        {claim.isPending ? (
          <p className="text-sm text-ink-mist">Начисление награды...</p>
        ) : claim.data ? (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              Ты получил +{claim.data.reward_coins}
              <IconCoin size={16} />
            </p>
          </div>
        ) : claim.isError ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(claim.error, "Не удалось начислить награду")}
          </p>
        ) : null}
        <button
          onClick={() => start.mutate(series.card)}
          disabled={start.isPending}
          className="rounded-2xl bg-accent px-6 py-3 font-semibold text-black disabled:opacity-50"
        >
          {start.isPending ? "Начинаем…" : "Сыграть ещё"}
        </button>
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
    <ShootoutKick
      series={series}
      kick={kick}
      results={results}
      onBack={async () => {
        if (!(await showConfirm("Серия не закончена — выход засчитается поражением. Выйти?"))) return;
        try {
          await forfeitPenalty(series.session_id);
        } catch {
          // Already over or offline: leaving is what matters.
        }
        navigate("/play");
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

/** Five kicks a side (more in sudden death): goal, saved/missed, to come. */
function Scoreboard({ results }: { results: Penalty3DResult[] }) {
  const rows: { label: string; kicker: Penalty3DKick["kicker"] }[] = [
    { label: "Ты", kicker: "player" },
    { label: "Бот", kicker: "bot" },
  ];
  return (
    <div className="flex flex-col gap-1">
      {rows.map(({ label, kicker }) => {
        const mine = results.filter((r) => r.kicker === kicker);
        const slots = Math.max(5, mine.length);
        return (
          <div key={kicker} className="flex items-center gap-1.5">
            <span className="w-8 text-right text-caption text-ink-mist">{label}</span>
            {Array.from({ length: slots }, (_, i) => {
              const r = mine[i];
              const color = !r ? "bg-white/15" : r.outcome === "goal" ? "bg-accent-lime" : "bg-red-400";
              return <span key={i} className={`h-2.5 w-2.5 rounded-full ${color}`} />;
            })}
          </div>
        );
      })}
    </div>
  );
}

/** Screen direction of a dive swipe → the point on the goal plane (mm). The
 * camera is behind the kicker (as in FIFA, for both sides' kicks), so the
 * screen's right is the world's +x. */
function diveTarget(dx: number, dy: number): { x: number; y: number } {
  const len = Math.hypot(dx, dy) || 1;
  const x = Math.max(-GOAL_HALF_WIDTH, Math.min(GOAL_HALF_WIDTH, (dx / len) * 3.1));
  const y = Math.max(0.25, Math.min(KEEPER_MAX_HAND_Y, 1.0 + (-dy / len) * 1.35));
  return { x: Math.round(x * 1000), y: Math.round(y * 1000) };
}

/** One kick of the shootout: the scene, the swipe (a shot or a dive) and the
 * server's verdict. The scene stays mounted from kick to kick. */
function ShootoutKick({
  series,
  kick,
  results,
  onBack,
  onResult,
  onNext,
}: {
  series: Series;
  kick: Penalty3DKick;
  results: Penalty3DResult[];
  onBack: () => void;
  onResult: (r: Penalty3DResult) => void;
  onNext: (r: Penalty3DResult) => void;
}) {
  const keeping = kick.kicker === "bot";
  const [dive, setDive] = useState<QuantizedDive | null>(null);
  const setup: ShotSetup = useMemo(
    () => (keeping ? playerKeeperSetup(kick.seed, dive) : createPenaltySetup(kick.seed, series.rating)),
    [keeping, kick.seed, dive, series.rating],
  );
  const [shot, setShot] = useState<LiveShot | null>(null);
  // Who kicked the shot on screen: the crowd reacts to that, never to the
  // next kick's side (they differ for a render when moving to the next kick).
  const [shotKicker, setShotKicker] = useState<Penalty3DKick["kicker"] | null>(null);
  const [shown, setShown] = useState(false);
  const [trail, setTrail] = useState<SwipePoint[]>([]);
  const [ready, setReady] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const onReady = useCallback(() => setReady(true), []);
  const points = useRef<SwipePoint[]>([]);
  const fpsRef = useRef<HTMLSpanElement | null>(null);
  const shotClock = useRef(-1);
  const crashLog = useCrashLog();
  const shotId = kick.kick_index + 1;
  const role: HowToRole = keeping ? "keep" : "shoot";
  // The first time in each role the how-to opens by itself; «?» reopens it.
  const [howTo, setHowTo] = useState<HowToRole | null>(null);
  useEffect(() => {
    if (ready && !isSeen(`penalty3d-howto-${role}`)) setHowTo(role);
  }, [ready, role]);
  const closeHowTo = () => {
    markSeen(`penalty3d-howto-${role}`);
    setHowTo(null);
  };
  const paused = howTo !== null;
  // «Прыгай!» from the strike until the player dives (or it's over).
  const [struck, setStruck] = useState(false);

  const answer = useMutation({
    mutationFn: (payload: { q: QuantizedSwipe } | { dive: QuantizedDive | null }) =>
      "q" in payload ? shootPenalty3D(series.session_id, payload.q) : savePenalty3D(series.session_id, payload.dive),
    onSuccess: onResult,
    onError: (err) => setErrorMsg(formatGameError(err, "Удар не засчитан — попробуй ещё раз")),
  });
  const verdict = answer.data;

  // A fresh kick: clean slate; the bot runs up on its own after a moment.
  useEffect(() => {
    setShot(null);
    setShotKicker(null);
    setShown(false);
    setDive(null);
    setErrorMsg(null);
    answer.reset();
    if (!keeping || !ready || paused) return;
    const timer = window.setTimeout(() => {
      const s0 = playerKeeperSetup(kick.seed, null);
      const bot = penaltyBotShot(kick.seed, null);
      const k = swipeToKick(s0, bot.swipe);
      setShot({ id: shotId, kick: k, trajectory: simulateShot(s0, k) });
      setShotKicker("bot");
      crowdTension(true);
    }, BOT_RUNUP_DELAY_MS);
    return () => window.clearTimeout(timer);
    // `answer` is a fresh object every render; only a new kick resets.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kick.seed, keeping, ready, paused]);

  // The crowd: humming all series long, a chant before each of the player's kicks.
  useEffect(() => startCrowd(), []);
  useEffect(() => {
    if (ready && !keeping) crowdChant();
  }, [ready, keeping, kick.seed]);

  const onDecided = useCallback(() => setShown(true), []);

  // The bot's kick needs no answer from the player's side to be decided: once
  // it's over, the dive (or none) goes to the server.
  useEffect(() => {
    if (shown && keeping && !answer.isPending && !answer.data && !answer.isError) answer.mutate({ dive });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown, keeping]);

  const replayed = shown && shot ? shot.trajectory.outcome : null;
  useEffect(() => {
    if (!replayed || !shotKicker) return;
    crowdHush();
    crowdTension(false);
    const good = shotKicker === "bot" ? replayed !== "goal" : replayed === "goal";
    hapticNotify(good ? "success" : "error");
    playFreeKickSfx(good ? "roar" : "groan");
  }, [replayed, shotKicker]);

  const aiming = ready && !paused && !keeping && shot === null;
  const diving = keeping && shot !== null && !shown && dive === null;

  useEffect(() => {
    if (!diving) {
      setStruck(false);
      return;
    }
    let frame = requestAnimationFrame(function tick() {
      setStruck(shotClock.current >= 0);
      frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [diving]);

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!aiming && !diving) return;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Not every WebView lets a pointer be captured; the swipe still works.
    }
    points.current = [{ x: e.clientX, y: e.clientY, t: e.timeStamp }];
    if (aiming) setTrail(points.current);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (points.current.length === 0) return;
    if (diving) {
      const p0 = points.current[0];
      const dx = e.clientX - p0.x;
      const dy = e.clientY - p0.y;
      if (Math.hypot(dx, dy) < DIVE_SWIPE_PX) return;
      // The dive starts the moment the swipe's direction is clear.
      points.current = [];
      const d = { ...diveTarget(dx, dy), reactionMs: Math.round(shotClock.current * 1000) };
      haptic("medium");
      setDive(d);
      const s1 = playerKeeperSetup(kick.seed, d);
      const bot = penaltyBotShot(kick.seed, d);
      const k = swipeToKick(s1, bot.swipe);
      // Same shot id: the clock keeps running, only the keeper (and, for an
      // early dive, the kicker's aim) changes.
      setShot({ id: shotId, kick: k, trajectory: simulateShot(s1, k) });
      return;
    }
    if (!aiming) return;
    points.current = [...points.current, { x: e.clientX, y: e.clientY, t: e.timeStamp }];
    setTrail(points.current);
  };
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!aiming || points.current.length === 0) {
      points.current = [];
      return;
    }
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
    setShot({ id: shotId, kick: k, trajectory: simulateShot(setup, k) });
    setShotKicker("player");
    answer.mutate({ q });
  };

  const outcome = shown && verdict ? verdict.outcome : null;
  const meaning = outcome ? VERDICT[kick.kicker][outcome] : null;
  const score = results.length ? results[results.length - 1] : null;
  const round = Math.floor(kick.kick_index / 2) + 1;

  return (
    <div className="fixed inset-0 z-50 select-none overflow-hidden bg-bg-base text-ink-chalk">
      <ErrorBoundary fallback={(error, retry) => <SceneCrash error={error} retry={retry} log={crashLog.current} />}>
        <FreeKickScene3D
          setup={setup}
          shot={shot}
          onDecided={onDecided}
          onReady={onReady}
          fpsRef={fpsRef}
          cheerGoals={!keeping}
          kickerKit={keeping ? "away" : "home"}
          kickerCelebration={!keeping && series.celebration === "cel_silly" ? "silly_dance" : "celebrate"}
          shotClockRef={shotClock}
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
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onBack}
            className="pointer-events-auto rounded-full bg-bg-surface/80 px-3 py-1.5 text-sm font-semibold"
          >
            ← Выйти
          </button>
          {(aiming || (keeping && !shot)) && (
            <button
              type="button"
              onClick={() => setHowTo(role)}
              aria-label={keeping ? "Как отбивать" : "Как бить"}
              className="pointer-events-auto h-8 w-8 rounded-full bg-bg-surface/80 text-sm font-bold"
            >
              ?
            </button>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="font-display text-sm">
            {kick.kick_index >= 10 ? "Внезапная смерть" : `Раунд ${round} / 5`} · {score?.player_score ?? 0} :{" "}
            {score?.bot_score ?? 0}
          </div>
          <Scoreboard results={results} />
          <span ref={fpsRef} className="hidden" />
        </div>
      </div>

      {ready && !paused && !outcome && (aiming || (keeping && !shot) || diving) && (
        <div className="pointer-events-none absolute inset-x-0 top-28 px-6 text-center text-sm text-ink-chalk/90 drop-shadow">
          {keeping
            ? "Ты на воротах. В момент удара свайпни, куда прыгать. Не трогаешь — вратарь стоит в центре."
            : `Твой удар (${series.card.player.display_name}). Свайпни от мяча к воротам: в угол — надёжнее, длиннее — выше.`}
          {errorMsg && <div className="mt-2 text-red-300">{errorMsg}</div>}
        </div>
      )}
      {struck && (
        <div className="pointer-events-none absolute inset-x-0 top-1/3 text-center font-display text-4xl text-accent-lime drop-shadow">
          Прыгай!
        </div>
      )}
      {howTo && <PenaltyHowTo role={howTo} onClose={closeHowTo} />}
      {!ready && (
        <div className="pointer-events-none absolute inset-x-0 top-28 text-center text-sm text-ink-chalk/90">Загружаем…</div>
      )}

      {shown && !verdict && answer.isPending && (
        <div className="absolute inset-x-0 bottom-10 text-center text-sm text-ink-mist">Судья смотрит повтор…</div>
      )}
      {shown && answer.isError && (
        <div className="absolute inset-x-0 bottom-10 flex flex-col items-center gap-2 px-6 text-center text-sm text-red-300">
          {errorMsg}
          <button
            type="button"
            onClick={() => (keeping ? answer.mutate({ dive }) : setShot(null))}
            className="rounded-xl bg-bg-surface px-4 py-2 font-semibold text-ink-chalk"
          >
            Повторить
          </button>
        </div>
      )}

      {meaning && verdict && (
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-2 bg-gradient-to-t from-bg-base/90 to-transparent p-6 pb-10 pt-16">
          <div className={`font-display text-4xl drop-shadow ${meaning.good ? "text-accent-lime" : "text-ink-mist"}`}>
            {meaning.label}
          </div>
          <div className="font-mono text-lg text-ink-chalk">
            {verdict.player_score} : {verdict.bot_score}
          </div>
          <button
            type="button"
            onClick={() => onNext(verdict)}
            className="mt-1 rounded-xl bg-accent px-6 py-3 font-semibold text-black"
          >
            {verdict.is_finished ? "Итоги серии" : verdict.next_kick?.kicker === "bot" ? "На ворота" : "Бить"}
          </button>
        </div>
      )}
    </div>
  );
}
