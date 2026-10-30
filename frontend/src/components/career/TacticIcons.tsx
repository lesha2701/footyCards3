/** Pictograms of the career tactics screen: one per setting and one per
 * value, drawn on the shared icon grid (24×24, the attack goes up). */
import type { ReactNode } from "react";

import { IconBase, IconBoot, type IconProps } from "@/components/icons";

const arrowUp = (x: number, y: number) => `M${x - 2.4} ${y + 2.6}L${x} ${y}l2.4 2.6`;

// A plain function, not a component: this file only exports pictograms.
const pic = (children: ReactNode, props: IconProps = {}) => <IconBase size={18} {...props}>{children}</IconBase>;

/** The setting's own icon, by axis key. */
export const AXIS_ICONS: Record<string, (p: IconProps) => ReactNode> = {
  direction: (p) => pic(<>
    <path d="M12 20v-6M12 14L6 6M12 14l6-8" />
    <path d="M5 9.5L6 6l3.5.6M19 9.5L18 6l-3.5.6" />
  </>, p),
  buildup: (p) => pic(<>
    <circle cx="5" cy="18" r="1.6" />
    <circle cx="12" cy="12" r="1.6" />
    <circle cx="19" cy="6" r="1.6" />
    <path d="M6.5 16.5l4-3M13.5 10.5l4-3" strokeDasharray="1.6 1.8" />
  </>, p),
  on_loss: (p) => pic(<>
    <circle cx="12" cy="12" r="3" />
    <path d="M19 12a7 7 0 1 1-2.1-5" />
    <path d="M17.4 3.6l-.5 3.4 3.4.4" />
  </>, p),
  on_win: (p) => pic(<>
    <path d="M13 3L6 13h5l-1 8 7-10h-5l1-8z" />
  </>, p),
  block: (p) => pic(<>
    <path d="M3 13h18" strokeDasharray="2.4 2" />
    <path d="M12 10V4M9.6 6.6L12 4l2.4 2.6M12 16v4" />
  </>, p),
  tackling: (p) => <IconBoot width={18} height={18} {...p} />,
};

/** Each value's pictogram, by axis then value. */
export const VALUE_ICONS: Record<string, Record<string, ReactNode>> = {
  direction: {
    wings: pic(<>
      <path d="M7 20C4 14 4.5 9 7 4M17 20c3-6 2.5-11 0-16" />
      <path d={arrowUp(7, 4)} /><path d={arrowUp(17, 4)} />
    </>),
    mixed: pic(<>
      <path d="M6 20C3.5 14 4 9 6 4M14 20V4" />
      <path d={arrowUp(6, 4)} /><path d={arrowUp(14, 4)} />
    </>),
    center: pic(<>
      <path d="M12 20V4" />
      <path d={arrowUp(12, 4)} />
      <path d="M6 20v-3M18 20v-3" strokeOpacity="0.4" />
    </>),
  },
  buildup: {
    short: pic(<>
      <circle cx="7" cy="19" r="1.3" /><circle cx="15" cy="15" r="1.3" /><circle cx="8" cy="10" r="1.3" /><circle cx="16" cy="5" r="1.3" />
      <path d="M8.2 18.4l5.6-2.8M13.9 14.2L9 10.8M9.2 9.2l5.6-3.4" strokeDasharray="1.4 1.4" />
    </>),
    mixed: pic(<>
      <circle cx="6" cy="19" r="1.3" /><circle cx="13" cy="15" r="1.3" /><circle cx="18" cy="5" r="1.3" />
      <path d="M7.2 18.4l4.6-2.8" strokeDasharray="1.4 1.4" />
      <path d="M13.6 13.8l3.8-7.4" />
    </>),
    direct: pic(<>
      <circle cx="6" cy="19" r="1.3" />
      <path d="M7 17.5Q10 6 18 4" strokeDasharray="2.2 1.6" />
      <path d="M14.6 3.2L18 4l-1.8 3" />
    </>),
  },
  on_loss: {
    counterpress: pic(<>
      <circle cx="12" cy="8" r="2.4" />
      <path d="M4 18l5.5-7M20 18l-5.5-7M12 20v-7" />
      <path d="M6.6 11.2l2.9-.2.2 2.8M17.4 11.2l-2.9-.2-.2 2.8" />
    </>),
    drop: pic(<>
      <path d="M3 18h18" strokeDasharray="2.4 2" />
      <path d="M7 4v9M17 4v9M4.6 10.4L7 13l2.4-2.6M14.6 10.4L17 13l2.4-2.6" />
    </>),
  },
  on_win: {
    fast: pic(<>
      <path d="M12 21V8" />
      <path d="M8 11l4-4 4 4M8 6l4-4 4 4" />
    </>),
    keep: pic(<>
      <circle cx="12" cy="12" r="2.6" />
      <path d="M5 12a7 7 0 0 1 12-5M19 12a7 7 0 0 1-12 5" />
      <path d="M17.3 3.8l-.3 3.2-3.2-.2M6.7 20.2l.3-3.2 3.2.2" />
    </>),
  },
  block: {
    high: pic(<>
      <rect x="3" y="3" width="18" height="18" rx="2" strokeOpacity="0.4" />
      <path d="M5 8h14" strokeDasharray="2.2 1.8" /><path d="M12 18v-6M9.6 14.6L12 12l2.4 2.6" />
    </>),
    mid: pic(<>
      <rect x="3" y="3" width="18" height="18" rx="2" strokeOpacity="0.4" />
      <path d="M5 12h14" strokeDasharray="2.2 1.8" />
    </>),
    low: pic(<>
      <rect x="3" y="3" width="18" height="18" rx="2" strokeOpacity="0.4" />
      <path d="M5 16h14" strokeDasharray="2.2 1.8" /><path d="M12 6v6M9.6 9.4L12 12l2.4-2.6" />
    </>),
  },
  tackling: {
    normal: <IconBoot width={18} height={18} />,
    hard: (
      <span className="relative inline-flex">
      <IconBoot width={18} height={18} />
      <span className="absolute -right-1.5 -top-1 text-[10px] font-black leading-none">!</span>
      </span>
    ),
    soft: <IconBoot width={18} height={18} strokeOpacity={0.55} />,
  },
};
