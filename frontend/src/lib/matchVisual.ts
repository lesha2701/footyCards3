import type { MatchEvent } from "@/types";

// Schematic match visualisation, derived purely from the event log the
// server already returns. The engine has no player coordinates — only event
// types (goal/save/blocked/tackle_won/…), the attacking `team` and, for
// chances, the shot type — so every position here is an illustrative spot
// for that kind of event, never a claim about where a player really stood.
//
// Pitch space: x 0..100 (left → right), y 0..60. The user always attacks
// to the right; the opponent attacks to the left.
//
// `team` semantics (see backend match_service._EVENT_DESCRIPTIONS): for every
// event except cards it is the side in possession / attacking — e.g.
// `tackle_won` with team "opponent" means the opponent attacked and the
// user's defender won the ball. For yellow/red cards it is the booked side.

export type MatchSide = "user" | "opponent";
export type FrameTone = MatchSide | "neutral";
export type FrameKind =
  | "goal" | "miss" | "save" | "blocked" | "tackle" | "foul" | "card" | "corner"
  | "offside" | "possession" | "pass_failed" | "other";

export interface PitchPoint { x: number; y: number }

export interface PitchFrame {
  kind: FrameKind;
  ball: PitchPoint;
  /** Shot origin, when the event is a shot (goal/miss/save/blocked). */
  from: PitchPoint | null;
  label: string | null;
  /** Whose moment this is visually (e.g. a save is the defending side's). */
  tone: FrameTone;
  /** Side whose goal is under threat, for the net highlight on a goal. */
  goalSide: MatchSide | null;
}

export const PITCH_W = 100;
export const PITCH_H = 60;
const MID_Y = PITCH_H / 2;

export const KICKOFF_FRAME: PitchFrame = {
  kind: "other", ball: { x: PITCH_W / 2, y: MID_Y }, from: null, label: null, tone: "neutral", goalSide: null,
};

const SHOT_ORIGIN_X: Record<string, number> = { in_box: 84, long_range: 70, empty_net: 78 };

function asSide(team: string): MatchSide | null {
  return team === "user" || team === "opponent" ? team : null;
}

export function otherSide(side: MatchSide): MatchSide {
  return side === "user" ? "opponent" : "user";
}

/** x measured from the attacking side's own goal (0) towards the goal it attacks (100). */
function attackX(side: MatchSide, x: number): number {
  return side === "user" ? x : PITCH_W - x;
}

/** Small deterministic vertical spread so consecutive events don't stack on one line. */
function spreadY(seed: number, range = 12): number {
  const step = ((seed * 37) % (2 * range + 1)) - range;
  return MID_Y + step;
}

// --- Two-side engines (club/player tournaments, career) -----------------------
//
// tournament_match_engine / career_tactics_service log sides as "a"/"b" and,
// unlike Card Arena, put the DEFENDING side in `team` for tackle_won and
// foul_stopped. Normalising to Arena semantics lets the same frames, pressure
// and stats run on both: "a" attacks right (drawn like "user"), "b" left.

const DEFENDER_TEAM_EVENTS = new Set(["tackle_won", "foul_stopped"]);

export function normalizeTwoSideEvents(events: MatchEvent[]): MatchEvent[] {
  return events.map((e) => {
    if (e.team !== "a" && e.team !== "b") return e;
    const team = e.team === "a" ? "user" : "opponent";
    const attacking = DEFENDER_TEAM_EVENTS.has(e.event_type) ? (team === "user" ? "opponent" : "user") : team;
    return { ...e, team: attacking };
  });
}

/** Where a shot starts, from what the event itself records. Set pieces and
 * penalties have a known spot; a career chance's zone (wing vs central)
 * picks the band; otherwise a spread spot for the shot type. */
function shotOrigin(event: MatchEvent, side: MatchSide, index: number): PitchPoint {
  const p = event.payload ?? {};
  if (p.is_penalty || p.set_piece === "penalty") return { x: attackX(side, 89), y: MID_Y };
  if (p.set_piece === "corner") return { x: attackX(side, 92), y: index % 2 ? MID_Y - 6 : MID_Y + 6 };
  if (p.set_piece === "free_kick") return { x: attackX(side, 74), y: spreadY(index, 10) };
  const shotType = typeof p.shot_type === "string" ? p.shot_type : "in_box";
  const x = attackX(side, SHOT_ORIGIN_X[shotType] ?? SHOT_ORIGIN_X.in_box);
  if (p.zone === "wing_attack") return { x, y: index % 2 ? 12 : PITCH_H - 12 };
  if (p.zone === "central_attack") return { x, y: spreadY(index, 5) };
  return { x, y: spreadY(index, 8) };
}

