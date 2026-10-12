import type { CSSProperties } from "react";

const svgUrl = (svg: string) => `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;

// Fine fractal noise tinted dark green — reads as turf without stripes.
const GRASS_NOISE = svgUrl(
  "<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'>"
  + "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/>"
  + "<feColorMatrix values='0 0 0 0 0.08  0 0 0 0 0.25  0 0 0 0 0.05  0 0 0 0.45 0'/></filter>"
  + "<rect width='100%' height='100%' filter='url(#n)'/></svg>",
);
// Sparse short blades on top of the noise for a little depth.
const GRASS_BLADES = svgUrl(
  "<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28'>"
  + "<g stroke='#9be08f' stroke-width='1' stroke-linecap='round' opacity='0.18'>"
  + "<path d='M4 20 l1 -5'/><path d='M7 21 l-1 -4'/><path d='M17 9 l1 -5'/><path d='M20 10 l-1 -4'/>"
  + "<path d='M23 24 l1 -4'/><path d='M12 27 l-1 -4'/></g></svg>",
);

/** One uniform turf colour with texture, plus a soft floodlight vignette. */
export const GRASS_STYLE: CSSProperties = {
  backgroundColor: "#3b8a3e",
  backgroundImage: [
    GRASS_BLADES,
    GRASS_NOISE,
    "radial-gradient(ellipse at 50% 45%, rgba(255,255,255,0.08), rgba(0,0,0,0.22) 85%)",
  ].join(", "),
};

/** Chalk-line grid cell border shared by the match board and the placement editor. */
export const CELL_LINES = "border-[0.5px] border-white/15";
