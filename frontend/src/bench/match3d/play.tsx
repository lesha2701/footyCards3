/** The match by itself, for a phone on the local network: bench/out/play.html.
 * Every 15 s it reports how the device copes (the server keeps it in
 * bench/results), so a real game is its own performance measurement. */
import { createRoot } from "react-dom/client";

import Match3DGame from "@/components/match3d/Match3DGame";

type Debug = { g?: { dpr: number; renderer: { info: { render: { calls: number; triangles: number } } } } };

const demo = new URLSearchParams(location.search).has("demo");
createRoot(document.getElementById("root")!).render(<Match3DGame demo={demo} onExit={() => location.reload()} />);

let last = performance.now();
let frames: number[] = [];
const started = Date.now();
const loop = (now: number) => {
  frames.push(now - last);
  last = now;
  requestAnimationFrame(loop);
};
requestAnimationFrame(loop);

setInterval(() => {
  const debug = (window as unknown as { __m3d?: Debug }).__m3d;
  if (!debug?.g || document.hidden) { frames = []; return; }
  const sorted = [...frames].sort((a, b) => a - b);
  const sum = frames.reduce((a, b) => a + b, 0) || 1;
  const info = debug.g.renderer.info.render;
  void fetch("/__bench", {
    method: "POST",
    body: JSON.stringify({
      kind: "play", at: Math.round((Date.now() - started) / 1000), ua: navigator.userAgent, screen: `${innerWidth}x${innerHeight}@${devicePixelRatio}`,
      fps: Math.round((frames.length * 1000) / sum), p95: Math.round(sorted[Math.floor(sorted.length * 0.95)] ?? 0), dpr: debug.g.dpr, calls: info.calls, tris: info.triangles,
    }),
  }).catch(() => {});
  frames = [];
}, 15000);
