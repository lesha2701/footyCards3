import { useQuery } from "@tanstack/react-query";
import { Suspense, lazy, memo, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { fetchCareerReplay, type CareerReplayResponse } from "@/api/career";
import { Segmented } from "@/components/career/CareerTactics";
import { goalEpisodes } from "@/lib/goalReplay3d";
import {
  PITCH_L,
  PITCH_W,
  REPLAY_KITS,
  SLOTS,
  activePass,
  boardStats,
  buildTimeline,
  clockAt,
  frameAt,
  groundBall,
  holderAt,
  interpolatePlayer,
  minuteLabel,
  moments,
  playerAt,
  revealedEvents,
  rosterAt,
  secondHalfFrame,
  segmentKindAt,
  type Moment,
  type Point,
} from "@/lib/matchReplay";
import { enterImmersive } from "@/lib/immersive";

// three.js is a lazy chunk: it loads only when a 3D replay is opened.
const GoalReplay3D = lazy(() => import("@/components/career/goal3d/GoalReplay3D"));
const SPEEDS = ["1", "2", "4"];
const MOMENT_STYLE: Record<Moment["kind"], string> = {
  goal: "⚽", yellow: "🟨", red: "🟥", sub: "🔁", chance: "",
};

/** 2D match view of a career match: scoreboard with possession, a vertical
 * pitch (the viewer's team attacks upwards) with numbered chips in team
 * colours, dashed passes, moments on a scrubbable timeline and the
 * commentary. Positions come from the backend's key frames; this only
 * interpolates them (requestAnimationFrame, attributes set directly so
 * React does not re-render 60 times a second). */
/** An extra tab under the pitch (the live break's substitutions and
 * tactics); `badge` marks it, e.g. tired players waiting for a change. */
export interface ReplayTab { key: string; label: string; badge?: string; content: ReactNode }

const BASE_TABS: { key: string; label: string; badge?: string }[] = [
  { key: "feed", label: "Лента" },
  { key: "stats", label: "Статистика" },
  { key: "lineups", label: "Составы" },
];

export function ReplayPlayer({ data, extraTabs, footer }: {
  data: CareerReplayResponse;
  /** Tabs after the built-in ones (feed, stats, line-ups). */
  extraTabs?: ReplayTab[];
  footer?: ReactNode;
}) {
  const { replay, events } = data;
  const tl = useMemo(() => buildTimeline(replay), [replay]);
  const half2 = useMemo(() => secondHalfFrame(replay), [replay]);
  const marks = useMemo(() => moments(tl, replay, events), [tl, replay, events]);
  const flip = data.my_side === "b";
  const kitOf = (side: "a" | "b") => (side === (data.my_side ?? "a") ? REPLAY_KITS.mine : REPLAY_KITS.theirs);
  const episodes = useMemo(() => goalEpisodes(tl, replay, events), [tl, replay, events]);
  // Index in `episodes` of the open 3D replay.
  const [replay3d, setReplay3d] = useState<number | null>(null);
  const replay3dRef = useRef(false);
  replay3dRef.current = replay3d !== null;
  const leaveImmersive = useRef<(() => void) | null>(null);

  const timeRef = useRef(0);
  const [frame, setFrame] = useState(0);
  const [tab, setTab] = useState("feed");
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState("1");
  const playingRef = useRef(playing);
  const speedRef = useRef(1);
  playingRef.current = playing;
  speedRef.current = Number(speed);

  const chipRefs = useRef<(SVGGElement | null)[]>([]);
  const ballRef = useRef<SVGGElement | null>(null);
  const passRef = useRef<SVGLineElement | null>(null);
  const frameRef = useRef(frame);
  const clockRef = useRef<HTMLSpanElement | null>(null);

  const toSvg = useCallback((p: Point): Point => (flip ? { x: PITCH_W - p.x, y: p.y } : { x: p.x, y: PITCH_L - p.y }), [flip]);

  const draw = useCallback((ms: number) => {
    const { frame: f, frac } = frameAt(tl, ms);
    for (let i = 0; i < SLOTS; i++) {
      const el = chipRefs.current[i];
      if (!el) continue;
      const p = toSvg(interpolatePlayer(tl, f, frac, i));
      el.setAttribute("transform", `translate(${p.x.toFixed(2)} ${p.y.toFixed(2)})`);
    }
    const b = toSvg(groundBall(tl, f + frac));
    ballRef.current?.setAttribute("transform", `translate(${b.x.toFixed(2)} ${b.y.toFixed(2)})`);
    const line = passRef.current;
    if (line) {
      const active = activePass(replay, f);
      if (active) {
        const [f0, f1, from, to] = active.pass;
        const p0 = toSvg(playerAt(tl, f0, from));
        const p1 = toSvg(playerAt(tl, f1, to));
        line.setAttribute("x1", p0.x.toFixed(2));
        line.setAttribute("y1", p0.y.toFixed(2));
        line.setAttribute("x2", p1.x.toFixed(2));
        line.setAttribute("y2", p1.y.toFixed(2));
        line.setAttribute("stroke-opacity", (0.75 * Math.max(0, active.fade)).toFixed(2));
      } else {
        line.setAttribute("stroke-opacity", "0");
      }
    }
    if (clockRef.current) {
      clockRef.current.textContent = minuteLabel(clockAt(tl, f, frac), half2 !== null && f >= half2);
    }
    if (f !== frameRef.current) {
      frameRef.current = f;
      setFrame(f);
    }
  }, [tl, replay, toSvg, half2]);

  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(100, now - last);
      last = now;
      if (playingRef.current) {
        timeRef.current = Math.min(tl.total, timeRef.current + dt * speedRef.current);
        if (timeRef.current >= tl.total) setPlaying(false);
      }
      // The 2D pitch is hidden under the 3D replay: don't draw it meanwhile.
      if (!replay3dRef.current) draw(timeRef.current);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [tl, draw]);

  const seek = (ms: number) => {
    timeRef.current = Math.max(0, Math.min(tl.total, ms));
    draw(timeRef.current);
  };
  const open3d = (event: number) => {
    const k = episodes.findIndex((ep) => ep.event === event);
    if (k < 0) return;
    setPlaying(false);
    leaveImmersive.current = enterImmersive();
    setReplay3d(k);
  };
  const close3d = useCallback(() => {
    leaveImmersive.current?.();
    leaveImmersive.current = null;
    setReplay3d(null);
  }, []);
  useEffect(() => () => leaveImmersive.current?.(), []);
  const has3d = useMemo(() => new Set(episodes.map((ep) => ep.event)), [episodes]);

  const toggle = () => {
    if (!playing && timeRef.current >= tl.total) seek(0);
    setPlaying(!playing);
  };

  const roster = useMemo(() => rosterAt(replay, frame), [replay, frame]);
  const stats = useMemo(() => boardStats(tl, replay, events, frame), [tl, replay, events, frame]);
  const shown = useMemo(() => revealedEvents(replay, frame), [replay, frame]);
  const holder = holderAt(tl, frame);
  const holderPlayer = holder !== null ? replay.players[roster[holder]] : null;
  const ended = frame >= tl.count - 1;
  const halfLabel = ended ? (replay.halves === 1 ? "Перерыв" : "Матч окончен") : half2 !== null && frame >= half2 ? "2-й тайм" : "1-й тайм";
  const homeKit = kitOf("a");
  const awayKit = kitOf("b");
  const allTabs = [...BASE_TABS, ...(extraTabs ?? [])];

  return (
    <section className="flex flex-col gap-2 rounded-3xl bg-bg-surface p-3" aria-label="Матч в 2D">
      {/* Scoreboard */}
      <div className="flex items-center gap-2">
        <p className="flex min-w-0 flex-1 items-center justify-end gap-1.5 text-right text-sm font-semibold text-ink-chalk">
          <span className="truncate">{data.home_name}</span>
          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: homeKit.fill }} />
        </p>
        <div className="flex flex-col items-center">
          <p className="font-mono text-2xl font-bold leading-none text-ink-chalk" aria-label="Счёт">
            {stats.score[0]}:{stats.score[1]}
          </p>
          <p className="mt-0.5 flex items-center gap-1 font-mono text-micro text-ink-mist">
            {data.live && !ended && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-400" />}
            <span ref={clockRef}>1'</span>
            <span className="text-ink-mist-dim">· {halfLabel}</span>
            {!ended && segmentKindAt(replay, frame) === "bridge" && (
              <span className="rounded bg-white/10 px-1 text-ink-chalk" title="Между моментами время ускорено">⏩ перемотка</span>
            )}
          </p>
        </div>
        <p className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-sm font-semibold text-ink-chalk">
          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: awayKit.fill }} />
          <span className="truncate">{data.away_name}</span>
        </p>
      </div>
      <div className="flex items-center gap-2 text-micro text-ink-mist">
        <span className="w-8 text-right font-mono text-ink-chalk">{stats.possession[0]}%</span>
        <div className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-white/10" aria-label={`Владение ${stats.possession[0]}% на ${stats.possession[1]}%`}>
          <span className="h-full transition-[width] duration-500" style={{ width: `${stats.possession[0]}%`, background: homeKit.fill }} />
          <span className="h-full flex-1" style={{ background: awayKit.fill }} />
        </div>
        <span className="w-8 font-mono text-ink-chalk">{stats.possession[1]}%</span>
      </div>
      <p className="text-center text-micro text-ink-mist">
        удары <span className="font-mono text-ink-chalk">{stats.shots[0]}–{stats.shots[1]}</span>
      </p>

      {/* Pitch */}
      <div className="relative">
        <svg
          viewBox={`-3 -3 ${PITCH_W + 6} ${PITCH_L + 6}`}
          className="mx-auto block h-auto w-full touch-none select-none"
          style={{ maxHeight: "56vh" }}
          role="img"
          aria-label="Поле"
        >
          <Pitch />
          <line ref={passRef} stroke="#ffffff" strokeWidth="0.45" strokeDasharray="1.4 1.1" strokeLinecap="round" strokeOpacity="0" />
          {Array.from({ length: SLOTS }, (_, i) => {
            const side = i < 11 ? "a" : "b";
            const kit = kitOf(side);
            const player = replay.players[roster[i]];
            const gk = i === 0 || i === 11;
            // No transform prop: the animation loop owns it (a re-render
            // must not snap the chip back to a key frame).
            return (
              <g key={i} ref={(el) => { chipRefs.current[i] = el; }}>
                <circle r="2.2" fill={gk ? kit.gk : kit.fill} stroke={holder === i ? "#ffffff" : "#0b1a12"} strokeWidth={holder === i ? 0.55 : 0.3} />
                <text y="0.85" textAnchor="middle" fontSize="2.3" fontWeight="700" fill={kit.text} style={{ fontFamily: "ui-monospace, monospace" }}>
                  {player?.n ?? ""}
                </text>
              </g>
            );
          })}
          <g ref={ballRef}>
            <circle r="1.05" fill="#ffffff" stroke="#0b1a12" strokeWidth="0.25" />
          </g>
        </svg>
        <p className="pointer-events-none absolute inset-x-0 bottom-1 truncate px-3 text-center text-caption font-semibold text-white drop-shadow">
          {holderPlayer?.name ? `${holderPlayer.n}. ${holderPlayer.name}` : " "}
        </p>
      </div>

      {/* Timeline with moments */}
      <div className="relative px-1 pt-3">
        <div className="pointer-events-none absolute inset-x-1 top-0 h-3">
          {marks.filter((m) => m.kind !== "chance").map((m) => (
            <button
              key={`${m.event}`}
              type="button"
              onClick={() => {
                seek(m.ms - 4000);
                if (m.kind === "goal" && has3d.has(m.event)) open3d(m.event);
              }}
              className="pointer-events-auto absolute -translate-x-1/2 text-[10px] leading-none"
              style={{ left: `${tl.total ? (m.ms / tl.total) * 100 : 0}%` }}
              aria-label={m.kind === "goal" && has3d.has(m.event)
                ? `3D-повтор гола ${events[m.event]?.minute ?? ""}'`
                : `Перейти к моменту ${events[m.event]?.minute ?? ""}'`}
            >
              {MOMENT_STYLE[m.kind]}
            </button>
          ))}
        </div>
        <div className="pointer-events-none absolute inset-x-1 top-[18px] h-1">
          {marks.filter((m) => m.kind === "chance").map((m) => (
            <span key={`${m.event}`} className="absolute h-1 w-0.5 -translate-x-1/2 rounded-full bg-white/40"
              style={{ left: `${tl.total ? (m.ms / tl.total) * 100 : 0}%` }} />
          ))}
        </div>
        <input
          type="range"
          min={0}
          max={Math.max(1, Math.round(tl.total))}
          step={50}
          value={Math.round(tl.starts[frame] ?? 0)}
          onChange={(e) => seek(Number(e.target.value))}
          className="w-full accent-[#c6e63a]"
          aria-label="Перемотка"
        />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={toggle}
          className="flex h-9 w-11 shrink-0 items-center justify-center rounded-xl bg-bg-raised text-base text-ink-chalk active:bg-white/5"
          aria-label={playing ? "Пауза" : "Смотреть"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="flex-1">
          <Segmented label="Скорость" value={speed} options={SPEEDS.map((s) => ({ value: s, label: `x${s}` }))} onChange={setSpeed} />
        </div>
      </div>
      {/* Tabs instead of a long page: the feed, stats, line-ups (and the
          live break's orders) under the pitch. */}
      <div className="flex gap-1 overflow-x-auto rounded-2xl bg-bg-base/40 p-1" role="tablist" aria-label="Разделы матча">
        {allTabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`min-w-fit flex-1 whitespace-nowrap rounded-xl px-1 py-1.5 text-micro font-semibold transition-colors min-[400px]:text-caption ${
              tab === t.key ? "bg-bg-raised text-ink-chalk" : "text-ink-mist active:bg-white/5"}`}
          >
            {t.label}
            {t.badge && <span className="ml-1 rounded-full bg-amber-300 px-1.5 text-micro font-bold text-bg-base">{t.badge}</span>}
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-label={allTabs.find((t) => t.key === tab)?.label}>
        {tab === "feed" && (
          <Commentary events={events} shown={shown} home={data.home_name} away={data.away_name} replayable={has3d} onReplay={open3d} />
        )}
        {tab === "stats" && (
          <MatchStats events={events} shown={shown} possession={stats.possession} home={data.home_name} away={data.away_name}
            homeKit={homeKit.fill} awayKit={awayKit.fill} />
        )}
        {tab === "lineups" && <Lineups data={data} roster={roster} home={homeKit.fill} away={awayKit.fill} />}
        {extraTabs?.find((t) => t.key === tab)?.content}
      </div>
      {footer}
      {replay3d !== null && (
        <Suspense fallback={
          <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[#0b1424] text-caption text-white/80" role="status">
            Загружаем 3D-повтор…
          </div>
        }>
          <GoalReplay3D data={data} tl={tl} episodes={episodes} initial={replay3d} onClose={close3d} />
        </Suspense>
      )}
    </section>
  );
}

