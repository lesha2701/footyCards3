/** Building thumbnails for «Клубная база» lists, cut from the town picture
 * (src/assets/base/thumbs/<code>.webp, the same buildings as on the map). */
const THUMBS = import.meta.glob<string>("@/assets/base/thumbs/*.webp", { eager: true, import: "default" });

export const thumbOf = (code: string): string | undefined => THUMBS[`/src/assets/base/thumbs/${code}.webp`];
