// Checks the finished moves.glb against the model that plays it:
//   node verify_moves.mjs <moves.glb> <footballer.glb> <one-on-one moves.glb>
// Lists the clips, then fails if a track targets a bone footballer.glb doesn't
// have, a finger, a scale channel, or targets a name the old moves don't use.
import { NodeIO } from "@gltf-transform/core";
import { EXTMeshoptCompression, KHRMeshQuantization, KHRTextureTransform, EXTTextureWebP } from "@gltf-transform/extensions";
import { MeshoptDecoder } from "meshoptimizer";

const [, , movesPath, modelPath, oldPath] = process.argv;
await MeshoptDecoder.ready;
const io = new NodeIO()
  .registerExtensions([EXTMeshoptCompression, KHRMeshQuantization, KHRTextureTransform, EXTTextureWebP])
  .registerDependencies({ "meshopt.decoder": MeshoptDecoder });

const FINGERS = /Hand(Thumb|Index|Middle|Ring|Pinky)\d/;
const nodes = (doc) => new Set(doc.getRoot().listNodes().map((n) => n.getName()));
const tracks = (doc) =>
  new Set(doc.getRoot().listAnimations().flatMap((a) => a.listChannels().map((c) => `${c.getTargetNode()?.getName()}.${c.getTargetPath()}`)));

const moves = await io.read(movesPath);
const model = await io.read(modelPath);
const old = await io.read(oldPath);
const modelNodes = nodes(model);
const oldTracks = tracks(old);
const oldClips = new Set([...old.getRoot().listAnimations(), ...model.getRoot().listAnimations()].map((a) => a.getName()));

const problems = [];
let total = 0;
for (const anim of moves.getRoot().listAnimations()) {
  let end = 0;
  const channels = anim.listChannels();
  for (const ch of channels) {
    const name = ch.getTargetNode()?.getName() ?? "(none)";
    const path = ch.getTargetPath();
    const times = ch.getSampler().getInput().getArray();
    end = Math.max(end, times[times.length - 1]);
    if (!modelNodes.has(name)) problems.push(`${anim.getName()}: ${name} is not in footballer.glb`);
    if (FINGERS.test(name)) problems.push(`${anim.getName()}: finger track ${name}`);
    if (path === "scale") problems.push(`${anim.getName()}: scale track on ${name}`);
    if (!oldTracks.has(`${name}.${path}`)) problems.push(`${anim.getName()}: ${name}.${path} is not a track of one-on-one moves.glb`);
  }
  if (oldClips.has(anim.getName())) problems.push(`${anim.getName()}: already a clip of the older files`);
  total += end;
  // The biggest turn of one bone from one key to the next, in degrees per
  // 1/30 s: a pop shows here (a fast limb reads high too).
  let worst = { deg: 0, bone: "", at: 0 };
  for (const ch of channels) {
    if (ch.getTargetPath() !== "rotation") continue;
    const times = ch.getSampler().getInput().getArray();
    const v = ch.getSampler().getOutput().getArray();
    const scale = ch.getSampler().getOutput().getNormalized() ? 1 / 32767 : 1;
    const q = (i) => {
      const p = [0, 1, 2, 3].map((k) => v[i * 4 + k] * scale);
      const n = Math.hypot(...p);
      return p.map((x) => x / n);
    };
    for (let i = 1; i < times.length; i++) {
      const a = q(i - 1);
      const b = q(i);
      const dot = Math.min(1, Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]));
      const deg = (2 * Math.acos(dot) * 180) / Math.PI / Math.max(1, (times[i] - times[i - 1]) * 30);
      if (deg > worst.deg) worst = { deg, bone: ch.getTargetNode()?.getName().replace(/^mixamorig\d*:/, ""), at: times[i] };
    }
  }
  console.log(
    `${anim.getName().padEnd(16)} ${end.toFixed(2).padStart(5)} s  ${channels.length} tracks  worst step ${worst.deg.toFixed(0).padStart(3)} deg ${worst.bone} at ${worst.at.toFixed(2)}s`,
  );
}
const meshes = moves.getRoot().listMeshes().length;
if (meshes) problems.push(`${meshes} meshes went out`);
console.log(`${moves.getRoot().listAnimations().length} clips, ${total.toFixed(1)} s, ${meshes} meshes`);
console.log(`bones animated: ${new Set([...tracks(moves)].map((t) => t.split(".")[0])).size}; hips track: ${[...tracks(moves)].filter((t) => /Hips/.test(t)).join(", ")}`);
if (problems.length) {
  console.log(`PROBLEMS (${problems.length}):`);
  [...new Set(problems)].slice(0, 30).forEach((p) => console.log("  " + p));
  process.exit(1);
}
console.log("OK: every track is on a footballer.glb bone, a track name of one-on-one moves.glb, no fingers, no scale, no duplicate clip");
