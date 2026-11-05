// What a slide is worth from each side and distance, for a man pressing the
// button at a carrier the AI drives: ball won, kept by his own side, foul, miss.
// Reads bench/out/engine.cjs (see sim.mjs).   node bench/slide.mjs [trials]
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const E = require("./out/engine.cjs");

const trials = Number(process.argv[2] ?? 40);
const PLAY = 1, ONE = { mx: 0, mz: 0, sprint: false, press: null, contain: false };
const SIDES = { front: [-1, 0], angle: [-0.7, 0.7], side: [0, 1], behind: [1, 0.2] };

function setUp(seed, rx, rz, gap) {
  const s = E.createMatch({ seed, home: "A", away: "B", homeRating: 0.78, awayRating: 0.78 }, 0);
  for (let i = 0; i < 900 && s.phase !== PLAY; i++) E.stepMatch(s, ONE);
  s.set = null;
  const c = s.players.find((p) => p.team === 1 && p.role === "CM");
  const u = s.players.find((p) => p.team === 0 && p.role === "CM");
  for (const p of s.players) {
    if (p === c || p === u || p.role === "GK") continue;
    const side = p.team === 0 ? -1 : 1;
    p.x = side * (30 + p.slot); p.z = 25 - p.slot; p.vx = 0; p.vz = 0;
    if (p.team === 0 && p.role === "W") { p.x = -14; p.z = 7 - p.i; }
  }
  c.x = 0; c.z = 0; c.hx = -1; c.hz = 0; c.vx = -5; c.vz = 0; c.act = 0; c.cool = 0; c.plan = null;
  const l = Math.sqrt(rx * rx + rz * rz);
  u.x = (rx / l) * gap; u.z = (rz / l) * gap;
  const hx = -rx / l, hz = -rz / l;
  u.hx = hx; u.hz = hz; u.vx = hx * 6; u.vz = hz * 6; u.act = 0; u.cool = 0;
  s.user = u.i; s.poss = 1;
  const b = s.ball;
  b.x = -0.5; b.y = 0.11; b.z = 0; b.vx = -5; b.vy = 0; b.vz = 0;
  b.owner = c.i; b.last = c.i; b.kick = 0; b.to = -1; b.since = 90;
  return { s, u, c };
}

console.log("side    gap  dislodged  ours  foul  miss");
for (const [name, [rx, rz]] of Object.entries(SIDES)) {
  for (const gap of [1.5, 2.5, 3.5, 4.5, 5.5]) {
    let won = 0, ours = 0, foul = 0, miss = 0;
    for (let n = 0; n < trials; n++) {
      const { s, u, c } = setUp(9000 + n * 13, rx, rz, gap);
      E.stepMatch(s, { ...ONE, press: { k: "slide" } });
      let lost = false, fouled = false;
      let i = 0;
      for (; i < 150; i++) {
        E.stepMatch(s, ONE);
        if (s.ev?.some?.((e) => e.t === "foul")) fouled = true;
        if (s.phase !== PLAY) break;
        if (s.ball.owner !== c.i) lost = true;
        if (lost && s.ball.owner >= 0 && s.ball.owner !== c.i) break;
      }
      if (fouled || s.set?.kind === "free" || s.set?.kind === "penalty") { foul++; continue; }
      if (!lost) { miss++; continue; }
      won++;
      if (s.ball.owner >= 0 && s.players[s.ball.owner].team === 0) ours++;
    }
    const f = (v) => String(Math.round((v / trials) * 100)).padStart(4) + "%";
    console.log(name.padEnd(7), String(gap).padEnd(4), f(won), "    ", f(ours), f(foul), f(miss));
  }
}

// In whole matches, AI against AI: how often they go to ground and what comes of it.
const c = { n: 0, won: 0, foul: 0, ours: 0, behind: 0 };
const games = 12;
for (let m = 0; m < games; m++) {
  const s = E.createMatch({ seed: 700 + m * 7, home: "A", away: "B", homeRating: 0.78, awayRating: 0.78 }, null);
  const was = new Array(22).fill(0);
  let open = null;
  while (s.phase !== 4 && s.tick < 60 * 400) {
    E.stepMatch(s, ONE);
    for (const p of s.players) {
      if (p.act === 4 && was[p.i] !== 4) c.n++;
      was[p.i] = p.act;
    }
    for (const e of s.ev) {
      if (e.t === "foul" && was[e.p] === 4) c.foul++;
      if (e.t === "tackle" && e.won && was[e.p] === 4) { c.won++; open = s.players[e.p].team; }
    }
    if (open !== null && s.ball.owner >= 0) { if (s.players[s.ball.owner].team === open) c.ours++; open = null; }
  }
}
console.log(`matches: ${(c.n / games).toFixed(1)} slides a match, won ${(c.won / (c.n || 1)).toFixed(2)}, kept by the side ${(c.ours / (c.won || 1)).toFixed(2)}, fouls ${(c.foul / (c.n || 1)).toFixed(2)}`);
