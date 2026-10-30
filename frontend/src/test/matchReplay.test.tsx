import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CareerReplay, CareerReplayResponse } from "@/api/career";
import { ReplayPlayer } from "@/components/career/MatchViewer";
import {
  PITCH_L,
  PITCH_W,
  activePass,
  boardStats,
  buildTimeline,
  catmullRom,
  clockAt,
  frameAt,
  holderAt,
  interpolateBall,
  interpolatePlayer,
  minuteLabel,
  moments,
  rosterAt,
  liveEdge,
  secondHalfFrame,
  segmentKindAt,
} from "@/lib/matchReplay";

// The 3D viewer is a lazy three.js chunk; jsdom has no WebGL.
vi.mock("@/components/career/goal3d/GoalReplay3D", () => ({
  default: ({ initial, onClose }: { initial: number; onClose: () => void }) => (
    <div role="dialog" aria-label="3D-повтор гола">
      повтор {initial}
      <button type="button" onClick={onClose}>Закрыть 3D-повтор</button>
    </div>
  ),
}));

const SIZE = 47;

/** Frames where slot 0 walks from x=0 to x=255 in steps and the ball
 * follows slot 2 (home) for the first half of them, then slot 12 (away). */
function makeFrames(count: number): string {
  const bytes = new Uint8Array(count * SIZE);
  for (let f = 0; f < count; f++) {
    const o = f * SIZE;
    bytes[o] = Math.round((f / (count - 1)) * 255);
    bytes[o + 1] = 128;
    bytes[o + 2] = f < count / 2 ? 2 : f === count - 1 ? 255 : 12;
    for (let s = 0; s < 22; s++) {
      bytes[o + 3 + s * 2] = s === 0 ? Math.round((f / (count - 1)) * 255) : 100;
      bytes[o + 4 + s * 2] = s < 11 ? 40 : 200;
    }
  }
  let bin = "";
  bytes.forEach((b) => { bin += String.fromCharCode(b); });
  return btoa(bin);
}

const replay: CareerReplay = {
  v: 1, step: 0.5, halves: 2, frame_size: SIZE, pitch: [68, 105], count: 10,
  formations: { a: "4-3-3", b: "4-4-2" },
  players: [
    ...Array.from({ length: 22 }, (_, i) => ({ s: (i < 11 ? "a" : "b") as "a" | "b", n: (i % 11) + 1, name: `P${i}`, slot: "MID1", id: i })),
    { s: "a", n: 12, name: "Запасной", slot: "FWD2", id: 99 },
  ],
  roster: Array.from({ length: 22 }, (_, i) => i),
  swaps: [[6, 5, 22]],
  // kickoff (2 frames @500ms), bridge (2 @300), goal episode (3 @500), second-half kickoff (3 @500)
  segments: [
    ["kickoff", 0, 2, 0, 1, 500],
    ["bridge", 2, 2, 1, 600, 300],
    ["goal", 4, 3, 600, 601.5, 500],
    ["kickoff", 7, 3, 2700, 2701.5, 500],
  ],
  marks: [[5, 0], [6, 1], [8, 2]],
  passes: [[3, 5, 2, 4]],
  frames: makeFrames(10),
};

const events = [
  { minute: 11, event_type: "goal", team: "a", description: "Гол хозяев", payload: { shooter: "P2" } },
  { minute: 11, event_type: "save", team: "b", description: "Сейв", payload: {} },
  { minute: 50, event_type: "foul_stopped", team: "a", description: "Фол, жёлтая", payload: { card: "yellow" } },
];

