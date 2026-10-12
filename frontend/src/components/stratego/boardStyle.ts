import type { CSSProperties } from "react";

const svgUrl = (svg: string) => `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;

// Fine fractal noise in a slightly deeper green — turf texture, not dirt.
const GRASS_NOISE = svgUrl(
  "<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'>"
  + "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3' stitchTiles='stitch'/>"
  + "<feColorMatrix values='0 0 0 0 0.12  0 0 0 0 0.38  0 0 0 0 0.1  0 0 0 0.28 0'/></filter>"
  + "<rect width='100%' height='100%' filter='url(#n)'/></svg>",
);
// Sparse light blades on top of the noise for a little sparkle.
const GRASS_BLADES = svgUrl(
  "<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28'>"
  + "<g stroke='#d6f7b8' stroke-width='1' stroke-linecap='round' opacity='0.22'>"
  + "<path d='M4 20 l1 -5'/><path d='M7 21 l-1 -4'/><path d='M17 9 l1 -5'/><path d='M20 10 l-1 -4'/>"
  + "<path d='M23 24 l1 -4'/><path d='M12 27 l-1 -4'/></g></svg>",
);

/** Bright, even match-day turf: one fresh green with texture, very faint
 *  mowing bands every two rows, and floodlight glow from both stands —
 *  lit, not vignetted, so the pitch reads well on the app's dark UI. */
export const GRASS_STYLE: CSSProperties = {
  backgroundColor: "#3c9e4a",
  backgroundImage: [
    GRASS_BLADES,
    GRASS_NOISE,
    "radial-gradient(ellipse 120% 60% at 50% -5%, rgba(235,255,210,0.28), transparent 65%)",
    "radial-gradient(ellipse 120% 60% at 50% 105%, rgba(235,255,210,0.18), transparent 65%)",
    "repeating-linear-gradient(180deg, rgba(255,255,255,0.045) 0 12.5%, rgba(255,255,255,0) 12.5% 25%)",
    "linear-gradient(180deg, #45ad52, #36924a)",
  ].join(", "),
};

/** Chalk-line grid cell border shared by the match board and the placement editor. */
export const CELL_LINES = "border-[0.5px] border-white/[0.09]";
