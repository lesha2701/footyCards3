// One stretch of a match as text: every kick, who got it, where.
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const E = require("./out/engine.cjs");
const K = ["-", "pass", "through", "lob", "cross", "SHOT", "clear", "throw", "save", "tackle", "header", "corner", "roll", "punt"];
const s = E.createMatch({ seed: Number(process.argv[2] ?? 77), home: "A", away: "B", homeRating: 0.78, awayRating: 0.78 }, null);
const from = 60 * Number(process.argv[3] ?? 30), to = from + 60 * Number(process.argv[4] ?? 40);
const tag = (p) => `${p.team ? "B" : "A"}${p.role}${p.i}`;
const at = (x, z) => `(${x.toFixed(0)},${z.toFixed(0)})`;
let owner = -1, took = 0;
while (s.phase !== 4 && s.tick < to) {
  E.stepMatch(s, E.NO_INPUT);
  const show = s.tick >= from;
  const b = s.ball;
  if (b.owner !== owner) {
    if (show && owner >= 0) { const o = s.players[owner]; console.log(`${(s.tick / 60).toFixed(1)}s   ${tag(o)} had it ${((s.tick - took) / 60).toFixed(1)}s, ended ${at(o.x, o.z)}`); }
    owner = b.owner; took = s.tick;
    if (show && owner >= 0) { const o = s.players[owner], d = o.team ? -1 : 1; let near = 99; for (const q of s.players) if (q.team !== o.team) near = Math.min(near, Math.hypot(q.x - o.x, q.z - o.z)); console.log(`${(s.tick / 60).toFixed(1)}s ${tag(o)} gets it ${at(o.x, o.z)} ax=${(o.x * d).toFixed(0)} near=${near.toFixed(1)}`); }
  }
  if (show) for (const e of s.ev) {
    if (e.t === "kick") { const p = s.players[e.p]; console.log(`${(s.tick / 60).toFixed(1)}s   ${tag(p)} ${K[e.kind]} v=${e.speed?.toFixed(0)} to=${b.to >= 0 ? tag(s.players[b.to]) : "-"} from ${at(p.x, p.z)} target ${b.to >= 0 ? at(s.players[b.to].x, s.players[b.to].z) : ""}`); }
    else if (e.t === "tackle" || e.t === "foul" || e.t === "out" || e.t === "goal" || e.t === "offside") console.log(`${(s.tick / 60).toFixed(1)}s   ** ${e.t} ${e.set ?? ""} ${e.won ?? ""}`);
  }
}
