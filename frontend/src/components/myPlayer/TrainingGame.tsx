import { useEffect, useRef, useState } from "react";

import { finishMyPlayerTraining, startMyPlayerTraining, type MyPlayerView } from "@/api/myPlayer";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";

interface Props {
  maxHits: number;
  xpBase: number;
  xpPerHit: number;
  onDone: (view: MyPlayerView) => void;
  onClose: () => void;
}

// Each shot the target gets narrower and the marker faster.
const ZONES = [
  { width: 26, speed: 0.9 },
  { width: 20, speed: 1.15 },
  { width: 14, speed: 1.4 },
];

/** Daily training «Точный удар»: stop the moving marker inside the green
 * zone, three shots. The run is opened on the server first (start), the
 * hit count is sent at the end; the server checks timing and pays once a day. */
export default function TrainingGame({ maxHits, xpBase, xpPerHit, onDone, onClose }: Props) {
  const [phase, setPhase] = useState<"loading" | "aim" | "result" | "sending" | "done">("loading");
  const [shot, setShot] = useState(0);
  const [results, setResults] = useState<boolean[]>([]);
  const [pos, setPos] = useState(0);
  const [zoneStart, setZoneStart] = useState(40);
  const [error, setError] = useState<string | null>(null);
  const [earned, setEarned] = useState<number | null>(null);
  const startedAt = useRef(0);
  const frame = useRef(0);
  const shots = Math.min(maxHits, ZONES.length);

  useEffect(() => {
    startMyPlayerTraining()
      .then(() => {
        startedAt.current = Date.now();
        setZoneStart(15 + Math.random() * 55);
        setPhase("aim");
      })
      .catch((err) => setError(formatGameError(err, "Не получилось начать тренировку")));
  }, []);

  useEffect(() => {
    if (phase !== "aim") return;
    const begin = performance.now();
    const speed = ZONES[shot].speed;
    const tick = (now: number) => {
      // Triangle wave 0..100..0.
      const t = ((now - begin) / 1000) * speed * 100;
      const v = t % 200;
      setPos(v <= 100 ? v : 200 - v);
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [phase, shot]);

  const finish = async (all: boolean[]) => {
    setPhase("sending");
    // The server wants a plausible duration; three shots normally take longer.
    const wait = 4500 - (Date.now() - startedAt.current);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    try {
      const view = await finishMyPlayerTraining(all.filter(Boolean).length);
      hapticNotify("success");
      setEarned(view.training_xp ?? null);
      setPhase("done");
      onDone(view);
    } catch (err) {
      setError(formatGameError(err, "Не получилось засчитать тренировку"));
    }
  };

  const kick = () => {
    if (phase !== "aim") return;
    cancelAnimationFrame(frame.current);
    const zone = ZONES[shot];
    const hit = pos >= zoneStart && pos <= zoneStart + zone.width;
    haptic(hit ? "medium" : "light");
    const next = [...results, hit];
    setResults(next);
    setPhase("result");
    setTimeout(() => {
      if (next.length >= shots) {
        void finish(next);
      } else {
        setShot(next.length);
        setZoneStart(10 + Math.random() * (80 - ZONES[next.length].width));
        setPhase("aim");
      }
    }, 900);
  };

  const zone = ZONES[Math.min(shot, ZONES.length - 1)];
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70" onClick={phase === "done" || error ? onClose : undefined}>
      <div
        className="w-full max-w-lg rounded-t-3xl bg-bg-surface p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))]"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="font-display text-lg font-bold text-ink-chalk">Тренировка: точный удар</p>
        <p className="mt-1 text-xs text-ink-mist">
          Останови мяч в зелёной зоне. {shots} удара, каждый сложнее. Опыт: {xpBase} + {xpPerHit} за каждое попадание.
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

        <div className="relative mt-5 h-12 overflow-hidden rounded-2xl bg-bg-raised" data-testid="training-bar">
          <div
            className="absolute inset-y-0 bg-accent-lime/35 ring-2 ring-accent-lime"
            style={{ left: `${zoneStart}%`, width: `${zone.width}%` }}
          />
          <div
            className="absolute top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white text-center text-xl leading-8 shadow"
            style={{ left: `${pos}%` }}
          >
            ⚽
          </div>
        </div>

        {error ? (
          <p className="mt-4 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>
        ) : phase === "done" ? (
          <div className="mt-4 text-center">
            <p className="font-display text-xl font-bold text-accent-lime">+{earned ?? 0} опыта</p>
            <p className="text-xs text-ink-mist">Попаданий: {results.filter(Boolean).length} из {shots}. Следующая тренировка — завтра.</p>
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
            {phase === "loading" ? "Готовимся…" : phase === "sending" ? "Считаем…" : phase === "result" ? (results[results.length - 1] ? "Гол!" : "Мимо") : "Удар!"}
          </button>
        )}
      </div>
    </div>
  );
}
