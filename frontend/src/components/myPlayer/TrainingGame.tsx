import { useEffect, useRef, useState } from "react";

import { finishMyPlayerTraining, startMyPlayerTraining, type MyPlayerDrill, type MyPlayerView } from "@/api/myPlayer";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";

interface Props {
  drill: MyPlayerDrill;
  name: string;
  hint: string;
  maxHits: number;
  xpBase: number;
  xpPerHit: number;
  onDone: (view: MyPlayerView) => void;
  onClose: () => void;
}

interface DrillSpec {
  /** What moves: the marker (ball/glove) or the target (an opponent). */
  moving: "marker" | "target";
  marker: string;
  target: string;
  /** Two targets (teammates) — either counts. */
  twin: boolean;
  shots: { width: number; speed: number }[];
  hit: string;
  miss: string;
  button: string;
  bar: string;
}

// Each attempt the target gets narrower and the movement faster.
const DRILLS: Record<MyPlayerDrill, DrillSpec> = {
  shot: {
    moving: "marker", marker: "⚽", target: "", twin: false, button: "Удар!", hit: "Гол!", miss: "Мимо",
    shots: [{ width: 26, speed: 0.9 }, { width: 20, speed: 1.15 }, { width: 14, speed: 1.4 }],
    bar: "bg-bg-raised",
  },
  pass: {
    moving: "marker", marker: "⚽", target: "🙋", twin: true, button: "Пас!", hit: "Точно в ноги!", miss: "Перехват",
    shots: [{ width: 16, speed: 1 }, { width: 13, speed: 1.2 }, { width: 10, speed: 1.45 }],
    bar: "bg-emerald-900/40",
  },
  tackle: {
    moving: "target", marker: "🦵", target: "🏃", twin: false, button: "Подкат!", hit: "Отбор!", miss: "Обыграл",
    shots: [{ width: 22, speed: 0.85 }, { width: 17, speed: 1.1 }, { width: 13, speed: 1.35 }],
    bar: "bg-bg-raised",
  },
  save: {
    moving: "marker", marker: "🧤", target: "⚽", twin: false, button: "Прыжок!", hit: "Сейв!", miss: "Пропустил",
    shots: [{ width: 22, speed: 1.1 }, { width: 17, speed: 1.35 }, { width: 13, speed: 1.6 }],
    bar: "bg-gradient-to-b from-slate-200/15 to-bg-raised ring-2 ring-white/40",
  },
};

const randomStart = (width: number) => 8 + Math.random() * (84 - width);

/** Daily training: stop the moving marker on the target (or tackle the
 * running opponent as he passes the defender), three attempts. The drill
 * changes with the weekday and the player's line. The run is opened on the
 * server first (start), the hit count is sent at the end; the server checks
 * timing and pays once a day (or one bought extra run). */
