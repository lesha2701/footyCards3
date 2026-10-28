import { useCallback, useMemo, useRef, useState, type PointerEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import ErrorBoundary from "@/components/common/ErrorBoundary";
import FreeKickScene3D, { type LiveShot } from "@/components/freeKick3d/FreeKickScene3D";
import { playFreeKickSfx } from "@/lib/freeKick3d/sfx";
import { swipeFromPoints, type SwipePoint } from "@/lib/freeKick3d/swipe";
import {
  createSetup,
  quantizeSwipe,
  simulateShot,
  swipeToKick,
  type ShotOutcome,
} from "@/lib/freeKick3d/trajectory";
import { haptic, hapticNotify } from "@/lib/telegram";

const OUTCOME: Record<ShotOutcome, { label: string; className: string }> = {
  goal: { label: "ГОЛ!", className: "text-accent-lime" },
  save: { label: "Сейв", className: "text-accent-cyan" },
  miss: { label: "Мимо", className: "text-ink-mist" },
  wall: { label: "В стенку", className: "text-ink-mist" },
};

const newSeed = () => Math.floor(Math.random() * 0x7fffffff);

/** «Живой штрафной» — a client-only 3D prototype (no rewards, no backend).
 * The shot itself is `simulateShot(createSetup(seed), swipeToKick(...))`,
 * a pure function the server can replay later; the scene only shows it. */
export default function FreeKick3DPage() {
  const navigate = useNavigate();
  // ?seed=N replays a position (handy for reproducing a shot).
  const [params] = useSearchParams();
  const [seed, setSeed] = useState(() => Number(params.get("seed")) || newSeed());
  const setup = useMemo(() => createSetup(seed), [seed]);
  const [shot, setShot] = useState<LiveShot | null>(null);
  const [result, setResult] = useState<ShotOutcome | null>(null);
  const [trail, setTrail] = useState<SwipePoint[]>([]);
  const [ready, setReady] = useState(false);
  const onReady = useCallback(() => setReady(true), []);
  const points = useRef<SwipePoint[]>([]);
  const shotCounter = useRef(0);
  const fpsRef = useRef<HTMLSpanElement | null>(null);

  const reset = useCallback((nextSeed?: number) => {
    setShot(null);
    setResult(null);
    setTrail([]);
    if (nextSeed !== undefined) setSeed(nextSeed);
  }, []);

  const onDecided = useCallback(
    (shotId: number) => {
      if (shotId !== shotCounter.current || !shot) return;
      const outcome = shot.trajectory.outcome;
      setResult(outcome);
      setTrail([]);
      hapticNotify(outcome === "goal" ? "success" : outcome === "save" ? "warning" : "error");
      playFreeKickSfx(outcome === "goal" ? "roar" : "groan");
    },
    [shot],
  );

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
    if (!swipe) {
      setTrail([]);
      return;
    }
    const kick = swipeToKick(setup, quantizeSwipe(swipe));
    shotCounter.current += 1;
    haptic("medium");
    setShot({ id: shotCounter.current, kick, trajectory: simulateShot(setup, kick) });
  };

  const speedKmh = shot ? Math.round(Math.hypot(shot.kick.velocity.x, shot.kick.velocity.y, shot.kick.velocity.z) * 3.6) : 0;
  const distance = Math.round(Math.hypot(setup.ball.x, setup.ball.z));

  return (
    <div className="fixed inset-0 select-none overflow-hidden bg-bg-base text-ink-chalk">
      {/* A 3D failure (WebGL, physics) restarts the scene, not the app. */}
      <ErrorBoundary fallback={(error, retry) => <SceneCrash error={error} retry={retry} />}>
        <FreeKickScene3D setup={setup} shot={shot} onDecided={onDecided} onReady={onReady} fpsRef={fpsRef} />
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
          onClick={() => navigate("/play")}
          className="pointer-events-auto rounded-full bg-bg-surface/80 px-3 py-1.5 text-sm font-semibold"
        >
          ← Назад
        </button>
        <div className="text-right">
          <div className="font-display text-sm">Штрафной 3D</div>
          <div className="text-caption text-ink-mist">
            прототип · {distance} м · #{seed} · <span ref={fpsRef}>— fps</span>
          </div>
        </div>
      </div>

      {(aiming || !ready) && (
        <div className="pointer-events-none absolute inset-x-0 top-16 px-6 text-center text-sm text-ink-chalk/90 drop-shadow">
          {ready
            ? "Свайпните от мяча к воротам. Быстрее — сильнее, длиннее — выше, дугой — закрутка."
            : "Загружаем физику…"}
        </div>
      )}

      {result && (
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-3 bg-gradient-to-t from-bg-base/90 to-transparent p-6 pb-10 pt-16">
          <div className={`font-display text-4xl drop-shadow ${OUTCOME[result].className}`}>{OUTCOME[result].label}</div>
          <div className="text-caption text-ink-chalk/80">{speedKmh} км/ч</div>
          <div className="flex gap-3">
            <button type="button" onClick={() => reset()} className="rounded-xl bg-accent px-5 py-3 font-semibold text-black">
              Ещё раз
            </button>
            <button type="button" onClick={() => reset(newSeed())} className="rounded-xl bg-bg-raised px-5 py-3 font-semibold">
              Другая позиция
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Prototype diagnostics: the scene failed — show what threw (the stack's
 * first lines, so a phone screenshot is enough to find it) and restart. */
function SceneCrash({ error, retry }: { error: Error; retry: () => void }) {
  const stack = (error.stack ?? "").split("\n").slice(0, 6).join("\n");
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-bg-base p-6 text-center">
      <div className="font-display text-lg">Сцена упала</div>
      <div className="text-sm text-ink-mist">{error.message}</div>
      <pre className="max-h-48 w-full overflow-auto whitespace-pre-wrap break-all rounded-lg bg-bg-surface p-3 text-left text-micro text-ink-mist">
        {stack}
      </pre>
      <button type="button" onClick={retry} className="rounded-xl bg-accent px-5 py-3 font-semibold text-black">
        Перезапустить сцену
      </button>
    </div>
  );
}