type ReplayEvent = CareerReplayResponse["events"][number];

/** Team stats of what has been shown so far. */
function MatchStats({ events, shown, possession, home, away, homeKit, awayKit }: {
  events: ReplayEvent[]; shown: number[]; possession: [number, number];
  home: string; away: string; homeKit: string; awayKit: string;
}) {
  const count = (test: (e: ReplayEvent) => boolean): [number, number] => {
    const out: [number, number] = [0, 0];
    for (const idx of shown) {
      const e = events[idx];
      if (!e || (e.team !== "a" && e.team !== "b") || !test(e)) continue;
      out[e.team === "a" ? 0 : 1] += 1;
    }
    return out;
  };
  const payload = (e: ReplayEvent) => (e.payload ?? {}) as Record<string, unknown>;
  const rows: [string, [number, number]][] = [
    ["Голы", count((e) => e.event_type === "goal")],
    ["Удары", count((e) => ["goal", "shot", "save", "blocked"].includes(String(e.event_type)))],
    ["В створ", count((e) => e.event_type === "goal" || e.event_type === "save")],
    ["Угловые", count((e) => payload(e).set_piece === "corner")],
    ["Отборы", count((e) => e.event_type === "tackle_won")],
    ["Фолы", count((e) => e.event_type === "foul_stopped")],
    ["Жёлтые", count((e) => payload(e).card === "yellow")],
    ["Красные", count((e) => payload(e).card === "red")],
  ];
  return (
    <div className="flex flex-col gap-1.5 rounded-2xl bg-bg-base/40 p-3 text-caption" aria-label="Статистика матча">
      <div className="flex justify-between gap-2 text-micro text-ink-mist">
        <span className="flex min-w-0 items-center gap-1 truncate"><span className="h-2 w-2 shrink-0 rounded-full" style={{ background: homeKit }} />{home}</span>
        <span className="flex min-w-0 items-center gap-1 truncate">{away}<span className="h-2 w-2 shrink-0 rounded-full" style={{ background: awayKit }} /></span>
      </div>
      <StatRow label="Владение" a={possession[0]} b={possession[1]} suffix="%" homeKit={homeKit} awayKit={awayKit} />
      {rows.map(([label, [a, b]]) => <StatRow key={label} label={label} a={a} b={b} homeKit={homeKit} awayKit={awayKit} />)}
    </div>
  );
}