describe("matchReplay timeline", () => {
  const tl = buildTimeline(replay);

  it("lays frames out by their segment's playback speed", () => {
    expect(tl.count).toBe(10);
    expect(Array.from(tl.starts.slice(0, 5))).toEqual([0, 500, 1000, 1300, 1600]);
    expect(tl.total).toBe(500 * 2 + 300 * 2 + 500 * 3 + 500 * 2);
    expect(frameAt(tl, 0)).toEqual({ frame: 0, frac: 0 });
    expect(frameAt(tl, 250)).toEqual({ frame: 0, frac: 0.5 });
    expect(frameAt(tl, 1150)).toEqual({ frame: 2, frac: 0.5 });
    expect(frameAt(tl, 1e9).frame).toBe(9);
    expect(frameAt(tl, -5).frame).toBe(0);
  });

  it("game clock follows the segments; minutes are capped per half", () => {
    expect(clockAt(tl, 2, 0)).toBe(1);
    expect(clockAt(tl, 3, 0)).toBeCloseTo(300.5);
    expect(clockAt(tl, 4, 0.5)).toBeCloseTo(600.25);
    expect(minuteLabel(0, false)).toBe("1'");
    expect(minuteLabel(659, false)).toBe("11'");
    expect(minuteLabel(2800, false)).toBe("45'");
    expect(minuteLabel(2700, true)).toBe("46'");
    expect(minuteLabel(6000, true)).toBe("90'");
    expect(secondHalfFrame(replay)).toBe(7);
  });

  it("interpolates players smoothly through key frames and the ball linearly", () => {
    const at0 = interpolatePlayer(tl, 3, 0, 0);
    const at1 = interpolatePlayer(tl, 4, 0, 0);
    const mid = interpolatePlayer(tl, 3, 0.5, 0);
    expect(mid.x).toBeGreaterThan(at0.x);
    expect(mid.x).toBeLessThan(at1.x);
    expect(at0.y).toBeCloseTo((40 / 255) * PITCH_L);
    // Catmull-Rom passes through its control points.
    expect(catmullRom(0, 1, 2, 3, 0)).toBe(1);
    expect(catmullRom(0, 1, 2, 3, 1)).toBe(2);
    const b = interpolateBall(tl, 0, 0.5);
    expect(b.x).toBeCloseTo(((0 + 28) / 2 / 255) * PITCH_W, 1);
    // Positions stay on the pitch even at the edges of the sequence.
    for (let f = 0; f < tl.count; f++) {
      for (const frac of [0, 0.3, 0.9]) {
        const p = interpolatePlayer(tl, f, frac, 0);
        expect(p.x).toBeGreaterThanOrEqual(0);
        expect(p.x).toBeLessThanOrEqual(PITCH_W);
      }
    }
  });

  it("scoreboard: score and shots from revealed events, possession from the holder", () => {
    expect(holderAt(tl, 0)).toBe(2);
    expect(holderAt(tl, 9)).toBeNull();
    expect(boardStats(tl, replay, events, 4).score).toEqual([0, 0]);
    const after = boardStats(tl, replay, events, 6);
    expect(after.score).toEqual([1, 0]);
    expect(after.shots).toEqual([1, 1]);
    expect(after.possession).toEqual([71, 29]); // 5 of 7 frames held by home
  });

  it("a second half on air plays in real time from its kick-off and ends with the show", () => {
    const at = new Date("2026-10-30T19:10:00Z").getTime();
    const iso = new Date(at).toISOString();
    expect(liveEdge(tl, replay, iso, at - 1000)).toBeNull(); // not kicked off yet
    expect(liveEdge(tl, replay, iso, at)).toBe(tl.starts[7]);
    expect(liveEdge(tl, replay, iso, at + 700)).toBe(tl.starts[7] + 700);
    expect(liveEdge(tl, replay, iso, at + 60_000)).toBeNull(); // over
    expect(liveEdge(tl, replay, null, at)).toBeNull();
  });

  it("knows the accelerated stretches between moments", () => {
    expect(segmentKindAt(replay, 0)).toBe("kickoff");
    expect(segmentKindAt(replay, 3)).toBe("bridge");
    expect(segmentKindAt(replay, 5)).toBe("goal");
    expect(segmentKindAt(replay, 99)).toBeNull();
  });

  it("substitutions, passes and moments", () => {
    expect(rosterAt(replay, 5)[5]).toBe(5);
    expect(rosterAt(replay, 6)[5]).toBe(22);
    expect(activePass(replay, 2)).toBeNull();
    expect(activePass(replay, 4)?.fade).toBe(1);
    expect(activePass(replay, 6)?.fade).toBeCloseTo(2 / 3);
    expect(activePass(replay, 8)).toBeNull();
    const ms = moments(tl, replay, events);
    expect(ms.map((m) => m.kind)).toEqual(["goal", "chance", "yellow"]);
    expect(ms[0].ms).toBe(tl.starts[5]);
  });
});

