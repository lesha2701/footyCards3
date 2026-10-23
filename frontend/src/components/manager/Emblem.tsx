import type { ManagerLook } from "@/api/manager";
import { EmblemArt } from "@/components/clubs/ClubLogo";
import { kitBackground } from "@/lib/managerLook";

const SHAPES: Record<string, string> = {
  shield: "M50 4 L92 16 L88 62 Q82 86 50 98 Q18 86 12 62 L8 16 Z",
  circle: "M50 4 A46 46 0 1 1 49.9 4 Z",
  crown: "M8 34 L24 12 L38 30 L50 6 L62 30 L76 12 L92 34 L86 92 L14 92 Z",
  star: "M50 4 L62 36 L96 38 L69 59 L79 94 L50 74 L21 94 L31 59 L4 38 L38 36 Z",
  hexagon: "M50 4 L90 27 L90 73 L50 96 L10 73 L10 27 Z",
  crest: "M10 6 Q50 22 90 6 V44 Q90 80 50 96 Q10 80 10 44 Z",
  diamond: "M50 4 L94 50 L50 96 L6 50 Z",
  castle: "M10 92 V30 H22 V16 H34 V30 H44 V10 H56 V30 H66 V16 H78 V30 H90 V92 Z",
};

/** The club emblem drawn from its look: shape and colours (the second colour is the inner
 * band), the symbol, and the «Обводка» / «Эффект» bought in «Стиль» (shared drawing with
 * the clubs' ClubLogo). */
export default function Emblem({ look, size = 48, className = "" }: {
  look: Pick<ManagerLook, "shape" | "symbol" | "color" | "color2"> & Partial<Pick<ManagerLook, "rim" | "fx">>;
  size?: number;
  className?: string;
}) {
  const path = SHAPES[look.shape] ?? SHAPES.shield;
  const rim = look.rim && look.rim !== "none" ? look.rim : null;
  const fx = look.fx && look.fx !== "none" ? look.fx : null;
  return (
    <span className={`inline-flex shrink-0 ${className}`} aria-hidden="true">
      <EmblemArt
        path={path}
        color={look.color}
        size={size}
        outline={rim}
        effect={fx}
        glow={look.color2}
        inside={<path d={path} fill="none" stroke={look.color2} strokeWidth={12} strokeLinejoin="round" />}
        mark={<text x="50" y="56" textAnchor="middle" dominantBaseline="middle" fontSize="40">{look.symbol}</text>}
      />
    </span>
  );
}

/** A small shirt in the club kit. */
export function KitShirt({ look, size = 40 }: { look: Pick<ManagerLook, "kit" | "kit_color" | "kit_color2">; size?: number }) {
  return (
    <span
      className="inline-block shrink-0"
      style={{
        width: size, height: size, background: kitBackground(look),
        clipPath: "polygon(25% 0, 40% 8%, 60% 8%, 75% 0, 100% 18%, 88% 38%, 80% 32%, 80% 100%, 20% 100%, 20% 32%, 12% 38%, 0 18%)",
      }}
      aria-hidden="true"
    />
  );
}
