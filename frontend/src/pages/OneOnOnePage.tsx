import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
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
          Выход один на один с вратарём. Держи палец — игрок бежит с мячом, веди влево-вправо — меняет направление.
          Быстрый свайп в сторону — финт: поймаешь вратаря на нём — он провалится. Удар — свайп вверх с отпусканием, как
          в штрафном: быстрее — сильнее, длиннее — выше, дугой — закрутка.
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

/** The thumb's sideways flick is sharper than the free kick's whole-screen
 * swipe: it leans the shot this much. */
const SHOT_AIM = 0.6;

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
  const input = useRef<LiveInput>({ live: false, hold: 0, steer: 0, feint: 0, shot: null });
  const stick = useRef(new Stick(window.innerWidth, window.innerHeight));
  const pad = useRef(new Finger(window.innerWidth, window.innerHeight, SHOT_AIM));
  const knob = useRef<HTMLDivElement | null>(null);
  const anchor = useRef<HTMLDivElement | null>(null);
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
      anchor.current.style.borderColor = st.hold === 2 ? "rgba(198,230,58,0.9)" : "rgba(255,255,255,0.3)";
    }
    if (knob.current) {
      knob.current.style.opacity = stick.current.down ? "1" : "0";
      knob.current.style.transform = `translate(${st.knob.x - 22}px, ${st.knob.y - 22}px)`;
    }
  };
  const syncStick = () => {
    const st = stick.current.read();
    input.current.hold = st.hold;
    input.current.steer = st.steer;
    placeStick();
  };
  // Which finger is which: the one that came down on the left half is the
  // stick, on the right half the action thumb.
  const fingers = useRef(new Map<number, "stick" | "pad">());

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
    if (left && !stick.current.down) {
      fingers.current.set(e.pointerId, "stick");
      stick.current.start({ x: e.clientX, y: e.clientY });
      syncStick();
    } else if (!left && !pad.current.down) {
      fingers.current.set(e.pointerId, "pad");
      pad.current.start({ x: e.clientX, y: e.clientY, t: e.timeStamp });
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
    } else {
      feint(pad.current.move({ x: e.clientX, y: e.clientY, t: e.timeStamp }));
    }
  };
  const release = (e: PointerEvent<HTMLDivElement>, cancelled: boolean) => {
    const role = fingers.current.get(e.pointerId);
    fingers.current.delete(e.pointerId);
    if (role === "stick") {
      stick.current.end();
      syncStick();
    } else if (role === "pad") {
      if (cancelled) return pad.current.cancel();
      const intent = pad.current.end({ x: e.clientX, y: e.clientY, t: e.timeStamp });
      if (!playing) return;
      if (intent.shot) {
        input.current.shot = intent.shot;
        haptic("medium");
        crowdTension(true);
      } else feint(intent.feint);
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
          className="pointer-events-none absolute left-0 top-0 rounded-full border-2 border-white/30 bg-black/15 opacity-0"
        />
        <div
          ref={knob}
          className="pointer-events-none absolute left-0 top-0 h-11 w-11 rounded-full bg-accent-lime/75 opacity-0 shadow"
        />
        {!started && ready && (
          // Where the thumbs go.
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-between px-6 pb-24 text-center text-caption text-ink-chalk/90">
            <div className="flex h-28 w-28 flex-col items-center justify-center rounded-full border-2 border-dashed border-white/40 bg-black/20">
              Бег
              <span className="text-ink-mist">до края — спринт</span>
            </div>
            <div className="flex h-28 w-28 flex-col items-center justify-center rounded-full border-2 border-dashed border-accent-lime/60 bg-black/20">
              Удар ↑
              <span className="text-ink-mist">рывок вбок — финт</span>
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
              Левый палец — джойстик: веди игрока, до края — спринт.
              <br />
              Правый палец: резкий рывок вбок — финт, свайп вверх — удар.
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
              input.current = { live: false, hold: 0, steer: 0, feint: 0, shot: null };
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
