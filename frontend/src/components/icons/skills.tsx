import type { ReactNode } from "react";

import { IconBase, type IconProps } from "./Icon";

/** Card-skill glyphs in the VICTOR FC icon alphabet (24×24, 1.8 stroke,
 * round caps). Drawn as bare children so the same glyph can sit either on
 * its own (SkillIcon) or inside the token hexagon (SkillTokenIcon). */
const GLYPHS: Record<string, ReactNode> = {
  // Crosshair — finishing.
  sniper: (
    <>
      <circle cx="12" cy="12" r="7" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <line x1="12" y1="2.5" x2="12" y2="6" />
      <line x1="12" y1="18" x2="12" y2="21.5" />
      <line x1="2.5" y1="12" x2="6" y2="12" />
      <line x1="18" y1="12" x2="21.5" y2="12" />
    </>
  ),
  // Ball weaving round a cone.
  dribbler: (
    <>
      <path d="M4 19c3 0 3-5 6-5s3 5 6 5" />
      <path d="M8 9.5 10 5h4l2 4.5" />
      <circle cx="18.5" cy="6" r="2.3" />
    </>
  ),
  // Two players linked by a through pass.
  playmaker: (
    <>
      <circle cx="5.5" cy="17.5" r="2.3" />
      <circle cx="18.5" cy="6.5" r="2.3" />
      <path d="M7.5 15.5 16.3 8.4" strokeDasharray="2.2 2.4" />
      <polyline points="13.6,8 16.4,8.3 16.1,11.1" />
    </>
  ),
  // Shield cutting a passing lane.
  interceptor: (
    <>
      <path d="M12 3.5 18.5 6v5.2c0 4-2.8 7.2-6.5 9.3-3.7-2.1-6.5-5.3-6.5-9.3V6Z" />
      <line x1="2.5" y1="12" x2="8" y2="12" strokeDasharray="1.8 2" />
      <line x1="16" y1="12" x2="21.5" y2="12" strokeDasharray="1.8 2" />
    </>
  ),
  // Ball above a jumping head.
  aerial_master: (
    <>
      <circle cx="12" cy="5" r="2.4" />
      <circle cx="12" cy="12.5" r="2.6" />
      <path d="M7 21v-1.5a5 5 0 0 1 10 0V21" />
      <polyline points="6.5,8.5 4.5,6.5 6.5,4.5" opacity="0.55" />
      <polyline points="17.5,8.5 19.5,6.5 17.5,4.5" opacity="0.55" />
    </>
  ),
  // Glove with reaction sparks.
  reflexes: (
    <>
      <path d="M7 21v-5.2a2.6 2.6 0 0 1 2.6-2.6h.4V9.6a1.3 1.3 0 0 1 2.6 0v3.6h.8V8.9a1.3 1.3 0 0 1 2.6 0v4.3h.3a1.3 1.3 0 0 1 1.3 1.3V18" />
      <path d="M7 21h10.6v-3" />
      <line x1="5" y1="5" x2="6.6" y2="6.6" />
      <line x1="9.5" y1="3" x2="9.5" y2="5.2" />
      <line x1="3" y1="9.5" x2="5.2" y2="9.5" />
    </>
  ),
  // Curling delivery from the flank onto a target.
  crosser: (
    <>
      <circle cx="5" cy="19" r="2" />
      <path d="M6.6 17.2C8 9 13 5.5 18 6.2" />
      <polyline points="15.6,4.4 18.2,6.2 16.3,8.7" />
      <circle cx="18.5" cy="15" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
  // The last line: a wall with the ball held in front of it.
  last_line: (
    <>
      <rect x="3.5" y="6" width="17" height="12" rx="1.5" />
      <line x1="3.5" y1="12" x2="20.5" y2="12" />
      <line x1="9" y1="6" x2="9" y2="12" />
      <line x1="15" y1="6" x2="15" y2="12" />
      <line x1="12" y1="12" x2="12" y2="18" />
      <line x1="2" y1="21" x2="22" y2="21" />
    </>
  ),
  // Goal mouth with a single attacker's ball heading in.
  one_on_one: (
    <>
      <path d="M3.5 13V5.5h17V13" />
      <line x1="3.5" y1="9.2" x2="20.5" y2="9.2" opacity="0.45" />
      <circle cx="12" cy="18" r="2.4" />
      <line x1="12" y1="15.6" x2="12" y2="13.5" />
    </>
  ),
};

const FALLBACK: ReactNode = <circle cx="12" cy="12" r="6" />;

export function SkillIcon({ code, ...props }: IconProps & { code: string }) {
  return <IconBase {...props}>{GLYPHS[code] ?? FALLBACK}</IconBase>;
}

/** A skill token: hexagonal chip with the skill's glyph inside. */
export function SkillTokenIcon({ code, ...props }: IconProps & { code: string }) {
  return (
    <IconBase {...props}>
      <path d="M12 1.8 21 7v10l-9 5.2L3 17V7Z" />
      <g transform="translate(6 6) scale(0.5)" strokeWidth={3}>
        {GLYPHS[code] ?? FALLBACK}
      </g>
    </IconBase>
  );
}
