/** Full-screen 3D replay of a goal of a career match (lazy chunk: three.js
 * loads only when a replay is opened). The episode is the 2D view's own
 * key frames (lib/goalReplay3d), so the scorer, the positions and the ball
 * in the net are exactly the 2D episode's. */
import { Canvas } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CareerReplayResponse } from "@/api/career";
import { cameraPose, type CameraMode, type GoalEpisode } from "@/lib/goalReplay3d";
import { REPLAY_KITS, boardStats, rosterAt, type Timeline } from "@/lib/matchReplay";

import { GoalScene, type ReplayClock, type SlotLook } from "./GoalScene";

const MODES: { value: CameraMode; label: string }[] = [
  { value: "tv", label: "ТВ" },
  { value: "goal", label: "За воротами" },
  { value: "top", label: "Сверху" },
  { value: "player", label: "Автор" },
];

const FINISH_LABEL: Record<GoalEpisode["finish"], string> = {
  shot: "удар", long_range: "дальний удар", header: "головой", volley: "с лёта", free_kick: "штрафной",
  penalty: "пенальти", empty_net: "в пустые ворота",
};

// Telegram full screen draws its own buttons over the top of the page.
const SAFE_TOP = "calc(env(safe-area-inset-top, 0px) + var(--tg-safe-area-inset-top, 0px) + var(--tg-content-safe-area-inset-top, 0px) + 8px)";

