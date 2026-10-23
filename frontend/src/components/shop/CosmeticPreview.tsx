import { staticUrl } from "@/lib/api";
import { BRUTALITY_EMOJI, ENTRANCE_EMOJI, GLOVE_FILTERS, SHORTS_STYLES, backgroundClass, cardSkinClass, frameClass } from "@/lib/cosmetics";
import type { CosmeticCatalogItem } from "@/types";

/** A small picture of what an item looks like; `lg` for shop tiles and the
 * details sheet. */
export default function CosmeticPreview({
  item, avatarUrl, size = "md",
}: {
  item: Pick<CosmeticCatalogItem, "kind" | "style_key"> & { image_path?: string | null };
  avatarUrl?: string;
  size?: "md" | "lg";
}) {
  const lg = size === "lg";
  if (item.image_path && item.kind !== "brutality") {
    return <img src={staticUrl(item.image_path)} alt="" className={`rounded-2xl object-cover ${lg ? "h-20 w-20" : "h-12 w-12"}`} />;
  }
  if (item.kind === "ring_gloves" || item.kind === "helmet" || item.kind === "ring_entrance") {
    const emoji = item.kind === "ring_gloves" ? "🥊" : item.kind === "helmet" ? "🪖" : ENTRANCE_EMOJI[item.style_key] ?? "✨";
    return (
      <span className={`flex items-center justify-center rounded-2xl bg-gradient-to-br from-yellow-500/25 via-red-500/10 to-transparent ${lg ? "h-20 w-20 text-5xl" : "h-12 w-12 text-3xl"}`}>
        <span style={item.kind === "ring_gloves" ? { filter: GLOVE_FILTERS[item.style_key] } : undefined}>{emoji}</span>
      </span>
    );
  }
  if (item.kind === "ring_shorts") {
    return (
      <span className={`flex flex-col items-center justify-end rounded-2xl bg-white/5 p-2 ${lg ? "h-20 w-20" : "h-12 w-12"}`}>
        <span className={`block h-1/2 w-full rounded-b-xl rounded-t-sm ${SHORTS_STYLES[item.style_key] ?? SHORTS_STYLES.red}`} />
      </span>
    );
  }
  if (item.kind === "brutality") {
    if (item.image_path) {
      return <img src={staticUrl(item.image_path)} alt="" className={`rounded-2xl object-cover ${lg ? "h-20 w-20" : "h-12 w-12"}`} />;
    }
    return (
      <span className={`flex items-center justify-center rounded-2xl bg-gradient-to-br from-red-600/40 via-yellow-500/20 to-transparent ${lg ? "h-20 w-20 text-5xl" : "h-12 w-12 text-3xl"}`}>
        {BRUTALITY_EMOJI[item.style_key] ?? "🥊"}
      </span>
    );
  }
  if (item.kind === "card_skin") {
    return (
      <span className={`block aspect-[3/4] rounded-lg bg-gradient-to-b from-slate-400 to-slate-600 p-[2px] ${lg ? "w-20" : "w-12"} ${cardSkinClass(item.style_key) ?? ""}`}>
        <span className="block h-full w-full rounded-[6px] bg-bg-base" />
      </span>
    );
  }
  if (item.kind === "profile_background") {
    return <span className={`block rounded-xl ${lg ? "h-20 w-28" : "h-12 w-16"} ${backgroundClass(item.style_key) ?? "bg-bg-raised"}`} />;
  }
  return (
    <span className={`block rounded-full ${lg ? "p-1" : "p-[3px]"} ${frameClass(item.style_key) ?? ""}`}>
      <img
        src={avatarUrl ?? staticUrl("players/placeholder/player_placeholder.webp")}
        alt=""
        className={`rounded-full object-cover ring-2 ring-bg-base ${lg ? "h-20 w-20" : "h-11 w-11"}`}
      />
    </span>
  );
}
