/** The match by itself, for a phone on the local network: bench/out/play.html.
 * Every 15 s it reports how the device copes (the server keeps it in
 * bench/results), so a real game is its own performance measurement. */
import { createRoot } from "react-dom/client";

import Match3DGame from "@/components/match3d/Match3DGame";

type Debug = { dpr: number; renderer: { getContext: () => WebGL2RenderingContext; capabilities: { maxTextureSize: number; maxAttributes: number; maxVertexTextures: number }; info: { render: { calls: number; triangles: number } } } };

const problems: string[] = [];
for (const level of ["error", "warn"] as const) {
  const original = console[level].bind(console);
  console[level] = (...args: unknown[]) => {
    if (problems.length < 12) problems.push(args.map(String).join(" ").slice(0, 600));
    original(...args);
  };
}

let game: Debug | null = null;
const demo = new URLSearchParams(location.search).has("demo");
createRoot(document.getElementById("root")!).render(<Match3DGame demo={demo} onExit={() => location.reload()} onGame={(g) => { game = g as unknown as Debug; (window as unknown as { __g: unknown }).__g = g; }} />);

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
  if (!game || document.hidden) { frames = []; return; }
  const sorted = [...frames].sort((a, b) => a - b);
  const sum = frames.reduce((a, b) => a + b, 0) || 1;
  const info = game.renderer.info.render;
  const caps = game.renderer.capabilities;
  const gl = game.renderer.getContext();
  const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
  void fetch("/__bench", {
    method: "POST",
    body: JSON.stringify({
      kind: "play", at: Math.round((Date.now() - started) / 1000), ua: navigator.userAgent, screen: `${innerWidth}x${innerHeight}@${devicePixelRatio}`,
      fps: Math.round((frames.length * 1000) / sum), p95: Math.round(sorted[Math.floor(sorted.length * 0.95)] ?? 0), dpr: game.dpr, calls: info.calls, tris: info.triangles,
      gpu: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : "", maxTexture: caps.maxTextureSize, maxAttributes: caps.maxAttributes, vertexTextures: caps.maxVertexTextures, glError: gl.getError(), problems,
    }),
  }).catch(() => {});
  frames = [];
}, 15000);
