/** What a side has decided about the match, and what it has learnt about the other
 * one. `reviewPlans` reads the score and the clock: a side behind late on throws
 * everything forward, a side ahead shuts up shop. Pure, like the rest of the engine. */
import {
  CLOCK_RATE, HZ, MATCH_SECONDS, Style, clamp, dirOf, rnd,
  type Gameplan, type MatchState, type Player,
} from "./core";

/** The line (m up the pitch), how far up `pressing` holds, where they hunt in packs. */
const PLANS: Record<Style, Pick<Gameplan, "line" | "press" | "hunt">> = {
  [Style.Balanced]: { line: 0, press: 20, hunt: 16 },
  [Style.Press]: { line: 5, press: 44, hunt: 6 },
  [Style.Block]: { line: -5, press: 2, hunt: 30 },
  [Style.Counter]: { line: -3, press: 10, hunt: 24 },
};

export const makePlan = (style: Style): Gameplan => ({ style, ...PLANS[style], siege: 0, protect: 0, said: 0 });

/** A side's pick for the night. */
export const pickStyle = (s: MatchState): Style => [Style.Press, Style.Block, Style.Counter][Math.floor(rnd(s) * 3)];

/** How far their back line is up, plans and scouting taken together. */
export function lineOf(s: MatchState, team: 0 | 1) {
  const g = s.plans[team];
  // Burnt by balls over the top, they don't stand so high.
  return g.line + g.siege * 12 - g.protect * 5 - Math.min(5, s.scout[team].through * 1.2);
}

/** Where they start hunting in numbers. */
export function huntFrom(s: MatchState, team: 0 | 1) {
  const g = s.plans[team];
  return g.hunt - g.siege * 22 + g.protect * 14;
}

/** Just won it, and that's what they came for. */
export function countering(s: MatchState, team: 0 | 1) {
  return s.plans[team].style === Style.Counter && s.tick - s.lostAt[team === 0 ? 1 : 0] < 200;
}

/** The share of the match gone. */
const gone = (s: MatchState) => s.clock / (MATCH_SECONDS * HZ * CLOCK_RATE);

const REVIEW = 30;
/** What's learnt fades: every 10 s a side has forgotten a fifth of it. */
const FADE = 0.992;
const SIEGE_SAID = 1, PROTECT_SAID = 2, STYLE_SAID = 4;

/** The best man the other side has, by what he has done to them so far. */
export function dangerMan(s: MatchState, team: 0 | 1): Player | null {
  const seen = s.scout[team].threat;
  let best: Player | null = null, top = -1;
  for (const p of s.players) {
    if (p.team === team || p.role === "GK") continue;
    const v = seen[p.slot] + p.shot + p.dribble + (p.role === "ST" || p.role === "W" ? 0.5 : 0);
    if (v > top) { top = v; best = p; }
  }
  return best;
}

export function reviewPlans(s: MatchState) {
  if (s.tick % REVIEW !== 0) return;
  const late = gone(s);
  for (const team of [0, 1] as const) {
    const g = s.plans[team], sc = s.scout[team];
    const lead = s.teams[team].goals - s.teams[team === 0 ? 1 : 0].goals;
    // Behind: more and more of them go. Level at the very end, both sides go for it.
    const siege = lead < 0 ? clamp((late - 0.4) / 0.4, 0, 1) : lead === 0 ? clamp((late - 0.82) / 0.18, 0, 1) * 0.45 : 0;
    const protect = lead > 0 ? clamp((late - 0.5) / 0.35, 0, 1) : 0;
    g.siege = siege; g.protect = protect;
    // Once the game is under way, so that the kick-off doesn't drown it.
    if (g.style !== Style.Balanced && !(g.said & STYLE_SAID) && s.tick > 120) { g.said |= STYLE_SAID; s.ev.push({ t: "plan", team, kind: "style", style: g.style }); }
    if (siege > 0.5 && !(g.said & SIEGE_SAID)) { g.said |= SIEGE_SAID; s.ev.push({ t: "plan", team, kind: "siege" }); }
    if (protect > 0.6 && !(g.said & PROTECT_SAID)) { g.said |= PROTECT_SAID; s.ev.push({ t: "plan", team, kind: "protect" }); }
    for (let k = 0; k < 4; k++) sc.feints[k] *= FADE;
    sc.through *= FADE;
    for (let k = 0; k < 11; k++) sc.threat[k] *= FADE;
    // Which side the attacks come down: the block leans that way a little.
    const b = s.ball;
    if (b.owner >= 0 && s.players[b.owner].team !== team && b.x * dirOf(team) < 6) sc.flank += (b.z - sc.flank) * 0.03;
  }
}
