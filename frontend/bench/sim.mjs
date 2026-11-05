// AI against AI, headless: how football-like a match is. Reads the esbuild
// bundle of src/lib/match3d/engine.ts (bench/out/engine.cjs).
//   node bench/sim.mjs <matches>
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const E = require("./out/engine.cjs");

const matches = Number(process.argv[2] ?? 40);
const sum = {};
const add = (k, v) => (sum[k] = (sum[k] ?? 0) + v);
const kinds = {};
const t0 = performance.now();
let ticks = 0, stuck = 0;
for (let m = 0; m < matches; m++) {
  const s = E.createMatch({ seed: 1000 + m * 7, home: "A", away: "B", homeRating: 0.78, awayRating: 0.78 }, null);
  let ev = {};
  let ownerless = 0;
  let maxFree = 0, free = 0;
  while (s.phase !== 4 && s.tick < 60 * 400) {
    E.stepMatch(s, E.NO_INPUT);
    ticks++;
    if (s.ball.owner < 0 && s.phase === 1) { free++; ownerless++; if (free > maxFree) maxFree = free; } else free = 0;
    for (const e of s.ev) {
      ev[e.t] = (ev[e.t] ?? 0) + 1;
      if (e.t === "out") ev["out_" + e.set] = (ev["out_" + e.set] ?? 0) + 1;
      if (e.t === "kick") { kinds[e.kind] = (kinds[e.kind] ?? 0) + 1; }
      if (e.t === "goal" && e.long) ev.longGoal = (ev.longGoal ?? 0) + 1;
    }
  }
  if (s.phase !== 4) stuck++;
  for (const k of Object.keys(ev)) add(k, ev[k]);
  for (const t of s.teams) {
    add("shots", t.shots); add("onTarget", t.onTarget); add("passes", t.passes); add("passesOk", t.passesOk);
    add("goals", t.goals); add("fouls", t.fouls); add("tackles", t.tackles); add("corners2", t.corners);
  }
  add("poss0", s.teams[0].possTicks); add("poss1", s.teams[1].possTicks);
  add("ticks", s.tick); add("ownerless", ownerless); add("maxFree", maxFree);
}
const ms = performance.now() - t0;
const per = {};
for (const k of Object.keys(sum).sort()) per[k] = +(sum[k] / matches).toFixed(2);
console.log(`${matches} matches, ${ticks} ticks, ${(ms / ticks * 1000).toFixed(1)} us/tick, ${(ms / matches).toFixed(0)} ms/match, stuck ${stuck}`);
console.log(JSON.stringify(per));
console.log("kicks by kind", JSON.stringify(kinds));
