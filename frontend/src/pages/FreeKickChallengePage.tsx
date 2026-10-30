import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { useNavigate } from "react-router-dom";

import { fetchFreeKickChallenge, shootFreeKickChallenge, startFreeKickChallenge } from "@/api/games";
import ErrorBoundary from "@/components/common/ErrorBoundary";
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
} from "@/lib/freeKick3d/trajectory";
import { audio } from "@/lib/sound";
import { haptic, hapticNotify, showConfirm } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { FreeKick3DKick, FreeKickChallenge, FreeKickChallengeShot, FreeKickChallengeStart, FreeKickTarget } from "@/types";

/** «Испытание дня» in the 3D free kick: the same positions and a target in
 * the goal for everyone today, one attempt; points by how close to the
 * target's centre, coins per target hit, the day's leaderboard. The server
 * replays every swipe (same engine as the series) and alone scores it. */
export default function FreeKickChallengePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [attempt, setAttempt] = useState<FreeKickChallengeStart | null>(null);
  const [kick, setKick] = useState<FreeKick3DKick | null>(null);
  const [last, setLast] = useState<FreeKickChallengeShot | null>(null);
  const [finished, setFinished] = useState<FreeKickChallengeShot | null>(null);

  const board = useQuery({ queryKey: ["free-kick-challenge"], queryFn: fetchFreeKickChallenge, enabled: attempt === null || !!finished });

  const start = useMutation({
    mutationFn: startFreeKickChallenge,
    onSuccess: (data) => {
      setAttempt(data);
      setKick(data.kick);
      setLast(null);
      setFinished(null);
    },
  });

  if (attempt && kick && !finished) {
    return (
      <ChallengeKick
        attempt={attempt}
        kick={kick}
        score={last?.score ?? attempt.score}
        hits={last?.hits ?? attempt.hits}
        onBack={async () => {
          if (await showConfirm("Выйти? Попытка сохранится — сможешь продолжить сегодня с этого удара.")) navigate("/play");
        }}
        onNext={(r) => {
          setLast(r);
          if (r.next_kick) setKick(r.next_kick);
          else {
            setFinished(r);
            if (r.new_balance != null) updateBalance(r.new_balance);
            hapticNotify("success");
            void queryClient.invalidateQueries({ queryKey: ["free-kick-challenge"] });
          }
        }}
      />
    );
  }

  const data = board.data;
  const my = data?.my;
  const canPlay = !my || !my.finished;
  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-2xl bg-gradient-to-br from-blue-600/40 to-bg-surface p-4">
        <p className="font-display text-xl font-bold text-ink-chalk">🎯 Испытание дня</p>
        <p className="mt-1 text-sm text-ink-mist">
          {data?.total_kicks ?? 5} штрафных — у всех одни и те же позиции и мишени. Попади в мишень: чем ближе к центру,
          тем больше очков (до 100), просто гол — 10. Одна попытка в день.
        </p>
        {data && (
          <p className="mt-2 text-sm text-ink-chalk">
            За каждую мишень +{data.coins_per_hit} <IconCoin size={13} className="inline" />, за все {data.total_kicks} ещё +
            {data.perfect_bonus} <IconCoin size={13} className="inline" />
          </p>
        )}
      </div>

      {finished && (
        <div className="rounded-2xl bg-accent-green/10 p-4 text-center">
          <p className="font-display text-2xl font-bold text-accent-lime">{finished.score} очков</p>
          <p className="text-sm text-ink-mist">
            Мишеней: {finished.hits} из {attempt?.total_kicks ?? 5}
            {finished.rank != null && ` · место ${finished.rank}`}
          </p>
          {finished.reward_coins > 0 && (
            <p className="mt-1 flex items-center justify-center gap-1 font-mono text-lg font-bold text-accent-green">
              +{finished.reward_coins}
              <IconCoin size={16} />
            </p>
          )}
        </div>
      )}

      {my && !finished && (
        <p className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk">
          {my.finished
            ? `Сегодня ты набрал ${my.score} очков (мишеней ${my.hits}) — ${my.rank} место. Новое испытание завтра.`
            : `Попытка начата: ${my.score} очков. Продолжи с того удара, где остановился.`}
        </p>
      )}

      {canPlay && !finished && (
        <button
          onClick={() => start.mutate()}
          disabled={start.isPending || board.isPending}
          className="rounded-2xl bg-accent px-6 py-3 font-semibold text-black disabled:opacity-50"
        >
          {start.isPending ? "Начинаем…" : my ? "Продолжить" : "Начать испытание"}
        </button>
      )}
      {start.isError && (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
          {formatGameError(start.error, "Не удалось начать испытание")}
        </p>
      )}

      <Leaderboard data={data} />

      <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
        К играм
      </button>
    </div>
  );
}

