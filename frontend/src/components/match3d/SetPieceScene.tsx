/** A penalty or a close free kick of the match, played in the game's own swipe
 * scene: the kick from the foul's spot, the keeper of «Пенальти» for their
 * penalty. It sits in the landscape box, so touches come through `toBox`, and
 * only the outcome goes back to the match. */
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";

import ErrorBoundary from "@/components/common/ErrorBoundary";
import type { LiveShot } from "@/components/freeKick3d/FreeKickScene3D";
import { crowdChant, crowdHush, crowdTension, playFreeKickSfx } from "@/lib/freeKick3d/sfx";
import { swipeFromPoints, type SwipePoint } from "@/lib/freeKick3d/swipe";
import {
  GOAL_HALF_WIDTH, KEEPER_MAX_HAND_Y, createPenaltySetup, createSetup, penaltyBotShot, playerKeeperSetup, quantizeSwipe, simulateShot, swipeToKick,
  type QuantizedDive,
} from "@/lib/freeKick3d/trajectory";
import type { SceneKick, SceneOutcome } from "@/lib/match3d/core";
import { audio } from "@/lib/sound";
import { haptic, hapticNotify } from "@/lib/telegram";

/** Worth starting early: the scene and its models come in their own chunk. */
export const loadScene = () => import("@/components/freeKick3d/FreeKickScene3D");
const FreeKickScene3D = lazy(loadScene);

/** A swipe this long (px) is a dive; it counts from the first few px. */
const DIVE_SWIPE_PX = 28;
const DIVE_START_PX = 6;
const BOT_RUNUP_DELAY_MS = 1300;
/** How long the outcome stays on before the match comes back. */
const OUTCOME_MS = 2300;

/** Same mapping as «Пенальти»: the camera is behind the kicker. */
function diveTarget(dx: number, dy: number) {
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const x = Math.max(-GOAL_HALF_WIDTH, Math.min(GOAL_HALF_WIDTH, (dx / len) * 3.1));
  const y = Math.max(0.25, Math.min(KEEPER_MAX_HAND_Y, 1.0 + (-dy / len) * 1.35));
  return { x: Math.round(x * 1000), y: Math.round(y * 1000) };
}

const CAPTION: Record<SceneOutcome, string> = { goal: "ГОЛ!", save: "Вратарь забрал", miss: "Мимо", wall: "В стенку" };
const KEPT: Record<SceneOutcome, string> = { goal: "Гол", save: "Отбил!", miss: "Мимо!", wall: "Мимо!" };

function Crashed({ onFail }: { onFail: () => void }) {
  useEffect(onFail, [onFail]);
  return null;
}

type Props = {
  kick: SceneKick;
  /** A touch in the box's own axes. */
  toBox: (x: number, y: number) => { x: number; y: number };
  height: number;
  /** null: the scene couldn't run, the match plays the kick itself. */
  onDone: (outcome: SceneOutcome | null) => void;
};

