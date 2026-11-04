import { createRequire } from "module";
const require = createRequire(import.meta.url);
const E = require("./engine.cjs");
// A human who never touches anything, a dead thumb: how long does he keep it?
const hold = [];
let stats = { starts: 0, won: 0, lost: 0, foul: 0 };
for (let m = 0; m < 10; m++) {
  const s = E.createMatch({ seed: 300 + m, home: "A", away: "B", homeRating: 0.78, awayRating: 0.78 }, 0);
  let since = -1;
  let lastAct = {};
  while (s.phase !== 4 && s.tick < 60 * 300) {
    E.stepMatch(s, E.NO_INPUT);
    for (const e of s.ev) {
      if (e.t === "tackle") stats[e.won ? "won" : "lost"]++;
      if (e.t === "foul") stats.foul++;
    }
    for (const p of s.players) { if (p.act === 3 && lastAct[p.i] !== 3) stats.starts++; lastAct[p.i] = p.act; }
    const b = s.ball;
    const mine = s.phase === 1 && b.owner >= 0 && b.owner === s.user;
    if (mine) { if (since < 0) since = s.tick; } else if (since >= 0) { hold.push(s.tick - since); since = -1; }
  }
  if (since >= 0) hold.push(s.tick - since);
}
hold.sort((a, b) => a - b);
console.log("human holds", hold.length, "median s", (hold[hold.length >> 1] / 60).toFixed(1), "max s", (hold[hold.length - 1] / 60).toFixed(1), JSON.stringify(stats));