function StatRow({ label, a, b, suffix = "", homeKit, awayKit }: {
  label: string; a: number; b: number; suffix?: string; homeKit: string; awayKit: string;
}) {
  const total = a + b;
  const share = total > 0 ? (a / total) * 100 : 50;
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex justify-between">
        <span className="font-mono text-ink-chalk">{a}{suffix}</span>
        <span className="text-ink-mist">{label}</span>
        <span className="font-mono text-ink-chalk">{b}{suffix}</span>
      </div>
      <div className="flex h-1 overflow-hidden rounded-full bg-white/10">
        <span className="h-full" style={{ width: `${share}%`, background: total ? homeKit : "transparent" }} />
        <span className="h-full flex-1" style={{ background: total ? awayKit : "transparent" }} />
      </div>
    </div>
  );
}

/** Who is on the pitch now (substitutes marked), both sides. */
function Lineups({ data, roster, home, away }: {
  data: CareerReplayResponse; roster: number[]; home: string; away: string;
}) {
  const { replay } = data;
  const starters = new Set(replay.roster);
  const side = (from: number, kit: string, name: string, formation: string) => (
    <div className="flex min-w-0 flex-col gap-1">
      <p className="flex items-center gap-1 truncate text-micro font-semibold text-ink-mist">
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: kit }} />
        <span className="truncate">{name} · {formation}</span>
      </p>
      {roster.slice(from, from + 11).map((pi, k) => {
        const p = replay.players[pi];
        return (
          <p key={k} className="flex items-center gap-1.5 text-caption text-ink-chalk">
            <span className="w-5 shrink-0 text-right font-mono text-ink-mist">{p?.n ?? ""}</span>
            <span className="min-w-0 flex-1 truncate">{p?.name ?? "—"}</span>
            {!starters.has(pi) && <span className="text-accent-lime" title="Вышел на замену">↑</span>}
          </p>
        );
      })}
    </div>
  );
  return (
    <div className="grid grid-cols-2 gap-3 rounded-2xl bg-bg-base/40 p-3" aria-label="Составы команд">
      {side(0, home, data.home_name, replay.formations.a)}
      {side(11, away, data.away_name, replay.formations.b)}
    </div>
  );
}

