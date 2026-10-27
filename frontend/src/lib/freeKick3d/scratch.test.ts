import { playShot } from "./trajectory";
test("find", () => {
  for (const [dy, dx, c] of [[-0.4,0.06,0],[-0.45,0.08,0.1],[-0.42,-0.1,-0.1],[-0.38,0.1,0],[-0.44,0.12,-0.15],[-0.36,0.04,0.12]]) {
    console.log(dy, dx, c, playShot(5, { dx, dy, curve: c, durationMs: 160 }).outcome);
  }
});