export function frameForEvent(event: MatchEvent, index: number, previous: PitchFrame = KICKOFF_FRAME): PitchFrame {
  const side = asSide(event.team);
  if (!side) return { ...previous, label: null, from: null, kind: "other", tone: "neutral", goalSide: null };

  const defending = otherSide(side);
  const shotFrom = shotOrigin(event, side, index);
  const at = (x: number, y = spreadY(index)): PitchPoint => ({ x: attackX(side, x), y });

  switch (event.event_type) {
    case "goal":
      return { kind: "goal", ball: at(99, MID_Y + (index % 2 ? 2 : -2)), from: shotFrom, label: "ГОЛ!", tone: side, goalSide: defending };
    case "shot":
      // Wide or over: finish beside the post, outside the goal mouth.
      return { kind: "miss", ball: at(100, index % 2 ? MID_Y - 13 : MID_Y + 13), from: shotFrom, label: "Мимо", tone: side, goalSide: null };
    case "save":
      return { kind: "save", ball: at(95, MID_Y + (index % 2 ? 3 : -3)), from: shotFrom, label: "Сейв", tone: defending, goalSide: null };
    case "blocked":
      return { kind: "blocked", ball: at(87, spreadY(index, 6)), from: shotFrom, label: "Блок", tone: defending, goalSide: null };
    case "tackle_won":
      return { kind: "tackle", ball: at(76), from: null, label: "Отбор", tone: defending, goalSide: null };
    case "foul_stopped": {
      const card = event.payload?.card;
      const label = card === "red" ? "Фол · красная" : card === "yellow" ? "Фол · жёлтая" : "Фол";
      return { kind: "foul", ball: at(72), from: null, label, tone: "neutral", goalSide: null };
    }
    case "pass_failed":
      return { kind: "pass_failed", ball: at(62), from: null, label: "Потеря", tone: defending, goalSide: null };
    case "corner":
      return { kind: "corner", ball: at(100, index % 2 ? 1 : PITCH_H - 1), from: null, label: "Угловой", tone: side, goalSide: null };
    case "offside":
      return { kind: "offside", ball: at(80), from: null, label: "Офсайд", tone: "neutral", goalSide: null };
    case "possession":
      return { kind: "possession", ball: at(58), from: null, label: null, tone: side, goalSide: null };
    case "substitution":
    case "tactic_change":
      // Bench decisions (career): nothing moves on the pitch.
      return {
        kind: "other", ball: previous.ball, from: null,
        label: event.event_type === "substitution" ? "Замена" : "Тактика", tone: side, goalSide: null,
      };
    case "yellow_card":
    case "red_card":
      // The ball doesn't move for a booking — keep it where the last moment
      // left it and just show the card.
      return {
        kind: "card", ball: previous.ball, from: null,
        label: event.event_type === "red_card" ? "Красная" : "Жёлтая", tone: "neutral", goalSide: null,
      };
    default:
      return { ...previous, kind: "other", from: null, label: null, tone: "neutral", goalSide: null };
  }
}

/**
 * The chance currently waiting for the player's decision (Match.pending_moment):
 * the ball sits at the shot spot for that side and shot type. Uses only what
 * the moment itself states — who attacks and what kind of shot it is.
 */
export function pendingFrame(team: string, shotType: string, index: number): PitchFrame | null {
  const side = asSide(team);
  if (!side) return null;
  const x = SHOT_ORIGIN_X[shotType] ?? SHOT_ORIGIN_X.in_box;
  return {
    kind: "other",
    ball: { x: attackX(side, x), y: spreadY(index, 8) },
    from: null,
    label: side === "user" ? "Твой момент" : "Угроза!",
    tone: side,
    goalSide: null,
  };
}

/** Frame for the latest of `events` (folding through so cards keep the prior ball spot). */
export function currentFrame(events: MatchEvent[]): PitchFrame {
  let frame = KICKOFF_FRAME;
  events.forEach((e, i) => { frame = frameForEvent(e, i, frame); });
  return frame;
}

// --- Pressure ("who's on top") ------------------------------------------------

const PRESSURE_WEIGHT: Record<string, number> = {
  possession: 1, corner: 1.5, offside: 0.5, pass_failed: 0.5,
  tackle_won: 1, foul_stopped: 1, shot: 2, save: 2.5, blocked: 2, goal: 3,
};

/**
 * -1 (opponent dominating) … 0 (even) … +1 (user dominating), from the last
 * `window` revealed events. Each event credits its attacking side; bookings
 * don't count as pressure.
 */
export function pressure(events: MatchEvent[], window = 6): number {
  let user = 0;
  let opponent = 0;
  for (const e of events.slice(-window)) {
    const w = PRESSURE_WEIGHT[e.event_type];
    if (!w) continue;
    if (e.team === "user") user += w;
    else if (e.team === "opponent") opponent += w;
  }
  const total = user + opponent;
  return total === 0 ? 0 : (user - opponent) / total;
}

// --- Post-match stats -----------------------------------------------------------

export interface SideStats {
  shots: number;
  onTarget: number;
  corners: number;
  tacklesWon: number;
  offsides: number;
  yellow: number;
  red: number;
}

const SHOT_EVENTS = new Set(["goal", "shot", "save", "blocked"]);
const ON_TARGET_EVENTS = new Set(["goal", "save"]);

function emptyStats(): SideStats {
  return { shots: 0, onTarget: 0, corners: 0, tacklesWon: 0, offsides: 0, yellow: 0, red: 0 };
}

export function matchStats(events: MatchEvent[]): Record<MatchSide, SideStats> {
  const stats: Record<MatchSide, SideStats> = { user: emptyStats(), opponent: emptyStats() };
  for (const e of events) {
    const side = asSide(e.team);
    if (!side) continue;
    const s = stats[side];
    if (SHOT_EVENTS.has(e.event_type)) s.shots += 1;
    if (ON_TARGET_EVENTS.has(e.event_type)) s.onTarget += 1;
    if (e.event_type === "corner") s.corners += 1;
    if (e.event_type === "offside") s.offsides += 1;
    if (e.event_type === "yellow_card") s.yellow += 1;
    if (e.event_type === "red_card") s.red += 1;
    // These two are narrated from the attacking side, but the tackle and the
    // foul (and any booking for it) belong to the defending side.
    if (e.event_type === "tackle_won") stats[otherSide(side)].tacklesWon += 1;
    if (e.event_type === "foul_stopped") {
      if (e.payload?.card === "yellow") stats[otherSide(side)].yellow += 1;
      if (e.payload?.card === "red") stats[otherSide(side)].red += 1;
    }
  }
  return stats;
}
