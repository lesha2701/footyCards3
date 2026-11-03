import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent, type RefObject } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import { claimOneOnOneReward, playOneOnOneAttack, startOneOnOne } from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import ErrorBoundary from "@/components/common/ErrorBoundary";
import GameHero from "@/components/common/GameHero";
import { IconCoin } from "@/components/icons";
import SceneCrash from "@/components/freeKick3d/SceneCrash";
import OneOnOneScene3D, { type LiveInput } from "@/components/oneOnOne/OneOnOneScene3D";
import { formatGameError } from "@/lib/errors";
import { useCrashLog } from "@/lib/freeKick3d/crashLog";
import { crowdChant, crowdHush, crowdTension, playFreeKickSfx, startCrowd } from "@/lib/freeKick3d/sfx";
import type { ShotIntent } from "@/lib/oneOnOne/aim";
import { createEpisode, type EpisodeEnd } from "@/lib/oneOnOne/engine";
import { Finger, Stick } from "@/lib/oneOnOne/gesture";
import { EpisodeRecorder } from "@/lib/oneOnOne/recorder";
import { FOOT_LABEL, KIND_LABEL, techniqueOf } from "@/lib/oneOnOne/technique";
import { audio } from "@/lib/sound";
import { haptic, hapticNotify, showConfirm } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { OneOnOneAttack, OneOnOneOutcome, OneOnOneResult, OneOnOneStartResult, UserCard } from "@/types";

const OUTCOME: Record<OneOnOneOutcome, { label: string; className: string }> = {
  goal: { label: "ГОЛ!", className: "text-accent-lime" },
  save: { label: "Сейв", className: "text-accent-cyan" },
  tackle: { label: "Вратарь забрал", className: "text-accent-cyan" },
  miss: { label: "Мимо", className: "text-ink-mist" },
  lost: { label: "Момент упущен", className: "text-ink-mist" },
};

const BONUS: Record<OneOnOneResult["bonuses"][number], string> = {
  feint: "после финта",
  chip: "парашютом",
};

type Series = OneOnOneStartResult & { card: UserCard };

/** «Атака 1 на 1»: pick a card, then a series of breakaways at the keeper
 * from server-chosen spots. The episode runs here from the finger, frame
 * for frame what the server will replay from the input timeline it gets —
 * the server alone decides the outcome and the coins. */
