import type { SVGProps } from "react";

export type IconProps = SVGProps<SVGSVGElement> & {
  size?: number;
};

/**
 * Shared geometry for the VICTOR FC icon set: 24x24 grid, 1.8px stroke,
 * rounded caps/joins, built only from circles/rects/lines so every icon
 * reads as the same "pill + circle" alphabet as the club crest.
 */
export function IconBase({ size = 20, children, ...props }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {children}
    </svg>
  );
}
