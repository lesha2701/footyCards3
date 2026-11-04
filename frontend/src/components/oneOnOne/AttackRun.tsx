import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent, type RefObject } from "react";

import ErrorBoundary from "@/components/common/ErrorBoundary";
import { IconCoin } from "@/components/icons";
import SceneCrash from "@/components/freeKick3d/SceneCrash";
import { OutcomeCaption, ScoreBug } from "@/components/oneOnOne/Broadcast";
import FeintPicker from "@/components/oneOnOne/FeintPicker";
import OneOnOneScene3D, { type LiveInput } from "@/components/oneOnOne/OneOnOneScene3D";
import { formatGameError } from "@/lib/errors";
import { useCrashLog } from "@/lib/freeKick3d/crashLog";
import { crowdChant, crowdHush, crowdTension, playFreeKickSfx, startCrowd } from "@/lib/freeKick3d/sfx";
import type { ShotIntent } from "@/lib/oneOnOne/aim";
import { createEpisode, type EpisodeEnd, type EpisodeTimeline } from "@/lib/oneOnOne/engine";
import { Finger, Stick } from "@/lib/oneOnOne/gesture";
import { EpisodeRecorder } from "@/lib/oneOnOne/recorder";
import { PASS_CROSS, PASS_CUTBACK, PASS_GROUND, PASS_THROUGH, createTeamEpisode, inChipZone, type TeamKind } from "@/lib/oneOnOne/team";
import { FOOT_LABEL, KIND_LABEL, techniqueOf } from "@/lib/oneOnOne/technique";
import { audio } from "@/lib/sound";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { OneOnOneOutcome, OneOnOneResult } from "@/types";

const BONUS: Record<OneOnOneResult["bonuses"][number], string> = {
  feint: "после финта",
  chip: "парашютом",
};

/** A button's power bar fills over this (ms) after a tap's length, a tap
 * being its quick version, and is red past the top of the goal. */
const CHARGE_MS = 900;
const TAP_GRACE_MS = 200;
const OVER_POWER = 0.9;
/** A thumb this far off a button's centre (its widths) still presses it. */
const BUTTON_REACH = 0.65;
const BAR_R = 46;
const BAR_LENGTH = 2 * Math.PI * BAR_R;
/** The round buttons beside the shot: dark, one thin edge, an icon over a word. */
const ACTION_FACE =
  "flex h-full w-full flex-col items-center justify-center gap-0.5 rounded-full border-2 bg-black/60 text-[10px] font-semibold leading-none shadow-[0_2px_10px_rgba(0,0,0,0.5)]";
