// Drops what the replay never shows from footballer-moves.glb: the fingers,
// scale channels (Mixamo keys none) and the rig's own empty take.
//   node strip_moves.mjs <in.glb> <out.glb>
import { NodeIO } from "@gltf-transform/core";

const [, , src, dst] = process.argv;
const io = new NodeIO();
const doc = await io.read(src);
const FINGERS = /Hand(Thumb|Index|Middle|Ring|Pinky)\d/;
for (const anim of doc.getRoot().listAnimations()) {
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
await io.write(dst, doc);
