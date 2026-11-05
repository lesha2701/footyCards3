// The benchmark's static server: the esbuild bundle (bench/out), the app's
// public assets, and /__bench keeping what a phone reports in bench/results.
import fs from "fs";
import http from "http";
import path from "path";

const root = path.dirname(new URL(import.meta.url).pathname);
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".webp": "image/webp", ".glb": "model/gltf-binary", ".css": "text/css" };

http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split("?")[0]);
  if (url === "/__bench" && req.method === "POST") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      fs.mkdirSync(path.join(root, "results"), { recursive: true });
      fs.writeFileSync(path.join(root, "results", `${Date.now()}.json`), body);
      res.writeHead(204).end();
    });
    return;
  }
  const files = url === "/" ? [path.join(root, "out/index.html")] : [path.join(root, "out", url), path.join(root, "..", "public", url)];
  const file = files.find((f) => fs.existsSync(f) && fs.statSync(f).isFile());
  if (!file) return res.writeHead(404).end();
  res.writeHead(200, { "Content-Type": types[path.extname(file)] ?? "application/octet-stream", "Cache-Control": "no-store" });
  fs.createReadStream(file).pipe(res);
}).listen(5173, "0.0.0.0");