export default function OneOnOnePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [series, setSeries] = useState<Series | null>(null);
  const [attack, setAttack] = useState<OneOnOneAttack | null>(null);
  const [results, setResults] = useState<OneOnOneResult[]>([]);
  const [finished, setFinished] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [cardSearch, setCardSearch] = useState("");

  const { data: collection } = useQuery({
    queryKey: ["collection", "one-on-one", cardSearch],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: cardSearch || undefined }),
    enabled: series === null,
  });

  const start = useMutation({
    mutationFn: (card: UserCard) => startOneOnOne(card.id).then((data) => ({ ...data, card })),
    onSuccess: (data) => {
      setSeries(data);
      setAttack(data.attack);
      setResults([]);
      setFinished(false);
      setErrorMsg(null);
      void queryClient.invalidateQueries({ queryKey: ["game-limits"] });
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать серию")),
  });

  const claim = useMutation({
    mutationFn: () => claimOneOnOneReward(series!.session_id),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
    },
  });

  if (!series || !attack) {
    return (
      <div className="flex flex-col gap-5">
        <GameHero game="one-on-one" title="Атака 1 на 1" />
        <p className="text-sm text-ink-mist">
          Выход один на один с вратарём, управление как в FIFA. Левый палец — джойстик: веди игрока с мячом, до края —
          спринт; куда он наклонён в момент удара — туда и летит мяч. «Удар»: держи и отпусти — удар подъёмом, чем
          дольше держишь, тем сильнее и выше (шкала покраснела — над перекладиной); свайп вверх с кнопки — удар на
          закрутку; тап — игрок всё выберет сам. Маленькая кнопка — парашют. Резкий рывок вбок с «Удара» — финт
          (поймаешь вратаря на нём — он провалится).
        </p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <CardPickerModal
          open={!start.isPending}
          title="Кто выходит один на один?"
          cards={collection?.items ?? []}
          onSelect={(card) => start.mutate(card)}
          onClose={() => navigate("/play")}
          searchValue={cardSearch}
          onSearchChange={setCardSearch}
        />
      </div>
    );
  }

  const total = results.length ? results[results.length - 1].total_coins : 0;

  if (finished) {
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        <p className="font-display text-2xl font-bold text-ink-chalk">Серия завершена</p>
        <div className="flex flex-wrap justify-center gap-2">
          {results.map((r, i) => (
            <span key={i} className={`rounded-lg bg-bg-surface px-2 py-1 text-xs font-semibold ${OUTCOME[r.outcome].className}`}>
              {OUTCOME[r.outcome].label}
            </span>
          ))}
        </div>
        <p className="text-sm text-ink-mist">
          Голов: {results.filter((r) => r.outcome === "goal").length} из {results.length} · Итог:{" "}
          <span className="inline-flex items-center gap-1 font-mono font-bold text-accent-lime">
            {total}
            <IconCoin size={14} />
          </span>
        </p>
        {claim.isPending ? (
          <p className="text-sm text-ink-mist">Начисление награды...</p>
        ) : claim.data ? (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              Ты получил +{claim.data.reward_coins}
              <IconCoin size={16} />
            </p>
            {claim.data.reward_coins === 0 && total > 0 && (
              <p className="mt-1 text-xs text-ink-mist">Лимит наградных серий на сегодня исчерпан</p>
            )}
          </div>
        ) : claim.isError ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(claim.error, "Не удалось начислить награду")}
          </p>
        ) : null}
        <button
          onClick={() => start.mutate(series.card)}
          disabled={start.isPending}
          className="rounded-2xl bg-accent px-6 py-3 font-semibold text-black disabled:opacity-50"
        >
          {start.isPending ? "Начинаем…" : "Сыграть ещё серию"}
        </button>
        {start.isError && (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(start.error, "Не удалось начать серию")}
          </p>
        )}
        <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
          Вернуться к играм
        </button>
      </div>
    );
  }

  return (
    <AttackRun
      series={series}
      attack={attack}
      total={total}
      onBack={async () => {
        if (await showConfirm("Серия не закончена — оставшиеся атаки сгорят. Выйти?")) navigate("/play");
      }}
      onResult={(r) => setResults((prev) => [...prev, r])}
      onNext={(r) => {
        if (r.next_attack) setAttack(r.next_attack);
        else {
          setFinished(true);
          claim.mutate();
        }
      }}
    />
  );
}

/** The shot button's power bar fills over this (ms) — after a tap's length
 * for the shot button, a tap there being the auto shot — and is red past
 * the top of the goal. */
const CHARGE_MS = 900;
const TAP_GRACE_MS = 200;
const OVER_POWER = 0.9;
const BAR_R = 46;
const BAR_LENGTH = 2 * Math.PI * BAR_R;

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
        stroke="#c6e63a"
        strokeWidth={6}
        strokeLinecap="round"
        strokeDasharray={BAR_LENGTH}
        strokeDashoffset={BAR_LENGTH}
      />
    </svg>
  );
}

