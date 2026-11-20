import { useEffect, useRef, useState } from "react";

import parkingUrl from "@/assets/zames/arena-parking.webp";
import tunnelUrl from "@/assets/zames/arena-tunnel.webp";
import { createGame, rageReady, step, type Input, type Mode, type State } from "@/lib/zames/engine";
import { arenaOf, classifySwipe } from "@/lib/zames/gestures";
import { haptic, hapticNotify } from "@/lib/telegram";

import { preloadSprites } from "./sprites";
import { drainEvents, drawFrame, makeFx, makeView, pickFighter, unproject, updateFx, type View } from "./render";

export interface ZamesResult {
  won: boolean;
  waves: number;
  knockouts: number;
  bestCombo: number;
  seconds: number;
}

interface Props {
  mode: Mode;
  seed: number;
  onFinish: (result: ZamesResult) => void;
  onExit: () => void;
}

const STEP = 1 / 60;
const TAP_MAX_MOVE = 14;
const HOLD_MS = 230;

function loadImage(url: string): HTMLImageElement {
  const img = new Image();
  img.src = url;
  return img;
}

export default function ZamesArena({ mode, seed, onFinish, onExit }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<State>(createGame(mode, seed));
  const inputs = useRef<Input[]>([]);
  const viewRef = useRef<View>(makeView(390, 760));
  const [rage, setRage] = useState(false);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(false);
  const doneRef = useRef(false);
  const onFinishRef = useRef(onFinish);
  onFinishRef.current = onFinish;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const images = { parking: loadImage(parkingUrl), tunnel: loadImage(tunnelUrl) };
    preloadSprites();
    const fx = makeFx();
    const topInset = 8;
    let raf = 0;
    let last = performance.now();
    let acc = 0;
    let clock = 0;
    let dpr = 1;
    let lastHaptic = 0;

    const resize = () => {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const vibrate = (kind: "light" | "medium" | "heavy" | "success" | "error") => {
      const now = performance.now();
      if (kind === "success" || kind === "error") return hapticNotify(kind);
      if (kind === "light" && now - lastHaptic < 70) return;
      lastHaptic = now;
      haptic(kind);
    };

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const s = stateRef.current;
      let dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (pausedRef.current) dt = 0;
      acc += dt;
      clock += dt;
      const rect = canvas.getBoundingClientRect();
      const view = makeView(rect.width, rect.height, arenaOf(s));
      viewRef.current = view;
      let steps = 0;
      while (acc >= STEP && steps < 5) {
        step(s, STEP, inputs.current.splice(0, inputs.current.length));
        acc -= STEP;
        steps += 1;
      }
      if (steps === 5) acc = 0;
      drainEvents(view, s, fx, vibrate);
      if (!pausedRef.current) {
        // particles live in real time, slowed with the fight
        updateFx(fx, s.slow > 0 ? dt * 0.4 : dt);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawFrame(ctx, view, s, fx, images[arenaOf(s)], clock, topInset);
      const ready = rageReady(s);
      setRage((r) => (r === ready ? r : ready));
      if (s.finished && !doneRef.current) {
        doneRef.current = true;
        onFinishRef.current({
          won: s.won, waves: s.wavesCleared, knockouts: s.knockouts, bestCombo: s.bestCombo, seconds: Math.round(s.time),
        });
      }
    };
    raf = requestAnimationFrame(frame);

    const onHide = () => {
      if (document.hidden) {
        pausedRef.current = true;
        setPaused(true);
      }
    };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      document.removeEventListener("visibilitychange", onHide);
    };
  }, []);

  // --- gestures ---------------------------------------------------------
  const gesture = useRef<{ id: number; points: { x: number; y: number }[]; t0: number; hold: boolean; timer: number } | null>(null);

  const local = (e: React.PointerEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onDown = (e: React.PointerEvent) => {
    if (paused || gesture.current) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const p = local(e);
    const g = { id: e.pointerId, points: [p], t0: performance.now(), hold: false, timer: 0 };
    g.timer = window.setTimeout(() => {
      const moved = Math.hypot(g.points[g.points.length - 1].x - p.x, g.points[g.points.length - 1].y - p.y);
      if (gesture.current === g && moved < TAP_MAX_MOVE) {
        g.hold = true;
        inputs.current.push({ k: "hold" });
      }
    }, HOLD_MS);
    gesture.current = g;
  };

  const onMove = (e: React.PointerEvent) => {
    const g = gesture.current;
    if (!g || g.id !== e.pointerId) return;
    g.points.push(local(e));
    if (g.points.length > 120) g.points.splice(1, 1);
  };

  const onUp = (e: React.PointerEvent) => {
    const g = gesture.current;
    if (!g || g.id !== e.pointerId) return;
    gesture.current = null;
    window.clearTimeout(g.timer);
    const p = local(e);
    g.points.push(p);
    if (g.hold) {
      inputs.current.push({ k: "release" });
      return;
    }
    const start = g.points[0];
    if (Math.hypot(p.x - start.x, p.y - start.y) < TAP_MAX_MOVE && g.points.length < 40) {
      const view = viewRef.current;
      const s = stateRef.current;
      const target = pickFighter(view, s, start.x, start.y);
      const floor = unproject(view, start.x, Math.max(start.y, view.floorTop));
      inputs.current.push({ k: "tap", x: target ? target.x : floor.x, z: target ? target.z : floor.z, target: target?.id });
      return;
    }
    const move = classifySwipe(g.points);
    if (move) inputs.current.push(move);
  };

  const onCancel = (e: React.PointerEvent) => {
    const g = gesture.current;
    if (!g || g.id !== e.pointerId) return;
    window.clearTimeout(g.timer);
    if (g.hold) inputs.current.push({ k: "release" });
    gesture.current = null;
  };

  const togglePause = (value: boolean) => {
    pausedRef.current = value;
    setPaused(value);
  };

  return (
    <div className="fixed inset-0 z-50 select-none bg-black" style={{ touchAction: "none" }}>
      <canvas
        ref={canvasRef}
        className="absolute inset-0 h-full w-full"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onCancel}
        onContextMenu={(e) => e.preventDefault()}
      />
      <button
        type="button"
        onClick={() => togglePause(true)}
        className="absolute bottom-3 left-3 rounded-full bg-black/50 px-3 py-1.5 text-caption font-bold text-white/80 ring-1 ring-white/20"
        style={{ marginBottom: "env(safe-area-inset-bottom)" }}
        aria-label="Пауза"
      >
        ❚❚
      </button>
      {rage && !paused ? (
        <button
          type="button"
          onPointerDown={(e) => {
            e.stopPropagation();
            inputs.current.push({ k: "rage" });
          }}
          className="absolute bottom-6 left-1/2 -translate-x-1/2 animate-pulse rounded-full bg-gradient-to-b from-yellow-300 to-orange-500 px-7 py-3 font-display text-lg font-black uppercase tracking-wide text-black shadow-[0_0_30px_rgba(255,140,40,0.8)] ring-4 ring-black/70"
          style={{ marginBottom: "env(safe-area-inset-bottom)" }}
        >
          🔥 Разнос!
        </button>
      ) : null}
      {paused ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/70 px-8 text-center">
          <p className="font-display text-3xl font-black text-white">Пауза</p>
          <button type="button" onClick={() => togglePause(false)} className="w-full max-w-xs rounded-2xl bg-lime-400 py-3 font-bold text-black">
            Продолжить замес
          </button>
          <button type="button" onClick={onExit} className="w-full max-w-xs rounded-2xl bg-white/10 py-3 font-bold text-white ring-1 ring-white/20">
            Сдаться и выйти
          </button>
        </div>
      ) : null}
    </div>
  );
}
