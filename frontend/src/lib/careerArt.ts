/** «Карьера тренера» art: assets/career/<group>/<code>.webp (transparent
 * pictures: achievements, divisions, scenes, camps). Undefined when a file is
 * not there, so a screen keeps its emoji or plain card. */
const ART = import.meta.glob("/src/assets/career/*/*.webp", { eager: true, query: "?url", import: "default" }) as Record<string, string>;

export type CareerArtGroup = "achievements" | "divisions" | "scenes" | "camps";

export function careerArt(group: CareerArtGroup, code: string | number | null | undefined): string | undefined {
  if (code === null || code === undefined) return undefined;
  return ART[`/src/assets/career/${group}/${code}.webp`];
}
