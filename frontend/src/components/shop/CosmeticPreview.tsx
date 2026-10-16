import { staticUrl } from "@/lib/api";
import { backgroundClass, cardSkinClass, frameClass } from "@/lib/cosmetics";
import type { CosmeticCatalogItem } from "@/types";

/** A small picture of what an item looks like. */
export default function CosmeticPreview({ item, avatarUrl }: { item: Pick<CosmeticCatalogItem, "kind" | "style_key">; avatarUrl?: string }) {
  if (item.kind === "card_skin") {
    return (
      <span className={`block aspect-[3/4] w-12 rounded-lg bg-gradient-to-b from-slate-400 to-slate-600 p-[2px] ${cardSkinClass(item.style_key) ?? ""}`}>
        <span className="block h-full w-full rounded-[6px] bg-bg-base" />
      </span>
    );
  }
  if (item.kind === "profile_background") {
    return <span className={`block h-12 w-16 rounded-lg ${backgroundClass(item.style_key) ?? "bg-bg-raised"}`} />;
  }
  return (
    <span className={`block rounded-full p-[3px] ${frameClass(item.style_key) ?? ""}`}>
      <img
        src={avatarUrl ?? staticUrl("players/placeholder/player_placeholder.webp")}
        alt=""
        className="h-11 w-11 rounded-full object-cover ring-2 ring-bg-base"
      />
    </span>
  );
}
