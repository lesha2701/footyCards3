/** Illustrated game art (src/assets/games/<key>.webp, 192 px): the Play tab tiles and the
 * game page headers (GameHero). Games without a picture keep their tinted icon. */
const GAME_ART = import.meta.glob<string>("@/assets/games/*.webp", { eager: true, import: "default" });

export const artOf = (key: string): string | undefined => GAME_ART[`/src/assets/games/${key}.webp`];