const Commentary = memo(function Commentary({ events, shown, home, away, replayable, onReplay }: {
  events: CareerReplayResponse["events"]; shown: number[]; home: string; away: string;
  /** Goals (event indices) that have a 3D replay. */
  replayable: Set<number>; onReplay: (event: number) => void;
}) {
  const items = shown.slice(-40).reverse();
  return (
    <ol className="flex max-h-44 flex-col gap-1 overflow-y-auto rounded-2xl bg-bg-base/40 p-2" aria-label="Комментарии" aria-live="polite">
      {items.length === 0 && <li className="text-caption text-ink-mist-dim">Матч начался</li>}
      {items.map((idx) => {
        const e = events[idx];
        if (!e) return null;
        const goal = e.event_type === "goal";
        return (
          <li key={idx} className={`flex gap-2 text-caption ${goal ? "font-semibold text-accent-lime" : "text-ink-chalk"}`}>
            <span className="w-7 shrink-0 text-right font-mono text-ink-mist">{e.minute}'</span>
            <span className="min-w-0 flex-1">{e.description || (e.team === "a" ? home : away)}</span>
            {goal && replayable.has(idx) && (
              <button
                type="button"
                onClick={() => onReplay(idx)}
                className="shrink-0 self-start rounded-full bg-accent-lime/15 px-2 py-0.5 text-micro font-semibold text-accent-lime active:bg-accent-lime/25"
              >
                3D-повтор
              </button>
            )}
          </li>
        );
      })}
    </ol>
  );
});

