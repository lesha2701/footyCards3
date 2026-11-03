/** How the shot looks: which foot and which technique the attacker uses,
 * and how the keeper takes the ball. Read off the episode the engine already
 * decided, so it is presentation only — the server never needs it, and the
 * same timeline always shows the same kick. */
import { FEINT_SIDE_SPEED, FEINT_TICKS, ballOf, type EpisodeState, type EpisodeTimeline, type ShotFlight } from "./engine";

export type Foot = "left" | "right";
/** instep — a drive with the laces; power — the same with everything,
 * off a full swing; side — placed with the inside;
 * curl — wrapped round with the inside; outside — bent with the outside;
 * chip — scooped over; toe — poked, no room for a backswing. */
export type ShotKind = "instep" | "power" | "side" | "curl" | "outside" | "chip" | "toe";
export type Technique = { foot: Foot; kind: ShotKind };

/** Moving sideways faster than this (m/s) picks the foot on that side. */
const SIDE_MOVE = 1.2;
/** Aimed further across than this (share of the speed) picks the foot. */
const SIDE_AIM = 0.12;
/** Closer to the keeper than this (m): a toe poke. */
const TOE_DIST = 2.2;
/** A drive from this speed (m/s): a ball struck clean through the middle
 * is the laces (the "kick"); only a soft one is side-footed. */
const DRIVE_SPEED = 19;
/** From this speed (m/s) it is struck with everything: the full swing. */
const POWER_SPEED = 29;
/** Bent away with this much sidespin (rad/s): the outside of the foot. */
const OUTSIDE_SPIN = 60;
/** Rising this steeply (vertical over horizontal speed) and no faster than
 * this (m/s): a chip — a hard one that steep is a drive into the roof of the net. */
const CHIP_LOFT = 0.5;
const CHIP_MAX_SPEED = 22;
/** Sidespin from this (rad/s): curled. */
const CURL_SPIN = 30;

export type RunAtShot = {
  /** Facing (unit, on the ground). */
  hx: number;
  hz: number;
  /** Sideways speed at the shot, positive to his left (m/s). */
  side: number;
  /** Distance to the keeper (m). */
  keeperDist: number;
};

/** Positive = to the left of someone facing (hx, hz). */
const leftOf = (hx: number, hz: number, x: number, z: number) => x * hz - z * hx;

/** Which way the sidespin bends the ball, positive to his left (0 for a
 * ball struck clean through the middle). The swerve goes along spin × v
 * (the Magnus force the flight uses). */
function bendOf(f: ShotFlight, hx: number, hz: number): number {
  const { velocity: v, spin } = f.kick;
  if (Math.abs(spin.y) < CURL_SPIN) return 0;
  return Math.sign(leftOf(hx, hz, spin.y * v.z - spin.z * v.y, spin.x * v.y - spin.y * v.x));
}

export function shotTechnique(f: ShotFlight, run: RunAtShot, chip: boolean): Technique {
  const v = f.kick.velocity;
  const flat = Math.hypot(v.x, v.z);
  const speed = Math.hypot(flat, v.y);
  const aim = leftOf(run.hx, run.hz, v.x, v.z) / Math.max(1e-6, flat);

  // Cutting to one side, he strikes with that foot; running straight, with
  // the foot that opens the body to where he aims (the inside across it).
  let foot: Foot;
  if (Math.abs(run.side) > SIDE_MOVE) foot = run.side > 0 ? "left" : "right";
  else if (Math.abs(aim) > SIDE_AIM) foot = aim > 0 ? "right" : "left";
  else foot = "right";

  // A ball struck clean is the laces (side-footed only when soft); a bent
  // one is curled with the inside, or with the outside of the right foot
  // when it bends away (wrapped into the near post from outside it). The
  // left foot never takes the outside: a ball bending left is the right
  // foot's inside.
  let kind: ShotKind;
  const bend = bendOf(f, run.hx, run.hz);
  if (foot === "left" && bend > 0) foot = "right";
  // The inside of the right foot wraps it to the left, the outside away.
  const inside = bend === 0 || (foot === "right") === bend > 0;
  const hardSpin = Math.abs(f.kick.spin.y) >= OUTSIDE_SPIN;
  // A ball with the bend on it is the finesse, never the scoop — even rising
  // steep from close in, or over a keeper who came out (the engine's chip).
  if (bend === 0 && (chip || (v.y / Math.max(1e-6, flat) > CHIP_LOFT && speed < CHIP_MAX_SPEED))) kind = "chip";
  else if (run.keeperDist < TOE_DIST) kind = "toe";
  else if (!inside && hardSpin) kind = "outside";
  else if (bend !== 0 && inside) kind = "curl";
  else kind = speed >= POWER_SPEED ? "power" : speed >= DRIVE_SPEED ? "instep" : "side";
  return { foot, kind };
}

/** A shot this soon after the feint's sidestep (ticks) still carries it. */
const FEINT_CARRY = FEINT_TICKS + 24;

/** The technique of an episode that ended in a shot (the state it ended
 * in, its timeline): his sideways way is the feint's sidestep when he
 * shoots out of it, else how far across the goal he is running. */
export function techniqueOf(s: EpisodeState, tl: EpisodeTimeline): Technique | null {
  const end = s.ended;
  if (!end?.flight) return null;
  const gx = -s.x;
  const gz = -s.z;
  const gl = Math.hypot(gx, gz) || 1;
  const fromFeint = tl.feint && end.tick - tl.feint.tick <= FEINT_CARRY ? -tl.feint.dir * FEINT_SIDE_SPEED : 0;
  const side = fromFeint || s.speed * leftOf(gx / gl, gz / gl, s.hx, s.hz);
  const b = ballOf(s);
  return shotTechnique(end.flight, { hx: s.hx, hz: s.hz, side, keeperDist: Math.hypot(b.x - s.kx, b.z - s.kz) }, end.chip);
}

/** How the keeper meets a saved shot. */
export type KeeperTake = "catch" | "parry" | "block";

/** Slower than this at the gloves (m/s) and near his body: he holds it. */
const CATCH_SPEED = 21;
const CATCH_WIDTH = 1.1;
const CATCH_LOW = 0.35;
const CATCH_HIGH = 1.9;

export function keeperTake(f: ShotFlight): KeeperTake | null {
  if (f.outcome !== "save") return null;
  const last = f.samples[f.samples.length - 1];
  const p = f.end.position;
  if (last.lying || f.keeper.lyingFor > 0) return "block";
  const atHands = Math.hypot(p.x - last.handX, p.y - last.handY) < 0.45;
  if (!atHands) return f.keeper.spread && p.y < 0.6 ? "block" : "parry";
  const prev = f.samples[Math.max(0, f.samples.length - 2)];
  const dt = Math.max(1e-6, last.t - prev.t);
  const inSpeed = Math.hypot(last.ball.x - prev.ball.x, last.ball.y - prev.ball.y, last.ball.z - prev.ball.z) / dt;
  const centred = Math.abs(p.x - f.keeper.x) < CATCH_WIDTH && p.y > CATCH_LOW && p.y < CATCH_HIGH;
  return inSpeed < CATCH_SPEED && centred ? "catch" : "parry";
}

export const KIND_LABEL: Record<ShotKind, string> = {
  instep: "подъёмом",
  power: "мощным подъёмом",
  side: "щёчкой",
  curl: "на закрутку",
  outside: "внешней",
  chip: "парашютом",
  toe: "пыром",
};
export const FOOT_LABEL: Record<Foot, string> = { left: "левой", right: "правой" };
