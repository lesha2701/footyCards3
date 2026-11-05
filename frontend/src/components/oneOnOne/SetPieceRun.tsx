import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps, type PointerEvent, type ReactNode } from "react";

import ErrorBoundary from "@/components/common/ErrorBoundary";
import FreeKickScene3D, { type LiveShot } from "@/components/freeKick3d/FreeKickScene3D";
import SceneCrash from "@/components/freeKick3d/SceneCrash";
import { ExitButton, OutcomeCaption, ScoreBug } from "@/components/oneOnOne/Broadcast";
import { formatGameError } from "@/lib/errors";
import { useCrashLog } from "@/lib/freeKick3d/crashLog";
import { crowdChant, crowdHush, crowdTension, playFreeKickSfx, startCrowd } from "@/lib/freeKick3d/sfx";
import { swipeFromPoints, type SwipePoint } from "@/lib/freeKick3d/swipe";
import { createPenaltySetup, createSetup, quantizeSwipe, simulateShot, swipeToKick, type QuantizedSwipe } from "@/lib/freeKick3d/trajectory";
import { audio } from "@/lib/sound";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { OneOnOneOutcome } from "@/types";

export type SetPieceRunProps = {
  /** A penalty or a free kick from the server's seed. */
  kind: "penalty" | "free_kick";
  seed: number;
  rating: number;
  bug: ComponentProps<typeof ScoreBug>;
  /** What this episode is, until the swipe. */
  title: string;
  gear: ComponentProps<typeof FreeKickScene3D>["gear"];
  celebration?: string | null;
  nextLabel: string;
  /** Under the outcome, once the server has answered. */
  note?: ReactNode;
  submit: (q: QuantizedSwipe) => Promise<unknown>;
  /** The ball has done what it was going to do. */
  onShown?: () => void;
  onBack: () => void;
  onNext: () => void;
};

/** One set piece of a match: the 3D kick by day, the swipe, the server's word. */
export default function SetPieceRun({ kind, seed, rating, bug, title, gear, celebration, nextLabel, note, submit, onShown, onBack, onNext }: SetPieceRunProps) {
  const setup = useMemo(() => (kind === "penalty" ? createPenaltySetup(seed, rating) : createSetup(seed, rating)), [kind, seed, rating]);
  const [shot, setShot] = useState<LiveShot | null>(null);
  const [shown, setShown] = useState(false);
  const [trail, setTrail] = useState<SwipePoint[]>([]);
  const [ready, setReady] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const points = useRef<SwipePoint[]>([]);
  const fpsRef = useRef<HTMLSpanElement | null>(null);
  const crashLog = useCrashLog();
  const onReady = useCallback(() => setReady(true), []);
  const onDecided = useCallback(() => setShown(true), []);

  const shoot = useMutation({
    mutationFn: submit,
    onError: (err) => {
      // The kick wasn't taken: let the player swipe it again.
      setErrorMsg(formatGameError(err, "Удар не засчитан — попробуй ещё раз"));
      setShot(null);
      setShown(false);
    },
  });

  useEffect(() => startCrowd(), []);
  useEffect(() => {
    if (ready) crowdChant();
  }, [ready, seed]);

  // The local replay is the server's own computation: no waiting for its answer.
  const replayed = shown && shot ? (shot.trajectory.outcome as OneOnOneOutcome) : null;
  useEffect(() => {
    if (replayed) onShown?.();
  }, [replayed, onShown]);
  useEffect(() => {
    if (!replayed) return;
    crowdHush();
    crowdTension(false);
    hapticNotify(replayed === "goal" ? "success" : replayed === "save" ? "warning" : "error");
    playFreeKickSfx(replayed === "goal" ? "roar" : "groan");
  }, [replayed]);

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
    setShot({ id: seed, kick: k, trajectory: simulateShot(setup, k) });
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
          time="day"
          kickerCelebration={celebration === "cel_silly" ? "silly_dance" : "celebrate"}
          gear={gear}
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
        <ExitButton onClick={onBack} />
        <div>
          <ScoreBug {...bug} />
          <span ref={fpsRef} className="hidden" />
        </div>
      </div>

      {(aiming || !ready) && (
        <div className="pointer-events-none absolute inset-x-0 top-24 px-6 text-center text-ink-chalk/90 drop-shadow">
          {ready ? (
            <>
              <div className="font-display text-xl font-bold uppercase text-white">{title}</div>
              <div className="mt-1 text-sm">Свайпни от мяча к воротам. Быстрее — сильнее, длиннее — выше, дугой — закрутка.</div>
            </>
          ) : (
            <span className="text-sm">Загружаем…</span>
          )}
          {errorMsg && <div className="mt-2 text-sm text-red-300">{errorMsg}</div>}
        </div>
      )}

      {shown && !shoot.isSuccess && shoot.isPending && (
        <div className="absolute inset-x-0 bottom-10 text-center text-sm text-ink-mist">Судья смотрит повтор…</div>
      )}

      <OutcomeCaption outcome={replayed} />

      {replayed && shoot.isSuccess && (
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-2 bg-gradient-to-t from-bg-base/90 to-transparent p-6 pb-10 pt-16">
          {note}
          <button
            type="button"
            onClick={() => {
              // Same scene, next kick: no WebGL context churn between kicks.
              setShot(null);
              setShown(false);
              shoot.reset();
              onNext();
            }}
            className="mt-1 rounded-xl bg-accent px-6 py-3 font-semibold text-black"
          >
            {nextLabel}
          </button>
        </div>
      )}
    </div>
  );
}
