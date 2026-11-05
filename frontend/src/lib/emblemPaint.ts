// «Особый цвет» of a «Менеджер» emblem: a paid gradient paint instead of a palette
// colour. "brand" is the Victor FC gradient of the crest's V and the «Играть» button
// (turquoise → green → lime, corner to corner); "lemon" runs top to bottom into lemon.

interface Paint { stops: string[]; diagonal: boolean; solid: string }

const PAINTS: Record<string, Paint> = {
  brand: { stops: ["#22d3c4", "#3ed17e", "#c6e63a"], diagonal: true, solid: "#3ed17e" },
  lemon: { stops: ["#14c8ea", "#5fd27f", "#d6d400"], diagonal: false, solid: "#9fd84a" },
};

export function paintOf(color: string): Paint | null {
  return PAINTS[color] ?? null;
}

/** A plain colour for whatever needs one hex (shades, stands, glow). */
export function solidPaint(color: string): string {
  return PAINTS[color]?.solid ?? color;
}

/** The colour as an SVG paint: the hex itself, or a url() of the gradient
 * PaintGradient draws under `id`. */
export function paintFill(color: string, id: string): string {
  return PAINTS[color] ? `url(#${id})` : color;
}

/** The colour as a CSS background (palette swatches). */
export function paintCss(color: string): string {
  const p = PAINTS[color];
  return p ? `linear-gradient(${p.diagonal ? "135deg" : "180deg"}, ${p.stops.join(", ")})` : color;
}
