// A scripted thumb playing team 0 through Input, as a phone does: how often a
// human's pass arrives, what becomes of the keeper's ball, how close the man
// he controls is to the action. Reads bench/out/engine.cjs (see sim.mjs).
//   node bench/human.mjs <matches>
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const E = require("./out/engine.cjs");

const matches = Number(process.argv[2] ?? 20);
const c = { shots: 0, onT: 0, pass: 0, passOurs: 0, passTheirs: 0, passOut: 0, gk: 0, gkOurs: 0, gkTheirs: 0, gkOut: 0, off: 0, defTicks: 0, defNearest: 0, defGap: 0, g0: 0, g1: 0, staminaEnd: 0, staminaN: 0, userGk: 0 };

let seedR = 12345;
const r = () => { seedR = (seedR * 1103515245 + 12345) & 0x7fffffff; return seedR / 0x7fffffff; };

for (let m = 0; m < matches; m++) {
  const s = E.createMatch({ seed: 500 + m * 11, home: "A", away: "B", homeRating: 0.78, awayRating: 0.78 }, 0);
  let open = null; // { gk } a kick of ours on its way
  let wait = 0, sx = 1, sz = 0, wild = 0;
  while (s.phase !== 4 && s.tick < 60 * 400) {
    const b = s.ball, u = s.user >= 0 ? s.players[s.user] : null;
    const inp = { mx: 0, mz: 0, sprint: false, press: null, contain: false };
    if (u) {
      const mine = b.owner === u.i;
      if (u.role === "GK") c.userGk++;
      const taking = s.set && s.set.taker === u.i && s.set.ready;
      if (mine || taking) {
        wait++;
        if (wild > 0) { sx = 1; sz = (r() - 0.5) * 1.4; wild = 0; }
        inp.mx = sx; inp.mz = sz; inp.sprint = mine && u.stamina > 0.3;
        if (wait > 90) { inp.press = { k: "pass", power: 0.4 }; wait = 0; wild = 1; }
        if (mine && u.x > 26 && Math.abs(u.z) > 14) { inp.press = { k: "lob", power: 0.6 }; wait = 0; wild = 1; c.crosses = (c.crosses ?? 0) + 1; }
        else if (mine && u.x > 24 && Math.abs(u.z) < 18 && wait > 6) { inp.press = { k: "shot", power: 0.7, curl: 0, chip: false }; wait = 0; }
      } else if (b.owner < 0 && b.to >= 0) {
        // The thumb stays where it was while the ball travels.
        inp.mx = sx; inp.mz = sz; inp.sprint = true;
      } else {
        const dx = b.x - u.x, dz = b.z - u.z, d = Math.sqrt(dx * dx + dz * dz) || 1;
        inp.mx = dx / d; inp.mz = dz / d; inp.sprint = d > 4;
        const o = b.owner >= 0 ? s.players[b.owner] : null;
        if (o && o.team === 1 && d < 1.5 && s.tick % 30 === 0) inp.press = { k: "tackle" };
      }
    }
    const wasOwner = b.owner;
    E.stepMatch(s, inp);
    for (const e of s.ev) {
      if (e.t === "offside" && s.players[e.p].team === 0) c.off++;
      if (e.t !== "kick") continue;
      const k = s.players[e.p];
      if (k.team !== 0 || s.ball.to < 0) continue;
      const gk = k.role === "GK";
      open = { gk }; c[gk ? "gk" : "pass"]++;
    }
    if (open) {
      const name = open.gk ? "gk" : "pass";
      if (s.ball.owner >= 0) { c[name + (s.players[s.ball.owner].team === 0 ? "Ours" : "Theirs")]++; open = null; }
      else if (s.phase !== 1) { c[name + "Out"]++; open = null; }
      else if (s.ball.to < 0 && s.ball.last >= 0 && s.players[s.ball.last].team === 1) { c[name + "Theirs"]++; open = null; }
    }
    if (s.phase === 1 && s.ball.owner >= 0 && s.players[s.ball.owner].team === 1 && s.user >= 0) {
      let top = 1e9;
      const bb = s.ball;
      for (const p of s.players) if (p.team === 0 && p.role !== "GK") top = Math.min(top, Math.hypot(p.x - bb.x, p.z - bb.z));
      const us = Math.hypot(s.players[s.user].x - bb.x, s.players[s.user].z - bb.z);
      c.defTicks++; c.defGap += us - top; if (us - top < 2) c.defNearest++;
      const back = s.players.filter((p) => p.team === 0 && (p.role === "CB" || p.role === "FB")).map((p) => p.x);
      const mid = s.players.filter((p) => p.team === 0 && (p.role === "CM" || p.role === "DM")).map((p) => p.x);
      c.lineSpread = (c.lineSpread ?? 0) + Math.max(...back) - Math.min(...back);
      c.lineGap = (c.lineGap ?? 0) + Math.abs(mid.reduce((a, v) => a + v, 0) / mid.length - back.reduce((a, v) => a + v, 0) / back.length);
    }
    void wasOwner;
  }
  c.corners = (c.corners ?? 0) + s.teams[0].corners; c.shots += s.teams[0].shots; c.onT += s.teams[0].onTarget; c.g0 += s.teams[0].goals; c.g1 += s.teams[1].goals;
  for (const p of s.players) if (p.stamina !== undefined) { c.staminaEnd += p.stamina; c.staminaN++; }
}
const pct = (a, b) => (b ? Math.round(a / b * 100) : 0);
console.log(`${matches} matches`);
console.log(`passes ${(c.pass / matches).toFixed(1)}/match: reached ours ${pct(c.passOurs, c.pass)}%, opponent ${pct(c.passTheirs, c.pass)}%, dead ${pct(c.passOut, c.pass)}%; offsides ${(c.off / matches).toFixed(1)}`);
console.log(`keeper ${(c.gk / matches).toFixed(1)}/match: ours ${pct(c.gkOurs, c.gk)}%, opponent ${pct(c.gkTheirs, c.gk)}%, dead ${pct(c.gkOut, c.gk)}%; ticks as keeper ${(c.userGk / matches).toFixed(0)}`);
console.log(`defending: within 2 m of the nearest man ${pct(c.defNearest, c.defTicks)}%, mean gap ${(c.defGap / (c.defTicks || 1)).toFixed(1)} m`);
console.log(`shape without the ball: back four ${(c.lineSpread / (c.defTicks || 1)).toFixed(1)} m deep, back to midfield ${(c.lineGap / (c.defTicks || 1)).toFixed(1)} m`);
console.log(`crosses ${((c.crosses ?? 0) / matches).toFixed(1)}, corners ${(c.corners / matches).toFixed(1)}`);
console.log(`shots ${(c.shots / matches).toFixed(1)}, on target ${(c.onT / matches).toFixed(1)}; goals ${(c.g0 / matches).toFixed(1)}:${(c.g1 / matches).toFixed(1)}; stamina at the end ${c.staminaN ? (c.staminaEnd / c.staminaN).toFixed(2) : "-"}`);
