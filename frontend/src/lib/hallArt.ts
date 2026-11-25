/** «Зал славы» art: the default sprites and the look of the owner's items.
 * A skin or a decor item is a cosmetic whose `style_key` names its file
 * (assets/hall/niche_<key>.webp, pedestal_<key>.webp, decor/<key>.webp);
 * a picture uploaded in the admin panel (`image_path`) wins over the file. */
import type { HallDecorItem } from "@/api/profile";
import { staticUrl } from "@/lib/api";

import bannerArt from "@/assets/hall/banner.webp";
import nicheArt from "@/assets/hall/cabinet_niche.webp";
import pedestalArt from "@/assets/hall/pedestal.webp";
import plantArt from "@/assets/hall/plant.webp";
import ropeArt from "@/assets/hall/rope.webp";

export { bannerArt, nicheArt, pedestalArt, plantArt, ropeArt };

const FILES: Record<string, string> = Object.fromEntries(
  Object.entries(import.meta.glob("../assets/hall/**/*.webp", { eager: true, import: "default" }) as Record<string, string>).map(
    ([path, url]) => [path.split("/assets/hall/")[1].replace(/\.webp$/, ""), url],
  ),
);

const own = (item: HallDecorItem, file: string) => (item.image_path ? staticUrl(item.image_path) : null) ?? FILES[file] ?? null;

export const nicheSrc = (item: HallDecorItem | null | undefined) => (item ? own(item, `niche_${item.style_key}`) : null) ?? nicheArt;
export const pedestalSrc = (item: HallDecorItem | null | undefined) =>
  (item ? own(item, `pedestal_${item.style_key}`) : null) ?? pedestalArt;
export const decorSrc = (item: HallDecorItem) => own(item, `decor/${item.style_key}`);
