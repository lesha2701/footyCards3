// Is it football? AI against AI, headless, measured the way a match is judged:
// spells of possession, how a carrier is met, how compact the sides are.
//   node bench/audit.mjs <matches>
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const E = require("./out/engine.cjs");
const matches = Number(process.argv[2] ?? 20);
const hyp = Math.hypot;
const kind = {}; let open = null;
const c = { spells: 0, spellTicks: 0, passes: 0, turnovers: 0, free: 0, ticks: 0, swarm: 0, near6: 0, duels: 0, duelTried: 0, duelWon: 0, carry: 0, carries: 0, carryMax: 0, depth: 0, width: 0, shapeN: 0, ahead: 0, tacklesEv: 0 };
for (let m = 0; m < matches; m++) {
  const s = E.createMatch({ seed: 900 + m * 13, home: "A", away: "B", homeRating: 0.78, awayRating: 0.78 }, null);
  let owner = -1, team = -1, start = 0, passes = 0, cx = 0, cz = 0;
  const near = new Map();
  while (s.phase !== 4 && s.tick < 60 * 400) {
    E.stepMatch(s, E.NO_INPUT);
    if (s.phase !== 1) continue;
    const b = s.ball;
    c.ticks++;
    if (b.owner < 0) c.free++;
    if (open && s.ball.owner >= 0) { const k = (kind[open.k] ??= { n: 0, ok: 0 }); k.n++; if (s.players[s.ball.owner].team === open.team) k.ok++; open = null; }
    for (const e of s.ev) { if (e.t === "kick" && e.kind >= 1 && e.kind <= 4) open = { k: e.kind, team: s.players[e.p].team, x: s.ball.x, z: s.ball.z };
      if (e.t === "kick" && e.kind <= 3) { passes++; c.passes++; } if (e.t === "tackle") c.tacklesEv++; }
    if (b.owner >= 0) {
      const o = s.players[b.owner];
      if (o.team !== team) {
        if (team >= 0) { c.spells++; c.spellTicks += s.tick - start; c.turnovers++; }
        team = o.team; start = s.tick; passes = 0;
      }
      if (b.owner !== owner) {
        if (owner >= 0) { const d = hyp(cx - s.players[owner].x, cz - s.players[owner].z); c.carry += d; c.carries++; c.carryMax = Math.max(c.carryMax, d); }
        owner = b.owner; cx = o.x; cz = o.z;
      }
      // Who is on him, and does he do anything about it?
      const seen = new Set();
      for (const p of s.players) {
        if (p.team === o.team || p.role === "GK") continue;
        if (hyp(p.x - o.x, p.z - o.z) < 1.7) {
          seen.add(p.i);
          const n = near.get(p.i) ?? { t: 0, tried: false };
          n.t++; if (p.act === 3 || p.act === 4) n.tried = true;
          near.set(p.i, n);
        }
      }
      for (const [i, n] of near) if (!seen.has(i)) {
        if (n.t > 12) { c.duels++; if (n.tried) c.duelTried++; }
        near.delete(i);
      }
      // The side without it.
      if (s.tick % 20 === 0) {
        const d = s.players.filter((p) => p.team !== o.team && p.role !== "GK");
        const xs = d.map((p) => p.x), zs = d.map((p) => p.z);
        c.depth += Math.max(...xs) - Math.min(...xs); c.width += Math.max(...zs) - Math.min(...zs); c.shapeN++;
        const dir = o.team === 0 ? -1 : 1;
        c.ahead += d.filter((p) => (p.x - b.x) * dir < 0).length; // beaten: behind the ball, wrong side
        c.near6 += d.filter((p) => hyp(p.x - b.x, p.z - b.z) < 6).length;
      }
    }
  }
}
const n = matches;
console.log(`possession: ${(c.spells / n).toFixed(1)} spells a match, ${(c.spellTicks / c.spells / 60).toFixed(1)} s each, ${(c.passes / c.spells).toFixed(1)} passes each`);
console.log(`ball free ${(c.free / c.ticks * 100).toFixed(0)}% of play; carries ${(c.carry / c.carries).toFixed(1)} m mean, ${c.carryMax.toFixed(0)} m longest`);
console.log(`duels (defender on the carrier 0.2 s+): ${(c.duels / n).toFixed(1)} a match, tackle tried in ${(c.duelTried / c.duels * 100).toFixed(0)}%; tackles won/lost events ${(c.tacklesEv / n).toFixed(1)}`);
console.log(`block: ${(c.depth / c.shapeN).toFixed(1)} m deep, ${(c.width / c.shapeN).toFixed(1)} m wide; men goal-side of the ball ${(c.ahead / c.shapeN).toFixed(1)} of 10; within 6 m of the ball ${(c.near6 / c.shapeN).toFixed(1)}`);
const names = { 1: "pass", 2: "through", 3: "lob", 4: "cross" };
for (const k of Object.keys(kind)) console.log(`${names[k]}: ${(kind[k].n / n).toFixed(1)} a match, ${(kind[k].ok / kind[k].n * 100).toFixed(0)}% kept`);