export default function SetPieceScene({ kick, toBox, height, onDone }: Props) {
  const keeping = kick.kind === "keep";
  const [dive, setDive] = useState<QuantizedDive | null>(null);
  const setup = useMemo(() => {
    if (keeping) return playerKeeperSetup(kick.seed, dive);
    if (kick.kind === "penalty") return createPenaltySetup(kick.seed, kick.rating);
    return createSetup(kick.seed, kick.rating, { distance: kick.distance, offset: kick.offset });
  }, [keeping, kick, dive]);
  const [shot, setShot] = useState<LiveShot | null>(null);
  const [shown, setShown] = useState(false);
  const [ready, setReady] = useState(false);
  const [trail, setTrail] = useState<SwipePoint[]>([]);
  const points = useRef<SwipePoint[]>([]);
  const diveFrom = useRef<number | null>(null);
  const fpsRef = useRef<HTMLSpanElement | null>(null);
  const shotClock = useRef(-1);
  const onReady = useCallback(() => setReady(true), []);
  const onDecided = useCallback(() => setShown(true), []);
  const failed = useCallback(() => onDone(null), [onDone]);

  useEffect(() => {
    if (ready && !keeping) crowdChant();
  }, [ready, keeping]);

  // Their penalty: the bot runs up by itself after a moment.
  useEffect(() => {
    if (!keeping || !ready) return undefined;
    const timer = window.setTimeout(() => {
      const s0 = playerKeeperSetup(kick.seed, null);
      const k = swipeToKick(s0, penaltyBotShot(kick.seed).swipe);
      setShot({ id: kick.seed, kick: k, trajectory: simulateShot(s0, k) });
      crowdTension(true);
    }, BOT_RUNUP_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [keeping, ready, kick.seed]);

  const outcome = shown && shot ? (shot.trajectory.outcome as SceneOutcome) : null;
  useEffect(() => {
    if (!outcome) return undefined;
    crowdHush();
    crowdTension(false);
    const good = keeping ? outcome !== "goal" : outcome === "goal";
    hapticNotify(good ? "success" : "error");
    playFreeKickSfx(good ? "roar" : "groan");
    const timer = window.setTimeout(() => onDone(outcome), OUTCOME_MS);
    return () => window.clearTimeout(timer);
  }, [outcome, keeping, onDone]);

  const aiming = ready && !keeping && shot === null;
  const diving = keeping && shot !== null && !shown && dive === null;
  const at = (e: PointerEvent<HTMLDivElement>): SwipePoint => ({ ...toBox(e.clientX, e.clientY), t: e.timeStamp });

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!aiming && !diving) return;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Not every WebView lets a pointer be captured; the swipe still works.
    }
    points.current = [at(e)];
    diveFrom.current = null;
    if (aiming) setTrail(points.current);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (points.current.length === 0) return;
    if (diving) {
      const p0 = points.current[0], p = at(e);
      const dx = p.x - p0.x, dy = p.y - p0.y;
      const moved = Math.sqrt(dx * dx + dy * dy);
      if (diveFrom.current === null && moved >= DIVE_START_PX) diveFrom.current = shotClock.current;
      if (moved < DIVE_SWIPE_PX) return;
      points.current = [];
      const d = { ...diveTarget(dx, dy), reactionMs: Math.round((diveFrom.current ?? shotClock.current) * 1000) };
      haptic("medium");
      setDive(d);
      const s1 = playerKeeperSetup(kick.seed, d);
      const k = swipeToKick(s1, penaltyBotShot(kick.seed).swipe);
      // Same shot id: the clock keeps running, only the keeper changes.
      setShot({ id: kick.seed, kick: k, trajectory: simulateShot(s1, k) });
      return;
    }
    if (!aiming) return;
    points.current = [...points.current, at(e)];
    setTrail(points.current);
  };
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!aiming || points.current.length === 0) {
      points.current = [];
      return;
    }
    const pts = [...points.current, at(e)];
    points.current = [];
    setTrail([]);
    const swipe = swipeFromPoints(pts, height);
    const q = swipe ? quantizeSwipe(swipe) : null;
    if (!q || q.dy >= 0) return;
    const k = swipeToKick(setup, q);
    haptic("medium");
    audio(); // resume the audio context inside the gesture (mobile autoplay rules)
    crowdTension(true);
    setShot({ id: kick.seed, kick: k, trajectory: simulateShot(setup, k) });
  };

  const title = keeping ? "Пенальти в твои ворота" : kick.kind === "penalty" ? "Пенальти" : "Штрафной";
  const hint = keeping ? "Свайпни туда, куда прыгнуть, в момент удара" : "Свайпни от мяча к воротам. Быстрее — сильнее, длиннее — выше, дугой — закрутка";

  return (
    <div style={{ position: "absolute", inset: 0, zIndex: 5, background: "#07121f", overflow: "hidden" }}>
      <ErrorBoundary fallback={() => <Crashed onFail={failed} />}>
        <Suspense fallback={null}>
          <FreeKickScene3D
            setup={setup}
            shot={shot}
            onDecided={onDecided}
            onReady={onReady}
            fpsRef={fpsRef}
            time="day"
            cheerGoals={!keeping}
            kickerKit={keeping ? "away" : "home"}
            shotClockRef={shotClock}
            layoutSize
          />
        </Suspense>
      </ErrorBoundary>

      <div
        style={{ position: "absolute", inset: 0, touchAction: "none" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => { points.current = []; setTrail([]); }}
      >
        {trail.length > 1 && (
          <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
            <polyline points={trail.map((p) => `${p.x},${p.y}`).join(" ")} fill="none" stroke="rgba(198,230,58,.85)" strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </div>
      <span ref={fpsRef} style={{ display: "none" }} />

      {!outcome && (
        <div style={{ position: "absolute", left: 0, right: 0, top: 12, textAlign: "center", pointerEvents: "none", textShadow: "0 1px 4px rgba(0,0,0,.7)" }}>
          {ready ? (
            <>
              <div style={{ fontWeight: 900, fontSize: 19, letterSpacing: 0.5, textTransform: "uppercase" }}>{title}</div>
              {shot === null || diving ? <div style={{ fontSize: 12, marginTop: 2, padding: "0 24px" }}>{hint}</div> : null}
            </>
          ) : <div style={{ fontSize: 13 }}>Выходим к мячу…</div>}
        </div>
      )}
      {outcome && (
        <div style={{ position: "absolute", top: "24%", left: "50%", transform: "translateX(-50%)", padding: "8px 22px", borderRadius: 8, background: "rgba(198,28,43,.86)", fontWeight: 900, fontSize: 26, whiteSpace: "nowrap", pointerEvents: "none" }}>
          {(keeping ? KEPT : CAPTION)[outcome]}
        </div>
      )}
    </div>
  );
}
