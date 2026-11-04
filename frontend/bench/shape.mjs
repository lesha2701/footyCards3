// What a player complains about, in numbers (AI against AI, headless):
// does the side without the ball clump or cover men, what becomes of long
// balls, how far a loose ball runs, do men get ahead of the ball, does the
// ball change flanks. Reads bench/out/engine.cjs (see sim.mjs).
//   node bench/shape.mjs <matches>
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const E = require("./out/engine.cjs");
const matches = Number(process.argv[2] ?? 20);
const hyp = Math.hypot;
const c = { n: 0, near6: 0, pairs: 0, pairsHave: 0, big: 0, free: 0, ahead: 0, runs: 0, sw: 0, keeperBack: 0, gk: 0 };
const longs = { n: 0, ours: 0, theirs: 0, header: 0, dead: 0, far: 0 };
const loose = {};
const pick = (o, k) => (o[k] ??= { n: 0, sum: 0, max: 0, over20: 0 });
const pairsOf = (t) => { let n = 0; for (let i = 0; i < t.length; i++) for (let j = i + 1; j < t.length; j++) if (hyp(t[i].x - t[j].x, t[i].z - t[j].z) < 6) n++; return n; };
for (let m = 0; m < matches; m++) {
  const s = E.createMatch({ seed: 900 + m * 13, home: "A", away: "B", homeRating: 0.78, awayRating: 0.78 }, null);
  let long = null, lo = null, gk = null;
  const dashing = new Set();
  while (s.phase !== 4 && s.tick < 60 * 400) {
    E.stepMatch(s, E.NO_INPUT);
    const b = s.ball;
    if (s.phase !== 1) { if (long) { longs.dead++; long = null; } lo = null; gk = null; continue; }
    for (const e of s.ev) {
      if (e.t !== "kick") continue;
      const p = s.players[e.p];
      if ((e.kind === 3 || e.kind === 13) && !long) { longs.n++; long = { team: p.team, tick: s.tick }; }
      if (e.kind === 10 && long) { longs.header++; long = null; }
      if (e.kind === 12 || e.kind === 13 || (p.role === "GK" && e.kind === 3)) { c.gk++; gk = { team: p.team, tick: s.tick, x: p.x, z: p.z }; }
      if (e.kind === 10 || e.kind === 9) lo = { k: e.kind === 10 ? "header" : "deflect", x: b.x, z: b.z };
      if (e.kind === 1 || e.kind === 3) { const t = b.to >= 0 ? s.players[b.to] : null; if (t && Math.abs(t.z - p.z) > 25) c.sw++; }
    }
    for (const e of s.ev) if (e.t === "tackle" && e.won) lo = { k: "tackle", x: b.x, z: b.z };
    if (b.owner >= 0) {
      const o = s.players[b.owner];
      if (long) { longs[o.team === long.team ? "ours" : "theirs"]++; long = null; }
      if (lo) { const d = hyp(b.x - lo.x, b.z - lo.z), q = pick(loose, lo.k); q.n++; q.sum += d; q.max = Math.max(q.max, d); if (d > 20) q.over20++; lo = null; }
      if (gk) { if (o.team !== gk.team && hyp(o.x - gk.x, o.z - gk.z) < 8 && s.tick - gk.tick < 120) c.keeperBack++; gk = null; }
      if (s.tick % 20 === 0) {
        const def = s.players.filter((p) => p.team !== o.team && p.role !== "GK");
        const att = s.players.filter((p) => p.team === o.team && p.role !== "GK");
        const dir = o.team === 0 ? 1 : -1;
        c.n++;
        c.near6 += def.filter((p) => hyp(p.x - b.x, p.z - b.z) < 6).length;
        c.pairs += pairsOf(def); c.pairsHave += pairsOf(att);
        let big = 0; for (const p of def) big = Math.max(big, def.filter((q) => hyp(p.x - q.x, p.z - q.z) < 9).length);
        c.big += big;
        c.free += att.filter((a) => a !== o && hyp(a.x - b.x, a.z - b.z) < 30 && !def.some((d) => hyp(a.x - d.x, a.z - d.z) < 5)).length;
        c.ahead += att.filter((a) => (a.x - b.x) * dir > 6).length;
      }
    }
    for (const p of s.players) { if (p.dash > 0) { if (!dashing.has(p.i)) { dashing.add(p.i); c.runs++; } } else dashing.delete(p.i); }
  }
}
const f = (v, k = 1) => v.toFixed(k);
console.log(`without the ball: ${f(c.near6 / c.n)} men within 6 m of it, ${f(c.pairs / c.n)} pairs closer than 6 m, biggest bunch ${f(c.big / c.n)}; free men near the ball ${f(c.free / c.n)}`);
console.log(`with the ball: ${f(c.pairsHave / c.n)} pairs closer than 6 m, ${f(c.ahead / c.n)} men 6 m+ ahead of it; ${f(c.runs / matches)} runs a match, ${f(c.sw / matches)} switches of flank`);
console.log(`long balls ${f(longs.n / matches)}: kept ${Math.round(longs.ours / longs.n * 100)}%, lost ${Math.round(longs.theirs / longs.n * 100)}%, headed ${Math.round(longs.header / longs.n * 100)}%, dead ${Math.round(longs.dead / longs.n * 100)}%`);
for (const k of Object.keys(loose)) console.log(`after a ${k}: ${f(loose[k].n / matches)} a match, ball runs ${f(loose[k].sum / loose[k].n)} m, ${loose[k].max.toFixed(0)} longest, ${Math.round(loose[k].over20 / loose[k].n * 100)}% over 20 m`);
console.log(`keeper's balls ${f(c.gk / matches)}, ${f(c.keeperBack / matches, 2)} a match straight to a man near him`);
