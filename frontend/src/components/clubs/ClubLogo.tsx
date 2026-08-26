import type { ClubLogoShape } from "@/types";

const SHAPE_PATHS: Record<ClubLogoShape, string> = {
  shield: "M50 5 L90 20 V50 C90 75 70 90 50 95 C30 90 10 75 10 50 V20 Z",
  circle: "M50 5 A45 45 0 1 1 49.99 5 Z",
  hexagon: "M50 5 L90 27.5 V72.5 L50 95 L10 72.5 V27.5 Z",
  star: "M50 5 L61 38 H96 L67 59 L78 92 L50 71 L22 92 L33 59 L4 38 H39 Z",
  diamond: "M50 5 L90 50 L50 95 L10 50 Z",
  banner: "M15 5 H85 V80 L50 65 L15 80 Z",
  crest: "M50 5 C70 5 88 15 88 35 C88 60 70 85 50 95 C30 85 12 60 12 35 C12 15 30 5 50 5 Z",
  chevron: "M10 30 L50 5 L90 30 L90 60 L50 35 L10 60 Z M10 65 L50 40 L90 65 L90 95 L50 70 L10 95 Z",
};

export function ClubLogo({ shape, color, size = 40 }: { shape: ClubLogoShape; color: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
      <path d={SHAPE_PATHS[shape]} fill={color} />
    </svg>
  );
}

export const CLUB_LOGO_SHAPES: ClubLogoShape[] = [
  "shield", "circle", "hexagon", "star", "diamond", "banner", "crest", "chevron",
];

export const CLUB_LOGO_COLORS: string[] = [
  "#EF4444", "#F97316", "#EAB308", "#22C55E", "#06B6D4", "#3B82F6", "#8B5CF6", "#EC4899",
];