function usePortrait(): boolean {
  const get = () => typeof window !== "undefined" && window.innerHeight > window.innerWidth;
  const [portrait, setPortrait] = useState(get);
  useEffect(() => {
    const on = () => setPortrait(get());
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return portrait;
}

export default function GoalReplay3D({ data, tl, episodes, initial, onClose }: {
  data: CareerReplayResponse;
  tl: Timeline;
  episodes: GoalEpisode[];
  /** Index in `episodes` to start with. */
  initial: number;
  onClose: () => void;
}) {
  const [index, setIndex] = useState(initial);
  const [mode, setMode] = useState<CameraMode>("tv");
  const [playing, setPlaying] = useState(true);
  const [hintClosed, setHintClosed] = useState(false);
  const portrait = usePortrait();
  const ep = episodes[index];
  const clock = useRef<ReplayClock>({ t: ep.f0, playing: true, ended: false });
  const barRef = useRef<HTMLDivElement | null>(null);
  const fpsRef = useRef<HTMLSpanElement | null>(null);
  const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const showFps = Boolean(params?.has("fps"));
  const figuresParam = params?.get("figures") === "simple" ? "simple" : "skinned";
  const { replay, events } = data;
  const flip = data.my_side === "b";

  const looks = useMemo<SlotLook[]>(() => {
    const roster = rosterAt(replay, ep.shot);
    return Array.from({ length: 22 }, (_, i) => {
      const side = i < 11 ? "a" : "b";
      return {
        kit: side === (data.my_side ?? "a") ? REPLAY_KITS.mine : REPLAY_KITS.theirs,
        n: replay.players[roster[i]]?.n ?? i + 1,
        keeper: i === 0 || i === 11,
      };
    });
  }, [replay, ep, data.my_side]);

  const scorer = ep.scorer !== null ? replay.players[rosterAt(replay, ep.shot)[ep.scorer]] : null;
  const score = boardStats(tl, replay, events, ep.goal).score;
  const team = ep.side === "a" ? data.home_name : data.away_name;

  const restart = useCallback(() => {
    clock.current = { t: ep.f0, playing: true, ended: false };
    setPlaying(true);
  }, [ep]);
  const toggle = () => {
    const c = clock.current;
    if (c.ended) return restart();
    c.playing = !c.playing;
    setPlaying(c.playing);
  };
  const go = (k: number) => {
    const next = episodes[k];
    if (!next) return;
    clock.current = { t: next.f0, playing: true, ended: false };
    setPlaying(true);
    setIndex(k);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onProgress = useCallback((u: number) => {
    if (barRef.current) barRef.current.style.width = `${Math.max(0, Math.min(1, u)) * 100}%`;
  }, []);
  const onEnded = useCallback(() => setPlaying(false), []);

  // Initial camera where the rig starts, so the first frame is not a jump.
  const start = cameraPose("tv", 0, 0, ep.side === "a" ? 52.5 : -52.5, portrait).pos;

  return (
    <div className="fixed inset-0 z-[70] select-none bg-[#0b1424]" role="dialog" aria-modal="true" aria-label="3D-повтор гола">
      <Canvas
        dpr={[1, 1.5]}
        flat
        gl={{ antialias: false, powerPreference: "high-performance", stencil: false }}
        camera={{ fov: 30, near: 0.5, far: 400, position: start }}
        style={{ touchAction: "none" }}
      >
        <GoalScene
          key={ep.event}
          tl={tl}
          replay={replay}
          figures={figuresParam}
          ep={ep}
          flip={flip}
          looks={looks}
          mode={mode}
          clock={clock}
          onProgress={onProgress}
          onEnded={onEnded}
          fpsRef={fpsRef}
        />
      </Canvas>

      {/* Top bar: close, what happened, camera angles */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start gap-2 px-3" style={{ paddingTop: SAFE_TOP }}>
        <button
          type="button"
          onClick={onClose}
          className="pointer-events-auto flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black/55 text-lg text-white active:bg-black/70"
          aria-label="Закрыть 3D-повтор"
        >
          ✕
        </button>
        <div className="min-w-0 flex-1 rounded-2xl bg-black/55 px-3 py-1.5 text-white">
          <p className="truncate text-caption font-semibold">
            ⚽ {ep.minute}' · {scorer?.name ? `${scorer.n}. ${scorer.name}` : team}
          </p>
          <p className="truncate text-micro text-white/70">
            {FINISH_LABEL[ep.finish]} · {data.home_name} <span className="font-mono text-white">{score[0]}:{score[1]}</span> {data.away_name}
          </p>
        </div>
        <div className="pointer-events-auto flex shrink-0 overflow-hidden rounded-full bg-black/55 p-0.5" role="group" aria-label="Ракурс">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => setMode(m.value)}
              aria-pressed={mode === m.value}
              className={`rounded-full px-2.5 py-1.5 text-micro font-semibold ${mode === m.value ? "bg-[#c6e63a] text-[#0b1a12]" : "text-white"}`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {portrait && !hintClosed && (
        <button
          type="button"
          onClick={() => setHintClosed(true)}
          className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-black/65 px-4 py-3 text-center text-caption text-white"
        >
          <span className="block text-2xl">📱↻</span>
          Поверните телефон горизонтально
          <span className="mt-1 block text-micro text-white/60">нажмите, чтобы смотреть так</span>
        </button>
      )}

      {/* Bottom bar: progress, play / replay, other goals */}
      <div className="absolute inset-x-0 bottom-0 flex items-center gap-2 px-3 pb-[max(10px,env(safe-area-inset-bottom))]">
        <button
          type="button"
          onClick={toggle}
          className="flex h-9 w-11 shrink-0 items-center justify-center rounded-xl bg-black/55 text-base text-white active:bg-black/70"
          aria-label={playing ? "Пауза" : "Смотреть"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <button
          type="button"
          onClick={restart}
          className="h-9 shrink-0 rounded-xl bg-black/55 px-3 text-caption font-semibold text-white active:bg-black/70"
        >
          ↺ Повтор
        </button>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/20" aria-hidden>
          <div ref={barRef} className="h-full rounded-full bg-[#c6e63a]" style={{ width: "0%" }} />
        </div>
        {showFps && <span ref={fpsRef} className="font-mono text-micro text-white/80" />}
        {episodes.length > 1 && (
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => go(index - 1)}
              disabled={index === 0}
              className="h-9 w-9 rounded-xl bg-black/55 text-white disabled:opacity-40"
              aria-label="Предыдущий гол"
            >
              ‹
            </button>
            <span className="font-mono text-micro text-white/80">{index + 1}/{episodes.length}</span>
            <button
              type="button"
              onClick={() => go(index + 1)}
              disabled={index === episodes.length - 1}
              className="h-9 w-9 rounded-xl bg-black/55 text-white disabled:opacity-40"
              aria-label="Следующий гол"
            >
              ›
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
