// What the AI does with the ball: every spell of the side that isn't the human's,
// from where it began to how it ended, and how its carriers move.
//   node bench/attack.mjs <matches>
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const E = require("./out/engine.cjs");
const matches = Number(process.argv[2] ?? 20);
const c = { spells: 0, ticks: 0, passes: 0, into3rd: 0, intoBox: 0, shots: 0, lost: 0, out: 0, gained: 0, back: 0, fwd: 0, side: 0, flips: 0, carryTicks: 0, stepped: 0 };
const ends = {};
for (let m = 0; m < matches; m++) {
  const s = E.createMatch({ seed: 500 + m * 11, home: "A", away: "B", homeRating: 0.78, awayRating: 0.78 }, null);
  let was = -1, sp = null, ux = 0, uz = 0, tackled = -99, lastKick = 0;
  const close = (why) => {
    if (!sp) return;
    c.spells++; c.ticks += s.tick - sp.t0; c.passes += sp.passes; c.gained += sp.best - sp.ax0;
    if (sp.third) c.into3rd++; if (sp.box) c.intoBox++;
    ends[why] = (ends[why] ?? 0) + 1; sp = null;
  };
  while (s.phase !== 4 && s.tick < 60 * 400) {
    E.stepMatch(s, E.NO_INPUT);
    for (const e of s.ev) {
      if (e.t === "tackle" && e.won) tackled = s.tick;
      if (e.t === "kick") lastKick = e.kind;
      if (!sp) continue;
      if (e.t === "kick" && s.players[e.p].team === sp.team) {
        if (e.kind === 5) { c.shots++; close("shot"); }
        else if (e.kind <= 3 || e.kind === 4) {
          sp.passes++;
          const p = s.players[e.p], d = p.team === 0 ? 1 : -1;
          const q = p.plan ?? null;
          if (q) { const g = (q.tx - p.x) * d; if (g > 4) c.fwd++; else if (g < -4) c.back++; else c.side++; }
        }
      }
      if (e.t === "out" && sp) close("out_" + e.set);
    }
    if (s.phase !== 1) { close("dead"); continue; }
    const b = s.ball;
    if (b.owner >= 0) {
      const o = s.players[b.owner], d = o.team === 0 ? 1 : -1, ax = o.x * d;
      if (sp && o.team !== sp.team) close(tackled > s.tick - 30 ? "lost_tackle" : "lost_k" + lastKick);
      if (!sp) sp = { team: o.team, t0: s.tick, ax0: ax, best: ax, passes: 0, third: false, box: false };
      sp.best = Math.max(sp.best, ax);
      if (ax > 17) sp.third = true;
      if (ax > 36 && Math.abs(o.z) < 20) sp.box = true;
      const v = Math.hypot(o.vx, o.vz);
      if (b.owner !== was) { ux = 0; uz = 0; was = b.owner; }
      if (v > 1) {
        const nx = o.vx / v, nz = o.vz / v;
        if ((ux !== 0 || uz !== 0) && ux * nx + uz * nz < 0.5) c.flips++;
        ux = nx; uz = nz; c.carryTicks++;
      }
    }
  }
  close("end");
}
const n = c.spells;
console.log(JSON.stringify({ spells_per_match: +(n / matches).toFixed(1), sec_per_spell: +(c.ticks / n / 60).toFixed(1), passes_per_spell: +(c.passes / n).toFixed(2), gained_m: +(c.gained / n).toFixed(1), reach_third: +(c.into3rd / n).toFixed(2), reach_box: +(c.intoBox / n).toFixed(2), shots_per_match: +(c.shots / matches).toFixed(1), fwd: c.fwd, side: c.side, back: c.back, sharp_turns_per_10s_carry: +(c.flips / (c.carryTicks / 600)).toFixed(1) }));
console.log(JSON.stringify(ends));
