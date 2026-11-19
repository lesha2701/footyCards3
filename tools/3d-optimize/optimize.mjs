// Shrinks the game's skinned footballer GLBs without touching what's shown:
//   - drops the rig's own empty Mixamo take ("Armature|mixamo.com|Layer0")
//     and scale channels (Mixamo keys none — every one is a constant 1);
//   - freezes the fingers (30 of the rig's 65 bones, ~45% of the clip data,
//     a few pixels on a phone): each finger bone's rest rotation becomes its
//     first "idle" key — a relaxed hand — and its channels are dropped. The
//     shared moves GLBs never animated the fingers anyway (strip_moves.mjs);
//   - resamples the clips: keys that linear/slerp interpolation reproduces
//     within a tiny tolerance are removed (fingers and most of the spine
//     barely move, so they collapse to a handful of keys);
//   - optionally (--simplify <ratio>) decimates the mesh, keeping UV seams
//     and the silhouette;
//   - writes meshopt-compressed (EXT_meshopt_compression), like the inputs.
//
//   node optimize.mjs <in.glb> <out.glb> [--simplify 0.6] [--tolerance 1e-4]
import { NodeIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS, EXTMeshoptCompression } from "@gltf-transform/extensions";
import { dedup, prune, resample, simplify, weld } from "@gltf-transform/functions";
import { MeshoptDecoder, MeshoptEncoder, MeshoptSimplifier } from "meshoptimizer";

const [, , src, dst, ...rest] = process.argv;
const opt = (name, fallback) => {
  const i = rest.indexOf(`--${name}`);
  return i >= 0 ? Number(rest[i + 1]) : fallback;
};
const simplifyRatio = opt("simplify", 0);
const tolerance = opt("tolerance", 1e-4);

await Promise.all([MeshoptDecoder.ready, MeshoptEncoder.ready, MeshoptSimplifier.ready]);
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ "meshopt.decoder": MeshoptDecoder, "meshopt.encoder": MeshoptEncoder });
const doc = await io.read(src);

const FINGERS = /Hand(Thumb|Index|Middle|Ring|Pinky)\d/;
const anims = doc.getRoot().listAnimations();
const idle = anims.find((a) => a.getName() === "idle");
for (const ch of idle?.listChannels() ?? []) {
  const node = ch.getTargetNode();
  if (ch.getTargetPath() === "rotation" && node && FINGERS.test(node.getName())) {
    node.setRotation(ch.getSampler().getOutput().getElement(0, []));
  }
}

for (const anim of anims) {
  if (anim.getName().includes("|")) {
    anim.listChannels().forEach((c) => c.getSampler()?.dispose());
    anim.dispose();
    continue;
  }
  for (const ch of anim.listChannels()) {
    const node = ch.getTargetNode();
    if (ch.getTargetPath() === "scale" || (node && FINGERS.test(node.getName()))) {
      ch.getSampler()?.dispose();
      ch.dispose();
    }
  }
}

const steps = [resample({ tolerance })];
if (simplifyRatio > 0) {
  steps.push(weld(), simplify({ simplifier: MeshoptSimplifier, ratio: simplifyRatio, error: 0.001 }));
}
steps.push(dedup(), prune({ keepAttributes: true, keepLeaves: true }));
await doc.transform(...steps);

doc.createExtension(EXTMeshoptCompression).setRequired(true).setEncoderOptions({
  method: EXTMeshoptCompression.EncoderMethod.FILTER,
});
await io.write(dst, doc);
