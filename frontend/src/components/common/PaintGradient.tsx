import { paintOf } from "@/lib/emblemPaint";

/** The SVG gradient behind paintFill(color, id) for a paint colour, laid over the
 * box it paints (user space, so thin strokes and text get it too); nothing for a hex. */
export default function PaintGradient({ id, color, x = 0, y = 0, w = 100, h = 100 }: {
  id: string; color: string; x?: number; y?: number; w?: number; h?: number;
}) {
  const paint = paintOf(color);
  if (!paint) return null;
  return (
    <linearGradient id={id} gradientUnits="userSpaceOnUse" x1={x} y1={y} x2={paint.diagonal ? x + w : x} y2={y + h}>
      {paint.stops.map((c, i) => <stop key={c} offset={`${[8, 50, 92][i]}%`} stopColor={c} />)}
    </linearGradient>
  );
}