export default function TrainingGame({ drill, name, hint, maxHits, xpBase, xpPerHit, onDone, onClose }: Props) {
  const spec = DRILLS[drill] ?? DRILLS.shot;
  const [phase, setPhase] = useState<"loading" | "aim" | "result" | "sending" | "done">("loading");
  const [shot, setShot] = useState(0);
  const [results, setResults] = useState<boolean[]>([]);
  const [pos, setPos] = useState(0);
  const [zones, setZones] = useState<number[]>([40]);
  const [error, setError] = useState<string | null>(null);
  const [earned, setEarned] = useState<number | null>(null);
  const [streak, setStreak] = useState<MyPlayerView["streak_reward"]>(null);
  const startedAt = useRef(0);
  const frame = useRef(0);
  const shots = Math.min(maxHits, spec.shots.length);

  const placeTargets = (attempt: number) => {
    const width = spec.shots[attempt].width;
    if (spec.twin) {
      setZones([4 + Math.random() * (40 - width), 54 + Math.random() * (40 - width)]);
    } else {
      setZones([randomStart(width)]);
    }
  };

  useEffect(() => {
    startMyPlayerTraining()
      .then(() => {
        startedAt.current = Date.now();
        placeTargets(0);
        setPhase("aim");
      })
      .catch((err) => setError(formatGameError(err, "Не получилось начать тренировку")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (phase !== "aim") return;
    const begin = performance.now();
    const { speed, width } = spec.shots[shot];
    const tick = (now: number) => {
      // Triangle wave 0..100..0.
      const t = ((now - begin) / 1000) * speed * 100;
      const v = t % 200;
      const wave = v <= 100 ? v : 200 - v;
      if (spec.moving === "marker") setPos(wave);
      else setZones([(wave / 100) * (100 - width)]);
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [phase, shot, spec]);

  const finish = async (all: boolean[]) => {
    setPhase("sending");
    // The server wants a plausible duration; three attempts normally take longer.
    const wait = 4500 - (Date.now() - startedAt.current);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    try {
      const view = await finishMyPlayerTraining(all.filter(Boolean).length);
      hapticNotify("success");
      setEarned(view.training_xp ?? null);
      setStreak(view.streak_reward ?? null);
      setPhase("done");
      onDone(view);
    } catch (err) {
      setError(formatGameError(err, "Не получилось засчитать тренировку"));
    }
  };

  const markerAt = spec.moving === "marker" ? pos : 50;
  const width = spec.shots[Math.min(shot, spec.shots.length - 1)].width;

  const kick = () => {
    if (phase !== "aim") return;
    cancelAnimationFrame(frame.current);
    const hit = zones.some((start) => markerAt >= start && markerAt <= start + width);
    haptic(hit ? "medium" : "light");
    const next = [...results, hit];
    setResults(next);
    setPhase("result");
    setTimeout(() => {
      if (next.length >= shots) {
        void finish(next);
      } else {
        setShot(next.length);
        placeTargets(next.length);
        setPhase("aim");
      }
    }, 900);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70" onClick={phase === "done" || error ? onClose : undefined}>
      <div
        className="w-full max-w-lg rounded-t-3xl bg-bg-surface p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))]"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="font-display text-lg font-bold text-ink-chalk">Тренировка: {name.toLowerCase()}</p>
        <p className="mt-1 text-xs text-ink-mist">
          {hint}. {shots} попытки, каждая сложнее. Опыт: {xpBase} + {xpPerHit} за каждое попадание.
        </p>

        <div className="mt-4 flex justify-center gap-2">
          {Array.from({ length: shots }).map((_, i) => (
            <span
              key={i}
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold ${
                results[i] === undefined ? "bg-bg-raised text-ink-mist" : results[i] ? "bg-accent-lime text-bg-base" : "bg-red-500/20 text-red-400"
              }`}
            >
              {results[i] === undefined ? i + 1 : results[i] ? "✓" : "✗"}
            </span>
          ))}
        </div>

        <div className={`relative mt-5 h-14 overflow-hidden rounded-2xl ${spec.bar}`} data-testid="training-bar" data-drill={drill}>
          {zones.map((start, i) => (
            <div
              key={i}
              className="absolute inset-y-0 flex items-center justify-center bg-accent-lime/35 text-xl ring-2 ring-accent-lime"
              style={{ left: `${start}%`, width: `${width}%` }}
            >
              {spec.target}
            </div>
          ))}
          <div
            className="absolute top-1/2 h-9 w-9 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white text-center text-xl leading-9 shadow"
            style={{ left: `${markerAt}%` }}
          >
            {spec.marker}
          </div>
        </div>

        {error ? (
          <p className="mt-4 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>
        ) : phase === "done" ? (
          <div className="mt-4 text-center">
            <p className="font-display text-xl font-bold text-accent-lime">+{earned ?? 0} опыта</p>
            <p className="text-xs text-ink-mist">Попаданий: {results.filter(Boolean).length} из {shots}.</p>
            {streak && (
              <p className="mt-2 rounded-xl bg-amber-400/15 px-3 py-2 text-sm font-semibold text-amber-300">
                🔥 Серия {streak.streak} дней! +{streak.tokens} жетон «{streak.skill_icon} {streak.skill_name}»
              </p>
            )}
            <button onClick={onClose} className="mt-3 w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base">
              Готово
            </button>
          </div>
        ) : (
          <button
            onClick={kick}
            disabled={phase !== "aim"}
            className="mt-4 w-full rounded-2xl bg-floodlight py-4 font-display text-lg font-bold text-bg-base disabled:opacity-50 active:scale-[0.98]"
          >
            {phase === "loading" ? "Готовимся…" : phase === "sending" ? "Считаем…" : phase === "result" ? (results[results.length - 1] ? spec.hit : spec.miss) : spec.button}
          </button>
        )}
      </div>
    </div>
  );
}
