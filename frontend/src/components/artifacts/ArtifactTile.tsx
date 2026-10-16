import { staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS } from "@/lib/rarity";
import type { ArtifactInfo } from "@/types";

/** The artifact's picture in a rarity frame — the same look as gifts. */
export default function ArtifactTile({
  artifact, serial, dimmed = false, size = "md",
}: {
  artifact: ArtifactInfo;
  serial?: number | null;
  dimmed?: boolean;
  size?: "sm" | "md";
}) {
  const box = size === "sm" ? "h-14 w-14" : "h-20 w-20";
  return (
    <span className={`relative block shrink-0 rounded-2xl bg-gradient-to-b p-[2px] ${RARITY_GRADIENTS[artifact.rarity]} ${dimmed ? "opacity-60 grayscale-[40%]" : ""}`}>
      <span className={`flex ${box} items-center justify-center overflow-hidden rounded-[14px] bg-bg-raised`}>
        {artifact.image_path ? (
          <img src={staticUrl(artifact.image_path)} alt={artifact.name} loading="lazy" decoding="async" className="h-full w-full object-cover" />
        ) : (
          <span className={size === "sm" ? "text-2xl" : "text-4xl"}>{artifact.icon}</span>
        )}
      </span>
      {serial != null && (
        <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 rounded-full bg-black/80 px-1.5 font-mono text-micro text-ink-chalk">
          №{serial}
        </span>
      )}
    </span>
  );
}