/** One attack: the 3D episode, the two thumbs, the server's verdict. */
function AttackRun({
  series,
  attack,
  total,
  onBack,
  onResult,
  onNext,
}: {
  series: Series;
  attack: OneOnOneAttack;
  total: number;
  onBack: () => void;
  onResult: (r: OneOnOneResult) => void;
  onNext: (r: OneOnOneResult) => void;
}) {
  const setup = useMemo(() => createEpisode(attack.seed, series.rating), [attack.seed, series.rating]);
  const recorder = useMemo(() => new EpisodeRecorder(setup), [setup]);
  const input = useRef<LiveInput>({ live: false, hold: 0, steer: 0, feint: 0, shot: null, aiming: false, aim: 0, power: null, lob: false });
  const stick = useRef(new Stick(window.innerWidth, window.innerHeight));
  const pad = useRef(new Finger(window.innerWidth, window.innerHeight));
  const knob = useRef<HTMLDivElement | null>(null);
  const anchor = useRef<HTMLDivElement | null>(null);
  const homeStick = useRef<HTMLDivElement | null>(null);
  const chipBtn = useRef<HTMLDivElement | null>(null);
  const shotBar = useRef<SVGCircleElement | null>(null);
  const chipBar = useRef<SVGCircleElement | null>(null);
  // The button held now: which, since when (performance.now), and whether
  // the press turned into a feint (then letting go is no shot).
  const press = useRef<{ kind: "pad" | "chip"; at: number; feinted: boolean } | null>(null);
  const fpsRef = useRef<HTMLSpanElement | null>(null);
  const crashLog = useCrashLog();
  const [ready, setReady] = useState(false);
  const [started, setStarted] = useState(false);
  const [feintUsed, setFeintUsed] = useState(false);
  const [ended, setEnded] = useState<EpisodeEnd | null>(null);
  const [shown, setShown] = useState(false);

  const play = useMutation({
    mutationFn: () => playOneOnOneAttack(series.session_id, recorder.timeline),
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
  const technique = useMemo(() => (ended ? techniqueOf(recorder.state, recorder.timeline) : null), [ended, recorder]);

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
      knob.current.style.transform = `translate(${st.knob.x - 22}px, ${st.knob.y - 22}px)`;
    }
  };
  const syncStick = () => {
    const st = stick.current.read();
    input.current.hold = st.hold;
    // While the right thumb is down the lean aims the shot and no longer
    // turns him (else aiming at a corner runs him off towards it).
    input.current.aim = st.steer;
    input.current.steer = input.current.aiming ? 0 : st.steer;
    placeStick();
  };
  // Which finger is which: the one that came down on the left half is the
  // stick, on the right half the action thumb (on the small button — the chip).
  const fingers = useRef(new Map<number, "stick" | "pad" | "chip">());

  /** The power bar of the button held: fills over CHARGE_MS (the shot's
   * from the end of a tap on), red once it is past the top of the goal. */
  const powerOf = (p: NonNullable<typeof press.current>, now: number) =>
    Math.min(1, Math.max(0, now - p.at - (p.kind === "pad" ? TAP_GRACE_MS : 0)) / CHARGE_MS);
  const drawBars = () => {
    const p = press.current;
    const power = p && !p.feinted ? powerOf(p, performance.now()) : 0;
    input.current.power = p && !p.feinted ? power : null;
    input.current.lob = p?.kind === "chip";
    for (const [bar, kind] of [[shotBar.current, "pad"], [chipBar.current, "chip"]] as const) {
      if (!bar) continue;
      const k = p?.kind === kind ? power : 0;
      bar.style.strokeDashoffset = `${BAR_LENGTH * (1 - k)}`;
      bar.style.stroke = k > OVER_POWER ? "#f87171" : "#c6e63a";
    }
    if (p) requestAnimationFrame(drawBars);
  };
  const startPress = (kind: "pad" | "chip") => {
    press.current = { kind, at: performance.now(), feinted: false };
    input.current.aiming = true;
    syncStick();
    requestAnimationFrame(drawBars);
  };
  const endPress = () => {
    const p = press.current;
    press.current = null;
    input.current.aiming = false;
    syncStick();
    drawBars();
    return p ? powerOf(p, performance.now()) : 0;
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
    const chip = chipBtn.current?.getBoundingClientRect();
    const onChip =
      !!chip && Math.hypot(e.clientX - (chip.left + chip.width / 2), e.clientY - (chip.top + chip.height / 2)) < chip.width * 0.75;
    if (left && !stick.current.down) {
      fingers.current.set(e.pointerId, "stick");
      stick.current.start({ x: e.clientX, y: e.clientY });
      syncStick();
    } else if (!left && !press.current && onChip) {
      fingers.current.set(e.pointerId, "chip");
      startPress("chip");
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
    } else if (role === "chip") {
      const power = endPress();
      if (!cancelled && playing) shootNow({ kind: "chip", power, aim: input.current.aim / 1000 });
    } else if (role === "pad") {
      const feinted = press.current?.feinted;
      const power = endPress();
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

  const isLast = attack.attack_index + 1 >= series.total_attacks;
  const outcome = shown && verdict ? verdict.outcome : null;

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
          ball={series.ball}
        />
      </ErrorBoundary>

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
          className="pointer-events-none absolute left-0 top-0 h-11 w-11 rounded-full border-2 border-black/50 bg-accent-lime opacity-0 shadow-lg"
        />
        {playing && (
          // Where the thumbs go: shown the whole attack, dark enough to read
          // over the pitch; the labels only until the first touch.
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-between px-6 pb-24 text-center text-caption font-semibold text-white [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]">
            <div
              ref={homeStick}
              className="flex h-28 w-28 flex-col items-center justify-center rounded-full border-[3px] border-white/70 bg-black/45 shadow-lg transition-opacity"
            >
              {started ? (
                <div className="h-11 w-11 rounded-full border-2 border-black/50 bg-accent-lime/80" />
              ) : (
                <>
                  Бег
                  <span className="font-normal text-white/80">до края — спринт</span>
                </>
              )}
            </div>
            <div className="relative h-28 w-28">
              <PowerRing barRef={shotBar} />
              <div className="flex h-full w-full flex-col items-center justify-center rounded-full border-[3px] border-accent-lime/90 bg-accent-lime/25 shadow-lg">
                Удар
                <span className="font-normal text-white/80">{started ? "держи · ↑" : "держи — сила, ↑ — закрутка"}</span>
              </div>
              {/* The chip: a small button, an arc for a sign. */}
              <div ref={chipBtn} className="absolute -left-3 -top-16 h-14 w-14" aria-label="Парашют">
                <PowerRing barRef={chipBar} />
                <div className="flex h-full w-full items-center justify-center rounded-full border-[3px] border-white/80 bg-black/50 shadow-lg">
                  <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" stroke="#fff" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 18 Q12 1 20 18" />
                    <path d="M16.5 15.5 L20 18 L20.8 13.8" />
                  </svg>
                </div>
              </div>
            </div>
          </div>
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
            Атака {attack.attack_index + 1} / {series.total_attacks}
          </div>
          <div className="flex items-center justify-end gap-1 text-caption text-ink-mist">
            {series.card.player.display_name} · {series.rating} ·
            <span className="inline-flex items-center gap-0.5 font-mono text-accent-lime">
              {total}
              <IconCoin size={11} />
            </span>
          </div>
          {started && !ended && (
            <div
              className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-caption font-semibold ${
                feintUsed ? "bg-white/10 text-ink-mist" : "bg-accent-lime/20 text-accent-lime"
              }`}
            >
              {feintUsed ? "Финт сделан" : "Финт готов"}
            </div>
          )}
          <span ref={fpsRef} className="hidden" />
        </div>
      </div>

      {!started && (
        <div className="pointer-events-none absolute inset-x-0 top-24 px-6 text-center text-sm text-ink-chalk/90 drop-shadow">
          {ready ? (
            <>
              Джойстик — бег, до края — спринт, наклон — угол удара.
              <br />
              «Удар»: держи — сила (выше), ↑ — закрутка, тап — авто, рывок вбок — финт. ⌒ — парашют.
            </>
          ) : (
            "Загружаем…"
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

      {outcome && verdict && (
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-2 bg-gradient-to-t from-bg-base/90 to-transparent p-6 pb-10 pt-16">
          <div className={`font-display text-4xl drop-shadow ${OUTCOME[outcome].className}`}>{OUTCOME[outcome].label}</div>
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
              input.current = { live: false, hold: 0, steer: 0, feint: 0, shot: null, aiming: false, aim: 0, power: null, lob: false };
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
            {isLast ? "Итоги серии" : "Следующая атака"}
          </button>
        </div>
      )}
    </div>
  );
}