const ACTION_ICON = {
  viewBox: "0 0 24 24",
  className: "h-5 w-5",
  fill: "none",
  strokeWidth: 2.4,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

/** The bar round a button (an SVG ring the page fills by its ref). */
function PowerRing({ barRef }: { barRef: RefObject<SVGCircleElement> }) {
  return (
    <svg viewBox="0 0 100 100" className="pointer-events-none absolute -inset-1.5 h-[calc(100%+12px)] w-[calc(100%+12px)] -rotate-90">
      <circle
        ref={barRef}
        cx={50}
        cy={50}
        r={BAR_R}
        fill="none"
        stroke="#fff"
        strokeWidth={6}
        strokeLinecap="round"
        strokeDasharray={BAR_LENGTH}
        strokeDashoffset={BAR_LENGTH}
      />
    </svg>
  );
}

/** What an attack needs to be played, whatever it is part of; `kind` — a
 * team episode (team.ts), none — one on one. */
export type AttackRunProps = {
  seed: number;
  kind?: TeamKind;
  index: number;
  total: number;
  rating: number;
  name: string;
  ball?: string | null;
  feint?: string | null;
  coins: number;
  results: OneOnOneOutcome[];
  nextLabel: string;
  /** Hands the timeline to whoever decides the outcome. */
  submit: (timeline: EpisodeTimeline) => Promise<OneOnOneResult>;
  onBack: () => void;
  onFeint: (code: string | null) => void;
  onResult: (r: OneOnOneResult) => void;
  onNext: (r: OneOnOneResult) => void;
};

const freshInput = (): LiveInput => ({
  live: false, hold: 0, steer: 0, feint: 0, shot: null, aiming: false, aim: 0, power: null, lob: false, pass: null, back: false, stride: null,
});

/** One attack: the 3D episode, the two thumbs, the verdict. */
export default function AttackRun({
  seed,
  kind,
  index,
  total,
  rating,
  name,
  ball,
  feint: feintStyle,
  coins,
  results,
  nextLabel,
  submit: submitTimeline,
  onBack,
  onFeint,
  onResult,
  onNext,
}: AttackRunProps) {
  const setup = useMemo(() => (kind ? createTeamEpisode(kind, seed, rating) : createEpisode(seed, rating)), [kind, seed, rating]);
  const recorder = useMemo(() => new EpisodeRecorder(setup), [setup]);
  const input = useRef<LiveInput>(freshInput());
  const stick = useRef(new Stick(window.innerWidth, window.innerHeight));
  const pad = useRef(new Finger(window.innerWidth, window.innerHeight));
  const knob = useRef<HTMLDivElement | null>(null);
  const anchor = useRef<HTMLDivElement | null>(null);
  const homeStick = useRef<HTMLDivElement | null>(null);
  const loftBtn = useRef<HTMLDivElement | null>(null);
  const passBtn = useRef<HTMLDivElement | null>(null);
  const throughBtn = useRef<HTMLDivElement | null>(null);
  const pointers = useRef<(HTMLDivElement | null)[]>([]);
  const shotBar = useRef<SVGCircleElement | null>(null);
  const loftBar = useRef<SVGCircleElement | null>(null);
  // The button held now: which, since when (performance.now), and whether
  // the press turned into a feint (then letting go is no shot).
  const press = useRef<{ kind: "pad" | "chip" | "cross"; at: number; feinted: boolean } | null>(null);
  const fpsRef = useRef<HTMLSpanElement | null>(null);
  const crashLog = useCrashLog();
  const [ready, setReady] = useState(false);
  const [started, setStarted] = useState(false);
  const [feintUsed, setFeintUsed] = useState(false);
  // What the lofted button does here; with nobody to find, always the chip.
  const [chipHere, setChipHere] = useState(true);
  const [ended, setEnded] = useState<EpisodeEnd | null>(null);
  const [shown, setShown] = useState(false);

  const play = useMutation({
    mutationFn: () => submitTimeline(recorder.timeline),
    onSuccess: onResult,
  });
  const verdict = play.data;

  useEffect(() => startCrowd(), []);
  useEffect(() => {
    if (ready) crowdChant();
  }, [ready]);
  useEffect(() => {
    const onResize = () => {
      stick.current.resize(window.innerWidth, window.innerHeight);
      pad.current.resize(window.innerWidth, window.innerHeight);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!kind) return;
    let frame = 0;
    const look = () => {
      // Pressed, the button stays what it was.
      if (!press.current) setChipHere(inChipZone(recorder.state));
      frame = requestAnimationFrame(look);
    };
    look();
    return () => cancelAnimationFrame(frame);
  }, [kind, recorder]);

  const onReady = useCallback(() => setReady(true), []);
  const { mutate: submit } = play;
  const onEnded = useCallback(
    (end: EpisodeEnd) => {
      setEnded(end);
      submit();
    },
    [submit],
  );
  const onDecided = useCallback(() => setShown(true), []);
  // Which foot and how (shown with the outcome; the same for this timeline).
  const technique = useMemo(() => (ended ? techniqueOf(recorder.state, recorder.timeline, input.current.stride) : null), [ended, recorder]);

  // The crowd reacts the moment the outcome is on screen — on the local
  // episode, which is the server's own computation.
  const local = shown ? ended?.outcome ?? null : null;
  useEffect(() => {
    if (!local) return;
    crowdHush();
    crowdTension(false);
    hapticNotify(local === "goal" ? "success" : local === "save" || local === "tackle" ? "warning" : "error");
    playFreeKickSfx(local === "goal" ? "roar" : "groan");
  }, [local]);

  const playing = ready && !ended;
  const placeStick = () => {
    const st = stick.current.read();
    const r = stick.current.radius;
    if (anchor.current) {
      anchor.current.style.opacity = stick.current.down ? "1" : "0";
      anchor.current.style.width = anchor.current.style.height = `${r * 2}px`;
      anchor.current.style.transform = `translate(${st.anchor.x - r}px, ${st.anchor.y - r}px)`;
      anchor.current.style.borderColor = st.hold === 2 ? "rgba(198,230,58,1)" : "rgba(255,255,255,0.85)";
    }
    // The resting stick steps aside while the thumb holds the live one.
    if (homeStick.current) homeStick.current.style.opacity = stick.current.down ? "0" : "1";
    if (knob.current) {
      knob.current.style.opacity = stick.current.down ? "1" : "0";
      knob.current.style.transform = `translate(${st.knob.x - 20}px, ${st.knob.y - 20}px)`;
    }
  };
  const syncStick = () => {
    const st = stick.current.read();
    input.current.hold = st.hold;
    input.current.back = st.hold === 3;
    // While the right thumb is down the lean aims the shot and no longer
    // turns him (else aiming at a corner runs him off towards it).
    input.current.aim = st.steer;
    input.current.steer = input.current.aiming ? 0 : st.steer;
    placeStick();
  };
  // Which finger is which: the one that came down on the left half is the
  // stick, on the right half the action thumb (on the lofted button — the
  // chip or the cross).
  const fingers = useRef(new Map<number, "stick" | "pad" | "chip" | "cross">());

  /** The power bar of the button held: fills over CHARGE_MS from the end of
   * a tap on, red once it is past the top of the goal. */
  const powerOf = (p: NonNullable<typeof press.current>, now: number) =>
    Math.min(1, Math.max(0, now - p.at - TAP_GRACE_MS) / CHARGE_MS);
  const drawBars = () => {
    const p = press.current;
    const power = p && !p.feinted ? powerOf(p, performance.now()) : 0;
    input.current.power = p && !p.feinted ? power : null;
    input.current.lob = p?.kind === "chip";
    for (const [bar, held] of [[shotBar.current, p?.kind === "pad"], [loftBar.current, !!p && p.kind !== "pad"]] as const) {
      if (!bar) continue;
      const k = held ? power : 0;
      bar.style.strokeDashoffset = `${BAR_LENGTH * (1 - k)}`;
      bar.style.stroke = k > OVER_POWER ? "#f87171" : "#fff";
    }
    if (p) requestAnimationFrame(drawBars);
  };
  const startPress = (kind: "pad" | "chip" | "cross") => {
    press.current = { kind, at: performance.now(), feinted: false };
    // Holding a cross he keeps running: the stick still steers him.
    input.current.aiming = kind !== "cross";
    syncStick();
    requestAnimationFrame(drawBars);
  };
  const endPress = () => {
    const p = press.current;
    press.current = null;
    input.current.aiming = false;
    syncStick();
    drawBars();
    const now = performance.now();
    return { power: p ? powerOf(p, now) : 0, tap: !!p && now - p.at < TAP_GRACE_MS };
  };
  const shootNow = (shot: ShotIntent) => {
    input.current.shot = shot;
    haptic("medium");
    crowdTension(true);
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!playing) return;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Not every WebView lets a pointer be captured; the controls still work.
    }
    audio(); // resume the audio context inside the gesture (mobile autoplay rules)
    input.current.live = true;
    if (!started) setStarted(true);
    const left = e.clientX < window.innerWidth / 2;
    // How far off a button the thumb came down, in its widths.
    const off = (el: HTMLElement | null) => {
      const r = el?.getBoundingClientRect();
      return r ? Math.hypot(e.clientX - (r.left + r.width / 2), e.clientY - (r.top + r.height / 2)) / r.width : Infinity;
    };
    const toPass = off(passBtn.current);
    const toThrough = off(throughBtn.current);
    const toLoft = off(loftBtn.current);
    // The nearest of them; past the buttons the right half is the shot.
    const onButton = Math.min(toPass, toThrough, toLoft) < BUTTON_REACH;
    if (left && !stick.current.down) {
      fingers.current.set(e.pointerId, "stick");
      stick.current.start({ x: e.clientX, y: e.clientY });
      syncStick();
    } else if (!left && !press.current && onButton && toLoft <= Math.min(toPass, toThrough)) {
      const what = !kind || inChipZone(recorder.state) ? "chip" : "cross";
      fingers.current.set(e.pointerId, what);
      startPress(what);
    } else if (!left && !press.current && onButton) {
      // A pass goes on the press: the moment is the whole point of it.
      input.current.pass = { mode: toPass < toThrough ? PASS_GROUND : PASS_THROUGH, power: 0 };
      haptic("light");
    } else if (!left && !press.current && !pad.current.down) {
      fingers.current.set(e.pointerId, "pad");
      pad.current.start({ x: e.clientX, y: e.clientY, t: e.timeStamp });
      startPress("pad");
    }
  };
  const feint = (dir: number) => {
    if (dir === 0 || feintUsed || recorder.state.feintUsed) return;
    input.current.feint = dir;
    setFeintUsed(true);
    haptic("light");
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const role = fingers.current.get(e.pointerId);
    if (!playing || !role) return;
    if (role === "stick") {
      stick.current.move({ x: e.clientX, y: e.clientY });
      syncStick();
    } else if (role === "pad") {
      const dir = pad.current.move({ x: e.clientX, y: e.clientY, t: e.timeStamp });
      if (dir !== 0 && press.current) press.current.feinted = true;
      feint(dir);
    }
  };
  const release = (e: PointerEvent<HTMLDivElement>, cancelled: boolean) => {
    const role = fingers.current.get(e.pointerId);
    fingers.current.delete(e.pointerId);
    if (role === "stick") {
      stick.current.end();
      syncStick();
    } else if (role === "cross") {
      // A tap is the cut-back; the bar the cross, from low and short to high
      // and long.
      const { power, tap } = endPress();
      if (!cancelled && playing) {
        input.current.pass = tap ? { mode: PASS_CUTBACK, power: 0 } : { mode: PASS_CROSS, power: Math.round(power * 100) };
        haptic("light");
      }
    } else if (role === "chip") {
      const { power, tap } = endPress();
      if (!cancelled && playing) shootNow(tap ? { kind: "auto", chip: true } : { kind: "chip", power, aim: input.current.aim / 1000 });
    } else if (role === "pad") {
      const feinted = press.current?.feinted;
      const { power } = endPress();
      if (cancelled) return pad.current.cancel();
      const intent = pad.current.end({ x: e.clientX, y: e.clientY, t: e.timeStamp });
      if (!playing || feinted) return;
      // As in FIFA: where it goes is the left stick's lean; the button held
      // and let go is a drive as hard as its bar, a swipe up off it the
      // finesse, a tap leaves it all to the striker.
      const aim = input.current.aim / 1000;
      if (intent.feint) feint(intent.feint);
      else if (intent.shot) shootNow({ kind: "finesse", swipe: intent.shot, aim });
      else if (intent.tap) shootNow({ kind: "auto" });
      else shootNow({ kind: "drive", power, aim });
    }
  };

  const outcome = shown && verdict ? verdict.outcome : null;
  const loftIsChip = !kind || chipHere;

  return (
    <div className="fixed inset-0 z-50 select-none overflow-hidden bg-bg-base text-ink-chalk">
      <ErrorBoundary fallback={(error, retry) => <SceneCrash error={error} retry={retry} log={crashLog.current} />}>
        <OneOnOneScene3D
          setup={setup}
          recorder={recorder}
          input={input}
          onEnded={onEnded}
          onDecided={onDecided}
          onReady={onReady}
          fpsRef={fpsRef}
          ball={ball}
          feint={feintStyle}
          pointers={pointers}
        />
      </ErrorBoundary>

      {kind &&
        [0, 1].map((i) => (
          <div
            key={i}
            ref={(el) => {
              pointers.current[i] = el;
            }}
            className="pointer-events-none absolute left-0 top-0 opacity-0 drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]"
            aria-hidden
          >
            <svg viewBox="0 0 24 24" className="h-9 w-9" fill="currentColor">
              <path d="M6 3 L21 12 L6 21 L10 12 Z" />
            </svg>
          </div>
        ))}

      {/* Touch surface over the canvas; the stick shows where the finger steers from. */}
      <div
        className="absolute inset-0"
        style={{ touchAction: "none" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={(e) => release(e, false)}
        onPointerCancel={(e) => release(e, true)}
      >
        <div
          ref={anchor}
          className="pointer-events-none absolute left-0 top-0 rounded-full border-[3px] border-white/85 bg-black/45 opacity-0 shadow-lg"
        />
        <div
          ref={knob}
          className="pointer-events-none absolute left-0 top-0 h-10 w-10 rounded-full border-2 border-black/50 bg-accent-lime opacity-0 shadow-lg"
        />
        {playing && (
          // Where the thumbs go: shown the whole attack, dark enough to read
          // over the pitch; the labels only until the first touch.
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-between px-5 text-center text-caption font-semibold text-white [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]"
            style={{ paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 36px)" }}
          >
            <div
              ref={homeStick}
              className="flex h-24 w-24 flex-col items-center justify-center rounded-full border-2 border-white/30 bg-black/60 shadow-[0_2px_10px_rgba(0,0,0,0.5)] transition-opacity"
            >
              {started ? (
                <div className="h-10 w-10 rounded-full border-2 border-black/50 bg-accent-lime/80" />
              ) : (
                <>
                  Бег
                  <span className="px-2 font-normal leading-tight text-white/80">край — спринт, вниз — назад</span>
                </>
              )}
            </div>
            <div className="relative h-20 w-20">
              <PowerRing barRef={shotBar} />
              <div className="flex h-full w-full flex-col items-center justify-center rounded-full bg-accent-lime text-sm font-bold text-black shadow-[0_2px_12px_rgba(0,0,0,0.6)] [text-shadow:none]">
                Удар
                {!started && <span className="px-2 text-[10px] font-medium leading-tight text-black/70">держи, ↑ — закрутка</span>}
              </div>
              {started && (
                <div className="absolute inset-x-0 -bottom-5 flex items-center justify-center gap-1 text-[10px] font-semibold leading-none">
                  <span className={`h-1.5 w-1.5 rounded-full ${feintUsed ? "bg-white/30" : "bg-accent-lime"}`} />
                  <span className={feintUsed ? "text-white/50" : ""}>финт</span>
                </div>
              )}
              {/* The others on one arc round it, by the thumb. */}
              {kind && (
                <div ref={passBtn} className="absolute -top-[70px] left-[7px] h-[52px] w-[52px]">
                  <div className={`${ACTION_FACE} border-white/30`}>
                    <svg {...ACTION_ICON} stroke="#fff">
                      <path d="M4 12 H19" />
                      <path d="M13.5 6.5 L19.5 12 L13.5 17.5" />
                    </svg>
                    Пас
                  </div>
                </div>
              )}
              {kind && (
                <div ref={throughBtn} className="absolute -left-[70px] top-[21px] h-[52px] w-[52px]">
                  <div className={`${ACTION_FACE} border-white/30`}>
                    <svg {...ACTION_ICON} stroke="#fff">
                      <path d="M5 4 V9 M5 15 V20" />
                      <path d="M2 12 H21" />
                      <path d="M16 7 L21.5 12 L16 17" />
                    </svg>
                    Разрез
                  </div>
                </div>
              )}
              {/* The lofted ball: says what it will be here. */}
              <div ref={loftBtn} className="absolute -left-[50px] -top-[40px] h-[52px] w-[52px]">
                <PowerRing barRef={loftBar} />
                {loftIsChip ? (
                  <div className={`${ACTION_FACE} border-amber-300/80`}>
                    <svg {...ACTION_ICON} stroke="#fcd34d">
                      <path d="M4 15 Q12 -3 20 15" />
                      <path d="M12 15 V21" />
                    </svg>
                    Парашют
                  </div>
                ) : (
                  <div className={`${ACTION_FACE} border-sky-300/80`}>
                    <svg {...ACTION_ICON} stroke="#7dd3fc">
                      <path d="M3 19 Q10 2 21 15" />
                      <path d="M21.5 9.5 L21 15.5 L15.5 14" />
                    </svg>
                    Навес
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-4">
        <button
          type="button"
          onClick={onBack}
          aria-label="Выйти"
          className="pointer-events-auto flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 border-white/30 bg-black/60 shadow-[0_2px_10px_rgba(0,0,0,0.5)]"
        >
          <svg {...ACTION_ICON} className="h-4 w-4" stroke="#fff">
            <path d="M12 3 V11" />
            <path d="M6.8 6.5 A8 8 0 1 0 17.2 6.5" />
          </svg>
        </button>
        <div>
          <ScoreBug
            index={index}
            total={total}
            results={results}
            coins={coins}
            name={name}
            rating={rating}
          />
          <span ref={fpsRef} className="hidden" />
        </div>
      </div>

      {!started && (
        <div className="pointer-events-none absolute inset-x-0 top-24 px-6 text-center text-sm text-ink-chalk/90 drop-shadow">
          {ready ? (
            <>
              Джойстик — бег, до края — спринт, вниз — назад, наклон — угол удара.
              <br />
              «Удар»: держи — сила (выше), ↑ — закрутка, тап — авто, рывок вбок — финт.
              <br />
              «Парашют»: держи — сила, тап — авто.
              {kind && (
                <>
                  <br />
                  «Пас» — низом, «Разрез» — на ход. С фланга вместо «Парашюта» «Навес»: держи — сила и высота, тап —
                  прострел.
                </>
              )}
            </>
          ) : (
            "Загружаем…"
          )}
          {ready && (
            <div className="mt-3 flex justify-center">
              <FeintPicker value={feintStyle ?? null} onChange={onFeint} />
            </div>
          )}
        </div>
      )}

      {shown && !verdict && play.isPending && (
        <div className="absolute inset-x-0 bottom-10 text-center text-sm text-ink-mist">Судья смотрит повтор…</div>
      )}

      {play.isError && (
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-2 p-6 pb-10">
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {formatGameError(play.error, "Атака не засчитана")}
          </p>
          <button type="button" onClick={() => play.mutate()} className="rounded-xl bg-accent px-6 py-3 font-semibold text-black">
            Отправить ещё раз
          </button>
        </div>
      )}

      <OutcomeCaption outcome={local} />

      {outcome && verdict && (
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-2 bg-gradient-to-t from-bg-base/90 to-transparent p-6 pb-10 pt-16">
          {technique && (
            <div className="text-sm text-ink-chalk">
              {FOOT_LABEL[technique.foot]} {KIND_LABEL[technique.kind]}
            </div>
          )}
          {(verdict.bonuses.length > 0 || verdict.feint) && (
            <div className="text-caption text-ink-chalk/80">
              {verdict.bonuses.length > 0
                ? verdict.bonuses.map((b) => (b === "chip" && technique?.kind === "chip" ? "бонус за парашют" : BONUS[b])).join(", ")
                : verdict.feint === "read"
                  ? "вратарь не купился на финт"
                  : "вратарь купился на финт"}
            </div>
          )}
          {verdict.coins_this_attack > 0 && (
            <div className="flex items-center gap-1 font-mono text-lg font-bold text-accent-lime">
              +{verdict.coins_this_attack}
              <IconCoin size={16} />
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              // Same scene, next attack: no WebGL context churn between attacks.
              input.current = freshInput();
              stick.current.end();
              pad.current.cancel();
              fingers.current.clear();
              placeStick();
              setStarted(false);
              setFeintUsed(false);
              setEnded(null);
              setShown(false);
              play.reset();
              onNext(verdict);
            }}
            className="mt-1 rounded-xl bg-accent px-6 py-3 font-semibold text-black">
            {nextLabel}
          </button>
        </div>
      )}
    </div>
  );
}
