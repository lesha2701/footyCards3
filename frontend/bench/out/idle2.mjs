import { createRequire } from "module";
const require = createRequire(import.meta.url);
const E = require("./engine.cjs");
for (let m = 0; m < 10; m++) {
  const s = E.createMatch({ seed: 300 + m, home: "A", away: "B", homeRating: 0.78, awayRating: 0.78 }, 0);
  let since = -1, done = false;
  while (s.phase !== 4 && s.tick < 60 * 300 && !done) {
    E.stepMatch(s, E.NO_INPUT);
    const b = s.ball;
    const mine = s.phase === 1 && b.owner >= 0 && b.owner === s.user;
    if (mine) { if (since < 0) since = s.tick; } else since = -1;
    if (since >= 0 && s.tick - since > 1500) {
      const u = s.players[s.user];
      const opp = s.players.filter(p => p.team === 1).map(p => ({ r: p.role, d: +Math.hypot(p.x - b.x, p.z - b.z).toFixed(1), duty: p.duty, act: p.act, cool: p.cool, want: +p.want.toFixed(1), t:[+p.tx.toFixed(0),+p.tz.toFixed(0)], x:+p.x.toFixed(0) })).sort((a, c) => a.d - c.d).slice(0, 3);
      console.log(m, JSON.stringify({ role: u.role, x: +u.x.toFixed(1), z: +u.z.toFixed(1), act: u.act, since: b.since, poss: s.poss, opp }));
      done = true;
    }
  }
}
