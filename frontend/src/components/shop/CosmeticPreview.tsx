import { staticUrl } from "@/lib/api";
import { backgroundClass, cardSkinClass, frameClass } from "@/lib/cosmetics";
import type { CosmeticCatalogItem } from "@/types";

/** A small picture of what an item looks like; `lg` for shop tiles and the
 * details sheet. */
export default function CosmeticPreview({
  item, avatarUrl, size = "md",
}: {
  item: Pick<CosmeticCatalogItem, "kind" | "style_key">;
  avatarUrl?: string;
  size?: "md" | "lg";
}) {
  const lg = size === "lg";
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