function Leaderboard({ data }: { data: FreeKickChallenge | undefined }) {
  if (!data) return null;
  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">Лучшие сегодня</h2>
        <span className="text-caption text-ink-mist">участников: {data.players}</span>
      </div>
      {data.top.length === 0 ? (
        <p className="mt-2 text-sm text-ink-mist">Пока никого — будь первым!</p>
      ) : (
        <ol className="mt-2 flex flex-col gap-1">
          {data.top.map((r) => (
            <li
              key={r.rank}
              className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${r.is_me ? "bg-accent/15 text-ink-chalk" : "text-ink-chalk/90"}`}
            >
              <span className="w-6 text-right font-mono text-ink-mist">{r.rank}</span>
              <span className="flex-1 truncate">
                {r.rank <= 3 ? ["🥇", "🥈", "🥉"][r.rank - 1] + " " : ""}
                {r.name}
                {!r.finished && <span className="text-caption text-ink-mist"> · играет</span>}
              </span>
              <span className="text-caption text-ink-mist">🎯{r.hits}</span>
              <span className="w-12 text-right font-mono font-bold">{r.score}</span>
            </li>
          ))}
        </ol>
      )}
      {data.my && !data.top.some((r) => r.is_me) && (
        <p className="mt-2 text-sm text-ink-chalk">
          Ты: {data.my.rank} место · {data.my.score} очков
        </p>
      )}
    </section>
  );
}

/** Where the target is in the goal (seen from the ball): it's small from
 * the spot, so a little map in the corner too. */
function GoalMap({ target }: { target: FreeKickTarget }) {
  const w = 2 * GOAL_HALF_WIDTH;
  return (
    <svg viewBox={`-0.15 -0.15 ${w + 0.3} ${GOAL_HEIGHT + 0.3}`} className="ml-auto mt-1 h-10 w-[7.5rem]" aria-hidden>
      <path d={`M0 ${GOAL_HEIGHT} V0 H${w} V${GOAL_HEIGHT}`} fill="rgba(255,255,255,0.08)" stroke="white" strokeWidth={0.12} />
      <circle cx={target.x + GOAL_HALF_WIDTH} cy={GOAL_HEIGHT - target.y} r={target.r} fill="rgba(198,230,58,0.35)" stroke="#c6e63a" strokeWidth={0.1} />
    </svg>
  );
}

/** One kick of the attempt: the scene with today's target, the swipe and
 * the server's verdict. */
function ChallengeKick({
  attempt,
  kick,
  score,
  hits,
  onBack,
  onNext,
}: {
  attempt: FreeKickChallengeStart;
  kick: FreeKick3DKick;
  score: number;
  hits: number;
  onBack: () => void;
  onNext: (r: FreeKickChallengeShot) => void;
}) {
  const setup = useMemo(() => createSetup(kick.seed, attempt.rating), [kick.seed, attempt.rating]);
  const target = attempt.targets[kick.kick_index];
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
    mutationFn: (q: QuantizedSwipe) => shootFreeKickChallenge(attempt.session_id, q),
    onError: (err) => {
      // The kick wasn't taken: let the player swipe it again.
      setErrorMsg(formatGameError(err, "Удар не засчитан — попробуй ещё раз"));
      setShot(null);
      setShown(false);
    },
  });
  const verdict = shown ? shoot.data : undefined;

  useEffect(() => startCrowd(), []);
  useEffect(() => {
    if (ready) crowdChant();
  }, [ready, kick.seed]);

  const replayed = shown && shot ? shot.trajectory.outcome : null;
  useEffect(() => {
    if (!replayed) return;
    crowdHush();
    crowdTension(false);
    hapticNotify(replayed === "goal" ? "success" : "error");
    playFreeKickSfx(replayed === "goal" ? "roar" : "groan");
  }, [replayed]);

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

  return (
    <div className="fixed inset-0 z-50 select-none overflow-hidden bg-bg-base text-ink-chalk">
      <ErrorBoundary fallback={(error, retry) => <SceneCrash error={error} retry={retry} log={crashLog.current} />}>
        <FreeKickScene3D
          setup={setup}
          shot={shot}
          onDecided={onDecided}
          onReady={onReady}
          fpsRef={fpsRef}
          kickerCelebration={attempt.celebration === "cel_silly" ? "silly_dance" : "celebrate"}
          gear={{ ball: attempt.ball, kickerBoots: attempt.boots }}
          target={target}
          targetHit={verdict ? verdict.hit : null}
        />
      </ErrorBoundary>

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
            🎯 Испытание · {kick.kick_index + 1} / {attempt.total_kicks}
          </div>
          <div className="text-caption text-ink-mist">
            {score} очков · мишеней {hits}
          </div>
          <GoalMap target={target} />
          <span ref={fpsRef} className="hidden" />
        </div>
      </div>

      {(aiming || !ready) && (
        <div className="pointer-events-none absolute inset-x-0 top-20 px-6 text-center text-sm text-ink-chalk/90 drop-shadow">
          {ready ? "Попади в мишень в воротах — чем ближе к центру, тем больше очков." : "Загружаем…"}
          {errorMsg && <div className="mt-2 text-red-300">{errorMsg}</div>}
        </div>
      )}

      {shown && !shoot.data && shoot.isPending && (
        <div className="absolute inset-x-0 bottom-10 text-center text-sm text-ink-mist">Судья смотрит повтор…</div>
      )}

      {verdict && (
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-2 bg-gradient-to-t from-bg-base/90 to-transparent p-6 pb-10 pt-16">
          <div className={`font-display text-4xl drop-shadow ${verdict.hit ? "text-yellow-300" : verdict.outcome === "goal" ? "text-accent-lime" : "text-ink-mist"}`}>
            {verdict.hit ? "В мишень!" : verdict.outcome === "goal" ? "Гол" : "Мимо"}
          </div>
          <div className="font-mono text-lg text-ink-chalk">+{verdict.points} очков</div>
          <button
            type="button"
            onClick={() => {
              setShot(null);
              setShown(false);
              shoot.reset();
              onNext(verdict);
            }}
            className="mt-1 rounded-xl bg-accent px-6 py-3 font-semibold text-black"
          >
            {verdict.is_finished ? "Итоги" : "Следующий удар"}
          </button>
        </div>
      )}
    </div>
  );
}