/** Grass stripes, lines, boxes and goals in pitch metres (vertical). */
const Pitch = memo(function Pitch() {
  const stripes = Array.from({ length: 10 }, (_, i) => i);
  const W = PITCH_W;
  const L = PITCH_L;
  const box = (y: number, h: number, w: number) => <rect x={(W - w) / 2} y={y} width={w} height={h} />;
  return (
    <g>
      <rect x={-3} y={-3} width={W + 6} height={L + 6} rx="2" fill="#11482f" />
      {stripes.map((i) => <rect key={i} x={0} y={(L / 10) * i} width={W} height={L / 10} fill={i % 2 ? "#145236" : "#11482f"} />)}
      <g fill="none" stroke="#ffffff" strokeOpacity="0.45" strokeWidth="0.3">
        <rect x={0} y={0} width={W} height={L} />
        <line x1={0} y1={L / 2} x2={W} y2={L / 2} />
        <circle cx={W / 2} cy={L / 2} r="9.15" />
        {box(0, 16.5, 40.3)}
        {box(0, 5.5, 18.3)}
        {box(L - 16.5, 16.5, 40.3)}
        {box(L - 5.5, 5.5, 18.3)}
        <path d={`M ${W / 2 - 7.3} 16.5 A 9.15 9.15 0 0 0 ${W / 2 + 7.3} 16.5`} />
        <path d={`M ${W / 2 - 7.3} ${L - 16.5} A 9.15 9.15 0 0 1 ${W / 2 + 7.3} ${L - 16.5}`} />
      </g>
      <g fill="#ffffff" fillOpacity="0.5">
        <circle cx={W / 2} cy={L / 2} r="0.4" />
        <circle cx={W / 2} cy={11} r="0.35" />
        <circle cx={W / 2} cy={L - 11} r="0.35" />
      </g>
      <g fill="#ffffff" fillOpacity="0.18" stroke="#ffffff" strokeOpacity="0.7" strokeWidth="0.3">
        <rect x={W / 2 - 3.66} y={-1.8} width={7.32} height={1.8} />
        <rect x={W / 2 - 3.66} y={L} width={7.32} height={1.8} />
      </g>
    </g>
  );
});

/** Fetches the replay of a league match and plays it; `fallback` (the old
 * text replay) renders when the match has no 2D record. */
export function CareerMatchViewer({ seasonId, round, match, extraTabs, fallback, footer }: {
  seasonId: number; round: number; match: number;
  /** Extra tabs (the live break's orders) — shown only while it's live. */
  extraTabs?: ReplayTab[];
  fallback?: ReactNode; footer?: ReactNode;
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["career", "replay", seasonId, round, match],
    queryFn: () => fetchCareerReplay(seasonId, round, match),
    staleTime: 60_000,
    retry: false,
  });
  if (isLoading) return <div className="h-96 animate-pulse rounded-3xl bg-bg-surface" aria-label="Загрузка матча" />;
  if (isError || !data) return <>{fallback ?? null}</>;
  return (
    <ReplayPlayer
      key={`${data.replay.count}-${data.live}`}
      data={data}
      extraTabs={data.live ? extraTabs : undefined}
      footer={footer}
    />
  );
}
