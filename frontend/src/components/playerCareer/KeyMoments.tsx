import { useMutation } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { playPlayerCareerMoment, type PlayerCareerMoment, type PlayerCareerView } from "@/api/playerCareer";
import { formatGameError } from "@/lib/errors";
import { CELEBRATION_EMOJI } from "@/lib/myPlayer";
import { haptic, hapticNotify } from "@/lib/telegram";

const KIND_ICON: Record<PlayerCareerMoment["kind"], string> = { attack: "⚡", defense: "🛡️", save: "🧤" };

function deadlineText(iso: string): string {
  return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

/** «Ключевые моменты» of the pending match: each waits for an action and a
 * timing hit; the server rolls the outcome. Open ones go to the coach at the
 * deadline. */
export default function KeyMoments({
  view, onView, onError,
}: { view: PlayerCareerView; onView: (v: PlayerCareerView) => void; onError: (e: unknown) => void }) {
  const pending = view.pending;
  const [active, setActive] = useState<PlayerCareerMoment | null>(null);
  // The popup outlives the section: the last moment finalizes the match and
  // clears `pending`, but the player still has to see how it went.
  const modal = (
    <AnimatePresence>
      {active && (
        <MomentModal
          moment={active}
          celebration={view.player?.celebration ?? null}
          onDone={(v) => onView(v)}
          onError={onError}
          onClose={() => setActive(null)}
        />
      )}
    </AnimatePresence>
  );
  const me = pending ? view.season?.rounds[pending.round]?.me : null;
  const open = pending ? pending.moments.filter((m) => m.status === "open").length : 0;
  return (
    <>
      {pending && (
        <section className="flex flex-col gap-2 rounded-2xl bg-gradient-to-br from-accent-lime/25 to-bg-surface p-4 ring-1 ring-accent-lime/40" data-testid="key-moments">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-base font-bold text-ink-chalk">⚡ Ключевые моменты</h2>
            <span className="text-caption text-ink-mist">до {deadlineText(pending.deadline)}</span>
          </div>
          <p className="text-caption text-ink-mist">
            Тур {pending.round + 1}{me ? ` · «${me.opponent}» · пока ${me.own}:${me.opp}` : ""}. Реши исход сам — иначе в {deadlineText(pending.deadline)} за тебя решит тренер.
          </p>
          {pending.moments.map((m) => (
            <div key={m.i} className="flex items-center gap-3 rounded-xl bg-bg-raised p-3">
              <span className="text-2xl">{KIND_ICON[m.kind]}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-ink-chalk">{m.minute}′ · {m.text}</span>
                {m.status === "done" && (
                  <span className={`block text-caption font-semibold ${m.success ? "text-accent-lime" : "text-red-400"}`}>
                    {m.options.find((o) => o.code === m.choice)?.label}: {m.success ? "получилось!" : "не вышло"}
                  </span>
                )}
              </span>
              {m.status === "open" ? (
                <button
                  onClick={() => { haptic("medium"); setActive(m); }}
                  className="shrink-0 rounded-lg bg-floodlight px-3 py-1.5 text-xs font-bold text-bg-base"
                >
                  Играть
                </button>
              ) : (
                <span className="text-lg">{m.success ? "✅" : "❌"}</span>
              )}
            </div>
          ))}
          {open === 0 && <p className="text-center text-caption text-ink-mist">Все моменты сыграны — итог матча уже в таблице</p>}
        </section>
      )}
      {modal}
    </>
  );
}

const ZONE = 16;
const SPEED = 1.25;

function MomentModal({
  moment, celebration, onDone, onError, onClose,
}: {
  moment: PlayerCareerMoment;
  celebration: string | null;
  onDone: (v: PlayerCareerView) => void;
  onError: (e: unknown) => void;
  onClose: () => void;
}) {
  const [option, setOption] = useState<string | null>(null);
  const [pos, setPos] = useState(0);
  const [zone] = useState(() => 12 + Math.random() * (76 - ZONE));
  const [result, setResult] = useState<{ success: boolean; hit: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const frame = useRef(0);
  const play = useMutation({
    mutationFn: ({ hit }: { hit: boolean }) => playPlayerCareerMoment(moment.i, option!, hit),
    onSuccess: (v, { hit }) => {
      const success = !!v.moment_result?.success;
      hapticNotify(success ? "success" : "error");
      setResult({ success, hit });
      onDone(v);
    },
    onError: (err) => { setError(formatGameError(err, "Не получилось")); onError(err); },
  });

  useEffect(() => {
    if (!option || result || play.isPending) return;
    const begin = performance.now();
    const tick = (now: number) => {
      const t = ((now - begin) / 1000) * SPEED * 100;
      const v = t % 200;
      setPos(v <= 100 ? v : 200 - v);
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [option, result, play.isPending]);

  const strike = () => {
    cancelAnimationFrame(frame.current);
    const hit = pos >= zone && pos <= zone + ZONE;
    haptic(hit ? "heavy" : "light");
    play.mutate({ hit });
  };
  const goal = moment.kind === "attack";
  const chosen = moment.options.find((o) => o.code === option);

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/75"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={result || error ? onClose : undefined}
    >
      <motion.div
        className="w-full max-w-lg rounded-t-3xl bg-bg-surface p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))]"
        initial={{ y: 80 }} animate={{ y: 0 }}
        onClick={(e) => e.stopPropagation()}
        data-testid="moment-modal"
      >
        <p className="font-display text-lg font-bold text-ink-chalk">{moment.minute}′ · {KIND_ICON[moment.kind]} {moment.text}</p>
        {!option && (
          <div className="mt-3 flex flex-col gap-2">
            {moment.options.map((o) => (
              <button
                key={o.code}
                onClick={() => { haptic("light"); setOption(o.code); }}
                className="flex items-center justify-between rounded-xl bg-bg-raised p-3 text-left active:scale-[0.99]"
              >
                <span className="text-sm font-semibold text-ink-chalk">{o.label}</span>
                <span className="text-caption text-ink-mist">
                  {o.chance}% · <b className="text-accent-lime">{o.chance_hit}%</b> с таймингом
                </span>
              </button>
            ))}
          </div>
        )}
        {option && !result && (
          <>
            <p className="mt-2 text-caption text-ink-mist">
              {chosen?.label}: попади в зелёную зону — шанс {chosen?.chance_hit}% вместо {chosen?.chance}%
            </p>
            <div className="relative mt-4 h-14 overflow-hidden rounded-2xl bg-bg-raised" data-testid="moment-bar">
              <div className="absolute inset-y-0 bg-accent-lime/35 ring-2 ring-accent-lime" style={{ left: `${zone}%`, width: `${ZONE}%` }} />
              <div
                className="absolute top-1/2 h-9 w-9 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white text-center text-xl leading-9 shadow"
                style={{ left: `${pos}%` }}
              >
                {goal ? "⚽" : "🛡️"}
              </div>
            </div>
            <button
              disabled={play.isPending}
              onClick={strike}
              className="mt-4 w-full rounded-2xl bg-floodlight py-4 font-display text-lg font-bold text-bg-base disabled:opacity-50 active:scale-[0.98]"
            >
              {play.isPending ? "…" : goal ? "Сейчас!" : "Стоп!"}
            </button>
          </>
        )}
        {result && (
          <motion.div className="mt-4 text-center" initial={{ scale: 0.6 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 260, damping: 14 }}>
            <p className={`font-display text-4xl font-black ${result.success ? "text-accent-lime" : "text-red-400"}`}>
              {result.success ? (goal ? (option === "pass" ? "ГОЛЕВОЙ ПАС!" : "ГОЛ!") : "СПАС!") : goal ? "Мимо…" : "Пропустили…"}
            </p>
            {result.success && goal && option !== "pass" && celebration && (
              <motion.p className="mt-1 text-5xl" initial={{ rotate: -20, y: 10 }} animate={{ rotate: 0, y: 0 }}>
                {CELEBRATION_EMOJI[celebration] ?? "🎉"}
              </motion.p>
            )}
            <p className="mt-1 text-caption text-ink-mist">{result.hit ? "Тайминг идеальный!" : "Тайминг мимо зоны"}</p>
            <button onClick={onClose} className="mt-3 w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base">Дальше</button>
          </motion.div>
        )}
        {error && <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
      </motion.div>
    </motion.div>
  );
}
