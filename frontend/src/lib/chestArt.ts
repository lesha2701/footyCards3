/** Activity chests of «Задания» (src/assets/chests/<kind>[-open].webp, 320 px). */
import emerald from "@/assets/chests/emerald.webp";
import emeraldOpen from "@/assets/chests/emerald-open.webp";
import gold from "@/assets/chests/gold.webp";
import goldOpen from "@/assets/chests/gold-open.webp";
import legend from "@/assets/chests/legend.webp";
import legendOpen from "@/assets/chests/legend-open.webp";

export type ChestArtKind = "emerald" | "gold" | "legend";

const ART: Record<ChestArtKind, [string, string]> = {
  emerald: [emerald, emeraldOpen],
  gold: [gold, goldOpen],
  legend: [legend, legendOpen],
};

export const chestArt = (kind: ChestArtKind, open = false): string => ART[kind][open ? 1 : 0];