describe("ReplayPlayer", () => {
  const data: CareerReplayResponse = {
    home_name: "Dev FC", away_name: "Бот 2", home_score: 1, away_score: 0,
    events: events.map((e) => ({ ...e, team: e.team })), my_side: "a", live: false, second_half_at: null, replay,
  };

  it("draws the board, pitch, timeline and commentary; no tactics buttons after the match", () => {
    render(<ReplayPlayer data={data} />);
    expect(screen.getByText("Dev FC")).toBeInTheDocument();
    expect(screen.getByLabelText("Счёт")).toHaveTextContent("0:0");
    expect(screen.getByLabelText("Поле")).toBeInTheDocument();
    expect(screen.getByLabelText("Перемотка")).toBeInTheDocument();
    expect(screen.queryByText("Тактика")).toBeNull();
    expect(screen.queryByText("Замена")).toBeNull();
    // Scrubbing to the end reveals the goal in the commentary and the score.
    fireEvent.change(screen.getByLabelText("Перемотка"), { target: { value: String(buildTimeline(replay).total) } });
    expect(screen.getByLabelText("Счёт")).toHaveTextContent("1:0");
    expect(screen.getByText("Гол хозяев")).toBeInTheDocument();
    expect(screen.getByText(/Матч окончен/)).toBeInTheDocument();
    // Full time: the man of the match and the ratings in the line-ups.
    expect(screen.getByLabelText("Лучший игрок матча")).toHaveTextContent("P2");
    fireEvent.click(screen.getByRole("tab", { name: "Составы" }));
    expect(screen.getByLabelText("Составы команд")).toHaveTextContent("7.7");
  });

  it("the latest moment shows on the pitch, scorers under the score; speed cycles with a tap", () => {
    render(<ReplayPlayer data={data} />);
    // Frame 5 has the goal (mark at frame 5): scrub just after it.
    fireEvent.change(screen.getByLabelText("Перемотка"), { target: { value: String(buildTimeline(replay).starts[6]) } });
    expect(screen.getByLabelText("Голы")).toHaveTextContent("11' P2");
    // The ticker has the latest one: the save right after the goal.
    expect(screen.getByText("Сейв", { selector: "p span" })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Скорость x1"));
    expect(screen.getByLabelText("Скорость x2")).toBeInTheDocument();
  });

  it("watching a second half on air: from its kick-off, LIVE badge, no peeking ahead", () => {
    const tlx = buildTimeline(replay);
    // Kicked off two minutes ago: still on air, so it starts from its kick-off.
    const at = new Date(Date.now() - 120_000).toISOString();
    render(<ReplayPlayer data={{ ...data, second_half_at: at }} />);
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    // The goal of the first half is known, the future isn't on the timeline.
    fireEvent.change(screen.getByLabelText("Перемотка"), { target: { value: String(tlx.total) } });
    expect(screen.getByText(/2-й тайм/)).toBeInTheDocument();
    expect(screen.queryByText(/Матч окончен/)).toBeNull();
  });

  it("a second half long over is an ordinary replay", () => {
    render(<ReplayPlayer data={{ ...data, second_half_at: new Date(Date.now() - 3_600_000).toISOString() }} />);
    expect(screen.queryByText("LIVE")).toBeNull();
  });

  it("tabs under the pitch: feed, stats, line-ups and the live break's own tabs", () => {
    render(<ReplayPlayer data={{ ...data, live: true }} extraTabs={[
      { key: "subs", label: "Замены", badge: "2", content: <p>Панель замен</p> },
    ]} />);
    expect(screen.getByRole("tab", { name: "Лента" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("Комментарии")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Статистика" }));
    expect(screen.getByLabelText("Статистика матча")).toHaveTextContent("Владение");
    expect(screen.queryByLabelText("Комментарии")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Составы" }));
    expect(screen.getByLabelText("Составы команд")).toHaveTextContent("P0");
    fireEvent.click(screen.getByRole("tab", { name: /Замены/ }));
    expect(screen.getByText("Панель замен")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Пауза"));
    expect(screen.getByLabelText("Смотреть")).toBeInTheDocument();
  });

  it("a goal opens its 3D replay from the commentary and from the timeline", async () => {
    render(<ReplayPlayer data={data} />);
    fireEvent.change(screen.getByLabelText("Перемотка"), { target: { value: String(buildTimeline(replay).total) } });
    fireEvent.click(screen.getByText("3D-повтор"));
    expect(await screen.findByRole("dialog", { name: "3D-повтор гола" })).toHaveTextContent("повтор 0");
    // The 2D view pauses underneath.
    expect(screen.getByLabelText("Смотреть")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Закрыть 3D-повтор"));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByLabelText("3D-повтор гола 11'"));
    expect(await screen.findByRole("dialog", { name: "3D-повтор гола" })).toBeInTheDocument();
  });
});
